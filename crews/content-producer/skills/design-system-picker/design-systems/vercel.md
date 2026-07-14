# Vercel Design System

## 1. Visual Theme & Atmosphere

Black and white precision. Every pixel is deliberate. The Vercel aesthetic communicates engineering rigor through extreme restraint -- no gradients on surfaces, no decorative illustration, no ornament. Information density is high but never cluttered because the typographic hierarchy is surgical.

The signature element is the **blueprint grid** -- a barely-visible line or dot matrix pattern (5-10% opacity) that signals systematic thinking. It decorates hero sections and feature showcases, never competing with content.

Atmospheric keywords: monochrome, precise, developer-tool, systematic, engineered, minimal-accent, high-contrast dark mode default.

**Primary mode: Dark.** Light mode exists but dark is canonical. All color values below list dark first.

---

## 2. Color Palette & Roles

### Dark Mode (default)

| Token | Hex | Role |
|-------|-----|------|
| `background-1` | `#000000` | Page and primary surface background |
| `background-2` | `#171717` | Secondary surface differentiation (use sparingly) |
| `color-1` | `#0A0A0A` | Component default background |
| `color-2` | `#111111` | Component hover background |
| `color-3` | `#1A1A1A` | Component active / pressed background; badge background |
| `color-4` | `#1A1A1A` | Default border |
| `color-5` | `#222222` | Hover border |
| `color-6` | `#2E2E2E` | Active / focus border |
| `color-7` | `#FAFAFA` | High-contrast background (primary buttons, inverted surfaces) |
| `color-8` | `#E5E5E5` | Hover state for high-contrast background |
| `color-9` | `#A1A1A1` | Secondary text and icons |
| `color-10` | `#EDEDED` | Primary text and icons |
| `blue-500` | `#0070F3` | Accent / link color (used minimally) |
| `red-500` | `#EE0000` | Error / destructive |
| `green-500` | `#00C853` | Success / online status |
| `amber-500` | `#F5A623` | Warning |

### Light Mode

| Token | Hex | Role |
|-------|-----|------|
| `background-1` | `#FFFFFF` | Page background |
| `background-2` | `#FAFAFA` | Secondary surface |
| `color-1` | `#F5F5F5` | Component default background |
| `color-2` | `#E5E5E5` | Component hover background |
| `color-3` | `#D4D4D4` | Component active background |
| `color-4` | `#E5E5E5` | Default border |
| `color-5` | `#D4D4D4` | Hover border |
| `color-6` | `#A3A3A3` | Active border |
| `color-7` | `#171717` | High-contrast background |
| `color-8` | `#0A0A0A` | Hover high-contrast background |
| `color-9` | `#737373` | Secondary text and icons |
| `color-10` | `#171717` | Primary text and icons |

### Accent Usage Rule

Accent blue (`#0070F3`) appears only on interactive text links, focus rings, and selected states. Never as a surface fill. The palette is 95% neutral; color is a signal, not decoration.

---

## 3. Typography Rules

**Font families:**
- `Geist Sans` -- all UI text, headings, body, labels, buttons
- `Geist Mono` -- code, monospace labels, inline code mentions

**Font loading:** `font-family: 'Geist Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`

### Heading Scale

| Style | Size | Weight | Letter-spacing | Usage |
|-------|------|--------|---------------|-------|
| Heading 72 | 72px | 600 | -2.88px | Marketing heroes only |
| Heading 64 | 64px | 600 | -2.56px | Marketing heroes |
| Heading 56 | 56px | 600 | -3.36px | Marketing heroes |
| Heading 48 | 48px | 600 | -1.92px | Section heroes |
| Heading 40 | 40px | 600 | -1.60px | Section heroes |
| Heading 32 | 32px | 600 | -1.28px | Dashboard headings, marketing subheadings |
| Heading 24 | 24px | 600 | -0.96px | Card titles, section labels |
| Heading 20 | 20px | 600 | -0.40px | Small section headings |
| Heading 16 | 16px | 600 | -0.32px | Compact headings |
| Heading 14 | 14px | 600 | -0.28px | Micro headings |

