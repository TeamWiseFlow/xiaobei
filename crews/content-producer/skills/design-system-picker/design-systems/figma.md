# Figma Design System

## 1. Visual Theme & Atmosphere

Figma's visual identity is built on **creative confidence**: a vibrant, multi-color palette that feels playful without sacrificing professionalism. The aesthetic channels a design tool that knows its users are visually literate, so it rewards attention with rich color and purposeful asymmetry rather than safe neutrality.

Key atmosphere traits:
- **Energetic optimism** -- saturated hues communicate possibility and creative freedom
- **Structured playfulness** -- bright colors are balanced by generous whitespace and a clean grid, never chaotic
- **Tool-first confidence** -- the UI feels like it belongs to a product you trust with your craft; chrome is minimal, content is foregrounded
- **Inclusive warmth** -- rounded geometry and warm tones keep the brand approachable despite its professional depth

## 2. Color Palette & Roles

### Core Brand Colors

| Semantic Name | Hex | Role |
|---|---|---|
| `brand-primary` | `#F24E1E` | Primary actions, CTAs, key highlights, logo mark |
| `brand-red` | `#FF7262` | Secondary accent, hover states on primary, illustration fills |
| `brand-purple` | `#A259FF` | Feature emphasis, badges, decorative gradient endpoints |
| `brand-green` | `#0ACF83` | Success states, positive indicators, growth metrics |
| `brand-blue` | `#1ABCFE` | Informational elements, links, data visualization |

### Surface & Neutral Colors (Dark Mode Primary)

| Semantic Name | Hex | Role |
|---|---|---|
| `surface-base` | `#1E1E1E` | Page background, canvas |
| `surface-raised` | `#2C2C2C` | Cards, panels, elevated containers |
| `surface-overlay` | `#3C3C3C` | Modals, dropdowns, popover backgrounds |
| `surface-hover` | `#4A4A4A` | Hover states on raised surfaces |
| `border-subtle` | `#3C3C3C` | Default borders, dividers |
| `border-strong` | `#5C5C5C` | Active borders, input focus rings |
| `text-primary` | `#FFFFFF` | Headings, primary body text |
| `text-secondary` | `#B3B3B3` | Captions, descriptions, muted labels |
| `text-tertiary` | `#808080` | Placeholders, disabled text, hints |

### Surface & Neutral Colors (Light Mode)

| Semantic Name | Hex | Role |
|---|---|---|
| `surface-base` | `#FFFFFF` | Page background |
| `surface-raised` | `#F5F5F5` | Cards, panels |
| `surface-overlay` | `#E8E8E8` | Modals, dropdowns |
| `border-subtle` | `#E5E5E5` | Default borders |
| `border-strong` | `#CCCCCC` | Active borders |
| `text-primary` | `#1E1E1E` | Headings, primary body text |
| `text-secondary` | `#666666` | Captions, descriptions |
| `text-tertiary` | `#999999` | Placeholders, disabled text |

### Semantic Colors

| Semantic Name | Hex | Role |
|---|---|---|
| `color-success` | `#0ACF83` | Confirmations, saved states, valid inputs |
| `color-warning` | `#FF9F43` | Caution alerts, unsaved changes |
| `color-error` | `#F24E1E` | Error states, destructive actions, validation failures |
| `color-info` | `#1ABCFE` | Tooltips, informational banners, help indicators |

### Gradient Presets

| Name | Value | Usage |
|---|---|---|
| `gradient-brand` | `linear-gradient(135deg, #F24E1E 0%, #A259FF 100%)` | Hero sections, feature highlights |
| `gradient-rainbow` | `linear-gradient(135deg, #F24E1E 0%, #A259FF 33%, #1ABCFE 66%, #0ACF83 100%)` | Brand moments, event banners |
| `gradient-warm` | `linear-gradient(135deg, #F24E1E 0%, #FF7262 100%)` | CTA backgrounds, emphasis panels |
| `gradient-cool` | `linear-gradient(135deg, #1ABCFE 0%, #A259FF 100%)` | Secondary feature blocks |

