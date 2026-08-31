# Design rules

SentinelLoop Command Center is an emergency operations surface, not a consumer app.

## Color

Exact tokens:

| Token | Value | Allowed use |
| --- | --- | --- |
| `--ink` | `#1C2024` | Application background |
| `--panel` | `#262B31` | Cards, panels, controls |
| `--chalk` | `#F2F0EA` | Text and high-contrast chrome |
| `--signal-amber` | `#E8A33D` | Medium risk, investigating |
| `--ember-orange` | `#C9642E` | High risk |
| `--hazard-red` | `#D64545` | Critical risk, open incidents, alert presence |
| `--verified-teal` | `#3FA796` | Low risk, verified, resolved |

Saturated colors (amber / ember / red / teal) may only represent:

- risk severity
- emergency states
- verification states
- resolution states

Never use them for buttons, branding, hover, gradients, or decoration.

Primary surfaces: background `--ink`, cards `--panel`, text `--chalk`.

Do not communicate Critical by color alone. Always include the word `Critical` (or `CRITICAL`) next to the indicator.

## Typography

| Role | Family |
| --- | --- |
| Display headings | Space Grotesk, 600 / 700 |
| Body | IBM Plex Sans |
| IDs, timestamps, coordinates, logs, risk scores, confidence, metadata | IBM Plex Mono |

Fallbacks: `sans-serif` / `monospace`. Loaded from Google Fonts with `display=swap`.

## Spacing and radius

Spacing scale: 4 / 8 / 12 / 16 / 24 / 32 / 48 px (`--space-1` … `--space-7`).

Radius: 6px (`--radius-sm`) or 8px (`--radius-md`) only. No pills or large rounded cards.

Shadows: none by default. Separate surfaces with `--border` and ink/panel contrast.

## Incident cards

Left risk tab is `--risk-tab-width: 5px` (within 4–6px).

| Risk | Tab |
| --- | --- |
| Low | verified-teal |
| Medium | signal-amber |
| High | ember-orange |
| Critical | hazard-red |

Remaining card: panel background, chalk text.

## Status mappings

Command-center keys:

| Status | Color |
| --- | --- |
| OPEN | hazard-red |
| INVESTIGATING | signal-amber |
| VERIFIED | verified-teal |
| RESOLVED | verified-teal |

Lifecycle aliases (`New`, `Validating`, `Assigned`, `In Progress`, `Awaiting Verification`, `Closed`, and SPEC enums) map onto those four keys in `design-system/colors.ts`.

## Components

Import from `design-system`. Do not introduce one-off colors or extra radii on pages.

- Buttons: neutral panel/chalk only.
- Cards: `incident-card`, `evidence-card`, `officer-card`, `analytics-card`, `activity-card` with hover, focus, skeleton, and empty states.
- Charts: dark, minimal grid (baseline only). Risk colors only on severity series.

## Motion

Honor `prefers-reduced-motion`. Transitions default to 120ms and collapse to 0 when reduced motion is requested. No flashing indicators or moving backgrounds.

## Accessibility

Visible `:focus-visible` ring in chalk. Keyboard activation on incident cards. Status and risk include text labels. Contrast is chalk on ink/panel.

## Layout

Desktop: sidebar + header + dense main columns.  
Tablet: two-column panels.  
Mobile: stacked workflow, horizontal sidebar navigation.
