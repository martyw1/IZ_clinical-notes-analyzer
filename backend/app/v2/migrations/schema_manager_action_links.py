from __future__ import annotations

from typing import Final

MANAGER_ACTION_PLAN_LINK_STATEMENTS: Final = (
    """CREATE TABLE manager_action_plan_links(
        action_id INTEGER PRIMARY KEY REFERENCES treatment_plan_manager_actions(id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        plan_version_id INTEGER NULL REFERENCES treatment_plan_versions(id) ON UPDATE RESTRICT ON DELETE RESTRICT
    )""",
    "CREATE INDEX ix_manager_action_plan_links_plan_version_id ON manager_action_plan_links(plan_version_id)",
    """WITH unique_candidate AS (
        SELECT patient.canonical_client_id,MIN(plan.id) AS plan_version_id,
            MIN(julianday(plan.imported_at)) AS imported_at
        FROM patients patient JOIN treatment_plan_versions plan ON plan.patient_id=patient.id
        GROUP BY patient.canonical_client_id HAVING COUNT(*)=1
    )
    INSERT INTO manager_action_plan_links(action_id,plan_version_id)
    SELECT action.id,CASE
        WHEN candidate.imported_at<=julianday(action.created_at)
            AND NOT EXISTS (
                SELECT 1 FROM reconciliation_outcomes outcome
                WHERE outcome.source_kind='legacy_manager_action'
                    AND outcome.source_record_id='legacy-action-' || action.id
            )
            AND NOT EXISTS (
                SELECT 1 FROM manager_dispositions disposition
                WHERE disposition.criterion_id=action.criterion_id
                    AND disposition.status=action.action
                    AND disposition.comment=action.comment
                    AND disposition.actor_user_id=CAST(action.actor_user_id AS INTEGER)
                    AND disposition.created_at=action.created_at
                    AND disposition.plan_version_id IS NOT candidate.plan_version_id
            )
        THEN candidate.plan_version_id ELSE NULL END
    FROM treatment_plan_manager_actions action
    LEFT JOIN unique_candidate candidate ON candidate.canonical_client_id=action.patient_id""",
    """CREATE TRIGGER manager_action_plan_links_no_update BEFORE UPDATE ON manager_action_plan_links
        BEGIN SELECT RAISE(ABORT,'manager_action_plan_links are immutable'); END""",
    """CREATE TRIGGER manager_action_plan_links_no_delete BEFORE DELETE ON manager_action_plan_links
        BEGIN SELECT RAISE(ABORT,'manager_action_plan_links are immutable'); END""",
    """CREATE TRIGGER manager_action_plan_links_no_replace BEFORE INSERT ON manager_action_plan_links
        WHEN EXISTS(SELECT 1 FROM manager_action_plan_links WHERE action_id=NEW.action_id)
        BEGIN SELECT RAISE(ABORT,'manager_action_plan_links are immutable'); END""",
)
