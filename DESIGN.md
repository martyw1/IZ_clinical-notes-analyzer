# IZ Clinical Notes Analyzer Design System

## 1. Atmosphere & Identity

IZ Clinical Notes Analyzer should feel like a clinical operations workbench: calm, dense, readable, and audit-ready. The signature is a risk-first status language: thin colored stripes, compact tabular counts, neutral rows, and document-like evidence panels that help a facility manager decide what to trust and what to act on today.

## 2. Color

### Palette

| Role | Token | Light | Dark | Usage |
|------|-------|-------|------|-------|
| App background | `--bg-app` | `#F7FAF8` | `#111815` | Page background |
| Surface | `--bg-surface` | `#FFFFFF` | `#18201D` | Panels, tables, cards |
| Subtle surface | `--bg-subtle` | `#EEF6F1` | `#223029` | Bands, selected fills |
| Raised surface | `--bg-raised` | `#FBFDFC` | `#1E2924` | Sticky toolbar, detail panel |
| Border soft | `--border-soft` | `#DDE7E1` | `#33423B` | Dividers and table borders |
| Border strong | `--border-strong` | `#AFC0B8` | `#52645C` | Active and focus borders |
| Text main | `--text-main` | `#18201D` | `#F4F8F5` | Primary text |
| Text muted | `--text-muted` | `#5F6F68` | `#A9B8B1` | Secondary text |
| Text faint | `--text-faint` | `#7C8B84` | `#7E9188` | Metadata, disabled |
| Primary action | `--action-primary` | `#18543B` | `#2F7D4F` | Primary commands |
| Primary action hover | `--action-primary-hover` | `#0F432D` | `#24623F` | Primary command hover |
| Action active fill | `--action-active-bg` | `#E2F1E8` | `#223C2D` | Active navigation and filters |
| Action hover fill | `--action-hover-bg` | `#F5FAF7` | `#223029` | Secondary command hover |
| Focus ring | `--focus-ring` | `rgba(37, 99, 168, 0.26)` | `rgba(147, 197, 253, 0.36)` | Keyboard focus outline |
| Overdue | `--status-overdue` | `#9F1D2D` | `#F87171` | True overdue or critical action |
| Urgent | `--status-urgent` | `#B45309` | `#FDBA74` | Immediate attention |
| Due soon | `--status-due-soon` | `#D39A16` | `#FCD34D` | Upcoming deadline |
| Returned | `--status-returned` | `#5B5FC7` | `#A5B4FC` | Returned to counselor |
| Needs review | `--status-needs-review` | `#2563A8` | `#93C5FD` | Manager review needed |
| Missing data | `--status-missing-data` | `#64748B` | `#CBD5E1` | Required evidence missing |
| Conflicting | `--status-conflicting` | `#7C3AED` | `#C4B5FD` | Source disagreement |
| Unable | `--status-unable` | `#374151` | `#D1D5DB` | Unable to evaluate |
| Compliant | `--status-compliant` | `#2F7D4F` | `#86EFAC` | Compliant or approved |
| Unvalidated | `--status-unvalidated` | `#6D28D9` | `#C084FC` | Configured but not validated |

### Rules

- Use color as status language, not decoration.
- Keep rows and panels neutral. Critical states use stripes, dots, borders, and badges instead of full-row color fills.
- Red is reserved for overdue or destructive action. Use slate for missing data and violet for source uncertainty or unvalidated configuration.

## 3. Typography

### Scale

| Level | Size | Weight | Line Height | Tracking | Usage |
|-------|------|--------|-------------|----------|-------|
| Page title | `1.5rem` | 600 | 1.2 | 0 | Workbench and route headings |
| Section title | `1.05rem` | 600 | 1.3 | 0 | Panel headings |
| Table header | `0.76rem` | 600 | 1.3 | 0 | Column labels |
| Body | `0.95rem` | 400 | 1.45 | 0 | Default UI text |
| Body small | `0.84rem` | 400 | 1.4 | 0 | Evidence text and helper copy |
| Caption | `0.74rem` | 600 | 1.3 | 0 | Metadata labels |
| Count | `1.3rem` | 600 | 1.1 | 0 | Risk strip counts |

### Font Stack

- Primary: `"Segoe UI", "Aptos", system-ui, -apple-system, BlinkMacSystemFont, sans-serif`
- Mono: `"Cascadia Mono", "SFMono-Regular", Consolas, "Liberation Mono", monospace`

### Rules

- Enable `font-variant-numeric: tabular-nums` on counts, dates, durations, and table cells.
- Body text stays at or above 14px. Dense views reduce padding before reducing type.
- Use sentence case for operational labels and headings.

## 4. Spacing & Layout

### Base Unit

All spacing derives from a base of 4px.

| Token | Value | Usage |
|-------|-------|-------|
| `--space-1` | `4px` | Tight icon or dot spacing |
| `--space-2` | `8px` | Compact row gaps |
| `--space-3` | `12px` | Inputs, toolbar controls |
| `--space-4` | `16px` | Panel interior spacing |
| `--space-5` | `20px` | Workbench gaps |
| `--space-6` | `24px` | Page section spacing |
| `--space-8` | `32px` | Major route spacing |

### Grid

- Max content width: `1480px`.
- Primary workbench: sticky toolbar, status strip, queue table left, detail panel right.
- Responsive breakpoints: collapse workbench to one column below 1100px and stack all fixed grids below 720px.

### Rules

