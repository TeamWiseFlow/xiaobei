# Stripe Design System

## 1. Visual Theme & Atmosphere

Stripe's visual identity is built on **engineered elegance** — a clean white canvas punctuated by signature purple gradients, weight-300 body typography that feels light and confident, and a trust-forward financial aesthetic that reads as precise without feeling cold. The system alternates between bright white surfaces and deep navy sections, with purple serving as the sole chromatic accent on chrome. Every surface feels considered and load-bearing; decoration is minimal and purposeful.

The design reads as "infrastructure you can trust rendered with the restraint of a Swiss poster." Headlines are set in a clean geometric sans at light weights (300) with generous letter-spacing, creating an airy authority. Code and data surfaces sit in dark wells that contrast sharply with the white canvas. Purple gradients flow across hero bands and CTAs, giving the system its signature warmth within a predominantly neutral palette.

**Key Characteristics:**

- White canvas (`#FFFFFF`) as the default page background with `#F6F9FC` for inset bands
- Signature purple gradient (`#635BFF` to `#7A73FF`) reserved for CTAs, hero bands, and accent surfaces
- Deep navy (`#0A2540`) for dark sections and code wells — never pure black
- Weight-300 body typography as the default, creating the system's characteristic lightness
- Generous whitespace (96px+ section rhythm) with tight in-card padding (16-24px)
- Subtle layered shadows that lift cards gently off the canvas — no hard edges
- Rounded corners in the 6-8px range for cards and containers, 4px for inputs and small elements

---

## 2. Color Palette & Roles

### Brand & Accent

| Name | Hex | Role |
|------|-----|------|
| `purple-600` | `#635BFF` | Primary brand color. CTAs, links, active states, hero gradient start. |
| `purple-500` | `#7A73FF` | Primary hover, gradient end stop, lighter accent surfaces. |
| `purple-400` | `#8B83FF` | Focus rings, subtle purple borders, disabled-active purple. |
| `purple-100` | `#E8E5FF` | Soft purple tint for backgrounds of highlighted or selected items. |
| `purple-50` | `#F4F2FF` | Faintest purple wash — inline code backgrounds, subtle row hover. |
| `gradient-hero` | `linear-gradient(135deg, #635BFF 0%, #7A73FF 100%)` | Hero band backgrounds, primary CTA fills, feature accent bands. |

### Surface

| Name | Hex | Role |
|------|-----|------|
| `white` | `#FFFFFF` | Default page canvas, card backgrounds, input fills. |
| `gray-50` | `#F6F9FC` | Inset bands, alternating section backgrounds, table row stripes. |
| `gray-100` | `#E8ECF1` | Dividers, hairline borders on light surfaces, subtle separators. |
| `gray-200` | `#C1C9D2` | Disabled borders, placeholder text underline, secondary dividers. |
| `navy-900` | `#0A2540` | Dark section backgrounds, code wells, footer canvas. |
| `navy-800` | `#1A2E4A` | Elevated dark surface, dark card backgrounds. |
| `navy-700` | `#2D3E54` | Secondary dark surface, in-well panel backgrounds. |

### Text

| Name | Hex | Role |
|------|-----|------|
| `ink` | `#1A1F36` | Primary body text on light surfaces. Near-black with warmth. |
| `body` | `#425466` | Long-form body copy where ink reads too heavy. |
| `charcoal` | `#5A6980` | Captions, metadata, secondary content. |
| `mute` | `#697386` | Placeholder text, supporting copy, inactive labels. |
| `ash` | `#8792A2` | Disabled text, tertiary labels, least-emphasis utility. |
| `stone` | `#A3ACB9` | Disabled foreground, neutral icon outlines. |
| `on-dark` | `#FFFFFF` | Primary text on navy/dark surfaces. |
| `on-dark-mute` | `rgba(255,255,255,0.72)` | Secondary text on dark surfaces. |

### Semantic

