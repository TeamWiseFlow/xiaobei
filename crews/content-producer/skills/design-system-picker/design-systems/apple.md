# Apple Design System

## 1. Visual Theme & Atmosphere

Apple's design language communicates premium simplicity. Every surface breathes. Content is the hero -- UI chrome recedes until needed.

**Core qualities:**
- Cinematic full-bleed photography and video dominate hero sections
- Typography carries weight: large, confident, never timid
- White space is structural, not decorative -- it creates rhythm and focus
- Dark mode feels rich and deep, never flat gray
- Transitions are smooth and physical (spring curves, not linear)
- Product imagery is always studio-quality on clean backgrounds
- Gradients are subtle and purposeful (radial glows, not rainbow sweeps)

**Atmosphere keywords:** confident, luminous, precise, unhurried, premium

---

## 2. Color Palette & Roles

### Light Mode

| Token | Hex | Role |
|-------|-----|------|
| `--color-bg` | `#FFFFFF` | Page background |
| `--color-surface` | `#F5F5F7` | Card / section fill |
| `--color-surface-elevated` | `#FFFFFF` | Elevated cards, modals |
| `--color-text-primary` | `#1D1D1F` | Headlines, body copy |
| `--color-text-secondary` | `#6E6E73` | Captions, descriptions |
| `--color-text-tertiary` | `#86868B` | Disabled, placeholders |
| `--color-accent` | `#0071E3` | Links, CTAs, interactive |
| `--color-accent-hover` | `#0077ED` | Accent hover state |
| `--color-accent-active` | `#0062CC` | Accent pressed state |
| `--color-accent-subtle` | `#0071E312` | Accent tinted backgrounds |
| `--color-separator` | `#D2D2D7` | Dividers, borders |
| `--color-separator-subtle` | `#E8E8ED` | Hairline separators |
| `--color-fill-green` | `#30D158` | Success, positive states |
| `--color-fill-red` | `#FF3B30` | Error, destructive actions |
| `--color-fill-orange` | `#FF9F0A` | Warning, attention |
| `--color-fill-yellow` | `#FFD60A` | Highlight, caution |

### Dark Mode

| Token | Hex | Role |
|-------|-----|------|
| `--color-bg` | `#000000` | Page background -- true black on OLED |
| `--color-surface` | `#1C1C1E` | Card / section fill |
| `--color-surface-elevated` | `#2C2C2E` | Elevated cards, modals |
| `--color-text-primary` | `#F5F5F7` | Headlines, body copy |
| `--color-text-secondary` | `#A1A1A6` | Captions, descriptions |
| `--color-text-tertiary` | `#6E6E73` | Disabled, placeholders |
| `--color-accent` | `#2997FF` | Links, CTAs (lighter blue for dark bg) |
| `--color-accent-hover` | `#4DB2FF` | Accent hover state |
| `--color-accent-active` | `#0A84FF` | Accent pressed state |
| `--color-accent-subtle` | `#2997FF18` | Accent tinted backgrounds |
| `--color-separator` | `#38383A` | Dividers, borders |
| `--color-separator-subtle` | `#2C2C2E` | Hairline separators |
| `--color-fill-green` | `#30D158` | Success (same as light) |
| `--color-fill-red` | `#FF453A` | Error (lighter for dark bg) |
| `--color-fill-orange` | `#FF9F0A` | Warning (same as light) |

---

## 3. Typography Rules

**Font stack:** SF Pro (primary), `-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif`

**Fallback for web without SF Pro:** `"Helvetica Neue", Helvetica, Arial, sans-serif`

### Type Scale

| Token | Size | Weight | Tracking | Line-height | Usage |
|-------|------|--------|----------|-------------|-------|
| `--text-hero` | `clamp(3rem, 5vw + 1rem, 5.5rem)` | 600 (semibold) | -0.03em | 1.05 | Product hero headlines |
| `--text-headline-lg` | `clamp(2.5rem, 3.5vw + 0.5rem, 3.5rem)` | 600 | -0.025em | 1.1 | Section headlines |
| `--text-headline` | `clamp(1.75rem, 2vw + 0.5rem, 2.5rem)` | 600 | -0.02em | 1.15 | Sub-section headlines |
| `--text-title` | `1.5rem` (24px) | 600 | -0.015em | 1.2 | Card titles, modal headers |
| `--text-subtitle` | `1.25rem` (20px) | 500 | -0.01em | 1.25 | Subtitles, supporting heads |
| `--text-body-lg` | `1.125rem` (18px) | 400 | 0 | 1.55 | Large body, introductions |
| `--text-body` | `1rem` (16px) | 400 | 0 | 1.5 | Default body text |
| `--text-caption` | `0.875rem` (14px) | 400 | 0.01em | 1.4 | Captions, metadata |
| `--text-overline` | `0.75rem` (12px) | 500 | 0.05em | 1.33 | Labels, badges, overlines (UPPERCASE) |