## 3. Typography Rules

### Font Stack

- **Display / Headlines**: `"Inter", system-ui, -apple-system, sans-serif`
- **Body**: `"Inter", system-ui, -apple-system, sans-serif`
- **Code / Monospace**: `"JetBrains Mono", "Fira Code", "Consolas", monospace`

Inter is used across all weights, with dramatic weight contrast creating hierarchy rather than switching font families.

### Type Scale

| Level | Size | Weight | Line Height | Letter Spacing | Usage |
|---|---|---|---|---|---|
| `display` | `clamp(3rem, 5vw, 5rem)` | 800 | 1.05 | -0.03em | Hero headlines, page titles |
| `h1` | `clamp(2.25rem, 3.5vw, 3.5rem)` | 700 | 1.1 | -0.02em | Section titles |
| `h2` | `clamp(1.75rem, 2.5vw, 2.5rem)` | 700 | 1.15 | -0.015em | Subsection titles |
| `h3` | `clamp(1.25rem, 1.5vw, 1.75rem)` | 600 | 1.2 | -0.01em | Card titles, feature headings |
| `body-lg` | `1.125rem` | 400 | 1.6 | 0 | Lead paragraphs, introductions |
| `body` | `1rem` | 400 | 1.6 | 0 | Default body text |
| `body-sm` | `0.875rem` | 400 | 1.5 | 0.005em | Captions, metadata, helper text |
| `caption` | `0.75rem` | 500 | 1.4 | 0.01em | Labels, badges, timestamps |
| `code` | `0.875rem` | 400 | 1.5 | 0 | Inline code, code blocks |

### Rules

- Never use weight below 400 for body text; 300 is reserved for decorative display only
- Headlines use tight negative letter-spacing; body text uses neutral or slightly positive tracking
- Maximum line length: 65ch for body text, 40ch for captions
- Use weight jumps (400 to 700) for emphasis rather than italic or underline in body text
- Code snippets always use monospace with a subtle background tint (`rgba(162, 89, 255, 0.08)` in dark mode)

## 4. Component Stylings

### Buttons

| Variant | Background | Text | Border | Radius | Hover |
|---|---|---|---|---|---|
| Primary | `#F24E1E` | `#FFFFFF` | none | 8px | `#D4411A`, translateY(-1px) |
| Secondary | `transparent` | `#FFFFFF` | `#5C5C5C` | 8px | border `#F24E1E`, text `#F24E1E` |
| Ghost | `transparent` | `#B3B3B3` | none | 8px | bg `rgba(255,255,255,0.06)` |
| Brand Gradient | `gradient-brand` | `#FFFFFF` | none | 8px | `gradient-warm`, translateY(-1px) |

- Padding: `12px 24px` default, `10px 20px` compact
- Transition: `all 150ms cubic-bezier(0.16, 1, 0.3, 1)`
- Active state: `translateY(1px)`, opacity 0.9
- Focus ring: `2px solid #1ABCFE`, offset 2px
- Icon buttons: 40x40px square, `border-radius: 10px`

### Cards

- Background: `surface-raised` (`#2C2C2C` dark / `#F5F5F5` light)
- Border: `1px solid border-subtle`
- Border-radius: `12px`
- Padding: `24px`
- Hover: `translateY(-2px)`, `box-shadow: 0 8px 30px rgba(0,0,0,0.3)`
- Transition: `transform 200ms cubic-bezier(0.16, 1, 0.3, 1), box-shadow 200ms ease`
- Featured cards: left border accent `3px solid` using brand color matching the content theme

### Inputs

- Background: `surface-base` (`#1E1E1E` dark / `#FFFFFF` light)
- Border: `1px solid border-subtle`
- Border-radius: `8px`
- Padding: `10px 14px`
- Focus: border `#1ABCFE`, `box-shadow: 0 0 0 3px rgba(26, 188, 254, 0.15)`
- Error: border `#F24E1E`, error message in `color-error` below input
- Placeholder: `text-tertiary`