| Name | Hex | Role |
|------|-----|------|
| `success` | `#30B566` | Success states, confirmations, positive indicators. |
| `success-soft` | `#E6F9EF` | Success background tint. |
| `warning` | `#E5A54B` | Warning states, caution indicators. |
| `warning-soft` | `#FFF6E9` | Warning background tint. |
| `error` | `#D84040` | Error states, destructive actions, validation failures. |
| `error-soft` | `#FDE8E8` | Error background tint. |
| `info` | `#00B4D8` | Informational badges, neutral highlights. |
| `info-soft` | `#E3F6FC` | Info background tint. |

### Dark Mode Override

| Name | Hex | Role |
|------|-----|------|
| `dm-canvas` | `#0A2540` | Default page background. |
| `dm-surface` | `#1A2E4A` | Card and elevated panel background. |
| `dm-surface-elevated` | `#2D3E54` | Button fills, input fills on dark. |
| `dm-hairline` | `rgba(255,255,255,0.08)` | Card borders on dark surfaces. |
| `dm-hairline-strong` | `rgba(255,255,255,0.16)` | Stronger dividers on dark. |

---

## 3. Typography Rules

### Font Families

| Role | Family | Fallback | Notes |
|------|--------|----------|-------|
| Display & UI | `Inter` | `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif` | Primary face. Load with `font-display: swap`. |
| Code | `JetBrains Mono` | `"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace` | API examples, inline code, terminal blocks. |

Inter is the primary typeface. Stripe's signature lightness comes from using **weight 300** as the default body weight — this is non-negotiable. Headlines and display type use weight 500 or 600 for structural contrast, never 700+. The result is an airy hierarchy where weight contrast does the work that size alone cannot.

### Hierarchy

| Token | Size | Weight | Line Height | Letter Spacing | Use |
|-------|------|--------|-------------|----------------|-----|
| `display-2xl` | 72px | 600 | 1.05 | -1.5px | Hero headline. One per page. |
| `display-xl` | 56px | 600 | 1.1 | -1px | Section openers, landing page headlines. |
| `display-lg` | 44px | 500 | 1.15 | -0.5px | Sub-section display, pricing tier names. |
| `display-md` | 32px | 500 | 1.25 | -0.3px | Feature card titles, in-section headlines. |
| `heading-lg` | 24px | 500 | 1.35 | -0.2px | Card headings, panel titles. |
| `heading-md` | 20px | 500 | 1.4 | 0 | In-card section heads, sidebar titles. |
| `heading-sm` | 16px | 500 | 1.5 | 0 | Small headings, form group labels. |
| `body-lg` | 18px | 300 | 1.65 | 0 | Lead paragraphs, hero subtitles. |
| `body-md` | 16px | 300 | 1.6 | 0 | Default body text, form labels, descriptions. |
| `body-sm` | 14px | 300 | 1.6 | 0 | Card descriptions, metadata, secondary copy. |
| `caption` | 12px | 400 | 1.5 | 0.2px | Timestamps, footer links, small utility text. |
| `link-md` | 16px | 500 | 1.6 | 0 | Inline body links — weight 500 distinguishes from body 300. |
| `button-lg` | 16px | 500 | 1.0 | 0.2px | Large CTA button label. |
| `button-md` | 14px | 500 | 1.0 | 0.2px | Default button label. |
| `code-md` | 14px | 400 | 1.7 | 0 | Code blocks, inline code, API paths. |
| `code-sm` | 12px | 400 | 1.6 | 0 | Tab labels, small code tokens. |

### Principles

- **Weight-300 is the default.** Body text at weight 300 creates the characteristic Stripe lightness. Never bump body to 400 for emphasis — use weight 500 on headings or change the family to `JetBrains Mono` for technical emphasis.
- **Negative letter-spacing on display sizes** tightens large type into cohesive blocks. Scale the negative value with size: -1.5px at 72px down to 0 at 16px.
- **Line height opens at body sizes** (1.6-1.65) to maintain readability with the light weight. Display sizes tighten to 1.05-1.25.
- **No serifs anywhere.** The system is entirely sans-serif for UI and monospace for code.

