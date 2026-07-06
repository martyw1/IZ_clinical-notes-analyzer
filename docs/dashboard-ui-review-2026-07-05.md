# Dashboard UI Review and Redesign Directions - 2026-07-05

## Evidence

Reviewed the running Windows desktop app at `http://127.0.0.1:8000`, launched through `scripts/start-windows-local.ps1` with the existing built frontend.

Captured evidence:

- `.omo/evidence/dashboard-ui-review-2026-07-05/status-dashboard-desktop.png`
- `.omo/evidence/dashboard-ui-review-2026-07-05/status-dashboard-lower-desktop.png`
- `.omo/evidence/dashboard-ui-review-2026-07-05/treatment-plans-desktop.png`
- `.omo/evidence/dashboard-ui-review-2026-07-05/review-queue-desktop-after-wait.png`

Inferred brief: R3 staff need a local-first clinical operations dashboard that answers, within a few seconds, what needs attention, why it needs attention, what source data is trustworthy, and what action is safest next. The audience includes admins, office managers, and counselors working under compliance pressure, so status hierarchy, cognitive load, and plain-language evidence matter more than visual novelty.

## Current Readability Problems

1. The app has useful status data, but the status story is fragmented.
   The top hero status, four global counters, Status Dashboard cards, Quick actions, review-source cards, Treatment Plans counters, filters, and selected-detail area all compete instead of forming one clear decision path.

2. The current dashboard reads like a list of panels, not a dashboard.
   Most elements use the same thin border, same white/gray card weight, same text scale, and similar spacing. That makes a safe state, an urgent state, an empty state, and an admin-only control feel too similar.

3. Treatment Plans is closer to the true operational dashboard, but its highest-value signals are buried.
   Overdue, urgent, missing data, LOC rule validation, evidence completeness, source due date, date-clock due date, and LOC-change due date should be the first scan path. Today they are spread across a banner, metric cards, filters, table rows, and the empty detail panel.

4. The visual system changes tone between screens.
   The main shell uses soft green/cream glass cards, while the Treatment Plans surface switches to flatter gray table styling, salmon action buttons, and harder rectangular filters. This makes the product feel assembled from separate layers rather than one clinical workspace.

5. Empty states do not teach the next operational move.
   With no loaded data, the dashboard has many zeroes but little explanation of what is healthy, what is missing, and what the user should do next.

## Recommended Layout Direction

### 1. Status Command Center

Use Status Dashboard as the true landing page and make it answer: "Can we operate today, and what needs attention first?"

Layout:

- Top band: one full-width operational summary with `Ready`, `Needs action`, or `Blocked` as the dominant state.
- Primary cards: `Overdue`, `Urgent`, `Needs review`, `Missing data`, with count, short meaning, and direct filter action.
- Work queue: a compact "Next actions" list sorted by risk, not by feature area.
- Source health rail: Manual upload, EMR/API readiness, Alleva sync gate, checklist version, runtime readiness.
- Admin drawer or rail: user/account/security controls moved out of the main scan path.

Best for: admins and office managers who need a daily check-in screen.

### 2. Treatment Plan Cockpit

Make Treatment Plans a dense but readable workbench rather than a left-panel/right-blank split.

Layout:

- Sticky toolbar: evaluation date, search, refresh, pull/sync, export actions.
- Status strip: segmented filters with color and counts in this order: `Overdue`, `Urgent`, `Due soon`, `Returned`, `Needs review`, `Missing data`, `Conflicting`, `Unable`, `Compliant`.
- Queue table: retain the table, but add a left risk stripe, stronger row grouping, and clearer due-date hierarchy.
- Detail panel: when no client is selected, show a composed empty state with three steps: load clients, select a risk row, review source evidence.
- Selected client: show a date-evidence timeline first, then source comparison, then checklist findings and override notes.

Best for: the actual timeliness tracker workflow.

### 3. Source Readiness Dashboard

Separate "Can I trust today's data?" from "Who needs action?"

Layout:

- Three source cards: Manual upload, API readiness, Alleva treatment-plan sync.
- Each source card has status, last check, next check, blockers, allowed actions, and data freshness.
- A small evidence ledger shows the latest successful safe check, latest failed check, and latest manual upload.
- Gated/live-sync blockers are visually persistent but not noisy: clear badge, plain text, action disabled until prerequisites exist.

Best for: admin setup, vendor readiness, and explaining why live import is intentionally blocked.

## Recommended Graphical Theme

### Theme A - Clinical Operations Light

This should be the default. It is calm, readable, and status-forward.

- Background: near-white with a very subtle cool green tint.
- Surfaces: flat white cards for data, faint green-tinted section bands for grouping, no heavy glass on data-heavy screens.
- Text: dark neutral ink, tabular numerals for counts and dates.
- Accent colors:
  - Critical: deep red
  - Urgent: burnt orange
  - Due soon: amber
  - Needs review: clinical blue
  - Missing data: slate gray with dashed treatment
  - Compliant/approved: green
  - Unvalidated/configuration: violet only for policy uncertainty, used sparingly
- Charts: small horizontal bars, freshness meters, and date timelines before decorative vertical bars.

### Theme B - High-Contrast Status Board

Use for the dashboard if R3 wants faster triage at a distance.

- A strong top status band with a single dominant state.
- Dark ink headings on light surfaces, but color blocks only for risk states.
- Status cards use left stripes and icon-free labels, not large colored backgrounds.
- Tables use zebra rows, persistent headers, and compact density.
- Best when the laptop is used in office conditions with interruptions.

### Theme C - Forensic Ledger

Use for logs, evidence details, and source comparison views.

- More compact, document-like layout.
- Monospace/tabular dates and IDs.
- Timeline and comparison blocks for source evidence.
- Less rounded, more grid-aligned, with stronger section dividers.
- Best for audit review, not for the daily landing page.

## Concrete UI Changes To Prioritize

1. Replace the four top global counters with a single operational status band plus risk-first counters.
2. Merge `Summary dashboard` and Treatment Plans summary metrics into one status model so the user does not see duplicate zero states.
3. Turn Quick actions into a right-side action rail grouped by role: Review work, Data/source setup, Admin.
4. Replace current trend pill-bars with compact sparklines or seven-day mini bar charts that do not dominate empty dashboards.
5. Add a real empty-state checklist for no loaded clients: `Pull treatment plans`, `Upload binder`, `Open API readiness`, `Review settings`.
6. Make the Treatment Plans detail empty state explain what will appear after selection: dates, evidence completeness, checklist result, overrides, audit history.
7. Standardize page styling around one theme: either soften the Treatment Plans table to match the app shell or simplify the shell to match a clinical operations board. The current hybrid is the main visual mismatch.

## Best Next Build Slice

Build Theme A with Layout 2 first. It is the highest-value surface because the app already defaults admins and office managers to Treatment Plans, and it contains the most important compliance status data. After that, fold the improved status model back into the main Status Dashboard.
