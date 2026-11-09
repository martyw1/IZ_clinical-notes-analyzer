# Alleva clinician name fallback

The approved clinician importer uses a single full name from Client.primaryClinicians when the explicit primaryClinician reference is absent and exactly one row in the complete staff pull has that name. Capitalization and whitespace are ignored. Explicit references, including unresolved references, do not fall back to names. Multiple-name rows remain unassigned for review, with an aggregate count displayed on Clinicians. Local assignment overrides retain precedence.

The combined-update integration test covers exact normalized matching, duplicate staff names, multiple names, partial names, explicit ID precedence, and conflicting explicit references. It verifies the mapped clinician in both the roster and plan detail. The focused backend suite passed 14 tests. Five Clinicians frontend tests, TypeScript and the production build passed. The local app was restarted on loopback and returned HTTP 200.