---

## 4. Component Stylings

### Buttons

**`button-primary`** — Purple gradient CTA

- Background: `gradient-hero` (`linear-gradient(135deg, #635BFF, #7A73FF)`)
- Text: `#FFFFFF`
- Typography: `button-md` (14px / 500)
- Border radius: 6px
- Padding: 10px 20px
- Height: 40px
- Border: none
- Hover: background shifts to solid `#635BFF`, slight brightness increase
- Active/pressed: background `#5850E6` (one shade darker)
- Focus: 3px ring in `purple-400` offset by 2px
- Transition: 150ms ease on background-color

**`button-primary-lg`** — Large hero CTA

- Same as `button-primary` but:
- Typography: `button-lg` (16px / 500)
- Padding: 14px 28px
- Height: 48px
- Border radius: 8px

**`button-secondary`** — Outline button

- Background: `#FFFFFF`
- Text: `ink` (`#1A1F36`)
- Typography: `button-md`
- Border: 1px solid `gray-100` (`#E8ECF1`)
- Border radius: 6px
- Padding: 9px 19px
- Height: 40px
- Hover: background `gray-50` (`#F6F9FC`), border darkens to `gray-200`
- Active: background `gray-100`, border `charcoal`
- Focus: 3px ring in `purple-400`

**`button-ghost`** — Inline text button

- Background: transparent
- Text: `purple-600` (`#635BFF`)
- Typography: `button-md`
- Border: none
- Padding: 4px 8px
- Height: auto
- Hover: text `purple-500`, faint `purple-50` background
- Active: text `purple-600`, background `purple-100`

**`button-dark`** — CTA on dark surfaces

- Background: `#FFFFFF`
- Text: `navy-900` (`#0A2540`)
- Typography: `button-md`
- Border radius: 6px
- Padding: 10px 20px
- Height: 40px
- Hover: background `gray-50`
- Active: background `gray-100`

**`button-disabled`**

- Background: `gray-50` (`#F6F9FC`)
- Text: `ash` (`#8792A2`)
- Border: 1px solid `gray-100`
- Cursor: not-allowed
- No hover or active states

### Cards

**`card-default`** — Standard content card

- Background: `#FFFFFF`
- Border: 1px solid `gray-100` (`#E8ECF1`)
- Border radius: 8px
- Padding: 24px
- Shadow: `0 2px 4px rgba(10,37,64,0.04), 0 4px 16px rgba(10,37,64,0.06)`
- Hover: shadow deepens to `0 4px 8px rgba(10,37,64,0.06), 0 8px 24px rgba(10,37,64,0.08)`, subtle translateY(-1px)
- Transition: 200ms ease on box-shadow and transform

**`card-elevated`** — Featured/highlight card

- Background: `#FFFFFF`
- Border: 1px solid `gray-100`
- Border radius: 8px
- Padding: 32px
- Shadow: `0 4px 8px rgba(10,37,64,0.06), 0 8px 24px rgba(10,37,64,0.08)`
- Used for pricing featured tier, primary feature showcase

**`card-dark`** — Card on dark surfaces

- Background: `navy-800` (`#1A2E4A`)
- Border: 1px solid `dm-hairline` (`rgba(255,255,255,0.08)`)
- Border radius: 8px
- Padding: 24px
- Shadow: `0 4px 16px rgba(0,0,0,0.2)`
- Text: `on-dark` (`#FFFFFF`)

**`card-pricing`** — Pricing tier card

- Background: `#FFFFFF`
- Border: 1px solid `gray-100`
- Border radius: 12px
- Padding: 32px
- Shadow: `0 2px 4px rgba(10,37,64,0.04), 0 4px 16px rgba(10,37,64,0.06)`

**`card-pricing-featured`** — Recommended pricing tier