### Tags / Badges

- Border-radius: `6px`
- Padding: `4px 10px`
- Font: `caption` (0.75rem, 500)
- Color variants use brand colors with 12% opacity backgrounds:
  - Purple badge: bg `rgba(162,89,255,0.12)`, text `#A259FF`
  - Green badge: bg `rgba(10,207,131,0.12)`, text `#0ACF83`
  - Blue badge: bg `rgba(26,188,254,0.12)`, text `#1ABCFE`
  - Red badge: bg `rgba(242,78,30,0.12)`, text `#F24E1E`

### Tooltips

- Background: `#4A4A4A`
- Text: `#FFFFFF`, `body-sm`
- Border-radius: `6px`
- Padding: `6px 12px`
- Arrow: 6px CSS triangle
- Delay: 300ms show, 100ms hide

### Toggles / Switches

- Track: `#3C3C3C` off, `#0ACF83` on
- Knob: `#FFFFFF`, 18px diameter
- Track height: 24px, width 44px, border-radius 12px
- Transition: `background 200ms ease, transform 200ms cubic-bezier(0.16, 1, 0.3, 1)`

## 5. Layout Principles

### Grid

- Desktop: 12-column grid, 24px gutters, 64px max outer margin
- Tablet: 8-column grid, 20px gutters
- Mobile: 4-column grid, 16px gutters
- Max content width: `1200px` (centered)
- Wide layout: `1440px` for hero and showcase sections

### Spacing Scale

| Token | Value | Usage |
|---|---|---|
| `space-1` | 4px | Inline gaps, icon padding |
| `space-2` | 8px | Tight component spacing |
| `space-3` | 12px | Form element gaps |
| `space-4` | 16px | Component internal padding |
| `space-5` | 24px | Card padding, standard gaps |
| `space-6` | 32px | Section sub-spacing |
| `space-7` | 48px | Between related sections |
| `space-8` | 64px | Between distinct sections |
| `space-9` | 96px | Major section dividers |
| `space-10` | 128px | Hero-level vertical rhythm |

### Layout Patterns

- **Z-pattern** for marketing pages: headline + CTA top-left, visual top-right, content flows diagonally
- **Feature grid**: 3-column cards with icon, title, description; each card may use a different brand accent color for its icon to reinforce the multi-color identity
- **Asymmetric split**: 60/40 text-to-visual ratio on feature sections, alternating sides
- **Full-bleed heroes**: content constrained to grid but background colors/gradients extend edge-to-edge
- Sticky navigation with `backdrop-filter: blur(12px)` and `background: rgba(30,30,30,0.85)`

## 6. Depth & Elevation

Figma's depth system is restrained and functional, favoring subtle surface differentiation over dramatic shadows.

### Elevation Levels

| Level | Shadow (Dark Mode) | Shadow (Light Mode) | Usage |
|---|---|---|---|
| Level 0 | none | none | Base canvas, flat surfaces |
| Level 1 | `0 1px 3px rgba(0,0,0,0.3)` | `0 1px 3px rgba(0,0,0,0.08)` | Cards at rest |
| Level 2 | `0 4px 12px rgba(0,0,0,0.3)` | `0 4px 12px rgba(0,0,0,0.1)` | Hovered cards, raised panels |
| Level 3 | `0 8px 30px rgba(0,0,0,0.4)` | `0 8px 30px rgba(0,0,0,0.12)` | Modals, dropdowns |
| Level 4 | `0 16px 50px rgba(0,0,0,0.5)` | `0 16px 50px rgba(0,0,0,0.16)` | Toast notifications, spotlight overlays |

### Depth Through Color

