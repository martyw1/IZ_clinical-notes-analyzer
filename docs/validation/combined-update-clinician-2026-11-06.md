# Combined update clinician projection - November 6, 2026

The combined update already imports staff and verified patient primaryClinician links during its plan stage. This change exposes the same effective assignment on treatment-plan detail as Current clinician, using the shared patient association and preserving local overrides and original plan content. Update-button explanatory text now describes automatic mapping. Missing mappings remain unassigned.

Validation: eight combined-update backend tests passed, including a new synthetic vendor-HTTP regression that runs the combined job endpoint and verifies a staff record without facility metadata links the patient, plan roster and exact plan detail. Twelve frontend detail/update-card tests passed. TypeScript and production build passed. git diff --check passed.

No new vendor endpoint or name-based inference was introduced. Clinician selection remains separate from account authorization. No installer qualification claimed.

Clean restart completed after checking no active import jobs. Version endpoint returned HTTP 200. In the existing signed-in Edge session, opened a real roster row and verified Current clinician is displayed on treatment-plan detail. No real assignments changed or real clinical screenshots saved.
