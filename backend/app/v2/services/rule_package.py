from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import REPO_ROOT


class RuleModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class ChecklistStep(RuleModel):
    step: int
    key: str = Field(min_length=1)
    title: str = Field(min_length=1)
    automation_level: str
    required_metadata: tuple[str, ...] = ()
    evidence_fields: tuple[str, ...] = ()


class ChecklistDocument(RuleModel):
    checklist_id: str
    version: str
    steps: tuple[ChecklistStep, ...]


class LevelOfCareRule(RuleModel):
    aliases: tuple[str, ...]
    treatment_plan_update_interval_days: int = Field(ge=1, le=365)


class LocChangeBlocker(RuleModel):
    status: str
    default_preset_calendar_days: int = Field(ge=0, le=365)


class RulesDocument(RuleModel):
    config_version: str
    checklist_version: str
    levels_of_care: dict[str, LevelOfCareRule]
    loc_change_blocker: LocChangeBlocker


@dataclass(frozen=True, slots=True)
class DeterministicRulePackage:
    checklist: ChecklistDocument
    rules: RulesDocument


@dataclass(frozen=True, slots=True)
class RuleConfigurationError(Exception):
    source_name: str
    reason: str

    def __str__(self) -> str:
        return f"Invalid deterministic rule configuration ({self.source_name}): {self.reason}"


def load_rule_package(
    checklist_path: Path | None = None,
    rules_path: Path | None = None,
) -> DeterministicRulePackage:
    if checklist_path is None and rules_path is None:
        return _default_rule_package()
    checklist_source = checklist_path or REPO_ROOT / "config" / "checklists" / "treatment-plan-v1.json"
    rules_source = rules_path or REPO_ROOT / "config" / "rules" / "alleva_treatment_plan_completeness_rules.yaml"
    return _load_rule_package(checklist_source, rules_source)


@cache
def _default_rule_package() -> DeterministicRulePackage:
    return _load_rule_package(
        REPO_ROOT / "config" / "checklists" / "treatment-plan-v1.json",
        REPO_ROOT / "config" / "rules" / "alleva_treatment_plan_completeness_rules.yaml",
    )


def _load_rule_package(checklist_source: Path, rules_source: Path) -> DeterministicRulePackage:
    try:
        checklist = ChecklistDocument.model_validate(json.loads(checklist_source.read_text(encoding="utf-8-sig")))
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise RuleConfigurationError(checklist_source.name, type(exc).__name__) from exc
    try:
        rules = RulesDocument.model_validate(yaml.safe_load(rules_source.read_text(encoding="utf-8-sig")))
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise RuleConfigurationError(rules_source.name, type(exc).__name__) from exc
    if len(checklist.steps) != 42:
        raise RuleConfigurationError(checklist_source.name, "canonical checklist must contain exactly 42 steps")
    if tuple(step.step for step in checklist.steps) != tuple(range(1, 43)):
        raise RuleConfigurationError(checklist_source.name, "canonical checklist steps must be ordered 1 through 42")
    if checklist.version != rules.checklist_version:
        raise RuleConfigurationError(rules_source.name, "checklist version does not match canonical checklist")
    return DeterministicRulePackage(checklist=checklist, rules=rules)
