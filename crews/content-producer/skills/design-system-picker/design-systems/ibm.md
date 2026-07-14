# IBM Design System

Enterprise authority through structured restraint. IBM's visual language is built on the Carbon Design System — an open-source framework where every pixel earns its place through utility, not decoration. The 8-bar motif from the IBM logo is the design philosophy made manifest: horizontal stripes of equal weight, orderly progression, nothing ornamental. Dark mode is not a luxury mode — it is a first-class citizen with dedicated theme tokens (g90, g100). Information density is a virtue, not a vice. Trust is communicated through consistency, not through charisma.

---

## 1. Visual Theme & Atmosphere

IBM's visual language communicates institutional trust and engineering rigor — the confidence of a company that has defined enterprise computing for over a century. Surfaces are flat and structured. Color is restrained: IBM Blue carries every primary action, gray-100 anchors every dark surface, and the 12-color palette family exists for data visualization and status communication, never for decoration. Typography works at two tempos: Productive (compact, task-focused, 14px default) for tools and dashboards; Expressive (fluid, spacious, larger scales) for marketing and storytelling. Both tempos are calibrated for IBM Plex, IBM's open-source typeface.

The page is a data surface. White and gray-10 are the light canvases; gray-90 and gray-100 are the dark canvases. Layers are differentiated by background color shifts, not shadows. The 8px grid governs every spacing decision. The 2x Grid system provides 16 columns at desktop with five responsive breakpoints. Data tables, forms, and dashboards are the native content — not hero images. Photography, when used, is secondary to information. The 8-bar stripe motif appears as a controlled signature, not as wallpaper.

**Keywords:** enterprise authority, structured restraint, information density, institutional trust, productive precision, Carbon discipline, 8-bar rhythm

---

## 2. Color Palette & Roles

IBM's color system is organized into 12 scale families, each with 10 stops (10 through 100, where 10 is lightest and 100 is deepest). Carbon defines four themes: White (high-contrast light), g10 (low-contrast light), g90 (low-contrast dark), g100 (high-contrast dark). Blue 60 (`#0F62FE`) is the canonical interactive color across all themes.

### Light Mode (White / g10)

| Token | Hex | Role |
|-------|-----|------|
| `--color-canvas` | `#FFFFFF` | Page background — the White theme default |
| `--color-surface` | `#F4F4F4` | Container background on canvas — gray-10, the g10 theme background |
| `--color-surface-elevated` | `#FFFFFF` | Elevated container on gray-10 surface — cards, modals |
| `--color-surface-strong` | `#E0E0E0` | Subtle border, tertiary background — gray-20 |
| `--color-ink` | `#161616` | Primary text — gray-100, high-contrast body and headings |
| `--color-body` | `#393939` | Default running text — gray-80 |
| `--color-muted` | `#525252` | Secondary text, labels — gray-70 |
| `--color-muted-soft` | `#6F6F6F` | Tertiary text, placeholder — gray-60 |
| `--color-primary` | `#0F62FE` | IBM Blue — all primary CTAs, links, active elements, interactive accent. blue-60 |
| `--color-primary-hover` | `#0043CE` | Hover state for primary — blue-70 |
| `--color-primary-active` | `#002D9C` | Active/pressed state for primary — blue-80 |
| `--color-primary-subtle` | `#EDF5FF` | Light tint background for selected/highlighted items — blue-10 |
| `--color-on-primary` | `#FFFFFF` | White text on blue buttons |
| `--color-hairline` | `#C6C6C6` | 1px dividers, input borders — gray-30 |
| `--color-hairline-strong` | `#8D8D8D` | Medium-contrast border, emphasis — gray-50 |
| `--color-accent` | `#8A3FFC` | Secondary accent — purple-60. Data viz, supplementary highlights |
| `--color-accent-hover` | `#6929C4` | Accent hover — purple-70 |
| `--color-success` | `#24A148` | Positive, available — green-50 |
| `--color-warning` | `#F1C21B` | Caution — yellow-30 |
| `--color-error` | `#DA1E28` | Destructive, error — red-60 |

### Dark Mode (g90 / g100)

