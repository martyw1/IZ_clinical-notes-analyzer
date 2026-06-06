# Source Evidence Matrix

| Analyzer field | Video source | Why it matters | Extraction / UI note |
|---|---|---|---|
| `admission_date` | Client Overview and treatment plan signature comparison | Anchor for initial and master plan rules | Show in selected client header and rule detail. |
| `current_level_of_care` | Client Overview and Level of Care panel | Selects recurrence interval and active LOC status | Infer from latest LOC row with blank discharge date when available. |
| `level_of_care_history[].effective_date` | Level of Care table admission/effective column | Potential anchor for LOC-based due dates | Needs validation because visible due date appears LOC-anchored. |
| `level_of_care_history[].discharge_date` | Level of Care table discharge column | Determines ended versus active LOC range | Blank discharge means current active level in video. |
| `initial.document_date` | Treatment Plan tab/version row | Confirms initial plan exists | Row existence alone is not enough. |
| `initial.staff_signature_date` | Initial Treatment Plan modal signature area | Required initial completion evidence | Must match admission date unless grace rule is confirmed. |
| `initial.client_signature_date` | Initial Treatment Plan modal signature area | Required initial completion evidence | Must match admission date unless grace rule is confirmed. |
| `master.document_date` | Treatment Plan tab/version row | Supports 30-day master plan check | Can be a created/document date, but signatures decide completion. |
| `master.staff_signature_date` | Master Treatment Plan modal signature area | Required master completion evidence | Must be within 30 days of admission. |
| `master.client_signature_date` | Master Treatment Plan modal signature area | Required master completion evidence | Must be within 30 days of admission. |
| `review.document_date` | Treatment Plan Reviews table/modal | Identifies review event | Useful but not decisive without staff signature. |
| `review.staff_signature_date` | Treatment Plan Review modal staff signature area | Primary review completion evidence | Presenter says this is the date she wants tracked. |
| `review.client_signature_date` | Treatment Plan Review modal client signature area | Optional for ongoing reviews | Blank client signature must not fail MVP review logic by itself. |
| `review.displayed_next_due_date` | Treatment Plan Review Note `Next Review Due` field | Existing source system due date | Use as cross-check and possible authority after R3 confirms. |
| `review.reviewer_signature_date` | Review modal reviewer signature area | Secondary signature evidence | Open question: when does this matter? |
| `loc_change_window_days` | Not confirmed in video | Project blocker | Keep configurable and unvalidated. |
| `rule_explanation` | All viewed source sections | Trust requirement | Show source path and dates for every status. |
