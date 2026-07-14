# BMW Design System

Precision engineering meets Bavarian heritage. Structured surfaces, measured contrast, and the unmistakable weight of a brand that has earned its authority over a century. Dark mode is the premium canvas — warm navy, not void black. Every element is machined, not molded.

---

## 1. Visual Theme & Atmosphere

BMW's visual language communicates engineered luxury — the confidence of something built to exacting standards, not designed to impress. Dark navy hero bands frame automotive photography shot in controlled studio light or at golden hour. The palette is restrained: corporate blue carries every primary action, warm dark surfaces anchor the page, and typography does the heavy lifting through extreme weight contrast (700 display against 300 body). The twin kidney grille inspires a design philosophy of symmetry, precision, and authoritative presence — nothing rounded, nothing soft, nothing that hasn't earned its place.

Photography is always premium: studio-lit vehicle renders on neutral backgrounds, or cinematic environmental shots at 16:9 and wider. Surfaces alternate between light canvas and dark navy bands in a deliberate rhythm. The M tricolor stripe appears only in motorsport contexts — a controlled accent, not a decorative device.

**Keywords:** engineered precision, measured luxury, Bavarian authority, structured, machined, warm dark

---

## 2. Color Palette & Roles

### Light Mode

| Token | Hex | Role |
|-------|-----|------|
| `--color-canvas` | `#FFFFFF` | Page background, base surface |
| `--color-surface-soft` | `#F7F7F7` | Footer, sub-navigation bands |
| `--color-surface-card` | `#FAFAFA` | Model card photo plates |
| `--color-surface-strong` | `#EBEBEB` | Section dividers, heavier breaks |
| `--color-ink` | `#262626` | Primary text, display headlines — not pure black, soft against photography |
| `--color-body` | `#3C3C3C` | Default running text |
| `--color-body-strong` | `#1A1A1A` | Emphasized paragraphs, lead text |
| `--color-muted` | `#6B6B6B` | Footer links, breadcrumbs, captions |
| `--color-muted-soft` | `#9A9A9A` | Disabled text, fine-print legal |
| `--color-primary` | `#1C69D4` | BMW Blue — all primary CTAs, active nav, interactive accent |
| `--color-primary-active` | `#0653B6` | Pressed/active state |
| `--color-primary-disabled` | `#D6D6D6` | Disabled button background |
| `--color-bavarian-blue` | `#0066B1` | Brand heritage blue — logo mark, motorsport context, M tricolor anchor |
| `--color-on-primary` | `#FFFFFF` | White text on blue buttons |
| `--color-hairline` | `#E6E6E6` | 1px dividers, input outlines, table separators |
| `--color-hairline-strong` | `#CCCCCC` | Emphasized borders, disabled secondary buttons |
| `--color-m-red` | `#E22718` | M tricolor stripe, error states — never as CTA |
| `--color-success` | `#22C55E` | Confirmation, available indicators |
| `--color-warning` | `#F59E0B` | Warning callouts |
| `--color-error` | `#DC2626` | Validation errors |

### Dark Mode (Premium Default)

| Token | Hex | Role |
|-------|-----|------|
| `--color-canvas` | `#1A2129` | Page background — warm dark navy, not pure black. The Bavarian warmth. |
| `--color-surface-elevated` | `#262E38` | Cards, elevated panels nested on dark hero |
| `--color-surface-card` | `#1E2730` | Model card plates on dark canvas |
| `--color-surface-soft` | `#151B22` | Footer band, deeper than canvas |
| `--color-ink` | `#F5F5F5` | Primary text on dark — warm white |
| `--color-body` | `#C8C8C8` | Default running text on dark |
| `--color-body-strong` | `#E8E8E8` | Emphasized paragraphs on dark |
| `--color-muted` | `#8A8A8A` | Secondary text, breadcrumbs |
| `--color-muted-soft` | `#5E5E5E` | Disabled, fine-print |
| `--color-primary` | `#3B8FE3` | BMW Blue shifted lighter for dark backgrounds |
| `--color-primary-active` | `#2A7BC8` | Pressed/active on dark |
| `--color-on-primary` | `#FFFFFF` | Text on blue buttons (unchanged) |
| `--color-hairline` | `#2E363F` | Dividers on dark — visible but not bright |
| `--color-hairline-strong` | `#3D4752` | Emphasized borders on dark |
| `--color-bavarian-blue` | `#1A8FD4` | Heritage blue, lightened for dark mode |

**Rule:** The dark palette is never pure black (`#000000`). BMW's dark surfaces carry a warm blue-navy undertone (`#1A2129`) — the Bavarian heritage showing through. This distinguishes BMW from Tesla's void-black and Apple's OLED-black. The warmth signals luxury, not emptiness.