- Same as `card-pricing` but:
- Border: 2px solid `purple-600` (`#635BFF`)
- Shadow: `0 4px 16px rgba(99,91,255,0.12), 0 8px 32px rgba(99,91,255,0.08)`

### Inputs

**`input-default`** — Standard text input

- Background: `#FFFFFF`
- Text: `ink` (`#1A1F36`)
- Placeholder: `mute` (`#697386`)
- Typography: `body-md` (16px / 300)
- Border: 1px solid `gray-100` (`#E8ECF1`)
- Border radius: 6px
- Padding: 10px 12px
- Height: 40px
- Hover: border `gray-200` (`#C1C9D2`)
- Focus: border `purple-600`, 3px ring in `purple-100` (`#E8E5FF`)
- Error: border `error` (`#D84040`), ring in `error-soft`
- Disabled: background `gray-50`, text `ash`, border `gray-100`, cursor not-allowed
- Transition: 150ms ease on border-color and box-shadow

**`input-dark`** — Input on dark surfaces

- Background: `navy-800` (`#1A2E4A`)
- Text: `on-dark`
- Placeholder: `on-dark-mute`
- Border: 1px solid `dm-hairline`
- Focus: border `purple-500`, ring `rgba(123,115,255,0.2)`

**`search-bar`** — Search input

- Same as `input-default` but:
- Height: 44px
- Border radius: 8px
- Padding: 12px 16px 12px 40px (left padding accounts for magnifier icon)

### Navigation

**`nav-primary`** — Top navigation bar

- Background: `#FFFFFF` with 1px bottom border in `gray-100`
- Height: 64px
- Layout: Logo at left, nav links centered, CTA + secondary link at right
- Nav link text: `body-sm` (14px / 300), color `charcoal`
- Nav link hover: color `ink`, subtle `gray-50` background pill
- Nav link active: color `purple-600`, weight 500
- Sticky on scroll with a `0 2px 8px rgba(10,37,64,0.06)` shadow appearing at scroll offset

**`nav-primary-dark`** — Top nav on dark sections

- Background: `navy-900` (`#0A2540`) with 1px bottom border in `dm-hairline`
- Nav link text: color `on-dark-mute`
- Nav link hover: color `on-dark`, subtle background in `dm-surface`
- Nav link active: color `purple-500`

**`nav-mobile`** — Mobile navigation

- Hamburger icon at left, logo centered, CTA at right
- Drawer slides from right with `navy-900` background
- Drawer links stacked vertically with `body-lg` (18px / 300), color `on-dark`
- Divider lines in `dm-hairline` between link groups

### Other Components

**`badge`** — Inline status badge

- Background: `purple-50` (`#F4F2FF`)
- Text: `purple-600`
- Typography: `caption` (12px / 400)
- Border radius: 9999px (full pill)
- Padding: 3px 10px
- Variants: `badge-success` (green), `badge-warning` (amber), `badge-error` (red), `badge-info` (cyan) — each using corresponding semantic-soft background and semantic text color

**`code-block`** — Code well

- Background: `navy-900` (`#0A2540`)
- Text: `on-dark`
- Typography: `code-md` (14px / JetBrains Mono)
- Border radius: 8px
- Padding: 20px 24px
- Tab strip at top: `code-sm` (12px), inactive tabs `on-dark-mute`, active tab `on-dark` with 2px `purple-600` bottom border

**`divider`** — Section separator

- Light surface: 1px solid `gray-100` (`#E8ECF1`)
- Dark surface: 1px solid `dm-hairline` (`rgba(255,255,255,0.08)`)

**`tooltip`** — Hover tooltip

- Background: `navy-900`
- Text: `on-dark`
- Typography: `body-sm` (14px / 300)
- Border radius: 6px
- Padding: 8px 12px
- Shadow: `0 4px 16px rgba(0,0,0,0.2)`
- Arrow: 6px CSS triangle in `navy-900`

---

## 5. Layout Principles

### Spacing Scale

