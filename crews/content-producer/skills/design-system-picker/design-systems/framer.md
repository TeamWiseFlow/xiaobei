# Framer Design System

Bold black and electric blue. Motion-first, design-forward. The interface feels alive — every transition is intentional, every hover is a micro-showcase. Built for people who build websites.

---

## 1. Visual Theme & Atmosphere

Dark, high-contrast surfaces with electric blue punctuating key interactions. The aesthetic says "creative tool" — confident, slightly playful, never corporate. Smooth motion is non-negotiable; static states feel broken. Interactive showcases and live previews are the content, not decoration around content.

**Keywords:** bold, electric, motion-first, interactive, creative, confident

---

## 2. Color Palette & Roles

| Name | Hex | Role |
|------|-----|------|
| Electric Blue | `#0055FF` | Primary accent, CTAs, active states, links |
| Deep Black | `#0A0A0A` | Primary background |
| Rich Black | `#141414` | Card/surface background |
| Elevated Black | `#1E1E1E` | Hover surfaces, input backgrounds |
| Pure White | `#FFFFFF` | Primary text on dark |
| Soft White | `#B0B0B0` | Secondary text, placeholders |
| Muted Gray | `#6B6B6B` | Tertiary text, disabled states |
| Border Subtle | `#2A2A2A` | Dividers, card borders |
| Blue Glow | `#0055FF` at 20% opacity | Focus rings, hover glow |
| Success | `#00C853` | Positive actions, confirmations |
| Warning | `#FFAB00` | Caution states |
| Error | `#FF1744` | Destructive actions, validation errors |

**Rule:** Electric Blue is the soul. Use it for every interactive affordance. Never dilute it with gradients — it should hit pure and saturated.

---

## 3. Typography Rules

**Primary:** Inter (or fallback: system sans-serif)
**Display:** Fraktion (or fallback: Inter with tight tracking)

| Element | Font | Weight | Size | Tracking | Case |
|---------|------|--------|------|----------|------|
| Display hero | Fraktion | 600 | clamp(48px, 5vw, 80px) | -0.04em | Title |
| Section title | Inter | 700 | clamp(28px, 2.5vw, 44px) | -0.02em | Title |
| Subheading | Inter | 600 | 20px | -0.01em | Sentence |
| Body | Inter | 400 | 16px | 0 | Sentence |
| Body small | Inter | 400 | 14px | 0 | Sentence |
| Caption | Inter | 500 | 12px | 0.02em | Uppercase |
| Code / mono | JetBrains Mono | 400 | 14px | 0 | — |

**Rules:**
- Display headlines use tight negative tracking to feel punchy and dense.
- Body line-height: 1.6. Headlines: 1.1.
- Bold (700) for emphasis, never italic. Italic reserved for captions only.
- Code snippets always use mono font with `#1E1E1E` background.

---

## 4. Component Stylings

### Buttons
- **Primary CTA:** `#0055FF` background, white text, `border-radius: 8px`, padding `12px 24px`, weight 600. On hover: scale 1.02, box-shadow `0 0 20px rgba(0,85,255,0.4)`.
- **Secondary CTA:** `#1E1E1E` background, white text, 1px `#2A2A2A` border. On hover: border becomes `#0055FF`.
- **Ghost:** Transparent, white text, no border. On hover: text becomes `#0055FF`.
- **Icon button:** 40x40px, `border-radius: 10px`, `#1E1E1E` bg. On hover: bg `#2A2A2A`.

### Navigation
- Fixed top bar, `height: 64px`, backdrop-blur over dark content.
- Logo left, nav center, CTA right.
- Active nav link: `#0055FF` text, 2px bottom border.
- Hover: text color transition 150ms.

### Cards
- Background: `#141414`, `border-radius: 12px`, 1px `#2A2A2A` border.
- Padding: 24px. Hover: border becomes `#0055FF`, subtle translateY(-2px) with 200ms ease-out.
- No box-shadow at rest. Glow on hover only.

### Input Fields
- Background: `#1E1E1E`, `border-radius: 8px`, 1px `#2A2A2A` border.
- Focus: border `#0055FF`, box-shadow `0 0 0 3px rgba(0,85,255,0.15)`.
- Placeholder: `#6B6B6B`.

### Interactive Showcases
- Live preview panels with `border-radius: 16px`, `border: 1px #2A2A2A`.
- Tab bar above preview: `#141414` bg, active tab has `#0055FF` bottom border.
- Preview area: `#0A0A0A` bg.

### Code Blocks
- `#1E1E1E` background, `border-radius: 8px`, JetBrains Mono.
- Line numbers: `#6B6B6B`. Syntax highlighting: blue `#0055FF`, green `#00C853`, yellow `#FFAB00`, red `#FF1744`.

---

## 5. Layout Principles

- **Max content width:** 1200px centered. Wide showcases: 1400px.
- **Grid:** 12-column, 16px gutters on desktop, 8px on mobile.
- **Sections alternate rhythm:** tight (64px padding) for feature stacks, generous (120px) for hero sections.
- **Asymmetric layouts:** 7/5 or 8/4 splits for text + interactive preview.
- **Sticky sidebars** on documentation pages (240px width).
- **Showcase sections** take near-full-width to let interactive demos breathe.

---

## 6. Depth & Elevation

Depth is expressed through layering and glow, not shadows:

| Level | Surface | Use |
|-------|---------|-----|
| 0 | `#0A0A0A` | Page background |
| 1 | `#141414` | Cards, panels |
| 2 | `#1E1E1E` | Inputs, elevated cards on hover |
| 3 | `#0055FF` glow | Focus, active states |

- **No ambient shadows.** Elevation = background lightness change.
- **Blue glow** on interactive elements creates perceived depth through color, not shadow.
- **Backdrop-blur** on fixed nav and modals (blur(12px), 80% opacity dark).

---

## 7. Do's and Don'ts

**Do:**
- Add motion to every state change (hover, focus, appear, exit) — 150–300ms ease-out
- Use Electric Blue consistently for all interactive elements
- Let interactive showcases be the hero content
- Use tight tracking on headlines for punch
- Round corners on cards and inputs (8–12px) — it softens the dark aesthetic
- Provide keyboard focus rings with blue glow

**Don't:**
- Use drop shadows for elevation — use surface color instead
- Apply Electric Blue to large background areas (it loses impact)
- Use more than one animation timing per element
- Place long paragraphs in dark surfaces without line-height 1.6
- Use gray for interactive elements — if it responds to input, it should hint blue
- Create static pages — motion is the brand

---

## 8. Responsive Behavior

| Breakpoint | Behavior |
|-----------|----------|
| < 640px | Single column. Interactive previews stack below text. Nav collapses to hamburger. Card grid: 1 column. |
| 640–768px | Single column. Preview panels go full-width. Sidebar navigation hidden (use top tabs). |
| 768–1024px | 2-column card grid. Side-by-side text+preview appears. Sidebar nav at 200px. |
| 1024–1440px | 3-column card grid. Full asymmetric splits. Sidebar at 240px. |
| > 1440px | Content max-width 1200px (1400px for showcases), centered. |

**Mobile-specific rules:**
- Interactive showcases become static screenshots with a "Try it" CTA linking to the full experience
- Hover states replaced by tap states with 100ms scale pulse
- Blue glow on focus adapts to `0 0 0 2px rgba(0,85,255,0.3)` (smaller ring)
- Touch targets: minimum 44x44px
- Bottom sheet for navigation on mobile instead of hamburger dropdown
