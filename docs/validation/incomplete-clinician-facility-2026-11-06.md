# Incomplete clinician facility records — November 6, 2026

## S0 and owner clarification
Preserved the existing working tree. The prior importer discarded staff when their source facility could not be mapped through an already imported patient. The owner explicitly confirmed incomplete clinician records are acceptable and missing facilities should be noted. No repository cleanup was performed.

## Change
Named staff with stable scoped IDs are now saved independently of facility mapping. A separate imported_clinician_directory_records table stores source role and mapped/missing/unmapped facility state. Missing facilities and unmapped facilities have different visible labels. Positive explicit IDs and relative facility resource links are recognized; facility names are never used as join keys. Zero IDs are treated as missing.

Administrators can review incomplete directory records without creating any local facility membership. Other roles still see only previously authorized facility or patient-observation scope. Explicit primaryClinician IDs/resource links can resolve staff independently of staff facility metadata; ambiguous IDs, contradictory routes and absent links remain unresolved. No assignment is inferred from a display name. Missing facility data alone no longer drops a record.

Count-only pull summaries still report facility issues as warnings while including retained records in the saved count. The UI says saved with facility not linked rather than skipped. Raw source profiles, clinical names and connection material are excluded from this validation document and diagnostic outputs.

## Validation
Ten clinician backend tests passed, including missing, empty, zero and unmatched facilities, idempotent imports, explicit assignment handling, private facility isolation and viewer exclusion from unscoped incomplete records. Five focused clinician UI tests, TypeScript and the production build passed. The additional synthetic all-unmapped directory batch regression and existing assignment/directory operational regression both passed.

The local running app was restarted after verifying no import job was active. The existing administrator session was used to rerun the approved clinician-only pull. Aggregate-only browser and database checks confirmed directory retention with facility-not-linked labels and unchanged treatment-plan version/evidence hashes. No live names or screenshots were recorded in test evidence. Missing source patient-to-clinician relationships remain unresolved rather than guessed.
