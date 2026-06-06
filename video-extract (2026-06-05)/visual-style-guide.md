# Visual Style Guide From Video

The source UI is Alleva, not the Loom website. The analyzer should borrow the operational clarity and evidence-first structure, not copy branding.

## Overall Feel

- Dense clinical operations UI.
- Quiet, table-heavy, utilitarian.
- Left navigation stays fixed and dark.
- Main content is light gray/white with thin dividers.
- Evidence appears in large modal/document overlays.
- Actions are icon-first and compact.
- Coral buttons draw attention to add/edit actions.
- Purple floating action button is present in Alleva but should be used sparingly in the analyzer.

## Observed Layout

- Browser-width clinical workspace with:
  - dark teal left sidebar,
  - white top bar with logo/search/icons,
  - light gray page title band,
  - white data panels with thin blue/teal separators,
  - gray table headers,
  - icon action columns,
  - large printable document modal over a dimmed background.

## Colors

Approximate palette observed from frames:

| Token | Color | Usage |
|---|---|---|
| `--video-nav` | `#0b2f3a` | left sidebar background |
| `--video-nav-deep` | `#06242d` | darker sidebar blocks |
| `--video-coral` | `#ff8069` | add/action buttons |
| `--video-coral-dark` | `#e66654` | button hover/active |
| `--video-purple` | `#7058f4` | floating add/action accent |
| `--video-green` | `#35c76f` | active/compliant status |
| `--video-line` | `#8ed4dd` | thin grid/section separator |
| `--video-table-head` | `#b9b9b9` | table header background |
| `--video-page` | `#f1f1f1` | app background |
| `--video-paper` | `#ffffff` | document/modal surface |
| `--video-text` | `#263238` | primary text |

## Typography

- Sans-serif, compact, medium-weight headings.
- Tables use small text and tight row height.
- Modal titles are larger but still restrained.
- Avoid oversized marketing headings.
- Keep letter spacing at normal.

## Components To Borrow

### Sidebar

- Fixed width around 250-270 px on desktop.
- User/operator block at top with avatar, role, and session action.
- Primary nav with icon + label rows.
- Active row has stronger contrast, not a large pill.

### Top Bar

- Hamburger/menu icon.
- Product/logo area.
- Search icon/field.
- Right aligned utility icons: calendar, help, notifications, alert, user badge.

### Evidence Tables

- Gray header row.
- Thin blue separator below header.
- Compact icon action column.
- Empty state should be plain text, not illustrated.
- Important evidence columns:
  - created date,
  - document date,
  - staff signature date,
  - client signature date,
  - displayed next due date,
  - status,
  - source.

### Document Modal

- Wide centered overlay.
- Top title bar with print and close actions.
- White paper body.
- Thin blue horizontal separator.
- Boxed sections for demographics, problem list, note content, next due date, signatures.
- Signature evidence is visually distinct because it is far down in the document; the analyzer should jump users directly to signature evidence or pin it in a side rail.

### Status Badges

- Green for active/compliant.
- Coral/red for overdue or blocking problems.
- Purple/indigo for needs review/attention.
- Gray for pending/missing.

## Analyzer-Specific UI Recommendations

- Build the first screen as a work queue, not a landing page.
- Use a dense two-column layout:
  - left: active clients due/urgent queue,
  - right: selected client evidence and calculation detail.
- Include an evidence comparison panel:
  - document-provided next due date,
  - calculated date from current LOC interval,
  - calculated date from last staff signature,
  - status/conflict.
- Surface the LOC-change blocker in the same view, not hidden in settings.
- Add quick filters: `Overdue`, `Urgent`, `Due Soon`, `Needs Review`, `Missing Data`, `Compliant`.
- Allow export/copy of next-due tasks for Asana or manual task entry until native integration exists.