All headings use `Geist Sans`. The aggressive negative letter-spacing at large sizes is critical to the Vercel look -- do not omit it.

### Button Scale

| Style | Size | Weight | Letter-spacing | Usage |
|-------|------|--------|---------------|-------|
| Button 16 | 16px | 500 | 0 | Largest CTA buttons |
| Button 14 | 14px | 500 | 0 | Default button |
| Button 12 | 12px | 500 | 0 | Tiny buttons inside input fields |

### Label Scale

| Style | Size | Weight | Letter-spacing | Usage |
|-------|------|--------|---------------|-------|
| Label 20 | 20px | 400 | 0 | Marketing text |
| Label 18 | 18px | 400 | 0 | Navigation items |
| Label 16 | 16px | 500 (strong) | 0 | Titles, differentiating from body |
| Label 14 | 14px | 500 (strong) | 0 | Most common; menus, list items |
| Label 14 Mono | 14px | 500 | 0 | Largest mono, pairs with >14 text |
| Label 13 | 13px | 400 | tabular | Secondary line next to labels; numbers |
| Label 13 Mono | 13px | 400 | 0 | Pairs with Label 14 |
| Label 12 | 12px | 500 (strong) | 0 | Tertiary text, caps (e.g. section headers) |
| Label 12 Mono | 12px | 400 | 0 | Smallest mono |

### Copy Scale

| Style | Size | Weight | Line-height | Usage |
|-------|------|--------|------------|-------|
| Copy 24 | 24px | 400 | 1.5 | Hero marketing body |
| Copy 20 | 20px | 400 | 1.5 | Hero marketing body |
| Copy 18 | 18px | 400 | 1.55 | Big quotes, feature descriptions |
| Copy 16 | 16px | 400 | 1.5 | Modals, spacious views |
| Copy 14 | 14px | 400 | 1.5 | Default body text (most common) |
| Copy 13 | 13px | 400 | 1.5 | Secondary text, space-constrained views |
| Copy 13 Mono | 13px | 400 | 1.5 | Inline code mentions |

---

## 4. Component Stylings

### Buttons

**Primary (high-contrast):**
```css
background: var(--color-7);   /* #FAFAFA dark / #171717 light */
color: var(--background-1);   /* #000000 dark / #FFFFFF light */
border: none;
border-radius: 8px;
padding: 8px 16px;
font: 500 14px / 1 'Geist Sans';
```
- Hover: `background: var(--color-8)` (`#E5E5E5` dark / `#0A0A0A` light)
- Active: `transform: scale(0.98)` (subtle press)
- Focus: `outline: 2px solid var(--blue-500); outline-offset: 2px`

**Secondary (ghost):**
```css
background: transparent;
color: var(--color-10);
border: 1px solid var(--color-5);
border-radius: 8px;
padding: 8px 16px;
font: 500 14px / 1 'Geist Sans';
```
- Hover: `background: var(--color-1)`; `border-color: var(--color-5)`
- Active: `background: var(--color-2)`

**Tertiary (link-button):**
```css
background: none;
color: var(--color-9);
border: none;
padding: 0;
font: 500 14px / 1 'Geist Sans';
text-decoration: underline;
text-underline-offset: 2px;
```
- Hover: `color: var(--color-10)`

### Cards

```css
background: var(--color-1);
border: 1px solid var(--color-4);
border-radius: 12px;
padding: 24px;
```
- Hover: `border-color: var(--color-5)` (no shadow shift, just border)
- Interactive card hover: subtle `border-color: var(--color-6)` + `background: var(--color-2)`

No box-shadow on cards at rest. Elevation is communicated through border brightness, not shadow.

### Inputs

```css
background: var(--background-1);
border: 1px solid var(--color-4);
border-radius: 8px;
padding: 8px 12px;
font: 400 14px / 1.5 'Geist Sans';
color: var(--color-10);
```
- Placeholder: `color: var(--color-9)`
- Hover: `border-color: var(--color-5)`
- Focus: `border-color: var(--color-6)`; `box-shadow: 0 0 0 1px var(--color-6)`
- Error: `border-color: var(--red-500)`
- Disabled: `opacity: 0.4`; `cursor: not-allowed`