- Prefer surface color shifts (darker backgrounds for elevation) over heavy shadows
- Overlay modals use `backdrop-filter: blur(8px)` on the scrim layer
- Glassmorphism accents: `background: rgba(44,44,44,0.7)`, `backdrop-filter: blur(16px)`, `border: 1px solid rgba(255,255,255,0.08)` -- use sparingly for floating toolbars and context menus only

### Overlap & Layering

- Hero sections may overlap into the next section by `-48px` to `--space-7` with a rounded bottom container
- Illustration elements can break out of their container bounds by up to 20% for visual energy
- Brand color shapes (circles, rounded rectangles at 10% opacity) may overlap content as decorative background layers

## 7. Do's and Don'ts

### Do

- Use the full brand color set (orange, red, purple, green, blue) to differentiate features and sections -- the palette is meant to be used, not hoarded
- Apply generous whitespace around headlines and CTAs to let the vibrant colors breathe
- Use Inter weight 700-800 for headlines and 400 for body to create clear typographic hierarchy
- Pair dark surfaces with saturated accent colors -- they need the contrast to pop
- Use gradient-brand for primary CTAs and hero moments; use solid brand-primary for repeated UI elements
- Round corners consistently: 8px for inputs and small elements, 12px for cards, 16px+ for hero containers
- Use micro-interactions (scale 1.02 on hover, 150-200ms) to reinforce the playful-but-precise personality
- Let illustrations and visuals carry color; keep chrome (navigation, toolbars) neutral

### Don't

- Don't use all five brand colors on a single component -- pick one accent per element
- Don't apply gradients to body text or small UI labels; reserve them for backgrounds and CTAs
- Don't use drop shadows on text -- Figma's brand never uses text shadows
- Don't mix warm (orange/red) and cool (blue/purple) accents as adjacent equals without a neutral spacer
- Don't use pure black (`#000000`) for text on dark backgrounds; use `#FFFFFF` or `text-primary` instead
- Don't over-blur -- limit `backdrop-filter: blur()` to 16px maximum and use only on overlay elements
- Don't use rounded corners below 6px -- the system avoids sharp edges entirely
- Don't place saturated accent-colored text on saturated backgrounds; maintain sufficient contrast (WCAG AA minimum)
- Don't animate `width`, `height`, `top`, or `left`; use `transform` and `opacity` for all motion

## 8. Responsive Behavior

### Breakpoints

| Name | Min Width | Columns | Gutter | Typical Target |
|---|---|---|---|---|
| `mobile` | 0 | 4 | 16px | Phones (<640px) |
| `tablet` | 640px | 8 | 20px | Tablets, small laptops |
| `desktop` | 1024px | 12 | 24px | Laptops, desktops |
| `wide` | 1440px | 12 | 24px | Large monitors |

### Adaptation Rules

- **Hero section**: Stacks vertically on mobile (headline over visual), maintains side-by-side from tablet up. Font size scales via `clamp()` across all breakpoints.
- **Feature grid**: 3 columns on desktop, 2 on tablet, 1 on mobile. Cards maintain consistent padding but reduce to `20px` on mobile.
- **Navigation**: Full horizontal nav on desktop, hamburger menu with slide-in drawer on mobile. Drawer uses `surface-raised` background with `border-left` accent in `brand-primary`.
- **CTAs**: Full-width on mobile, auto-width on tablet and up. Minimum touch target: 44px height on mobile.
- **Images and illustrations**: `width: 100%` with `aspect-ratio` preserved. Hero visuals may be hidden or replaced with a simplified version below `tablet` breakpoint if they contain fine detail.
- **Typography scaling**: All heading sizes use `clamp()` to fluidly scale between breakpoints. Body text stays at `1rem` across all sizes.
- **Color accents**: Brand color shapes used as decorative backgrounds are hidden on mobile to reduce visual noise. Gradient hero backgrounds simplify to solid `brand-primary` on mobile.
- **Spacing reduction**: `space-9` and `space-10` sections collapse to `space-7` on tablet and `space-6` on mobile. Card grids reduce gap from `space-5` to `space-4` to `space-3` respectively.