---

## 3. Typography Rules

**Primary:** BMW Type Next Latin (licensed, not publicly available)
**Fallback stack:** `"Helvetica Neue", Helvetica, "Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`

**Substitute recommendation:** Inter (variable) at weights 700 / 300 — closest open-source match to BMW Type Next's character.

### Type Scale

| Token | Size | Weight | Line Height | Tracking | Usage |
|-------|------|--------|-------------|----------|-------|
| `--text-display-xl` | `clamp(40px, 5vw, 64px)` | 700 | 1.05 | 0 | Hero headlines — model names ("iX3", "5 Series") |
| `--text-display-lg` | `clamp(32px, 4vw, 48px)` | 700 | 1.1 | 0 | Section heads, configurator titles |
| `--text-display-md` | `clamp(24px, 2.5vw, 32px)` | 700 | 1.15 | 0 | Sub-section heads, feature band titles |
| `--text-display-sm` | `24px` | 700 | 1.25 | 0 | CTA-band headlines, spec values |
| `--text-title-lg` | `20px` | 700 | 1.3 | 0 | Card group titles |
| `--text-title-md` | `18px` | 700 | 1.4 | 0 | Model card titles, intro paragraphs |
| `--text-title-sm` | `16px` | 700 | 1.4 | 0 | Inventory card titles, list labels |
| `--text-body-md` | `16px` | 300 (Light) | 1.55 | 0 | Default body — BMW Type Next Latin Light |
| `--text-body-sm` | `14px` | 300 (Light) | 1.55 | 0 | Footer body, fine-print, secondary copy |
| `--text-caption` | `12px` | 400 | 1.4 | 0.5px | Photo captions, meta, timestamps |
| `--text-label-uppercase` | `13px` | 700 | 1.3 | 1.5px | "LEARN MORE" inline links, category tabs (UPPERCASE) |
| `--text-button` | `14px` | 700 | 1.0 | 0.5px | Standard CTA button label |
| `--text-nav-link` | `14px` | 400 | 1.4 | 0.3px | Top-nav menu items |

### Typography Principles

- **The 700/300 contrast is non-negotiable.** Weight 700 for all display and interactive text. Weight 300 (Light) for all body and descriptive copy. This is BMW's editorial signature — "European-engineered" precision through typographic contrast.
- **No negative letter-spacing.** BMW Type Next Latin works on a wide body. Apple-style tightening reads off-brand. Tracking stays at 0 for display and body; only labels and buttons use positive tracking.
- **UPPERCASE inline links** — "LEARN MORE", "CONFIGURE", "DISCOVER" run uppercase with 1.5px tracking. The machined-precision voice.
- **Weight 400 is narrow-lane.** Only caption and nav-link, both neutral utility contexts. Weight 500 is absent from the system entirely.
- **Headlines never wrap more than two lines.** If a headline wraps, reduce the copy, not the font size.
- **Line height for display: 1.05–1.25. For body: 1.55.** The generous body line height balances the tight display leading.

---

## 4. Component Stylings

### Buttons

**Primary CTA (BMW Blue)**
```css
background: var(--color-primary);
color: var(--color-on-primary);
padding: 14px 32px;
height: 48px;
border-radius: 0px;
font-size: 14px;
font-weight: 700;
letter-spacing: 0.5px;
border: none;
cursor: pointer;
transition: background 200ms ease;
```
- Hover: `var(--color-primary-active)`
- Active: pressed state + `scale(0.98)`
- Disabled: `background: var(--color-primary-disabled); color: var(--color-muted)`

**Secondary (Outlined)**
```css
background: var(--color-canvas);
color: var(--color-ink);
padding: 13px 31px;
height: 48px;
border-radius: 0px;
border: 1px solid var(--color-hairline-strong);
font-size: 14px;
font-weight: 700;
letter-spacing: 0.5px;
```
- Hover: `background: var(--color-surface-soft)`

**Secondary on Dark**
```css
background: transparent;
color: var(--color-ink);
padding: 13px 31px;
border-radius: 0px;
border: 1px solid var(--color-ink);
```
- Used over dark hero bands and CTA sections

**Text Link (Inline UPPERCASE)**
```css
background: transparent;
color: var(--color-ink);
font-size: 13px;
font-weight: 700;
letter-spacing: 1.5px;
text-transform: uppercase;
```
- Terminated by a `›` chevron. No underline, no background.
- Hover: `color: var(--color-primary)`

**No pill buttons. No rounded corners on buttons. No icon-only buttons without a label.** The rectangular 0px-radius button is the BMW corporate signature — engineered, not decorated.

