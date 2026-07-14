# Supabase Design System

> Dark emerald green theme. Code-first developer aesthetic. Dark surfaces with green accents. Technical documentation feel.

---

## 1. Visual Theme & Atmosphere

Supabase speaks to developers who live in terminals and editors. The visual language borrows from IDE dark modes: deep charcoal backgrounds, syntax-highlighted accents, and monospaced code blocks as first-class content. The emerald green brand color (`#3ECF8E`) punctuates an otherwise austere dark palette, signaling "active," "live," and "connected" -- a visual echo of a running Postgres instance.

**Atmosphere keywords:** developer-tooling, terminal-dark, documentation-grade, surgical precision, open-source credibility.

**Primary mode:** Dark. Light mode exists in the dashboard but is secondary. This design system defaults to dark.

**Signature moments:**

- Green-glow code blocks with syntax tokens that mirror the brand palette
- `$ supabase` CLI prompts woven into marketing pages
- Data tables with tight row heights (28px) that feel like a spreadsheet, not a marketing site
- Subtle green `rgba(62, 207, 142, 0.1)` flash on state changes

---

## 2. Color Palette & Roles

### Brand

| Semantic Name        | Hex       | HSL               | Role                                    |
|----------------------|-----------|--------------------|-----------------------------------------|
| `brand-primary`      | `#3ECF8E` | 153.1 60.2% 52.7% | Primary actions, links, active states   |
| `brand-accent`       | `#34B97D` | 152.9 56.1% 46.5% | Hover/pressed brand, emphasis accents   |
| `brand-600`          | `#84E0B7` | 153 59.5% 70%     | Light brand for dark-surface highlights  |
| `brand-500`          | `#15593B` | 153.5 61.8% 21.6% | Brand on dark surfaces (muted green)     |
| `brand-400`          | `#0B3824` | 153.3 65.2% 13.5% | Deep brand background                   |
| `brand-300`          | `#062618` | 153.8 69.6% 9%    | Darkest brand surface                   |
| `brand-200`          | `#041C11` | 152.5 75% 6.3%    | Near-black brand tint                   |

### Gray (Dark Mode) -- Core Neutral

| Semantic Name      | Hex       | Role                                |
|--------------------|-----------|-------------------------------------|
| `gray-dark-100`    | `#151515` | Deepest background (sidebar, dialog)|
| `gray-dark-200`    | `#1C1C1C` | Default page/canvas background      |
| `gray-dark-300`    | `#222222` | Control background, surface 100     |
| `gray-dark-400`    | `#282828` | Surface 200, muted background       |
| `gray-dark-500`    | `#2D2D2D` | Button default bg, overlay default  |
| `gray-dark-600`    | `#343434` | Border default, selection bg        |
| `gray-dark-700`    | `#3D3D3D` | Border strong, surface 400          |
| `gray-dark-800`    | `#505050` | Border button hover, stronger border|
| `gray-dark-900`    | `#6F6F6F` | Foreground muted                    |
| `gray-dark-1000`   | `#7D7D7D` | Foreground lighter                  |
| `gray-dark-1100`   | `#9F9F9F` | Foreground light                    |
| `gray-dark-1200`   | `#ECECEC` | Foreground default (primary text)   |

### Slate (Dark Mode) -- Cool Neutral Alternative

| Semantic Name      | Hex       | Role                                |
|--------------------|-----------|-------------------------------------|
| `slate-dark-100`   | `#141617` | Cool deep background                |
| `slate-dark-200`   | `#1A1D1E` | Cool canvas background              |
| `slate-dark-300`   | `#1F2324` | Cool surface                        |
| `slate-dark-400`   | `#26292B` | Cool muted surface                  |
| `slate-dark-500`   | `#2A2E30` | Cool button/overlay background      |
| `slate-dark-600`   | `#313538` | Cool border                         |
| `slate-dark-700`   | `#393E41` | Cool stronger border                |
| `slate-dark-800`   | `#4C5155` | Cool hover border                   |
| `slate-dark-900`   | `#687076` | Cool muted foreground               |
| `slate-dark-1000`  | `#787E84` | Cool lighter foreground             |
| `slate-dark-1100`  | `#9AA0A5` | Cool light foreground               |
| `slate-dark-1200`  | `#EBECED` | Cool primary text                   |

