# Linear Design System

## 1. Visual Theme & Atmosphere

Linear is an engineer-focused productivity tool defined by **radical restraint**. Every pixel is intentional. The interface feels like a precision instrument: dark, quiet, and fast. Decoration is eliminated unless it serves function. The purple accent is used as a surgical highlight, never as decoration. Surfaces are flat and matte. Transitions are quick and purposeful. The overall impression is a tool that respects your attention and gets out of your way.

**Atmosphere keywords**: dark, precise, quiet, instrument-grade, no-nonsense, surgical purple accents

**Design personality**: The engineering lead who speaks in bullet points and ships on time. No small talk, no ornament, just clarity.

---

## 2. Color Palette & Roles

### Core Backgrounds

| Semantic Name | Hex | Role |
|---|---|---|
| `bg-root` | `#0A0A0F` | Deepest background; canvas behind everything |
| `bg-surface-1` | `#111118` | Primary surface; panels, sidebar, main content area |
| `bg-surface-2` | `#181820` | Elevated surface; modals, dropdowns, popovers |
| `bg-surface-3` | `#1F1F2A` | Highest elevation; tooltips, notification toasts |
| `bg-hover` | `#25252F` | Hover state fill on interactive surfaces |

### Text

| Semantic Name | Hex | Role |
|---|---|---|
| `text-primary` | `#E8E8ED` | Primary body text, headings, active labels |
| `text-secondary` | `#8B8B96` | Secondary labels, descriptions, placeholder text |
| `text-tertiary` | `#5C5C66` | Disabled text, metadata, timestamps |
| `text-on-accent` | `#FFFFFF` | Text on accent-colored backgrounds |

### Accent

| Semantic Name | Hex | Role |
|---|---|---|
| `accent` | `#5E6AD2` | Primary accent; active states, links, focus rings, CTAs |
| `accent-hover` | `#6C75DB` | Hover state on accent elements |
| `accent-muted` | `#3D4480` | Muted accent; subtle badges, inline highlights |
| `accent-subtle` | `rgba(94, 106, 210, 0.12)` | Ghost accent; selected row backgrounds, hover tints |

### Semantic Colors

| Semantic Name | Hex | Role |
|---|---|---|
| `success` | `#4ADE80` | Completed states, confirmations |
| `warning` | `#FBBF24` | Caution states, in-progress |
| `error` | `#F87171` | Errors, destructive actions, validation failures |
| `info` | `#60A5FA` | Informational badges, neutral highlights |

### Borders

| Semantic Name | Hex | Role |
|---|---|---|
| `border-default` | `#25252F` | Default borders between sections and panels |
| `border-subtle` | `#1A1A24` | Very subtle dividers within a surface |
| `border-active` | `#5E6AD2` | Active/focused border on inputs and selections |

---

## 3. Typography Rules

### Font Stack

- **Primary**: `-apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif`
- **Monospace**: `"SF Mono", "Fira Code", "Cascadia Code", Menlo, monospace`
- **Display (hero only)**: `"Inter", -apple-system, sans-serif` at weight 600

### Type Scale

| Element | Size | Weight | Line Height | Letter Spacing | Color |
|---|---|---|---|---|---|
| Display / Hero | `48px` | 600 | 1.1 | `-0.02em` | `text-primary` |
| H1 / Page Title | `24px` | 600 | 1.3 | `-0.01em` | `text-primary` |
| H2 / Section | `18px` | 600 | 1.4 | `0` | `text-primary` |
| H3 / Subsection | `14px` | 600 | 1.4 | `0` | `text-primary` |
| Body | `14px` | 400 | 1.5 | `0` | `text-primary` |
| Body Small | `13px` | 400 | 1.5 | `0` | `text-secondary` |
| Caption / Meta | `12px` | 400 | 1.4 | `0.01em` | `text-tertiary` |
| Label | `12px` | 500 | 1.3 | `0.02em` | `text-secondary` |
| Code | `13px` | 400 | 1.5 | `0` | `accent` |

### Rules

- Never use italic for UI text. Only for long-form content.
- Labels and metadata are always `text-secondary` or `text-tertiary`, never `text-primary`.
- Headings never have decorative underlines or borders.
- Text does not use gradients. Use solid color only.
- Maximum line width: `680px` for readable body text.

---

## 4. Component Stylings

### Buttons

**Primary Button**
- Background: `accent` (`#5E6AD2`)
- Text: `text-on-accent` (`#FFFFFF`), 14px, weight 500
- Padding: `6px 16px`
- Border-radius: `6px`
- Border: none
- Hover: `accent-hover` (`#6C75DB`), slight brightness shift
- Active: `#5258B8`, `translateY(1px)` (1px push)
- Focus: `2px` outline `accent`, `2px` offset
- Disabled: opacity `0.4`, no hover effect