### Dynamic Type Rules

- Hero text uses `clamp()` for fluid scaling between breakpoints
- Body text never goes below 16px on mobile
- Tracking tightens as size increases (hero: -0.03em, body: 0)
- Weight stays within 400-600 range; never use 300 or below for English
- Chinese/Japanese text uses SF Pro SC/SF Pro JP with same size scale but tracking at 0

---

## 4. Component Stylings

### Buttons

**Primary (Blue)**
```css
background: var(--color-accent);
color: #FFFFFF;
padding: 12px 24px;
border-radius: 980px; /* full pill */
font-size: 1rem;
font-weight: 500;
letter-spacing: 0;
border: none;
cursor: pointer;
transition: background 200ms ease;
```
- Hover: `var(--color-accent-hover)`
- Active: `var(--color-accent-active)` + scale(0.98)
- Disabled: opacity 0.4, no pointer events

**Secondary (Tinted)**
```css
background: var(--color-accent-subtle);
color: var(--color-accent);
padding: 12px 24px;
border-radius: 980px;
font-size: 1rem;
font-weight: 500;
border: none;
```

**Text / Ghost**
```css
background: transparent;
color: var(--color-accent);
padding: 8px 12px;
border-radius: 980px;
font-size: 1rem;
font-weight: 500;
border: none;
```
- Hover: `background: var(--color-accent-subtle)`

**Large Hero CTA**
```css
padding: 16px 32px;
font-size: 1.125rem;
```

### Cards

```css
background: var(--color-surface);
border-radius: 20px;
padding: 24px;
border: none;
box-shadow: none;
```
- Elevated variant: `background: var(--color-surface-elevated)` + subtle shadow
- Image cards: image fills top portion with `border-radius: 20px 20px 0 0`, no gap between image and content
- Product tiles: centered content, generous padding (32px+)

### Inputs

```css
background: var(--color-surface);
border: 1px solid var(--color-separator);
border-radius: 12px;
padding: 12px 16px;
font-size: 1rem;
color: var(--color-text-primary);
outline: none;
transition: border-color 200ms ease;
```
- Focus: `border-color: var(--color-accent)` + `box-shadow: 0 0 0 3px var(--color-accent-subtle)`
- Placeholder: `var(--color-text-tertiary)`
- Error: `border-color: var(--color-fill-red)`
- Search inputs: rounded pill (980px), magnifying glass icon at left

### Navigation

- **Sticky nav**: `backdrop-filter: saturate(180%) blur(20px)` + semi-transparent background
  - Light: `rgba(255, 255, 255, 0.72)`
  - Dark: `rgba(29, 29, 31, 0.72)`
- Nav height: `48px` (compact, not tall)
- Nav links: `font-size: 0.75rem; font-weight: 400; letter-spacing: 0; color: var(--color-text-secondary)`
- Active link: `color: var(--color-text-primary)`
- Max content width within nav: `980px` centered
- Mobile: hamburger icon, full-screen slide-down menu with `backdrop-filter: blur(20px)`

### Tabs

```css
background: var(--color-surface);
border-radius: 980px;
padding: 2px;
```
- Active tab pill: `background: var(--color-surface-elevated)` + `box-shadow: 0 1px 3px rgba(0,0,0,0.08)`
- Tab label: `font-size: 0.8125rem; font-weight: 500`

---

## 5. Layout Principles

### Whitespace Philosophy

White space is the most important design element. It is not "empty" -- it is intentional breathing room that directs attention.

- Section padding: `clamp(4rem, 8vw, 8rem)` vertical
- Between headline and body: `0.75em` to `1em`
- Between body and CTA: `1.5em` to `2em`
- Between sibling cards: `20px` to `24px`
- Edge padding (mobile): `20px`
- Edge padding (desktop): centered within `980px` max-width

### Grid

