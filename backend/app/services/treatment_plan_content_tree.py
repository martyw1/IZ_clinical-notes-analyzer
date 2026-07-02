from __future__ import annotations

import re
from typing import Any

from app.services.treatment_plan_content_safety import DEFAULT_MAX_CONTENT_ITEMS, normalized_content_items, structured_content_items

CONTENT_TREE_PATH_PATTERNS = (
    (
        'intervention',
        re.compile(
            r'^problems\[(?P<problem>\d+)\]\.goals\[(?P<goal>\d+)\]\.objectives\[(?P<objective>\d+)\]\.interventions\[(?P<intervention>\d+)\]$'
        ),
    ),
    ('objective', re.compile(r'^problems\[(?P<problem>\d+)\]\.goals\[(?P<goal>\d+)\]\.objectives\[(?P<objective>\d+)\]$')),
    ('goal', re.compile(r'^problems\[(?P<problem>\d+)\]\.goals\[(?P<goal>\d+)\]$')),
    ('diagnosis', re.compile(r'^problems\[(?P<problem>\d+)\]\.diagnoses\[(?P<diagnosis>\d+)\]$')),
    (
        'behavioral_definition',
        re.compile(r'^problems\[(?P<problem>\d+)\]\.behavioralDefinitions\[(?P<behavioral_definition>\d+)\]$'),
    ),
    ('problem', re.compile(r'^problems\[(?P<problem>\d+)\]$')),
)
TOP_LEVEL_CONTENT_TREE_PATH_PATTERNS = (
    ('diagnosis', re.compile(r'^diagnoses\[(?P<index>\d+)\]$'), 'top_level_diagnoses'),
    ('behavioral_definition', re.compile(r'^behavioralDefinitions\[(?P<index>\d+)\]$'), 'top_level_behavioral_definitions'),
    ('goal', re.compile(r'^goals\[(?P<index>\d+)\]$'), 'top_level_goals'),
    ('objective', re.compile(r'^objectives\[(?P<index>\d+)\]$'), 'top_level_objectives'),
    ('intervention', re.compile(r'^interventions\[(?P<index>\d+)\]$'), 'top_level_interventions'),
)


def _content_tree_node(item: dict[str, Any]) -> dict[str, Any]:
    node = {
        'kind': item.get('kind', 'content'),
        'label': item.get('label', ''),
        'source_path': item.get('source_path', ''),
        'text_present': bool(item.get('text_present')),
    }
    for key in ('text', 'redacted_text_sha256', 'metadata'):
        value = item.get(key)
        if value:
            node[key] = value
    return node


def _placeholder_node(kind: str, index: int, source_path: str) -> dict[str, Any]:
    return {
        'kind': kind,
        'label': f'{kind.replace("_", " ").title()} {index}',
        'source_path': source_path,
        'text_present': False,
    }


def _problem_node(problems_by_index: dict[int, dict[str, Any]], index: int) -> dict[str, Any]:
    node = problems_by_index.get(index)
    if node is None:
        node = _placeholder_node('problem', index, f'problems[{index}]')
        node['diagnoses'] = []
        node['behavioral_definitions'] = []
        node['goals'] = []
        problems_by_index[index] = node
    return node


def _goal_node(problem: dict[str, Any], goal_index: int) -> dict[str, Any]:
    goals = problem.setdefault('goals', [])
    goal_path = f'{problem["source_path"]}.goals[{goal_index}]'
    for goal in goals:
        if goal.get('source_path') == goal_path:
            return goal
    goal = _placeholder_node('goal', goal_index, goal_path)
    goal['objectives'] = []
    goals.append(goal)
    return goal


def _objective_node(goal: dict[str, Any], objective_index: int) -> dict[str, Any]:
    objectives = goal.setdefault('objectives', [])
    objective_path = f'{goal["source_path"]}.objectives[{objective_index}]'
    for objective in objectives:
        if objective.get('source_path') == objective_path:
            return objective
    objective = _placeholder_node('objective', objective_index, objective_path)
    objective['interventions'] = []
    objectives.append(objective)
    return objective


def _replace_node(nodes: list[dict[str, Any]], replacement: dict[str, Any]) -> None:
    source_path = replacement.get('source_path')
    for index, node in enumerate(nodes):
        if node.get('source_path') == source_path:
            replacement.update({key: node[key] for key in ('objectives', 'interventions') if key in node})
            nodes[index] = replacement
            return
    nodes.append(replacement)