- Fixed-format elements such as status segments, table rows, toolbar controls, and evidence meters must have stable dimensions so filters and state changes do not shift layout.
- Prefer thin dividers and table tracks over nested cards.

## 5. Components

### Operational Toolbar

- **Structure**: `header` with title and source freshness, search/date/filter controls, then action buttons.
- **Variants**: Treatment Plans, Dashboard summary, Source readiness.
- **Spacing**: `--space-3` to `--space-4`.
- **States**: sticky, hover, focus, disabled, loading.
- **Accessibility**: labeled inputs, visible focus ring, no hidden action text.
- **Motion**: hover and press use transform only.

### Risk Status Strip

- **Structure**: one compact segment per status in risk-first order.
- **Variants**: interactive filters, read-only dashboard summary.
- **Spacing**: `--space-2` internal gap with thin dividers.
- **States**: default, hover, active, focus, disabled empty.
- **Accessibility**: `aria-pressed` on filter segments and title text for helper copy.
- **Motion**: border and background color transition only.

### Work Queue Table

- **Structure**: grouped status headers followed by button rows with a left risk stripe.
- **Variants**: Treatment Plans queue, compact preview.
- **Spacing**: compact cell padding using `--space-2` and `--space-3`.
- **States**: hover, active selection, focus, empty, filtered-empty.
- **Accessibility**: table roles retained; row buttons have MRN-only labels.
- **Motion**: no row height animation.

### Roster Table

- **Structure**: MRN-first rows with authorized full name, compact provenance fields, and one primary treatment-plan action per record.
- **Variants**: Patient Roster with an MRN patient-detail action and plan selector; Treatment Plans Roster with linked MRN patient-detail actions, plan actions, lineage columns, and noninteractive unlinked-plan identity.
- **Spacing**: compact table cells with a minimum readable selector width; stacked labeled cells below 900px.
- **States**: loading, empty, filtered-empty, no-plan, selectable, refresh-in-progress.
- **Accessibility**: MRN buttons announce the full name and MRN; native select controls use MRN-specific labels; plan buttons announce both plan ID and MRN; 24-hour timestamps include an explicit timezone.
- **Motion**: none.

### Detail Panel

- **Structure**: selected patient identity and full name followed by document-like semantic sections with source paths and no repeated raw field dump.
- **Variants**: Patient Record Detail with every source field and treatment-plan selector; Treatment Plan Detail with identity/provenance, date evidence, clinical hierarchy, review/signature history, checklist evidence, warnings, source archive, and raw diagnostics; no-selection instructional empty state.
- **Spacing**: `--space-4` sections with document-like dividers.
- **States**: empty, loading, selected, evidence modal.
- **Accessibility**: section labels describe evidence purpose, not visual styling.
- **Motion**: no essential animation.

### Source Readiness Cards

- **Structure**: source name, state badge, status fields, blockers, allowed and disabled actions.
- **Variants**: Manual upload, API readiness, Alleva treatment-plan sync.
- **Spacing**: `--space-4`.
- **States**: ready, fresh, stale, blocked, not configured, failed, manual only, awaiting approval.
- **Accessibility**: blockers use text plus badge color, never color alone.
- **Motion**: hover for actionable cards only.

### Compact Job Status

- **Structure**: phase and progress first, followed by compact record/warning counts and the last completed timestamp.
- **Variants**: diagnostic preview, active patient roster pull, approved treatment-plan sync.
- **Spacing**: `--space-2` between status rows with a thin left state stripe.
- **States**: idle, queued, running, writing, completed, completed with warnings, failed, cancelled, interrupted.
- **Accessibility**: one polite atomic live region per job, a labeled progress bar, `aria-busy` while active, and alert semantics only for failures.
- **Motion**: progress width may transition; status changes must not shift the surrounding action controls.

### Evidence Ledger

- **Structure**: compact newest-first event list with event label, source, timestamp, and state.
- **Variants**: dashboard preview, source readiness full ledger, selected-client audit snippet.
- **Spacing**: `--space-2` row rhythm.
- **States**: empty and populated.
- **Accessibility**: timestamps are visible text, not title-only metadata.
- **Motion**: none.

## 6. Motion & Interaction

### Timing

| Type | Duration | Easing | Usage |
|------|----------|--------|-------|
| Micro | `120ms` | `ease-out` | Button hover and press |
| Standard | `180ms` | `ease-in-out` | Filter active state |
| Emphasis | `240ms` | `ease-out` | Detail panel focus affordance |

### Rules

- Only animate `transform`, `opacity`, `background-color`, `border-color`, or `color`.
- All buttons and row actions have hover, active, focus, and disabled states.
- Respect `prefers-reduced-motion` by removing transform transitions.

## 7. Depth & Surface

### Strategy

Use borders-only with subtle tonal shifts. Avoid glass, large shadows, decorative gradients, and nested card stacks.

| Type | Value | Usage |
|------|-------|-------|
| Default border | `1px solid var(--border-soft)` | Panels, table outlines |
| Strong border | `1px solid var(--border-strong)` | Active filters, focused controls |
| Status stripe | `4px solid var(--status-*)` | Queue rows and group headers |
| Surface shift | `var(--bg-subtle)` | Dashboard bands, active rows, empty states |

### Rules

- Cards are for repeated items, source cards, modals, or framed tools only.
- Page sections are full-width work areas, not floating decorative cards.
- The detail timeline is the richest graphic element; charts remain small and functional.