- Max content width: `980px` (Apple's standard)
- Wide layouts: `1200px` for product showcase pages
- Grid columns: 12-column at desktop, 4-column at tablet, 1-column at mobile
- Column gap: `24px`
- Content never stretches edge-to-edge on desktop; always maintain margin

### Content Rhythm

1. **Hero section**: Full viewport height or near-full. Headline + subtitle + CTA centered. Background imagery or video.
2. **Feature sections**: Alternating image-left / text-right then flip. Each section separated by generous vertical space.
3. **Spec/benefit grids**: 2-4 columns of icon + short text. Compact but not cramped.
4. **Final CTA section**: Centered, bold headline, single button. Often on colored background.

---

## 6. Depth & Elevation

### Frosted Glass (Vibrancy)

Apple's signature depth cue. Use on any overlaying surface:

```css
background: rgba(255, 255, 255, 0.72);         /* light */
background: rgba(29, 29, 31, 0.72);             /* dark */
backdrop-filter: saturate(180%) blur(20px);
-webkit-backdrop-filter: saturate(180%) blur(20px);
```

Apply to: navigation bar, modal overlays, popover menus, floating toolbars.

### Shadow Levels

| Level | Shadow | Use Case |
|-------|--------|----------|
| 0 | none | Inline cards on colored surface |
| 1 | `0 1px 2px rgba(0,0,0,0.04)` | Subtle lift, default cards |
| 2 | `0 4px 12px rgba(0,0,0,0.08)` | Elevated cards, dropdowns |
| 3 | `0 8px 32px rgba(0,0,0,0.12)` | Modals, popovers |
| 4 | `0 16px 48px rgba(0,0,0,0.16)` | Hero modals, large overlays |

Dark mode shadows: use `rgba(0,0,0,0.4)` base and increase opacity by 1.5x compared to light.

### Material Surfaces

- **Regular material**: solid `var(--color-surface)` background
- **Thin material**: `backdrop-filter: blur(20px)` + 60% opacity fill
- **Thick material**: `backdrop-filter: blur(40px)` + 80% opacity fill
- **Ultra-thin material**: `backdrop-filter: blur(10px)` + 40% opacity fill (for subtle overlays)

### Border Radius Scale

| Token | Value | Usage |
|-------|-------|-------|
| `--radius-sm` | `8px` | Small chips, badges |
| `--radius-md` | `12px` | Inputs, small cards |
| `--radius-lg` | `20px` | Cards, modal containers |
| `--radius-xl` | `28px` | Large feature cards |
| `--radius-pill` | `980px` | Buttons, pills, search bars |

---

## 7. Do's and Don'ts

### Do

- Use full-bleed cinematic imagery for hero sections -- let photos breathe
- Use SF Pro at semibold (600) for headlines; it reads as confident, not heavy
- Generously pad everything; if it feels tight, add more space
- Use the blue accent sparingly -- one blue element per section is enough
- Apply frosted glass to floating and overlay surfaces
- Use `clamp()` for all headline sizes to ensure fluid scaling
- Animate with spring-like easing: `cubic-bezier(0.25, 0.1, 0.25, 1)` or CSS `spring()`
- Pair large headlines with small, quiet body text for contrast
- Use true black (`#000000`) for dark mode backgrounds on OLED
- Use `saturate(180%)` in backdrop-filter for that signature Apple vibrancy

### Don't

- Never use drop shadows on text -- Apple never does this
- Never use more than two font weights on a single page (400 + 600 is the standard pair)
- Never add colored backgrounds behind body text on white pages
- Never use underlines on links within body copy -- use blue color only
- Never round-card product images on product detail pages -- use rectangle with subtle radius
- Never use uppercase for headlines or body text (only overline labels)
- Never add visible borders to cards on light backgrounds -- use surface color difference instead
- Never use gray (`#808080` or similar) as a decorative accent
- Never animate layout properties (width, height, margin, padding) -- use transform and opacity only
- Never place text directly over busy photography without a scrim or blur layer

---

## 8. Responsive Behavior

### Breakpoints

| Name | Width | Layout |
|------|-------|--------|
| Mobile | `< 734px` | Single column, stacked sections |
| Tablet | `734px - 1068px` | 2-column grid, compact nav |
| Desktop | `1069px - 1440px` | Full layout, centered content |
| Wide | `> 1440px` | Max-width constrained, margins grow |

### Key Responsive Patterns

**Navigation:**
- Desktop: horizontal links in nav bar
- Tablet: condensed links or dropdown
- Mobile: hamburger icon, full-screen overlay menu with frosted glass

**Hero Sections:**
- Desktop: large text (hero scale), side-by-side image + text or full-bleed image with centered overlay text
- Mobile: stacked (text above image), reduced type scale, image may become background with scrim

**Feature Grids:**
- Desktop: 3-4 columns
- Tablet: 2 columns
- Mobile: 1 column, full-width cards

**Product Images:**
- Desktop: large, often 50% of viewport width
- Mobile: full-width with `aspect-ratio: 4/3` or `1/1`

**Spacing Scale (mobile vs desktop):**

| Context | Mobile | Desktop |
|---------|--------|---------|
| Section vertical padding | `3rem` | `clamp(4rem, 8vw, 8rem)` |
| Card padding | `20px` | `24px` to `32px` |
| Edge margin | `20px` | auto (centered in max-width) |
| Between-section gap | `2rem` | `4rem` to `6rem` |
| Card grid gap | `16px` | `24px` |

**Touch Targets:**
- Minimum 44px x 44px on mobile
- Tap targets separated by at least 8px
- Buttons on mobile: full-width or minimum 140px wide

### Dark Mode Switching

Use `prefers-color-scheme` media query. All color tokens swap simultaneously. Images and photography may also switch (Apple often uses different hero images for light/dark on product pages). Transition between modes should be instant (no animation on color swap) -- only user-triggered interactions animate.