| Token | Hex | Role |
|-------|-----|------|
| `--color-canvas` | `#161616` | Page background — gray-100, the g100 theme default |
| `--color-surface` | `#262626` | Container background on dark canvas — gray-90, the g90 theme default |
| `--color-surface-elevated` | `#393939` | Elevated container on dark surface — gray-80 |
| `--color-surface-strong` | `#525252` | Subtle border on dark, tertiary dark background — gray-70 |
| `--color-ink` | `#F4F4F4` | Primary text on dark — gray-10 |
| `--color-body` | `#C6C6C6` | Default running text on dark — gray-30 |
| `--color-muted` | `#A8A8A8` | Secondary text on dark — gray-40 |
| `--color-muted-soft` | `#8D8D8D` | Tertiary text on dark — gray-50 |
| `--color-primary` | `#0F62FE` | IBM Blue — unchanged across themes. blue-60 is universal |
| `--color-primary-hover` | `#4589FF` | Hover on dark — blue-50, shifted lighter for dark backgrounds |
| `--color-primary-active` | `#78A9FF` | Active on dark — blue-40 |
| `--color-primary-subtle` | `#001141` | Dark tint background for selected items — blue-100 |
| `--color-on-primary` | `#FFFFFF` | White text on blue buttons (unchanged) |
| `--color-hairline` | `#393939` | 1px dividers on dark — gray-80 |
| `--color-hairline-strong` | `#6F6F6F` | Emphasis borders on dark — gray-60 |
| `--color-accent` | `#A56EFF` | Secondary accent on dark — purple-50, shifted lighter |
| `--color-accent-hover` | `#BE95FF` | Accent hover on dark — purple-40 |
| `--color-success` | `#42BE65` | Positive on dark — green-40, shifted lighter |
| `--color-warning` | `#F1C21B` | Caution on dark — yellow-30, unchanged |
| `--color-error` | `#FA4D56` | Error on dark — red-50, shifted lighter |

**Rule:** IBM Blue (`#0F62FE`, blue-60) is the one color that does not shift between light and dark themes. It is the fixed North Star — every other accent color shifts lighter on dark backgrounds to maintain contrast and legibility. The dark palette uses the gray scale inverted: gray-10 becomes text, gray-100 becomes canvas. This inversion is systematic, not aesthetic.

### Full Color Families (for Data Visualization)

| Family | 10 | 20 | 30 | 40 | 50 | 60 | 70 | 80 | 90 | 100 |
|--------|------|------|------|------|------|------|------|------|------|------|
| Gray | `#F4F4F4` | `#E0E0E0` | `#C6C6C6` | `#A8A8A8` | `#8D8D8D` | `#6F6F6F` | `#525252` | `#393939` | `#262626` | `#161616` |
| Cool Gray | `#F2F4F8` | `#DDE1E6` | `#C1C7CD` | `#A2A9B0` | `#878D96` | `#697077` | `#4D5358` | `#343A3F` | `#21272A` | `#121619` |
| Blue | `#EDF5FF` | `#D0E2FF` | `#A6C8FF` | `#78A9FF` | `#4589FF` | `#0F62FE` | `#0043CE` | `#002D9C` | `#001D6C` | `#001141` |
| Red | `#FFF1F1` | `#FFD7D9` | `#FFB3B8` | `#FF8389` | `#FA4D56` | `#DA1E28` | `#A2191F` | `#750E13` | `#520408` | `#2D0709` |
| Green | `#DEFBE6` | `#A7F0BA` | `#6FDC8C` | `#42BE65` | `#24A148` | `#198038` | `#0E6027` | `#044317` | `#022D0D` | `#071908` |
| Yellow | `#FCF4D6` | `#FDDC69` | `#F1C21B` | `#D2A106` | `#B28600` | `#8E6A00` | `#684E00` | `#483700` | `#302400` | `#1C1500` |
| Purple | `#F6F2FF` | `#E8DAFF` | `#D4BBFF` | `#BE95FF` | `#A56EFF` | `#8A3FFC` | `#6929C4` | `#491D8B` | `#31135E` | `#1C0F30` |
| Cyan | `#E5F6FF` | `#BAE6FF` | `#82CFFF` | `#33B1FF` | `#1192E8` | `#0072C3` | `#00539A` | `#003A6D` | `#012749` | `#061727` |
| Teal | `#D9FBFB` | `#9EF0F0` | `#3DDBD9` | `#08BDBA` | `#009D9A` | `#007D79` | `#005D5D` | `#004144` | `#022B30` | `#081A1C` |
| Magenta | `#FFF0F7` | `#FFD6E8` | `#FFAFD2` | `#FF7EB6` | `#EE5396` | `#D02670` | `#9F1853` | `#740937` | `#510224` | `#2A0A18` |
| Orange | `#FFF2E8` | `#FFD9BE` | `#FFB784` | `#FF832B` | `#EB6200` | `#BA4E00` | `#8A3800` | `#5E2900` | `#3E1A00` | `#231000` |