### Semantic Colors

| Semantic Name        | Hex       | Role                       |
|----------------------|-----------|----------------------------|
| `destructive`        | `#E54D2D` | Error states, delete, danger |
| `destructive-hover`  | `#F0694F` | Destructive hover/pressed  |
| `destructive-muted`  | `#7E2215` | Destructive on dark surface |
| `warning`            | `#FFB224` | Caution, pending states    |
| `warning-hover`      | `#F1A00C` | Warning hover/pressed      |
| `secondary`          | `#FFFFFF` | White accent, secondary actions |

### Code Syntax Tokens (Dark)

| Token            | Hex       | Usage                         |
|------------------|-----------|-------------------------------|
| `code-foreground`| `#FFFFFF` | Default code text             |
| `code-keyword`   | `#BDA4FF` | Language keywords             |
| `code-constant`  | `#3ECF8E` | Constants, functions, properties (matches brand) |
| `code-string`    | `#FFCDA1` | String literals, expressions  |
| `code-comment`   | `#7E7E7E` | Comments                      |
| `code-highlight` | `#232323` | Active/highlighted line bg    |

---

## 3. Typography Rules

### Font Stack

| Purpose    | Font                          | Fallback                       |
|------------|-------------------------------|--------------------------------|
| UI Body    | Inter                         | system-ui, -apple-system, sans-serif |
| Code       | `custom-font` (monospaced)    | ui-monospace, SFMono-Regular, Menlo, monospace |
| Display    | `custom-font` (variable)      | Inter, system-ui, sans-serif   |

> Note: Supabase uses a proprietary custom font loaded via `@font-face` in weights 400 (Book) and 500 (Medium). For reproduction, use Inter as the closest open-source substitute for body text and JetBrains Mono or Fira Code for code.

### Type Scale

| Level          | Size                          | Weight | Line-Height | Usage                        |
|----------------|-------------------------------|--------|-------------|------------------------------|
| `display-xl`   | `clamp(2.5rem, 5vw, 4.5rem)` | 500    | 1.1         | Hero headlines               |
| `display-lg`   | `clamp(2rem, 4vw, 3rem)`     | 500    | 1.15        | Section headlines            |
| `h2`           | `1.875rem` (30px)             | 500    | 1.25        | Sub-section headers          |
| `h3`           | `1.25rem` (20px)              | 500    | 1.3         | Card titles, panel headers   |
| `body-lg`      | `1.125rem` (18px)             | 400    | 1.6         | Hero body, lead paragraphs   |
| `body`         | `0.875rem` (14px)             | 400    | 1.5         | Default body text            |
| `body-sm`      | `0.8125rem` (13px)            | 400    | 1.5         | Secondary text, captions     |
| `code`         | `0.875rem` (14px)             | 400    | 1.6         | Inline code, code blocks     |
| `label`        | `0.75rem` (12px)              | 500    | 1.4         | Labels, badges, tags         |

### Typography Rules

- Never use italic for emphasis in UI text; use weight 500 instead.
- Monospace is reserved for code, CLI commands, API paths, and database identifiers.
- Code blocks use a darker background (`#1C1C1C`) than the page background.
- Headlines never use letter-spacing. Body text at small sizes may use `0.01em`.
- Avoid center-aligned text for paragraphs longer than two lines.

---

## 4. Component Stylings

### Buttons

```
Primary Button
  bg: #3ECF8E
  text: #1C1C1C
  border-radius: 6px
  padding: 8px 16px
  font-weight: 500
  font-size: 14px
  hover: bg #34B97D
  active: bg #2DA06D, translateY(1px)
  disabled: bg #2D2D2D, text #6F6F6F

Secondary Button
  bg: #2D2D2D
  text: #ECECEC
  border: 1px solid #343434
  border-radius: 6px
  padding: 8px 16px
  font-weight: 400
  hover: bg #343434, border-color #3D3D3D
  active: bg #3D3D3D
  disabled: bg #222222, text #6F6F6F, border-color #282828

Ghost Button
  bg: transparent
  text: #9F9F9F
  border: none
  padding: 8px 12px
  hover: text #ECECEC, bg rgba(255,255,255,0.05)
  active: bg rgba(255,255,255,0.08)

Destructive Button
  bg: #E54D2D
  text: #FFFFFF
  border-radius: 6px
  hover: bg #F0694F
  active: bg #D13B1C
```