### Navigation Bar

```css
background: var(--background-1);
border-bottom: 1px solid var(--color-4);
height: 64px;
padding: 0 24px;
```
- Nav items: `Label 14`, `color: var(--color-9)`, no underline
- Active item: `color: var(--color-10)`, `font-weight: 500`
- Hover: `color: var(--color-10)`
- Top nav is sticky, transparent until scroll then `background: var(--background-1)` with `backdrop-filter: blur(12px)` and `opacity: 0.9`

### Badges / Status Indicators

```css
background: var(--color-2);
color: var(--color-9);
border-radius: 9999px;  /* pill shape */
padding: 2px 8px;
font: 500 12px / 1 'Geist Sans';
letter-spacing: 0.02em;
```
- Variant: `Label 12` in ALL CAPS for section headers

### Toggle / Switch

```css
/* Track */
width: 40px; height: 22px;
background: var(--color-3);
border: 1px solid var(--color-5);
border-radius: 9999px;
transition: background 150ms ease;

/* Thumb */
width: 16px; height: 16px;
background: var(--color-10);
border-radius: 50%;
/* Off: translateX(2px) */
/* On: translateX(20px), track background: var(--blue-500) */
```

---

## 5. Layout Principles

### Spacing Scale (4px base unit)

| Token | Value | Usage |
|-------|-------|-------|
| `space-1` | 4px | Tight gaps (icon-to-text) |
| `space-2` | 8px | Component internal padding |
| `space-3` | 12px | Input padding, small gaps |
| `space-4` | 16px | Default component padding |
| `space-5` | 20px | Section internal spacing |
| `space-6` | 24px | Card padding, nav padding |
| `space-7` | 32px | Between related sections |
| `space-8` | 40px | Section separators |
| `space-9` | 48px | Large section gaps |
| `space-10` | 64px | Page-level vertical rhythm |
| `space-11` | 80px | Hero internal spacing |
| `space-12` | 96px | Major section dividers |

### Grid

- Max content width: `1200px` (centered, auto margins)
- Marketing hero width: `1440px`
- Column count: 12
- Gutter: `24px` (desktop), `16px` (tablet), `8px` (mobile)
- Page margin: `24px` (desktop), `16px` (mobile)

### Whitespace Philosophy

Whitespace is the primary tool for grouping. Vercel uses generous vertical spacing between sections (64-96px) and tight internal padding within components (8-16px). This creates a strong rhythm: dense functional clusters separated by wide breathing room.

- Related elements: 4-8px apart
- Unrelated peer elements: 16-24px apart
- Section breaks: 64-96px apart
- Never use decorative dividers; spacing alone separates

### Blueprint Grid (decorative)

For hero sections and feature showcases:
```css
/* Line grid */
background-image:
  linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px),
  linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px);
background-size: 64px 64px;

/* Dot matrix */
background-image: radial-gradient(circle, rgba(255,255,255,0.08) 1px, transparent 1px);
background-size: 24px 24px;
```
- Maximum opacity: 8% (dark), 5% (light). If visible at first glance, reduce further.
- Grid spacing must align with layout grid (multiples of 8px).

---

## 6. Depth & Elevation

Vercel uses the Geist **Material** system. Elevation is encoded through border and shadow, not shadow alone.

### Material Types

| Type | Shadow | Border | Radius | Usage |
|------|--------|--------|--------|-------|
| `base` | none | 1px solid `var(--color-4)` | 12px | Resting cards, panels |
| `small` | `0 2px 4px rgba(0,0,0,0.3)` | 1px solid `var(--color-5)` | 12px | Raised cards |
| `large` | `0 8px 24px rgba(0,0,0,0.4)` | 1px solid `var(--color-5)` | 16px | Feature cards, highlighted surfaces |
| `tooltip` | `0 4px 12px rgba(0,0,0,0.5)` | 1px solid `var(--color-6)` | 8px | Tooltips, popovers |
| `menu` | `0 8px 24px rgba(0,0,0,0.5)` | 1px solid `var(--color-6)` | 12px | Dropdown menus |
| `modal` | `0 16px 48px rgba(0,0,0,0.6)` | 1px solid `var(--color-6)` | 16px | Dialog overlays |
| `fullscreen` | `0 0 0 rgba(0,0,0,0)` | none | 0 | Full-page takeovers |