**Data visualization rule:** Use stops 40-70 for chart fills (sufficient contrast on both light and dark backgrounds). Use stops 10-20 for background tints. Use stops 80-100 for text labels on light charts. Never use stops 10-30 as text — insufficient contrast.

---

## 3. Typography Rules

**Primary:** IBM Plex Sans (IBM's open-source typeface, designed by Mike Abbink)
**Mono:** IBM Plex Mono (code, data, technical content)
**Serif:** IBM Plex Serif (long-form editorial, rarely used in product UI)
**Fallback stack:** `"IBM Plex Sans", "Helvetica Neue", Arial, sans-serif`

### Productive Type Set (Product UI — Dashboards, Tools, Forms)

| Token | Size | Weight | Line Height | Tracking | Usage |
|-------|------|--------|-------------|----------|-------|
| `--text-heading-05` | `32px` | 400 / Regular | 40px | 0 | Page titles, top-level headings in dashboards |
| `--text-heading-04` | `28px` | 400 / Regular | 36px | 0 | Section headings, panel titles |
| `--text-heading-03` | `24px` | 400 / Regular | 32px | 0 | Sub-section headings, card titles |
| `--text-heading-02` | `20px` | 400 / Regular | 28px | 0 | Component headings, group labels |
| `--text-heading-01` | `14px` | 600 / Semi-Bold | 18px | 0.16px | Small headings, field group labels, tile titles |
| `--text-body-02` | `16px` | 400 / Regular | 24px | 0 | Default body text, paragraphs, descriptions |
| `--text-body-01` | `14px` | 400 / Regular | 20px | 0.16px | Compact body — the product default. Table cells, form fields, lists |
| `--text-body-compact-02` | `16px` | 400 / Regular | 22px | 0 | Tighter line-height body for dense UI |
| `--text-body-compact-01` | `14px` | 400 / Regular | 18px | 0.16px | Tightest body — data tables, dense forms |
| `--text-label-02` | `14px` | 600 / Semi-Bold | 20px | 0 | Form labels, badge text, table headers |
| `--text-label-01` | `12px` | 400 / Regular | 16px | 0.32px | Captions, helper text, metadata, timestamps |
| `--text-helper-text` | `12px` | 400 / Regular | 16px | 0.32px | Inline help, validation messages |
| `--text-caption` | `12px` | 400 / Italic | 16px | 0.32px | Editorial captions only — never in product UI |
| `--text-code-02` | `16px` | 400 / Regular | 24px | 0.32px | Code blocks — IBM Plex Mono |
| `--text-code-01` | `14px` | 400 / Regular | 20px | 0.32px | Inline code — IBM Plex Mono |

### Expressive Type Set (Marketing — Landing Pages, Campaigns, Storytelling)

| Token | Size (lg) | Weight | Line Height | Tracking | Usage |
|-------|-----------|--------|-------------|----------|-------|
| `--text-display-03` | `64px` | 300 / Light | 72px | -0.5px | Hero headlines, campaign mastheads |
| `--text-display-02` | `48px` | 300 / Light | 56px | 0 | Section heroes, feature leads |
| `--text-display-01` | `36px` | 300 / Light | 44px | 0 | Feature titles, marketing sub-heads |
| `--text-expressive-heading-05` | `28px` | 600 / Semi-Bold | 36px | 0 | Marketing section headings |
| `--text-expressive-heading-04` | `24px` | 600 / Semi-Bold | 32px | 0 | Marketing sub-section headings |
| `--text-expressive-heading-03` | `20px` | 400 / Regular | 26px | 0 | Feature descriptions, intro paragraphs |
| `--text-expressive-heading-02` | `18px` | 600 / Semi-Bold | 24px | 0 | Card headings, callout titles |
| `--text-expressive-heading-01` | `14px` | 600 / Semi-Bold | 20px | 0.16px | Small callout headings, eyebrow text |
| `--text-expressive-paragraph-01` | `18px` | 400 / Regular | 28px | 0 | Marketing body, longer-form storytelling |
| `--text-quotation-02` | `24px` | 300 / Light | 34px | 0 | Pull quotes, testimonial text |
| `--text-quotation-01` | `18px` | 400 / Regular | 28px | 0 | Smaller pull quotes, inline citations |

### Typography Principles

- **14px is the product default.** IBM's product UI lives at 14px body text — not 16px. This is intentional: enterprise dashboards need information density, and 14px / 20px line-height maximizes visible data while remaining legible. This is the single biggest differentiator from consumer design systems.
- **Weight 400 is the workhorse.** Productive headings use Regular (400) weight — not Bold. Only label tokens and the smallest heading token (heading-01) use Semi-Bold (600). IBM trusts size and spacing for hierarchy, not weight.
- **Expressive mode uses Light (300) for display.** Marketing display headlines run at weight 300 with larger sizes — the inverse of the productive pattern. This creates the characteristic IBM marketing voice: large, light, confident.
- **IBM Plex Mono is mandatory for code and data.** Never use a generic monospace fallback when IBM Plex Mono is available. The typeface is designed to harmonize with Plex Sans at the same x-height.
- **Tracking is minimal.** Productive text uses 0-0.32px tracking. Expressive display uses -0.5px to 0. No large positive tracking — IBM is not a fashion brand.
- **Fluid sizing for expressive headings.** Display-03 scales from 36px at sm breakpoint to 64px at lg+. This is the only place Carbon uses fluid type.

---

## 4. Component Stylings

### Buttons

**Primary (IBM Blue)**
```css
background: var(--color-primary);
color: var(--color-on-primary);
padding: 11px 16px;
height: 48px;
border-radius: 0px;
font-size: 14px;
font-weight: 400;
font-family: "IBM Plex Sans", sans-serif;
letter-spacing: 0;
border: none;
cursor: pointer;
transition: background 110ms ease;
```
- Hover: `var(--color-primary-hover)`
- Active: `var(--color-primary-active)`
- Disabled: `background: var(--color-surface-strong); color: var(--color-muted-soft)`

**Secondary (Outlined)**
```css
background: transparent;
color: var(--color-primary);
padding: 10px 15px;
height: 48px;
border-radius: 0px;
border: 1px solid var(--color-primary);
font-size: 14px;
font-weight: 400;
letter-spacing: 0;
```
- Hover: `background: var(--color-primary-subtle)`

**Tertiary (Ghost)**
```css
background: transparent;
color: var(--color-primary);
padding: 11px 16px;
height: 48px;
border-radius: 0px;
border: none;
font-size: 14px;
font-weight: 400;
```
- Hover: `background: var(--color-surface)` on light; `background: var(--color-surface-elevated)` on dark

**Danger**
```css
background: var(--color-error);
color: #FFFFFF;
padding: 11px 16px;
height: 48px;
border-radius: 0px;
font-size: 14px;
font-weight: 400;
border: none;
```

**Button rules:** No rounded corners — 0px border-radius is the Carbon standard. No icon-only buttons without a visible label. Buttons are 48px height (large) or 32px height (small variant). Weight is always 400 — buttons do not shout.

### Navigation

- **UI Shell (Top bar):** `height: 48px`, `background: var(--color-canvas)`.
- Left: IBM 8-bar logo mark. Center/left-aligned: side navigation trigger + page title. Right: actions, user avatar.
- Nav links: 14px / 400 / 0px tracking, `var(--color-ink)`. Active: `var(--color-primary)`.
- **Side Navigation:** Fixed left panel, `width: 256px` (expanded) / `64px` (collapsed, icon-only). `background: var(--color-canvas)`. Items: 14px / 400, `height: 32px` per item, with 4px left border indicator for active.
- No hamburger icon on desktop. Below 768px: side nav collapses to icon-only or becomes a sheet.
- Header may use `border-bottom: 1px solid var(--color-hairline)` for subtle separation.

### Cards

- **Tile:** `background: var(--color-surface-elevated)`, `border-radius: 0px`, `padding: 16px` or `24px`. No box-shadow in default state.
- **Clickable Tile:** Same as Tile + `border: 1px solid var(--color-hairline)`. Hover: `background: var(--color-surface)` on light. Active: `border-color: var(--color-primary)`.
- **Selectable Tile:** Selected state shows `border: 2px solid var(--color-primary)`.
- **Expandable Tile:** Expands vertically with chevron icon. Divider: 1px `var(--color-hairline)`.
- No border-radius on cards. No decorative shadows. Depth is communicated through background color differentiation.

### Image Treatments

- Photography is secondary to content. IBM product UI prioritizes data and text.
- When used: `width: 100%`, `object-fit: cover`. No rounded corners on images.
- Aspect ratios: 16:9 for hero, 3:2 for feature cards, 1:1 for avatars.
- No decorative image borders. No visible frame elements.
- Overlay gradient for text legibility only: `linear-gradient(to top, rgba(22, 22, 22, 0.8) 0%, transparent 60%)`.
- The 8-bar stripe motif may appear as a thin decorative band (4px per bar, 2px gap) at section boundaries — never as a background pattern or fill.

### Data / Specs

- Data tables are the centerpiece of IBM product UI.
- Table header: 12px / 600 / `var(--color-muted)` — uppercase, `letter-spacing: 0.32px`.
- Table cell: 14px / 400 / `var(--color-ink)` — the productive body-01 default.
- Row height: 48px (standard) / 32px (compact).
- Alternating row backgrounds: `var(--color-canvas)` and `var(--color-surface)`.
- Sortable columns show arrow icon in header. Filterable columns show filter icon.
- No decorative borders. Dividers: 1px `var(--color-hairline)` between rows only.
- Status indicators use the color families: green-50 for success, red-60 for error, yellow-30 for warning — as small dot icons or inline tags, never as row background fills.

---

## 5. Layout Principles

### Grid — The IBM 2x Grid

Carbon's 2x Grid is a 16-column system at desktop with five breakpoints. Every dimension derives from the base 8px unit.

| Breakpoint | Min Width | Columns | Gutter | Margin |
|------------|-----------|---------|--------|--------|
| sm | 320px | 4 | 16px | 16px |
| md | 672px | 8 | 16px | 16px |
| lg | 1056px | 16 | 24px | 24px |
| xlg | 1312px | 16 | 24px | 24px |
| max | 1584px | 16 | 32px | 32px |

- **Max content width:** 1584px. Content is centered with margins absorbing remaining space.
- **16-column grid** at lg and above. 8-column at md. 4-column at sm.
- Column spans specified per breakpoint: `<Column sm={4} md={8} lg={16}>` for full-width content.
- Subgrid supported for nested layouts with alignment to parent columns.

### Spacing System

Base unit: **8px**. Every spacing token is a multiple of 8 or derived from the 2x/4x/8x progression.

| Token | Value | Usage |
|-------|-------|-------|
| `--space-01` | 2px | Tightest internal gaps, icon-to-label |
| `--space-02` | 4px | Icon gaps, chip internal padding, inline spacing |
| `--space-03` | 8px | Base unit — component internal padding, tight element gaps |
| `--space-04` | 12px | Small component padding, form field internal |
| `--space-05` | 16px | Standard component padding, gutter at sm/md breakpoints |
| `--space-06` | 24px | Section internal gaps, gutter at lg/xlg, card padding |
| `--space-07` | 32px | Sub-section gaps, margin between components |
| `--space-08` | 40px | Section spacing, larger component margins |
| `--space-09` | 48px | Major section breaks, page-level vertical rhythm |
| `--space-10` | 64px | Section padding (marketing pages) |
| `--space-11` | 80px | Large section padding |
| `--space-12` | 96px | Maximum section padding — editorial/landing pages |
| `--space-13` | 160px | Rare — page-level hero spacing only |

### Layout Spacing (Component-Level vs. Page-Level)

Carbon defines two spacing scales: the general spacing scale above (for within components) and a layout spacing scale for between components and sections. The layout scale uses the same tokens but is applied to margin and padding at the section level.

### Section Rhythm

- Product pages use `48px` (space-09) vertical section rhythm — compact and information-dense.
- Marketing pages use `80-96px` (space-11/12) vertical section rhythm — more breathing room.
- Between heading and body: `16px` (space-05).
- Between body and CTA: `24px` (space-06).
- Edge padding (mobile): `16px` (space-05).
- Edge padding (desktop): `24-32px` (space-06/07).

### Alignment

- Left-aligned is the default. Enterprise content is not centered.
- Data tables: left-aligned labels, right-aligned numeric values.
- Forms: left-aligned labels above inputs (not inline labels).
- Headlines: left-aligned in product UI. Center-aligned only in marketing hero sections.
- Navigation: left-aligned. Side navigation is the primary navigation pattern for product UI.

---

## 6. Depth & Elevation

Carbon's depth system is flat by conviction, using background color shifts instead of shadows for surface hierarchy. Where shadows are used, they are subtle and functional — not decorative.

### Surface Hierarchy

| Level | Light Treatment | Dark Treatment | Use Case |
|-------|----------------|----------------|----------|
| 0 | `var(--color-canvas)` — no shadow, no border | `var(--color-canvas)` — no shadow, no border | Page background, top bar, footer |
| 1 | `var(--color-surface)` — background shift only | `var(--color-surface)` — background shift only | Container panels, inset sections, table row alternation |
| 2 | `var(--color-surface-elevated)` — background shift | `var(--color-surface-elevated)` — background shift | Cards, tiles, modals — elevated surfaces on inset backgrounds |
| 3 | 1px `var(--color-hairline)` border | 1px `var(--color-hairline)` border | Clickable tiles, input fields, data table cells |
| 4 | `box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2)` | `box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4)` | Dropdowns, popovers, tooltips — transient floating elements only |
| 5 | `box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2)` | `box-shadow: 0 6px 16px rgba(0, 0, 0, 0.4)` | Modal dialogs — the only element that should cast a strong shadow |

### Layer Sets (Carbon's Layering Tokens)

Carbon defines layering tokens with numbered suffixes (-00, -01, -02, -03) that automatically adapt to the current theme:

| Layer | Light Background | Dark Background | Use Case |
|-------|-----------------|-----------------|----------|
| layer-00 | `#FFFFFF` | `#161616` | Base page, top-level container |
| layer-01 | `#F4F4F4` | `#262626` | Raised section, inset panel |
| layer-02 | `#FFFFFF` | `#393939` | Card on inset panel |
| layer-03 | `#F4F4F4` | `#525252` | Nested element on card |

### Overlay

- Light overlay: `rgba(22, 22, 22, 0.5)` — for loading spinners and gentle content fade
- Dark overlay: `rgba(22, 22, 22, 0.85)` — for modal dialogs and focused interactions

### Brand Signature Depth

- **8-Bar Stripe Motif:** 8 horizontal bars, each 4px tall with 2px gap between. Used only as a section divider or as a thin decorative accent at the top of a page/section. Colors: all bars in `var(--color-primary)` (IBM Blue) for brand contexts, or `var(--color-ink)` for neutral contexts. Never as a fill pattern, never as a background texture, never animated.

---

## 7. Do's and Don'ts

**Do:**

- Use IBM Blue (`#0F62FE`) as the single primary interactive color — it carries every CTA, link, and active element
- Set productive body at 14px — information density is a virtue in enterprise UI
- Use weight 400 (Regular) for most text — IBM trusts size and spacing for hierarchy, not weight
- Use the gray scale systematically — gray-100 for light text, gray-10 for dark text, gray-30 for borders, gray-80 for dark borders
- Let background color shifts communicate surface hierarchy instead of shadows
- Use IBM Plex Sans as the sole typeface — it is designed for this system
- Use the Carbon spacing tokens (space-01 through space-13) for all spacing decisions
- Use left-alignment as the default — enterprise content is not centered
- Support dark mode as a first-class citizen — Carbon provides g90 and g100 theme tokens for a reason
- Use the full 12-color family palette for data visualization charts and status indicators
- Use 0px border-radius for buttons and cards — the Carbon standard
- Use the 8-bar stripe motif as a controlled signature accent, not as wallpaper

**Don't:**

- Do not use blue-60 (`#0F62FE`) for decoration — it is reserved for interactive elements and primary actions only
- Do not add rounded corners to buttons, cards, or inputs — 0px radius is the Carbon identity
- Do not use decorative drop shadows on cards or static elements — shadows are for transient floating elements only
- Do not use weight 700 (Bold) for headings in productive UI — Carbon uses weight 400/600, not 700
- Do not set body text at 16px in product UI — 14px is the enterprise standard; 16px is for marketing only
- Do not use pure black (`#000000`) for dark backgrounds — gray-100 (`#161616`) is the darkest Carbon surface
- Do not center-align body text, form labels, or table content — left-alignment is the enterprise default
- Do not use more than two type sets on a single page — choose Productive or Expressive, do not mix
- Do not use the color families (red, green, yellow, etc.) for decoration — they are for status and data visualization
- Do not use italic for emphasis in product UI — use weight 600 or size change instead
- Do not use negative letter-spacing on body text — 0 to 0.32px tracking only
- Do not use the 8-bar motif as a background pattern or fill — it is a section divider and accent only
- Do not design without considering data density — IBM surfaces are information-rich by default

---

## 8. Responsive Behavior

### Breakpoints

| Name | Min Width | Columns | Gutter | Margin | Behavior |
|------|-----------|---------|--------|--------|----------|
| sm | 320px | 4 | 16px | 16px | Single column stacked. Side nav collapses to icon-only or sheet. Data tables scroll horizontally. Hero headline reduces to 36px (expressive). Productive headings unchanged. Footer 4-col to 1-col. |
| md | 672px | 8 | 16px | 16px | Two-column layouts possible. Side nav icon-only. Data tables remain scrollable. Hero headline 48px (expressive). Cards 2-up. |
| lg | 1056px | 16 | 24px | 24px | Full 16-column grid. Expanded side navigation (256px). Full data tables. Hero headline 64px (expressive). Cards 3-up or 4-up. |
| xlg | 1312px | 16 | 24px | 24px | Wider gutters. More sidebar content visible. Dashboard layouts reach full density. |
| max | 1584px | 16 | 32px | 32px | Maximum content width. Gutters and margins absorb remaining space. No content stretching beyond 1584px. |

### Mobile-Specific Rules

- Productive body text stays at 14px across all breakpoints — do not enlarge for mobile
- Data tables scroll horizontally on mobile with sticky first column — never restructure into card layouts
- Side navigation collapses to icon-only (64px) or becomes a full-screen sheet on mobile
- Touch targets: minimum 44x44px (WCAG AAA)
- Button height: 48px standard, 32px small — same as desktop
- Form inputs: 40px height (standard), with 48px touch target area via padding
- Expressive display type scales down: display-03 from 64px to 36px at sm breakpoint
- Productive headings do not scale — they are fixed sizes regardless of breakpoint
- Cards stack to single column at sm, 2-up at md
- Modal dialogs become full-screen sheets at sm breakpoint
- Pagination converts to "load more" pattern on mobile

### Content Behavior

- Side navigation width: 256px (expanded) / 64px (collapsed). Collapsed state shows icons only with tooltip on hover.
- Data tables: sticky header, sticky first column on mobile. Horizontal scroll with fade indicator.
- Forms: single-column layout on mobile. Two-column at md+. Three-column at lg+ for dense admin forms.
- Footer: 4-column at lg, 2-column at md, 1-column at sm with accordion sections.

### Dark Mode Switching

Carbon supports four themes. Use `prefers-color-scheme` media query for automatic switching; always provide a manual toggle in the UI Shell. All color tokens swap simultaneously through the theme layer — no partial theme application. The layer tokens (layer-00 through layer-03) automatically invert, so nested surface hierarchy is preserved in both modes. Transition between modes should be instant (no animation on color swap — enterprise users value predictability over delight).