### Navigation

- Fixed top bar, `height: 64px`, white (`var(--color-canvas)`) background.
- Dark mode: `var(--color-canvas)` background, white text.
- Left: BMW roundel logo. Center: primary horizontal menu (Models, Electric, Build Your Own, Dealers). Right: search icon, profile.
- Nav links: 14px / 400 / 0.3px tracking, `var(--color-ink)`. Active: `var(--color-primary)`.
- No hamburger icon on desktop. Below 768px: full-screen sheet menu.
- Transparent variant over hero images: `background: rgba(26, 33, 41, 0.85); backdrop-filter: blur(12px)`.

### Cards

- **Model Card:** `background: var(--color-canvas)`, `border-radius: 0px`, `padding: 24px`. Vehicle render on `var(--color-surface-card)` plate (edge-to-edge, no border). Model name in 18px / 700 below. One-line tagline in 14px / 300. "LEARN MORE ›" text link.
- **Feature Card:** Same structure with 16:9 lifestyle photo top, headline + excerpt below.
- **No box-shadow on cards.** Depth comes from color-block contrast (light card on white vs. dark hero band), not from elevation shadows.
- **No border-radius on cards.** 0px corners — the machined aesthetic.

### Image Treatments

- Hero photography: full-bleed, `width: 100%; aspect-ratio: 16/9` or `21/9`, `object-fit: cover`.
- Model card renders: `aspect-ratio: 16/10`, studio-lit on neutral background, full vehicle silhouette visible.
- No rounded corners on images. No visible image borders. No decorative frames.
- Overlay gradient only for text legibility: `linear-gradient(to top, rgba(26, 33, 41, 0.85) 0%, transparent 60%)`.
- Dark mode: photography may shift to more dramatic, low-key lighting — but always premium, never gritty.

### Data / Specs

- Spec cells use `var(--color-muted)` labels in `--text-label-uppercase`, `var(--color-ink)` values in `--text-display-sm` (24px / 700).
- Vertical spacing between spec rows: 24px.
- No alternating row colors. Dividers: 1px `var(--color-hairline)`.
- Spec values always run in weight 700 — even a number is a statement of precision.

---

## 5. Layout Principles

### Grid

- **Max content width:** 1440px, center-aligned.
- **12-column grid** at desktop. 4-column at tablet. 1-column at mobile.
- **Column gap:** 24px.
- **Model card grids:** 4-up or 5-up at desktop, 2-up at tablet, 1-up on mobile.
- **Configurator:** 3-up filter row + 4-up vehicle cards, denser than editorial pages.

### Spacing System

Base unit: **8px**.

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xxs` | 4px | Tight internal gaps |
| `--space-xs` | 8px | Icon gaps, chip internal |
| `--space-sm` | 12px | Category tab padding |
| `--space-md` | 16px | Card padding (inventory), input padding |
| `--space-lg` | 24px | Card padding (model/feature), column gap |
| `--space-xl` | 32px | Sub-section gaps |
| `--space-xxl` | 48px | Section internal breaks |
| `--space-section` | 80px | Major editorial band padding — the heartbeat |

### Section Rhythm

Pages alternate between light and dark bands in a deliberate cadence: light canvas, dark hero, light feature, dark CTA, light footer. Two consecutive same-mode bands are not allowed — the rhythm demands alternation.

- Section padding: `80px` vertical (tighter than BMW M's 96px — corporate is more utility-driven).
- Between headline and body: `24px`.
- Between body and CTA: `32px`.
- Edge padding (mobile): `16px`.
- Edge padding (desktop): auto, centered in 1440px max-width.

### Alignment

- Headlines and CTAs are center-aligned in hero and CTA bands.
- Feature sections use asymmetric split: 60% image / 40% text, or vice versa.
- Spec tables are left-aligned with right-aligned values.
- The twin kidney grille philosophy: symmetry where it matters (navigation, hero layout), asymmetric balance everywhere else.

---

## 6. Depth & Elevation

**No drop shadows. Ever.** BMW's depth system is flat by conviction. Depth comes from color-block contrast (light canvas vs. dark hero) and photographic subject lighting, not from artificial elevation.

### Surface Hierarchy

| Level | Treatment | Use Case |
|-------|-----------|----------|
| 0 | `var(--color-canvas)` — no shadow, no border | Body, top nav, footer, hero bands |
| 1 | 1px `var(--color-hairline)` border | Configurator option tiles, table dividers |
| 2 | `var(--color-surface-card)` background — no shadow | Model card photo plates |
| 3 | Edge-to-edge photography | Hero bands, vehicle renders |
| 4 | `var(--color-surface-elevated)` on dark | Nested cards over dark hero |

### Metallic Surface Cues

BMW uses subtle surface differentiation to evoke metallic materiality:

- **Light mode:** `#FFFFFF` vs `#FAFAFA` vs `#F7F7F7` — three shades of white that read as brushed aluminum surfaces under different light angles.
- **Dark mode:** `#1A2129` vs `#1E2730` vs `#262E38` — warm navy layers that evoke matte gunmetal and anodized surfaces, not flat void.
- Transition between surface levels: `200ms ease` — swift but not sudden, like a precision mechanism.