### Border-as-Elevation Rule

At rest, surfaces have no shadow. The 1px border (`var(--color-4)`) alone separates them from the background. Shadow is reserved for floating elements (tooltips, menus, modals) that break the flat plane. This keeps the interface feeling **architectural** rather than layered.

### Inner Highlight

Some elevated surfaces add a subtle top-edge highlight:
```css
box-shadow: inset 0 1px 0 rgba(255,255,255,0.06);
```
This simulates a light source from above and adds perceived depth without adding shadow weight.

---

## 7. Do's and Don'ts

### Do

- Use negative letter-spacing on headings 32px and above -- it is the single most identifiable typographic signature
- Use `color-9` for secondary text, `color-10` for primary; the two-tier system is sufficient
- Rely on border brightness changes for hover states, not shadow changes
- Use the blueprint grid at hero scale only; never on dashboard or form surfaces
- Use `Geist Mono` for any code-adjacent text: deployment IDs, URLs, timestamps, file paths
- Keep button text short and imperative: "Deploy", "Continue", "Create"
- Use pill-shaped badges (`border-radius: 9999px`) for status; rounded rectangles for everything else
- Use `backdrop-filter: blur(12px)` for sticky nav overlays

### Don't

- Never add colored fills as surface backgrounds (no purple panels, no blue cards)
- Never use gradient backgrounds on UI surfaces; gradients only for marketing hero accents
- Never use rounded `border-radius` above 16px on containers (except pills at 9999px)
- Never mix multiple accent colors in the same view
- Never use decorative illustration or stock photography as section backgrounds
- Never apply shadow to resting cards -- border only
- Never use `font-weight: 300` (light) or below; minimum is 400
- Never use ALL CAPS below 12px (becomes illegible)
- Never animate `width`, `height`, `top`, `left`, `margin`, or `padding`; use `transform` and `opacity` only
- Never use the blueprint grid pattern on surfaces with interactive form elements

---

## 8. Responsive Behavior

### Breakpoints

| Name | Min-width | Columns | Gutter | Margin |
|------|-----------|---------|--------|--------|
| Mobile | 0 | 4 | 8px | 16px |
| Tablet | 768px | 8 | 16px | 24px |
| Desktop | 1024px | 12 | 24px | 24px |
| Wide | 1440px | 12 | 24px | auto (max-width: 1200px) |

### Typography Scaling

Headings 40px and above scale down one tier per breakpoint:

| Desktop | Tablet | Mobile |
|---------|--------|--------|
| 72px | 56px | 40px |
| 56px | 48px | 32px |
| 48px | 40px | 32px |
| 40px | 32px | 24px |
| 32px | 24px | 20px |

Headings 24px and below remain constant across breakpoints.

Body copy stays at 14px on all screens. On mobile, `Copy 14` may shift to `Copy 13` in space-constrained layouts.

### Layout Behavior

- Navigation collapses to hamburger menu below 768px
- Cards stack vertically on mobile (single column); 2-column on tablet; 3-column on desktop
- Sidebars hide below 1024px; content takes full width
- Hero sections: text stacks vertically, visual above text on mobile
- Tables convert to card-list on mobile (each row becomes a card)
- `border-radius` stays constant across breakpoints (no rounding changes)
- Blueprint grid pattern: hide on mobile (below 768px) to reduce visual noise

### Touch Adaptations

- Minimum tap target: 44px x 44px
- Button padding increases on mobile: `12px 20px` (from `8px 16px`)
- Spacing between interactive list items: minimum 8px gap
- Bottom sheet replaces dropdown menus on mobile for better touch ergonomics