**Secondary Button**
- Background: `transparent`
- Text: `text-primary`, 14px, weight 500
- Padding: `6px 16px`
- Border-radius: `6px`
- Border: `1px solid border-default` (`#25252F`)
- Hover: background `bg-hover` (`#25252F`)
- Active: background `bg-surface-2` (`#181820`)
- Focus: `2px` outline `accent`, `2px` offset

**Ghost Button**
- Background: `transparent`
- Text: `text-secondary`, 14px, weight 400
- Padding: `6px 12px`
- Border-radius: `6px`
- Border: none
- Hover: background `bg-hover`, text becomes `text-primary`
- Active: background `bg-surface-2`
- Focus: `2px` outline `accent`, `2px` offset

**Danger Button**
- Same as secondary but text and border use `error` (`#F87171`)
- Hover: background `rgba(248, 113, 113, 0.08)`

### Cards

- Background: `bg-surface-1` (`#111118`)
- Border-radius: `8px`
- Border: `1px solid border-default` (`#25252F`)
- Padding: `20px`
- Hover: border-color `#2F2F3A`, very subtle
- No box-shadow in default state
- No decorative gradients on cards

### Inputs

**Text Input**
- Background: `bg-surface-1` (`#111118`)
- Border: `1px solid border-default` (`#25252F`)
- Border-radius: `6px`
- Padding: `8px 12px`
- Text: `text-primary`, 14px
- Placeholder: `text-tertiary`
- Focus: border `accent`, subtle `0 0 0 3px accent-subtle` ring
- Error: border `error`, error message in `error` color at 12px below input

**Select / Dropdown**
- Same base as text input
- Dropdown panel: `bg-surface-2` (`#181820`), `8px` border-radius, `1px` border `border-default`
- Dropdown shadow: `0 8px 24px rgba(0, 0, 0, 0.4)`
- Selected item: `accent-subtle` background, `accent` text
- Hover item: `bg-hover` background

### Navigation

**Sidebar**
- Background: `bg-surface-1` (`#111118`)
- Width: `240px` (collapsible to `48px` icon-only mode)
- Border-right: `1px solid border-default`
- Item height: `32px`
- Item padding: `0 12px`
- Item border-radius: `6px`
- Item text: `text-secondary`, 13px, weight 400
- Active item: background `accent-subtle`, text `accent`, weight 500
- Hover item: background `bg-hover`, text `text-primary`
- Group labels: `text-tertiary`, 11px, weight 600, `0.04em` letter-spacing, uppercase

**Top Bar**
- Background: `bg-surface-1` with `border-bottom: 1px solid border-default`
- Height: `44px`
- Breadcrumbs: `text-secondary`, 13px, separated by `/` in `text-tertiary`
- Actions aligned right

### Badges / Tags

- Border-radius: `9999px` (pill shape)
- Padding: `2px 8px`
- Font: 11px, weight 500
- Variants:
  - Default: `bg-hover` background, `text-secondary` text
  - Accent: `accent-subtle` background, `accent` text
  - Success: `rgba(74, 222, 128, 0.1)` background, `success` text
  - Warning: `rgba(251, 191, 36, 0.1)` background, `warning` text
  - Error: `rgba(248, 113, 113, 0.1)` background, `error` text

### Toggles

- Track: `bg-hover` off, `accent` on
- Knob: `text-primary`, `12px` circle
- Track size: `32px x 18px`, border-radius `9999px`
- Transition: `150ms ease`

---

## 5. Layout Principles

### Spacing Scale

| Token | Value | Usage |
|---|---|---|
| `xs` | `4px` | Tight inline gaps, icon-to-label |
| `sm` | `8px` | Between related items |
| `md` | `12px` | Between form fields, list items |
| `lg` | `16px` | Section padding, card inner gaps |
| `xl` | `20px` | Card padding, section margins |
| `2xl` | `24px` | Major section separation |
| `3xl` | `32px` | Page-level vertical rhythm |
| `4xl` | `48px` | Hero-level spacing |
| `5xl` | `64px` | Maximum section gap |

### Grid

- Content max-width: `1200px`
- Sidebar + main layout: sidebar `240px` fixed, main fills remaining
- Gutter: `16px` between columns
- Card grid: 3 columns at >= 1200px, 2 at >= 768px, 1 below
- Grid column gap: `16px`
- Grid row gap: `16px`

### Whitespace Rules

- Sections are separated by `border-subtle` lines, not by increased whitespace alone.
- Vertical rhythm is tight: prefer `12px-16px` between items, not `24px-32px`.
- Horizontal padding in panels is always `16px` minimum.
- Content never touches viewport edges: minimum `16px` horizontal padding on mobile, `24px` on desktop.
- There is no decorative whitespace. Whitespace exists to group or separate, never to fill.

### Alignment

