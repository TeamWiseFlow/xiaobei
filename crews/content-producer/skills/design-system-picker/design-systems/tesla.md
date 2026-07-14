# Tesla Design System

Radical subtraction. Cinematic full-viewport photography. Nearly zero UI chrome. Every element earns its place or is removed.

---

## 1. Visual Theme & Atmosphere

Pure black voids. Full-bleed hero imagery of vehicles shot at golden hour or in stark studio lighting. The product is the visual — UI recedes until needed. Pages feel like a film trailer: slow reveals, minimal text, maximum impact. No decorative elements. No gradients. No patterns. Silence as a design tool.

**Keywords:** radical subtraction, cinematic, electric, powerful, silent, confident

---

## 2. Color Palette & Roles

| Name | Hex | Role |
|------|-----|------|
| Void | `#000000` | Primary background, dominant surface |
| Pure White | `#FFFFFF` | Primary text, divider lines, CTA text |
| Cool Gray | `#A6A6A6` | Secondary text, captions, disabled states |
| Steel | `#5C5C5C` | Tertiary text, subtle borders |
| Tesla Red | `#E82127` | Accent only — error states, rare highlights |
| Surface Dark | `#171717` | Card backgrounds, secondary surfaces |
| Surface Mid | `#222222` | Hover states, elevated surfaces |

**Rule:** The palette is almost monochrome. Tesla Red is used no more than once per page. Cool Gray is the workhorse for anything that is not primary content.

---

## 3. Typography Rules

**Primary:** Universal Sans (or fallback: Inter, system sans-serif)

| Element | Weight | Size | Tracking | Case |
|---------|--------|------|----------|------|
| Hero headline | 600 | clamp(48px, 6vw, 96px) | -0.03em | Title |
| Section headline | 500 | clamp(32px, 3vw, 56px) | -0.02em | Title |
| Body large | 400 | 20px | 0 | Sentence |
| Body | 400 | 16px | 0 | Sentence |
| Caption / spec | 400 | 13px | 0.02em | Title |
| CTA | 500 | 14px | 0.04em | Uppercase |

**Rules:**
- Never use italic for emphasis. Use weight or size contrast.
- Hero headlines: one line, no wrapping. If it wraps, the copy is too long.
- All-caps tracking must be wide — never let uppercase text feel cramped.
- Line height for headlines: 1.05. For body: 1.5.

---

## 4. Component Stylings

### Buttons
- **Primary CTA:** White text on `#000000` with 1px white border, padding `14px 40px`, uppercase tracking 0.04em. On hover: background becomes `#FFFFFF`, text becomes `#000000`.
- **Ghost CTA:** White text, no border, underline on hover (2px, offset 4px).
- **No filled colored buttons.** No rounded pill buttons. No icon-only buttons without label.

### Navigation
- Fixed top bar, `height: 56px`, transparent over hero images.
- Nav links: 13px uppercase, tracking 0.06em, white, no underline.
- No hamburger icon on desktop. No sidebars.

### Cards
- Background: `#171717` or transparent over imagery.
- No border-radius (0px). No box-shadow.
- Content sits flush against edges.

### Image Treatments
- Full-viewport hero images: `width: 100vw; height: 100vh; object-fit: cover`.
- No rounded corners on images. No visible image borders.
- Overlay gradient only when text legibility demands it: `linear-gradient(to top, #000 0%, transparent 60%)`.

### Data / Specs
- Spec tables use Cool Gray labels, White values, no grid lines.
- Vertical spacing between spec rows: 24px.
- No alternating row colors.

---

## 5. Layout Principles

- **Full-viewport sections.** Each section occupies the entire viewport. No content peeks into the next section.
- **Extreme whitespace.** Between sections: 120px minimum. Between headline and body: 40px.
- **Centered single column** for headlines and CTAs. Max content width: 960px.
- **Asymmetric split** for feature sections: 60% image / 40% text, or vice versa.
- **No sidebars. No multi-column grids of cards.** The product is the grid.
- **Sticky scroll behavior:** as the user scrolls, the next vehicle image cross-fades in. Content overlays the imagery.

---

## 6. Depth & Elevation

- **No shadows.** Ever. Depth comes from layering full-bleed imagery, not from drop shadows.
- **No blur/glass effects.** The interface is crisp and opaque.
- Elevation hierarchy:
  - Level 0: `#000000` background
  - Level 1: `#171717` surface
  - Level 2: `#222222` hover/elevated
  - Level 3: `#FFFFFF` inverted CTA on hover
- Z-index is flat. Only the nav bar (z-50) and modals sit above content.

---

## 7. Do's and Don'ts

**Do:**
- Let photography do the heavy lifting — use the largest images possible
- Use generous whitespace to create breathing room around text
- Keep copy short: headlines under 6 words, body under 40 words per section
- Use animation only for scroll-triggered reveals (opacity 0 to 1, translateY)
- Make CTAs obvious through contrast, not decoration

**Don't:**
- Add decorative icons, illustrations, or patterns
- Use rounded corners on any element (border-radius: 0)
- Apply drop shadows or elevation shadows
- Use more than one accent color per page
- Place text over busy image areas without a gradient overlay
- Use carousels — one hero image per viewport
- Add social media feeds, tickers, or scrolling banners

---

## 8. Responsive Behavior

| Breakpoint | Behavior |
|-----------|----------|
| < 640px | Single column, stacked. Hero images scale to `100vh` width-aware. Headline reduces to 32px. Nav collapses to hamburger. |
| 640–1024px | Single column. Side-by-side spec splits stack vertically. CTA buttons stretch full-width. |
| 1024–1440px | Asymmetric splits appear. Desktop nav visible. Spec tables go two-column. |
| > 1440px | Content max-width 960px, centered. Background imagery extends full-bleed. |

**Mobile-specific rules:**
- Hero images may crop differently (focus on vehicle front, not full side profile)
- Bottom sticky CTA bar appears on mobile (transparent black, white text)
- Spec sections collapse into horizontal scroll cards only on mobile
- Touch targets: minimum 48x48px