| Token | Value | Use |
|-------|-------|-----|
| `xxs` | 4px | Inline tight gaps, icon-to-label spacing |
| `xs` | 8px | Small internal gaps, badge padding |
| `sm` | 12px | Input padding, in-card element spacing |
| `md` | 16px | Default card padding (small cards), gutter spacing |
| `lg` | 24px | Standard card padding, section sub-spacing |
| `xl` | 32px | Pricing card padding, feature row gaps |
| `xxl` | 48px | Large feature section vertical padding |
| `xxxl` | 64px | Major section vertical padding |
| `section` | 96px | Full section rhythm on desktop |
| `band` | 128px | Hero band vertical padding |

### Grid

- **Max content width:** 1200px centered, with 24px side padding growing to 48px on ultrawide
- **Hero bands:** full-bleed up to 1440px content area
- **Card grids:** 3-up at desktop (400px per card), 2-up at tablet, 1-up at mobile
- **Feature rows:** 2-up split (copy left 45%, visual right 55%) collapsing to stacked at tablet
- **Footer:** 4-column link grid at desktop, 2-up at tablet, 1-up at mobile

### Whitespace Philosophy

Whitespace is the system's primary structural tool. Sections breathe at 96px on desktop with no decorative dividers — the white canvas carries from hero to footer with rhythm established by alternating `white` and `gray-50` bands. Inside cards, the system tightens to 16-24px so content reads as compact and precise. The white canvas never feels empty because the generous spacing and light typography create intentional breathing room, not vacancy.

---

## 6. Depth & Elevation

### Shadow System

| Level | Shadow | Use |
|-------|--------|-----|
| 0 — flat | none | Canvas, inline text, footer |
| 1 — rest | `0 2px 4px rgba(10,37,64,0.04), 0 4px 16px rgba(10,37,64,0.06)` | Default cards at rest |
| 2 — hover | `0 4px 8px rgba(10,37,64,0.06), 0 8px 24px rgba(10,37,64,0.08)` | Card hover state, elevated panels |
| 3 — floating | `0 8px 16px rgba(10,37,64,0.08), 0 16px 48px rgba(10,37,64,0.12)` | Modals, dropdowns, popovers |
| 4 — purple glow | `0 4px 16px rgba(99,91,255,0.12), 0 8px 32px rgba(99,91,255,0.08)` | Featured pricing card, purple-accented elevated surfaces |

### Surface Hierarchy

| Level | Surface | Use |
|-------|---------|-----|
| 0 | `white` (`#FFFFFF`) | Page canvas, card backgrounds |
| 1 | `gray-50` (`#F6F9FC`) | Inset bands, alternating sections, table row stripes |
| 2 | `gray-100` (`#E8ECF1`) | Dividers, borders, subtle inset backgrounds |
| 3 | `navy-900` (`#0A2540`) | Dark sections, code wells, footer |
| 4 | `navy-800` (`#1A2E4A`) | Cards on dark, elevated dark surfaces |
| 5 | `navy-700` (`#2D3E54`) | In-well panels, dark input fills |

Elevation on light surfaces comes from layered shadows with the `rgba(10,37,64,...)` tint — never pure black shadows, which would read too harsh against the warm white canvas. On dark surfaces, depth is built from the navy surface ladder, not shadows.

---

## 7. Do's and Don'ts

### Do

- Use weight 300 as the default body weight. This is the single most important typographic decision in the system.
- Reserve `purple-600` (`#635BFF`) and the hero gradient for CTAs, links, and accent surfaces. The purple should feel like a signature, not wallpaper.
- Use `navy-900` (`#0A2540`) for dark sections rather than pure black (`#000000`). The navy carries warmth and brand coherence.
- Apply the layered shadow system (`rgba(10,37,64,...)`) instead of pure-black shadows. The slight blue tint matches the navy palette.
- Alternate between `white` and `gray-50` bands to create section rhythm without visible dividers.
- Set display type with negative letter-spacing proportional to size. Tighter at larger sizes, 0 at body scale.
- Use `JetBrains Mono` for all code surfaces — API examples, terminal blocks, inline code. Never use the sans-serif face for code.
- Give cards a subtle `translateY(-1px)` on hover to reinforce the shadow lift. The motion should feel like the card is breathing upward, not bouncing.
- Maintain 96px section rhythm on desktop. The whitespace is structural, not decorative.