def _content_tree_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        'plan_field_count': sum(1 for item in items if item.get('kind') == 'plan_field'),
        'problem_count': sum(1 for item in items if item.get('kind') == 'problem'),
        'diagnosis_count': sum(1 for item in items if item.get('kind') == 'diagnosis'),
        'behavioral_definition_count': sum(1 for item in items if item.get('kind') == 'behavioral_definition'),
        'goal_count': sum(1 for item in items if item.get('kind') == 'goal'),
        'objective_count': sum(1 for item in items if item.get('kind') == 'objective'),
        'intervention_count': sum(1 for item in items if item.get('kind') == 'intervention'),
    }


def _sorted_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(nodes, key=lambda node: (str(node.get('source_path') or ''), str(node.get('label') or '')))


def content_tree_from_items(value: Any) -> dict[str, Any]:
    items = normalized_content_items(value)
    plan_fields: list[dict[str, Any]] = []
    problems_by_index: dict[int, dict[str, Any]] = {}
    top_level_targets: dict[str, list[dict[str, Any]]] = {
        'top_level_diagnoses': [],
        'top_level_behavioral_definitions': [],
        'top_level_goals': [],
        'top_level_objectives': [],
        'top_level_interventions': [],
    }
    unattached_items: list[dict[str, Any]] = []

    for item in items:
        node = _content_tree_node(item)
        source_path = str(item.get('source_path') or '')
        if item.get('kind') == 'plan_field':
            plan_fields.append(node)
            continue
        attached = False
        for expected_kind, pattern in CONTENT_TREE_PATH_PATTERNS:
            match = pattern.fullmatch(source_path)
            if match is None or item.get('kind') != expected_kind:
                continue
            indexes = {key: int(raw_index) for key, raw_index in match.groupdict().items()}
            problem = _problem_node(problems_by_index, indexes['problem'])
            if expected_kind == 'problem':
                node.setdefault('diagnoses', [])
                node.setdefault('behavioral_definitions', [])
                node.setdefault('goals', [])
                problems_by_index[indexes['problem']] = node
            elif expected_kind == 'diagnosis':
                problem.setdefault('diagnoses', []).append(node)
            elif expected_kind == 'behavioral_definition':
                problem.setdefault('behavioral_definitions', []).append(node)
            elif expected_kind == 'goal':
                node.setdefault('objectives', [])
                _replace_node(problem.setdefault('goals', []), node)
            elif expected_kind == 'objective':
                goal = _goal_node(problem, indexes['goal'])
                node.setdefault('interventions', [])
                _replace_node(goal.setdefault('objectives', []), node)
            elif expected_kind == 'intervention':
                goal = _goal_node(problem, indexes['goal'])
                objective = _objective_node(goal, indexes['objective'])
                objective.setdefault('interventions', []).append(node)
            attached = True
            break
        if attached:
            continue
        for expected_kind, pattern, target_key in TOP_LEVEL_CONTENT_TREE_PATH_PATTERNS:
            if pattern.fullmatch(source_path) is not None and item.get('kind') == expected_kind:
                top_level_targets[target_key].append(node)
                attached = True
                break
        if not attached:
            unattached_items.append(node)

    return {
        'counts': _content_tree_counts(items),
        'plan_fields': _sorted_nodes(plan_fields),
        'problems': _sorted_nodes(list(problems_by_index.values())),
        'top_level_diagnoses': _sorted_nodes(top_level_targets['top_level_diagnoses']),
        'top_level_behavioral_definitions': _sorted_nodes(top_level_targets['top_level_behavioral_definitions']),
        'top_level_goals': _sorted_nodes(top_level_targets['top_level_goals']),
        'top_level_objectives': _sorted_nodes(top_level_targets['top_level_objectives']),
        'top_level_interventions': _sorted_nodes(top_level_targets['top_level_interventions']),
        'unattached_items': _sorted_nodes(unattached_items),
    }


def structured_content_tree(raw: dict[str, Any], *, max_items: int = DEFAULT_MAX_CONTENT_ITEMS) -> dict[str, Any]:
    return content_tree_from_items(structured_content_items(raw, max_items=max_items))
