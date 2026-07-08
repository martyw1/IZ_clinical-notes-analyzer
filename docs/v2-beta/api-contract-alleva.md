# Alleva API Contract

V2 patient-centered production pulls use:

- `GET /clients`
- `GET /treatment-plans?ClientId={patient_id}`

`patient_id` is the canonical Alleva client ID from `/clients.id`. `ClientId` is case-sensitive and must use uppercase `C` and uppercase `I`. Treatment-plan ownership is validated from raw client references such as `/clients/{id}`.

The app must not use `source_id`, `chartId`, `externalId`, `mrn`, `clientName`, lowercase `clientId`, or `uniqueId` as production join keys. Patient names are not requested, stored, displayed, exported, logged, or used for matching by default.

Live Alleva sync remains gated until official tenant credentials, endpoint mapping, pagination/rate-limit behavior, attachment behavior, vendor documentation, and compliance approval exist.