### Brand Signature Depth

- **M Tricolor Divider:** 4px horizontal stripe (`#1A8FD4` / `#1C69D4` / `#E22718`). Only in M-model contexts and motorsport badges. Never as a CTA fill, never as a general decorative element. This is a controlled accent — the engineering stripe on a cam cover, not a racing stripe on the hood.

---

## 7. Do's and Don'ts

**Do:**

- Use BMW Blue (`#1C69D4` light / `#3B8FE3` dark) as the single primary action color — it carries every CTA
- Set display headlines in weight 700 and body in Light 300 — the contrast is the editorial signature
- Use UPPERCASE letter-spaced links ("LEARN MORE ›") as inline CTAs — the machined-precision voice
- Alternate light and dark bands in deliberate rhythm — no two consecutive same-mode sections
- Place model card photos on `#FAFAFA` plates with the title beneath — the standard BMW corporate pattern
- Hold section rhythm at 80px — the corporate heartbeat
- Use the warm dark navy (`#1A2129`) for dark surfaces — it carries Bavarian heritage, not emptiness
- Let photography do the heavy lifting — studio-lit vehicle renders and cinematic environmental shots
- Use rectangular 0px-radius for all interactive elements — engineered, not decorated
- Reserve the M tricolor stripe exclusively for M-model contexts

**Don't:**

- Do not use pure black (`#000000`) for dark mode backgrounds — BMW's dark surfaces are warm navy, not void
- Do not use pill or rounded buttons — 0px rectangular is the brand button
- Do not add drop shadows to cards or any element — depth comes from color-block contrast and photography
- Do not drop display weight below 700 or raise body weight above 300 — the duo is fixed
- Do not use weight 500 — it is absent from the system; choose 400 or 700
- Do not use negative letter-spacing — BMW Type works at default tracking; tightening reads off-brand
- Do not use more than one brand accent color per page — BMW Blue carries all primary actions
- Do not use the M tricolor stripe as a CTA fill or general decoration — divider and accent role only
- Do not place text over busy photography without a gradient overlay scrim
- Do not use italic for emphasis — use weight contrast or size contrast instead
- Do not mix rounded and rectangular elements — if one element is 0px radius, all must be

---

## 8. Responsive Behavior

### Breakpoints

| Name | Width | Behavior |
|------|-------|----------|
| Mobile | `< 768px` | Single column, stacked. Hero headline reduces to 40px. Nav collapses to hamburger with full-screen sheet. Model card grid 1-up. Configurator filters scroll horizontally. Footer 4-col to 1-col. |
| Tablet | `768–1024px` | Secondary nav hides under "More". Model card 2-up. Inventory 2-up. Hero headline 48px. |
| Desktop | `1024–1440px` | Full top-nav. 4-up or 5-up model card grid. Inventory 3-up. Full configurator UI. Hero headline 64px. |
| Wide | `> 1440px` | Same as desktop. Content fixed at 1440px max-width. Gutters absorb remaining space. |

### Mobile-Specific Rules

- Hero headline: `clamp(40px, 5vw, 64px)` — never below 40px
- Model card grid collapses to single column with full-width cards
- Configurator filter chip row scrolls horizontally — no wrapping
- Bottom sticky CTA bar may appear on mobile (transparent dark navy, white text)
- Touch targets: minimum 48x48px (above WCAG AAA)
- Text input height: 48px
- Category tabs: 12px vertical padding for tap area > 44px
- Hero photography shifts to more vertical crop (art direction for mobile aspect ratios)
- Inventory photos may shift from 16:9 to 4:3 on mobile

### Image Behavior

- Model renders scale at every breakpoint while preserving native aspect ratios
- Hero photography crops to focus on vehicle front on mobile; full side profile on desktop
- The M tricolor stripe stays at 4px height across every breakpoint

### Dark Mode Switching

Dark mode is the premium default for product configurator and model detail pages. Use `prefers-color-scheme` media query for automatic switching; always provide a manual toggle. All color tokens swap simultaneously. Photography may shift between modes — BMW often uses more dramatic, low-key imagery in dark mode. Transition between modes should be instant (no animation on color swap).