### Cards

```
Surface Card
  bg: #222222 (gray-dark-300)
  border: 1px solid #343434 (gray-dark-600)
  border-radius: 8px
  padding: 16px (1rem)
  hover: border-color #3D3D3D, subtle glow rgba(62,207,142,0.04)

Featured Card
  bg: #282828 (gray-dark-400)
  border: 1px solid #3D3D3D (gray-dark-700)
  border-radius: 8px
  padding: 24px (1.5rem)
  hover: border-color #3ECF8E at 0.3 opacity

Code Card / Terminal Card
  bg: #1C1C1C (gray-dark-200)
  border: 1px solid #2D2D2D
  border-radius: 8px
  padding: 16px
  font-family: monospace
```

### Inputs

```
Text Input
  bg: #222222 (gray-dark-300)
  border: 1px solid #343434 (gray-dark-600)
  border-radius: 6px
  padding: 8px 12px
  text: #ECECEC
  placeholder: #6F6F6F
  height: 36px (default), 28px (compact)
  focus: border-color #3ECF8E, ring rgba(62,207,142,0.3)
  error: border-color #E54D2D, ring rgba(229,77,45,0.2)
  disabled: bg #1C1C1C, text #6F6F6F
```

### Navigation

```
Top Nav
  bg: rgba(21,21,21,0.8) with backdrop-blur
  border-bottom: 1px solid #2D2D2D
  height: 56px
  text: #9F9F9F
  active/hover text: #ECECEC
  brand link: #3ECF8E

Sidebar Nav
  bg: #151515 (gray-dark-100)
  width: 240px (collapsed: 48px)
  item text: #9F9F9F
  item hover: bg #222222, text #ECECEC
  item active: bg #282828, text #3ECF8E, left-border 2px #3ECF8E
  section label: #6F6F6F, uppercase, 12px, 500 weight, letter-spacing 0.05em

Breadcrumb
  text: #7D7D7D
  separator: #6F6F6F
  current: #ECECEC
```

### Badges / Tags

```
Default Badge
  bg: #2D2D2D
  text: #9F9F9F
  border-radius: 9999px
  padding: 2px 8px
  font-size: 12px

Brand Badge
  bg: #15593B (brand-500)
  text: #3ECF8E
  border-radius: 9999px

Destructive Badge
  bg: #7E2215
  text: #E54D2D
  border-radius: 9999px
```

### Data Table

```
Table
  header bg: #1C1C1C
  row bg: #222222
  row alt bg: #1C1C1C
  row hover bg: #282828
  row height: 28px
  header text: #9F9F9F, 12px, 500
  cell text: #ECECEC, 13px
  cell padding: 8px horizontal
  border: 1px solid #2D2D2D
```

---

## 5. Layout Principles

### Spacing Scale

| Token   | Value   | Usage                               |
|---------|---------|-------------------------------------|
| `xs`    | 4px     | Inline gaps, icon-to-label spacing  |
| `sm`    | 8px     | Tight component padding             |
| `md`    | 16px    | Default component padding, card gutters |
| `lg`    | 32px    | Section spacing, panel padding      |
| `xl`    | 64px    | Major section separation            |

### Page Layout

```
Max content width: 1128px (--content-width-screen-xl)
Container max: 128rem (--container-site)
Page horizontal padding: 16px (mobile), 24px (tablet), 32px (desktop)
Sidebar width: 240px (expanded), 48px (collapsed)
Sidebar + content gap: 0 (sidebar shares border with content)
```

### Grid

- Dashboard uses a sidebar + content layout (no CSS grid for the main split).
- Card grids: 12-column at `lg+`, 1-column on mobile.
- Gap between cards: 16px (`md`).
- Feature grids on marketing pages: 3 columns at `xl`, 2 at `md`, 1 at `sm`.

### Content Rhythm

- Headline to body: 12px gap.
- Body to next section: 32px (`lg`).
- Card internal: 16px padding, 12px between label and value.
- Documentation left-nav items: 4px vertical gap.

---

