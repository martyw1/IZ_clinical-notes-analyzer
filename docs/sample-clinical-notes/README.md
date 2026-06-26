# Synthetic clinical note samples

These files are **synthetic examples only**. They contain no real PHI and should not be described as proprietary Alleva exports. They model fields commonly needed by the IZ Clinical Notes Analyzer manual-upload workflow and by future API/export mapping work.

## Included files

- `treatment_plan_tracking_note.txt` - a Treatment Plan Tracking note with one intentionally deficient item.
- `progress_note.txt` - an individual progress note tied to a treatment-plan objective.
- `group_note.txt` - a group note example with a broad objective-linkage deficiency.
- `discharge_or_transition_note.txt` - a discharge/transition note with missing acknowledgement.
- `notes_export_example.csv` - tabular export-shaped example for parser and documentation review.
- `notes_export_example.json` - JSON export-shaped example for API-boundary discussions.

## Fields demonstrated

The examples cover patient identifier, service date, treatment-plan reference, problem/goal/objective/intervention, progress/status, provider/counselor, signature or completion status, review/approval status, and missing/deficient item examples. Patient names are intentionally omitted because the app uses Patient ID only.

## Parsing assumptions

The app is upload-first. Text files are extracted directly; supported PDF/DOCX formats are parsed when the relevant Python libraries can read them; legacy `.doc` files may need conversion before reliable text extraction. These samples are safe fixtures for local smoke tests and documentation, but runtime behavior must not depend on them being present.