### Don't

- Don't use weight 400 or 500 for body text. Weight 300 is the Stripe voice. Bumping weight breaks the system's characteristic lightness.
- Don't apply the purple gradient to large background surfaces or full-bleed sections outside of the hero. Purple is an accent, not a canvas.
- Don't use pure black (`#000000`) for text, shadows, or backgrounds. `ink` (`#1A1F36`) and `navy-900` (`#0A2540`) are warmer and brand-coherent.
- Don't add visible dividers between sections. Rhythm comes from alternating surface colors and generous spacing.
- Don't round corners beyond 12px on cards. The system stays in the 6-8px range for most elements. Pill-shaped cards break the precise aesthetic.
- Don't use colored shadows outside of the purple glow on featured elements. All other shadows use the `rgba(10,37,64,...)` tint.
- Don't pair purple with a secondary brand color. Purple is the only accent; semantic colors (green, amber, red) are functional, not decorative.
- Don't set code in the sans-serif face, even inline. Code always gets `JetBrains Mono`.
- Don't add drop shadows on dark surfaces. Elevation on dark is built from the surface-color ladder.

---

## 8. Responsive Behavior

### Breakpoints

| Name | Width | Key Changes |
|------|-------|-------------|
| ultrawide | 1920px+ | Content max-width holds at 1200px; outer gutters grow to 48-80px |
| desktop | 1280px | Default — 3-up card grids, 2-up feature rows, full nav |
| desktop-small | 1024px | Card grids 2-up; feature rows remain side-by-side but narrower |
| tablet | 768px | Card grids 1-up; feature rows stack; nav collapses to hamburger |
| mobile | 480px | Single-column everything; hero display-2xl scales 72px to 36px |
| mobile-narrow | 320px | Section padding tightens to 48px; card padding reduces to 16px |

### Touch Targets

- All buttons meet WCAG AA at minimum 40px height. `button-primary-lg` sits at 48px (AAA).
- `input-default` is 40px height. `search-bar` is 44px (AAA).
- Inline links and ghost buttons receive additional padding (8px minimum) to extend tap area without visual change.
- Nav links on mobile: 44px minimum tap height with full-width tap targets.

### Collapsing Strategy

- **Primary nav:** desktop horizontal cluster collapses to hamburger at 768px. Logo and primary CTA remain visible at all breakpoints.
- **Hero headline:** `display-2xl` scales 72px -> 56px -> 44px -> 36px across breakpoints. Letter-spacing reduces proportionally.
- **Feature rows:** 2-up side-by-side at desktop -> stacked at tablet with visual below copy.
- **Card grids:** 3-up -> 2-up at desktop-small -> 1-up at tablet.
- **Pricing tier grid:** 3-up -> stacked at tablet with featured tier remaining first.
- **Footer:** 4-column -> 2-up at tablet -> 1-up at mobile.
- **Section padding:** 96px desktop -> 64px tablet -> 48px mobile.
- **Code blocks:** horizontal scroll at mobile rather than reflow — code formatting must be preserved.

### Animation Guidelines

- **Card hover:** 200ms ease on box-shadow and transform. Subtle lift (1px) with shadow deepening.
- **Button hover:** 150ms ease on background-color and border-color. No transform.
- **Nav shadow on scroll:** 200ms ease on opacity appearing at scroll offset.
- **Page transitions:** 300ms ease-out on opacity. No slide or scale transitions on page-level elements.
- **Reduced motion:** All transitions collapse to 0ms; hover states apply instantly without motion.
