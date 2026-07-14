# Shopify Design System

## 1. Visual Theme & Atmosphere

Shopify's design language is **dark-first and cinematic**. The interface feels like a control center for commerce: deep dark surfaces, razor-sharp typography at ultra-light weights, and a neon green accent that cuts through like a terminal cursor. Photography is dramatic and moody. Products and merchants are cast in high-contrast, studio-lit scenes. The overall impression is a platform that means business -- modern, powerful, and unapologetically commercial.

**Core qualities:**
- Dark surfaces dominate; light mode exists but feels secondary
- Ultra-light font weights (300, even 200) for display headlines -- airy, not heavy
- Neon green (#008060) as surgical accent; never decorative, always functional
- Cinematic photography with deep shadows and dramatic lighting
- Generous negative space on dark surfaces creates depth without elevation hacks
- Surfaces are matte and flat; depth comes from background color layering, not shadows
- Micro-interactions are quick and responsive (150ms-200ms); the platform feels fast
- E-commerce data density is handled through clear hierarchy, not visual noise

**Atmosphere keywords:** dark-commerce, neon-green, cinematic, ultra-light type, platform-power, merchant-centric, terminal-sharp

**Design personality:** The commerce platform that treats your store like a mission-critical dashboard. Confident, efficient, with just enough visual drama to feel premium.

---

## 2. Color Palette & Roles

### Dark Mode (Primary)

| Token | Hex | Role |
|-------|-----|------|
| `--color-bg` | `#0B1215` | Deepest background; canvas behind all surfaces |
| `--color-surface` | `#111820` | Primary surface; panels, sidebar, main content |
| `--color-surface-elevated` | `#1A232B` | Elevated surface; cards, dropdowns |
| `--color-surface-overlay` | `#222D38` | Overlay surface; modals, popovers |
| `--color-surface-hover` | `#1E2A35` | Hover state fill on interactive surfaces |
| `--color-text-primary` | `#E3E8EB` | Headlines, body copy, primary labels |
| `--color-text-secondary` | `#8B9DA7` | Descriptions, captions, secondary info |
| `--color-text-tertiary` | `#5C6F7A` | Disabled text, placeholders, metadata |
| `--color-text-inverse` | `#FFFFFF` | Text on accent backgrounds |
| `--color-accent` | `#008060` | Primary accent; CTAs, active states, links, focus rings |
| `--color-accent-hover` | `#009A73` | Accent hover state |
| `--color-accent-active` | `#006B4F` | Accent pressed/active state |
| `--color-accent-subtle` | `rgba(0, 128, 96, 0.12)` | Ghost accent; selected rows, hover tints |
| `--color-accent-glow` | `rgba(0, 128, 96, 0.25)` | Glow ring for focus states |
| `--color-separator` | `#1E2A35` | Borders between sections and panels |
| `--color-separator-subtle` | `#162029` | Hairline dividers within a surface |
| `--color-success` | `#008060` | Completed states (shares accent green) |
| `--color-success-surface` | `rgba(0, 128, 96, 0.10)` | Success background tints |
| `--color-warning` | `#FFC453` | Caution, pending, attention required |
| `--color-warning-surface` | `rgba(255, 196, 83, 0.10)` | Warning background tints |
| `--color-error` | `#E43E3E` | Errors, destructive actions, validation failures |
| `--color-error-surface` | `rgba(228, 62, 62, 0.10)` | Error background tints |
| `--color-info` | `#5BA4CF` | Informational badges, neutral highlights |
| `--color-info-surface` | `rgba(91, 164, 207, 0.10)` | Info background tints |

### Light Mode

| Token | Hex | Role |
|-------|-----|------|
| `--color-bg` | `#F6F7F8` | Page background |
| `--color-surface` | `#FFFFFF` | Card / section fill |
| `--color-surface-elevated` | `#FFFFFF` | Elevated cards, modals |
| `--color-surface-hover` | `#F1F2F3` | Hover state fill |
| `--color-text-primary` | `#1A1F25` | Headlines, body copy |
| `--color-text-secondary` | `#637381` | Captions, descriptions |
| `--color-text-tertiary` | `#919BA3` | Disabled, placeholders |
| `--color-text-inverse` | `#FFFFFF` | Text on accent backgrounds |
| `--color-accent` | `#008060` | Primary accent (same as dark) |
| `--color-accent-hover` | `#006B4F` | Accent hover (darker on light bg) |
| `--color-accent-active` | `#005A42` | Accent pressed |
| `--color-accent-subtle` | `rgba(0, 128, 96, 0.08)` | Ghost accent tint |
| `--color-separator` | `#E1E3E5` | Borders, dividers |
| `--color-separator-subtle` | `#F1F2F3` | Hairline separators |
| `--color-success` | `#008060` | Same as accent |
| `--color-warning` | `#D4860A` | Darker warning for light bg |
| `--color-error` | `#D72B2B` | Darker error for light bg |
| `--color-info` | `#2E6EA6` | Darker info for light bg |

### Brand Extension Colors

| Name | Hex | Usage |
|------|-----|-------|
| Shopify Green | `#008060` | Primary brand; identical to accent |
| Shopify Green Light | `#95D7B2` | Decorative only; illustrations, data viz |
| Shopify Green Dark | `#004E3A` | Pressed states, deep emphasis |
| Polar Night 1 | `#0B1215` | Darkest dark surface |
| Polar Night 2 | `#111820` | Standard dark surface |
| Snow Storm | `#E3E8EB` | Lightest text on dark |

---

## 3. Typography Rules

**Font stack:** `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`

**Display font (hero only):** Same stack at weight 200-300 for that ultra-light, cinematic feel.

**Monospace:** `"SF Mono", "Fira Code", Menlo, Consolas, monospace`

### Type Scale

| Token | Size | Weight | Tracking | Line-height | Usage |
|-------|------|--------|----------|-------------|-------|
| `--text-hero` | `clamp(2.75rem, 5vw + 0.5rem, 4.5rem)` | 300 (light) | -0.025em | 1.1 | Hero headlines, splash sections |
| `--text-headline-lg` | `clamp(2rem, 3vw + 0.5rem, 2.5rem)` | 300 | -0.02em | 1.15 | Section headlines, feature titles |
| `--text-headline` | `clamp(1.5rem, 1.5vw + 0.5rem, 1.75rem)` | 400 | -0.015em | 1.2 | Sub-section headlines |
| `--text-title` | `1.125rem` (18px) | 500 | -0.01em | 1.3 | Card titles, modal headers |
| `--text-subtitle` | `1rem` (16px) | 500 | 0 | 1.4 | Subtitles, emphasis body |
| `--text-body` | `0.875rem` (14px) | 400 | 0 | 1.5 | Default body text |
| `--text-body-sm` | `0.8125rem` (13px) | 400 | 0.01em | 1.5 | Compact body, table cells |
| `--text-caption` | `0.75rem` (12px) | 400 | 0.02em | 1.4 | Captions, metadata, timestamps |
| `--text-overline` | `0.6875rem` (11px) | 600 | 0.06em | 1.3 | Labels, overlines (UPPERCASE) |
| `--text-data` | `1.5rem` (24px) | 500 | -0.01em | 1.2 | Dashboard metrics, big numbers |

### Rules

- Hero and headline text uses weight 300 (light) for the signature airy look. Never use 200 except on oversized display type (64px+).
- Body text is always 400 regular. Never use 300 for body copy -- it becomes illegible at small sizes.
- Tracking tightens progressively as size increases (hero: -0.025em, body: 0).
- Maximum measure (line width): `640px` for readable body text.
- Dashboard metric numbers use `--text-data` with tabular-nums font-feature for aligned columns.
- Labels and overlines are always uppercase with wide tracking.
- Never use italic for UI text. Reserve italic for long-form editorial content only.

---

## 4. Component Stylings

### Buttons

**Primary (Accent Green)**
```css
background: var(--color-accent);
color: var(--color-text-inverse);
padding: 8px 20px;
border-radius: 8px;
font-size: 0.875rem;
font-weight: 500;
letter-spacing: 0;
border: none;
cursor: pointer;
transition: background 150ms ease, box-shadow 150ms ease;
```
- Hover: `var(--color-accent-hover)`
- Active: `var(--color-accent-active)` + `scale(0.98)`
- Focus: `box-shadow: 0 0 0 2px var(--color-accent-glow)`
- Disabled: `opacity: 0.4`, no pointer events
- Loading: text replaced by 16px spinner in `var(--color-text-inverse)`

**Secondary (Outlined)**
```css
background: transparent;
color: var(--color-text-primary);
padding: 8px 20px;
border-radius: 8px;
font-size: 0.875rem;
font-weight: 500;
border: 1px solid var(--color-separator);
```
- Hover: `background: var(--color-surface-hover)`, border lightens
- Active: `background: var(--color-surface-elevated)`
- Focus: `box-shadow: 0 0 0 2px var(--color-accent-glow)`

**Tertiary (Ghost)**
```css
background: transparent;
color: var(--color-text-secondary);
padding: 8px 12px;
border-radius: 8px;
font-size: 0.875rem;
font-weight: 400;
border: none;
```
- Hover: `background: var(--color-surface-hover)`, text becomes `--color-text-primary`

**Destructive**
```css
background: var(--color-error);
color: var(--color-text-inverse);
/* same shape/size as primary */
```
- Hover: `#C93232`
- Secondary destructive: outline style with `--color-error` text and border

**Large CTA (Hero)**
```css
padding: 12px 28px;
font-size: 1rem;
font-weight: 500;
border-radius: 10px;
```

**Icon Button**
- `32px x 32px` square, `border-radius: 8px`
- Icon: `16px`, color `--color-text-secondary`
- Hover: `background: var(--color-surface-hover)`

### Cards

```css
background: var(--color-surface-elevated);
border-radius: 12px;
padding: 20px;
border: 1px solid var(--color-separator);
box-shadow: none;
```
- Hover (interactive cards): `border-color: var(--color-accent)` at 30% opacity
- Selected: `border-color: var(--color-accent)`, `background: var(--color-accent-subtle)`
- Metric cards: large number (`--text-data`) top-left, label (`--text-caption`) below, sparkline or delta right
- Product cards: image top with `border-radius: 8px`, title in `--text-body` weight 500, price in `--text-body-sm` `--color-text-secondary`
- No box-shadow on default state cards

### Inputs

**Text Input**
```css
background: var(--color-surface);
border: 1px solid var(--color-separator);
border-radius: 8px;
padding: 8px 12px;
font-size: 0.875rem;
color: var(--color-text-primary);
outline: none;
transition: border-color 150ms ease, box-shadow 150ms ease;
```
- Focus: `border-color: var(--color-accent)` + `box-shadow: 0 0 0 2px var(--color-accent-glow)`
- Placeholder: `var(--color-text-tertiary)`
- Error: `border-color: var(--color-error)`, error message in `--color-error` at 12px below
- Disabled: `opacity: 0.5`, `cursor: not-allowed`
- Prefix/suffix slots: icon or text in `--color-text-tertiary` inside input with `border-left`/`border-right` separator

**Search Input**
```css
border-radius: 980px; /* pill shape */
padding: 8px 12px 8px 36px; /* room for magnifier icon */
```

**Select / Dropdown**
- Same base styling as text input
- Dropdown panel: `--color-surface-overlay` background, `8px` border-radius, `1px` border `--color-separator`
- Dropdown shadow: `0 8px 24px rgba(0, 0, 0, 0.4)`
- Selected item: `--color-accent-subtle` background, `--color-accent` text
- Hover item: `--color-surface-hover` background

### Navigation

**Sidebar**
- Background: `--color-surface` (`#111820`)
- Width: `240px` (collapsible to `56px` icon-only mode)
- Border-right: `1px solid var(--color-separator)`
- Item height: `36px`
- Item padding: `0 12px`
- Item border-radius: `8px`
- Item text: `--color-text-secondary`, 14px, weight 400
- Active item: background `--color-accent-subtle`, text `--color-accent`, weight 500
- Hover item: background `--color-surface-hover`, text `--color-text-primary`
- Group labels: `--color-text-tertiary`, 11px, weight 600, `0.06em` letter-spacing, uppercase
- Shopify logo: 28px mark in `--color-accent` at top, app name in `--text-subtitle` weight 500

**Top Bar / Command Bar**
- Background: `--color-surface` with `border-bottom: 1px solid var(--color-separator)`
- Height: `56px`
- Search bar centered: pill-shaped input, `--color-text-tertiary` placeholder "Search your store..."
- Breadcrumbs: `--color-text-secondary`, 14px, separated by chevron in `--color-text-tertiary`
- Action buttons aligned right

### Badges / Status Tags

- Border-radius: `980px` (pill shape)
- Padding: `2px 8px`
- Font: 12px, weight 500
- Variants:
  - Default: `--color-surface-hover` background, `--color-text-secondary` text
  - Success: `--color-success-surface` background, `--color-success` text
  - Warning: `--color-warning-surface` background, `--color-warning` text
  - Error: `--color-error-surface` background, `--color-error` text
  - Info: `--color-info-surface` background, `--color-info` text

### Data Table

- Header row: `--color-surface-hover` background, `--text-overline` style labels, sticky on scroll
- Row height: `48px`
- Cell text: `--text-body-sm` (13px)
- Row hover: `--color-surface-hover` background
- Row selected: `--color-accent-subtle` background
- Zebra striping: not used; hover state is sufficient
- Column borders: none; horizontal separators only (`1px solid var(--color-separator-subtle)`)

---

## 5. Layout Principles

### Spacing Scale

| Token | Value | Usage |
|-------|-------|-------|
| `--space-1` | `4px` | Tight inline gaps, icon-to-label |
| `--space-2` | `8px` | Between related items, compact padding |
| `--space-3` | `12px` | Between form fields, list items |
| `--space-4` | `16px` | Section padding, card inner gaps |
| `--space-5` | `20px` | Card padding, comfortable spacing |
| `--space-6` | `24px` | Major section separation |
| `--space-8` | `32px` | Page-level vertical rhythm |
| `--space-10` | `40px` | Section dividers |
| `--space-12` | `48px` | Hero-level spacing |
| `--space-16` | `64px` | Maximum section gap |

### Grid

- Content max-width: `1200px`
- Sidebar + main layout: sidebar `240px` fixed, main fills remaining
- Admin content max-width within main: `960px` for readability
- Gutter: `16px` between columns
- Card grid: 3 columns at >= 1200px, 2 at >= 768px, 1 below
- Grid gap: `16px`

### Whitespace Philosophy

- The dark surface does the work of separation; excessive whitespace is unnecessary
- Section padding: `32px` to `48px` vertical (compact efficiency over luxury breathing)
- Between headline and body: `8px` to `12px` (tight rhythm)
- Between body and CTA: `16px` to `20px`
- Between sibling cards: `16px`
- Edge padding (mobile): `16px`
- Edge padding (desktop): `24px` to `32px`
- Content never touches viewport edges

### Content Rhythm

1. **Hero section**: Dark cinematic background with product photography or platform illustration. Ultra-light headline (weight 300) + short subtitle + green CTA. Content left-aligned, not centered.
2. **Feature sections**: Stacked or alternating layout. Headline at `--text-headline` + body + optional illustration. Compact vertical rhythm.
3. **Dashboard sections**: Metric cards in a row, then a data table or chart. Dense but legible.
4. **CTA section**: Often on slightly lighter dark surface. Bold headline, single green button.

---

## 6. Depth & Elevation

Shopify conveys depth through **background color layering**, not shadows. The darkest surface is the canvas; each step up in elevation is a slightly lighter dark.

### Elevation Levels (Dark Mode)

| Level | Background | Border | Shadow | Usage |
|-------|------------|--------|--------|-------|
| 0 (canvas) | `#0B1215` | none | none | Root background |
| 1 (surface) | `#111820` | `1px solid #1E2A35` | none | Panels, sidebar, main content |
| 2 (raised) | `#1A232B` | `1px solid #1E2A35` | none | Cards, list items, sections |
| 3 (overlay) | `#222D38` | `1px solid #2A3845` | `0 4px 16px rgba(0,0,0,0.3)` | Dropdowns, popovers |
| 4 (floating) | `#2A3845` | `1px solid #334555` | `0 8px 32px rgba(0,0,0,0.4)` | Modals, command palette |

### Accent Glow

The neon green accent produces a subtle glow when focused or highlighted, reinforcing the "terminal cursor" feel:

- Focus ring: `box-shadow: 0 0 0 2px rgba(0, 128, 96, 0.25)`
- Active CTA glow (hero only): `box-shadow: 0 0 20px rgba(0, 128, 96, 0.2)`
- Never use glow on resting-state cards, badges, or navigation items

### Overlay

- Modal backdrop: `rgba(0, 0, 0, 0.6)` with `backdrop-filter: blur(4px)`
- Toast notifications: surface-level 3, fixed at bottom-right, stacked with `8px` gap

### Border Radius Scale

| Token | Value | Usage |
|-------|-------|-------|
| `--radius-sm` | `4px` | Small badges, inline tags |
| `--radius-md` | `8px` | Buttons, inputs, nav items |
| `--radius-lg` | `12px` | Cards, modal containers |
| `--radius-xl` | `16px` | Large feature cards, image containers |
| `--radius-pill` | `980px` | Search bar, status badges, pills |

---

## 7. Do's and Don'ts

### Do

- Use weight 300 for hero and section headlines -- this is the signature Shopify look
- Use `--color-accent` (#008060) for interactive elements only: buttons, links, active states, focus rings
- Keep surfaces matte and flat. Background color shifts convey elevation more cleanly than shadows.
- Use `--color-accent-subtle` for selected/hover tints -- it provides context without visual noise.
- Use tabular-nums for dashboard metrics and price columns to maintain alignment.
- Use 14px as the default body size. Shopify is a dense admin interface; 16px body is too large for data-rich surfaces.
- Animate with `150ms ease` for interactive state changes. Speed signals efficiency.
- Use monospace font for order IDs, discount codes, and API keys.
- Pair the ultra-light headline with a regular-weight subtitle for maximum contrast.
- Use dark mode as the primary design target; light mode is the variant, not the other way around.
- Use full-bleed cinematic photography in marketing/hero sections, but keep admin UI photography contained and purposeful.
- Use 1px borders. Never 2px or 3px except for focus rings.

### Don't

- Do not use `--color-accent` for decorative elements like dividers, background fills, or icons that aren't interactive.
- Do not use gradients on text. Ever.
- Do not use weight 200 below 48px -- it becomes illegible.
- Do not use weight 700 (bold). 600 is the maximum, reserved for labels and small caps only.
- Do not add box-shadows to resting-state cards or list items. Shadows are reserved for overlays and popovers only.
- Do not use rounded corners greater than `12px` on rectangular content cards. No `20px` or `24px` radius cards.
- Do not center-align paragraphs, form layouts, or dashboard content. Left-align everything.
- Do not use zebra striping in tables. Row hover is sufficient.
- Do not animate `width`, `height`, `top`, `left`, or `margin`. Use `transform` and `opacity` only.
- Do not use color alone to convey status. Pair with text labels or icons (e.g., green dot + "Active").
- Do not use decorative gradients on card backgrounds. Subtle radial glows in hero sections are the only exception.
- Do not use emoji in navigation labels, button text, or status indicators.
- Do not mix light and dark surfaces in the same view without clear visual separation (border or spacing).

---

## 8. Responsive Behavior

### Breakpoints

| Name | Min Width | Layout Behavior |
|------|-----------|-----------------|
| `mobile` | `0` | Single column, sidebar hidden (hamburger), stacked cards, bottom sheet modals |
| `tablet` | `768px` | Optional sidebar, 2-column card grid, side-by-side forms |
| `desktop` | `1024px` | Full sidebar visible, 2-3 column grid, standard modal overlays |
| `wide` | `1200px` | Maximum content width enforced, 3-column card grid |

### Adaptation Rules

- **Sidebar**: Hidden below `1024px`, replaced by hamburger menu overlay. Overlay slides in from left (`transform: translateX`, 200ms ease) with `--color-surface` background.
- **Navigation items**: Text + icon on desktop; icon-only below `768px` if sidebar is collapsed.
- **Cards**: Full-width below `768px`, 2-up at `768px+`, 3-up at `1200px+`.
- **Top bar**: Search bar collapses to icon-only below `768px`. Title truncates with ellipsis.
- **Data tables**: Convert to stacked card list on mobile. Each row becomes a card with label-value pairs. Critical columns (status, amount) remain visible as compact rows.
- **Forms**: Single column always. Top-aligned labels. Full-width inputs on mobile, max `480px` on desktop.
- **Modals**: Full-screen on mobile (with safe-area padding), centered overlay on desktop.
- **Dashboard metrics**: Stack vertically on mobile, horizontal row on desktop.
- **Font sizes**: Reduce hero from fluid scale to `2rem` (32px) below `768px`. Body text stays `14px` at all sizes -- never scale body down on mobile.

### Spacing Scale (Mobile vs Desktop)

| Context | Mobile | Desktop |
|---------|--------|---------|
| Section vertical padding | `24px` | `32px` to `48px` |
| Card padding | `16px` | `20px` |
| Edge margin | `16px` | `24px` to `32px` |
| Between-section gap | `24px` | `32px` to `48px` |
| Card grid gap | `12px` | `16px` |
| Sidebar width | hidden | `240px` |

### Touch Targets

- Minimum `44px x 44px` on mobile for all interactive elements
- Tap targets separated by at least `8px`
- Buttons on mobile: full-width or minimum `120px` wide

### Dark Mode Handling

Dark mode is the default. Use `prefers-color-scheme: light` to activate the light variant. All color tokens swap simultaneously. Transition between modes should be instant (no animation on color swap). Product imagery may remain the same between modes -- only UI surfaces swap.