- All content is left-aligned. Center alignment only for modals and empty states.
- Labels sit above inputs (top-aligned), never to the left in forms.
- Icons are `16px` and vertically centered with adjacent text.

---

## 6. Depth & Elevation

Linear uses minimal shadows. Elevation is communicated primarily through background color shifts and border presence, not drop shadows.

### Elevation Levels

| Level | Background | Border | Shadow | Usage |
|---|---|---|---|---|
| 0 (base) | `bg-root` (`#0A0A0F`) | none | none | Canvas |
| 1 (surface) | `bg-surface-1` (`#111118`) | `1px border-default` | none | Panels, sidebar, cards |
| 2 (raised) | `bg-surface-2` (`#181820`) | `1px border-default` | `0 4px 16px rgba(0,0,0,0.3)` | Dropdowns, popovers |
| 3 (overlay) | `bg-surface-3` (`#1F1F2A`) | `1px border-default` | `0 8px 24px rgba(0,0,0,0.4)` | Modals, command palette |

### Glow Effects (use sparingly)

- Accent glow on focused inputs: `box-shadow: 0 0 0 3px rgba(94, 106, 210, 0.2)`
- CTA button glow (hero only): `box-shadow: 0 0 20px rgba(94, 106, 210, 0.3)`
- Never use glow on cards, badges, or navigation items.

### Overlay

- Modal backdrop: `rgba(0, 0, 0, 0.6)` with `backdrop-filter: blur(4px)`

---

## 7. Do's and Don'ts

### Do

- Use `accent` sparingly. One accent element per viewport is often enough.
- Keep surfaces flat. Background color differences, not shadows, convey depth.
- Use monospace font for IDs, keys, and code snippets.
- Round numbers precisely. Border-radius is `6px` for inputs/buttons, `8px` for cards, `9999px` for pills only.
- Use `text-secondary` for descriptions and `text-tertiary` for metadata. This hierarchy is the primary way to guide attention.
- Animate with `150ms-200ms ease` for interactive state changes. Nothing slower.
- Use 1px borders. Never 2px or 3px except for focus rings.
- Prefer icon + text for actions. Icon-only only if the action is universally understood (e.g., close X, search magnifier).

### Don't

- Do not use gradients on text. Ever.
- Do not use decorative gradients on backgrounds of cards, panels, or sections. Subtle radial glows in hero sections are the only exception.
- Do not use rounded corners greater than `8px` on rectangular elements. No `16px` or `24px` radius cards.
- Do not add box-shadows to resting-state cards or list items.
- Do not use `accent` color for decorative elements like dividers or background fills (except `accent-subtle` for selection states).
- Do not use bold/weight-700 for body text. 600 is the maximum and only for headings and labels.
- Do not center-align paragraphs or form layouts. Left-align everything.
- Do not use emoji or decorative icons in navigation labels.
- Do not animate `width`, `height`, `top`, `left`, or `margin`. Use `transform` and `opacity` only.
- Do not use color alone to convey state. Pair with text labels or icons.

---

## 8. Responsive Behavior

### Breakpoints

| Name | Min Width | Layout Behavior |
|---|---|---|
| `mobile` | `0` | Single column, sidebar hidden (hamburger), stacked cards |
| `tablet` | `768px` | Optional sidebar, 2-column card grid |
| `desktop` | `1024px` | Full sidebar visible, 2-column grid, side-by-side forms |
| `wide` | `1200px` | 3-column card grid, maximum content width enforced |

### Adaptation Rules

- **Sidebar**: Hidden below `1024px`, replaced by hamburger menu overlay. Overlay uses `bg-surface-2` with slide-in from left (`transform: translateX`, 200ms ease).
- **Navigation items**: Text + icon on desktop; icon-only below `768px` if sidebar is collapsed.
- **Cards**: Full-width below `768px`, 2-up at `768px+`, 3-up at `1200px+`.
- **Top bar**: Title truncates with ellipsis below `768px`. Breadcrumbs collapse to last segment + ellipsis.
- **Forms**: Single column always. Top-aligned labels. Full-width inputs on mobile, max `480px` on desktop.
- **Modals**: Full-screen on mobile (with safe-area padding), centered overlay on desktop.
- **Tables**: Convert to stacked card list on mobile. Each row becomes a card with label-value pairs.
- **Font sizes**: Reduce display/hero from `48px` to `32px` below `768px`. H1 from `24px` to `20px` below `768px`. Body text stays `14px` at all sizes.
- **Touch targets**: Minimum `36px` height for all interactive elements on mobile (up from `32px` on desktop).

### Performance Notes

- Use `will-change: transform` sparingly, only on elements actively animating.
- Prefer CSS transitions over JS-driven animations for state changes.
- Backdrop-filter (blur) should be used only for modal overlays; avoid on frequently toggled elements.