## 6. Depth & Elevation

Supabase uses minimal elevation. The dark theme creates depth through surface color steps, not drop shadows.

### Surface Stack (dark to light)

| Level | Background  | Usage                        |
|-------|-------------|------------------------------|
| 0     | `#151515`   | Sidebar, dialogs, overlays   |
| 1     | `#1C1C1C`   | Canvas, page background      |
| 2     | `#222222`   | Controls, inputs, card base  |
| 3     | `#282828`   | Hover states, featured cards |
| 4     | `#2D2D2D`   | Button default, elevated bg  |
| 5     | `#343434`   | Active/hover button, borders |

### Shadows

```css
/* Rarely used. Prefer surface color step instead. */
--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
--shadow-md: 0 4px 12px rgba(0, 0, 0, 0.4);
--shadow-lg: 0 12px 32px rgba(0, 0, 0, 0.5);

/* Brand glow -- used sparingly for emphasis */
--glow-brand: 0 0 20px rgba(62, 207, 142, 0.15);
--glow-brand-strong: 0 0 40px rgba(62, 207, 142, 0.25);
```

### Overlays

```
Backdrop: rgba(0, 0, 0, 0.6)
Modal: bg #151515, border 1px solid #2D2D2D
Toast: bg #2D2D2D, border 1px solid #3D3D3D, slight shadow
```

---

## 7. Do's and Don'ts

### Do

- Use the brand green (`#3ECF8E`) for primary CTAs, active nav items, and positive states only.
- Use monospace for anything a developer would type or read in a terminal.
- Step through the gray-dark scale for elevation; avoid adding shadows where a darker background step suffices.
- Use `rgba(62, 207, 142, 0.1)` for subtle brand-tinted highlights (flash animations, hover accents).
- Keep data tables compact (28px row height). Developers expect density.
- Use `#BDA4FF` for code keywords and `#FFCDA1` for strings to create syntax-highlighted content blocks.
- Round corners at 6-8px. Not 0 (too harsh), not 16px (too bubbly for a dev tool).

### Don't

- Do not use the brand green as a background color for large surface areas. It is an accent, not a fill.
- Do not use pure white (`#FFFFFF`) for body text on dark backgrounds. Use `#ECECEC` instead; pure white creates excessive contrast.
- Do not add colored shadows or gradients to cards. Supabase surfaces are flat and distinguished by background value.
- Do not use rounded display fonts or playful typefaces. The tone is technical and precise.
- Do not center-align long-form prose. Left-align everything except hero headlines and short taglines.
- Do not use more than two font weights in a single view (400 and 500).
- Do not apply `border-radius: 9999px` to anything that is not a badge, tag, or pill button.
- Do not use the slate palette and gray palette interchangeably in the same view. Pick one neutral track.

---

## 8. Responsive Behavior

### Breakpoints

| Name     | Min Width | Layout Changes                       |
|----------|-----------|--------------------------------------|
| `sm`     | 640px     | Single column, full-width cards      |
| `md`     | 768px     | Two-column card grids, sidebar hidden |
| `lg`     | 1024px    | Sidebar visible (collapsed), 2-3 col grids |
| `xl`     | 1280px    | Full sidebar, max content width      |
| `2xl`    | 1536px    | Wider gutters, more whitespace       |

### Mobile Adaptations

- **Sidebar:** Hidden below `lg`, replaced by hamburger menu with slide-out drawer (bg `#151515`).
- **Data tables:** Horizontally scrollable with sticky first column. Row height stays 28px.
- **Code blocks:** Horizontally scrollable. Never truncate or hide code content.
- **Navigation:** Top nav collapses to logo + hamburger + CTA button.
- **Hero:** Stack headline, body, and CTA vertically. Reduce display-xl to `2rem` at `sm`.
- **Card grids:** Shift from multi-column to single-column stacked cards.
- **Padding:** Page horizontal padding reduces from 32px to 16px at `sm`.

### Dashboard-Specific

- Sidebar collapses from 240px to 48px (icon-only) at `lg`, hides completely at `md`.
- Panel resizers maintain 2px grab area (`--panel`).
- Table column widths are user-adjustable; minimum column width is 80px.
- Mobile dashboard shows a bottom tab bar instead of sidebar.
