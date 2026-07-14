# Notion Design System

## 1. Visual Theme & Atmosphere

Notion embodies **warm minimalism** — the aesthetic of a well-lit study, not a cold lab. Surfaces feel like quality paper. Typography carries intellectual weight through serif headings while the body stays crisp and readable. Every element breathes; nothing is crowded. The overall impression is calm competence: a tool that respects your attention and gets out of the way.

**Atmosphere keywords:** warm, calm, scholarly, approachable, paper-like, unhurried, trustworthy

**Core visual traits:**
- Cream and warm whites dominate — never pure white (#FFF) on large surfaces
- Serif headings create a book-like cadence; sans-serif body keeps scanning fast
- Shadows are whispered, not shouted — surfaces lift gently, never float dramatically
- Icons and illustrations use thin strokes at 1.5px, never filled heavy shapes
- Color is used sparingly as semantic accent, never as decoration
- Interaction feedback is subtle: soft hovers, gentle transitions (150–200ms)

---

## 2. Color Palette & Roles

### Surface Colors

| Name | Hex | Role |
|------|-----|------|
| bg-primary | #FFFFFF | Page canvas, main content area (used with warm surrounding context) |
| bg-warm | #FBFBFA | App shell background, sidebar backdrop |
| bg-cream | #F7F6F3 | Sidebar surface, panel backgrounds |
| bg-hover | #EBEBEA | Hover state for list items, menu rows |
| bg-active | #E3E3E2 | Active/pressed state |
| bg-selected | #2EAADC1A | Selected item highlight (blue at 10% opacity) |

### Text Colors

| Name | Hex | Role |
|------|-----|------|
| text-primary | #37352F | Body text, headings — the universal dark ink |
| text-secondary | #9B9A97 | Placeholder text, secondary labels, timestamps |
| text-tertiary | #C4C4C4 | Disabled text, dividers within text |
| text-link | #379ADC | Hyperlinks, navigational anchors |
| text-on-accent | #FFFFFF | Text on colored buttons/badges |

### Accent / Semantic Colors

| Name | Hex | Role |
|------|-----|------|
| accent-blue | #2EAADC | Primary actions, links, selection highlights |
| accent-blue-hover | #299FC7 | Blue hover state |
| accent-red | #EB5757 | Errors, destructive actions, warnings |
| accent-red-hover | #D14343 | Red hover state |
| accent-green | #0F7B6C | Success, confirmations, positive indicators |
| accent-yellow | #DFAB01 | Caution, pending states |
| accent-orange | #D9730D | Attention, secondary warnings |
| accent-pink | #AD1A72 | Tags, category markers |
| accent-purple | #6940A5 | Tags, category markers |

### Border / Divider

| Name | Hex | Role |
|------|-----|------|
| border-default | #E9E9E7 | Input borders, card outlines, table borders |
| border-hover | #D3D3D1 | Hover state on borders |
| divider | #E9E9E7 | Horizontal rules, section dividers |

### Notion Color Tags (inline text/background pairs)

| Tag | Text Hex | Background Hex |
|-----|----------|----------------|
| Blue | #2EAADC | #2EAADC1A |
| Red | #EB5757 | #EB57571A |
| Green | #0F7B6C | #0F7B6C1A |
| Yellow | #DFAB01 | #DFAB011A |
| Orange | #D9730D | #D9730D1A |
| Pink | #AD1A72 | #AD1A721A |
| Purple | #6940A5 | #6940A51A |
| Gray | #9B9A97 | #9B9A971A |
| Brown | #64473A | #64473A1A |

---

## 3. Typography Rules

### Font Stack

- **Serif headings:** `"Noto Serif", "Ionicons", "Apple Color Emoji", Georgia, serif`
- **Sans-serif body:** `ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif`
- **Monospace code:** `"SFMono-Regular", Menlo, Consolas, "PT Mono", "Liberation Mono", Courier, monospace`

### Hierarchy

| Level | Font | Weight | Size | Line Height | Letter Spacing |
|-------|------|--------|------|-------------|----------------|
| H1 | Serif | 700 | 30px | 1.3 | -0.02em |
| H2 | Serif | 600 | 24px | 1.3 | -0.015em |
| H3 | Serif | 600 | 20px | 1.4 | -0.01em |
| H4 | Sans-serif | 600 | 16px | 1.5 | 0 |
| Body | Sans-serif | 400 | 16px | 1.6 | 0 |
| Body small | Sans-serif | 400 | 14px | 1.5 | 0 |
| Caption | Sans-serif | 400 | 12px | 1.5 | 0 |
| Code | Monospace | 400 | 14px | 1.6 | 0 |
| Button label | Sans-serif | 500 | 14px | 1.0 | 0 |
| Overline / label | Sans-serif | 500 | 12px | 1.3 | 0.02em |

### Key Typography Rules

1. **Serif is for headings only (H1–H3).** H4 and below use sans-serif. This creates the signature "book chapter" feel at the top of the hierarchy.
2. **Never use italic serif for emphasis in headings.** Use weight changes instead (600 → 700).
3. **Body text stays at 16px minimum.** 14px for secondary text, 12px only for captions and labels.
4. **Code blocks use 14px monospace** on a slightly tinted background (#F7F6F3).
5. **Line height is generous** — 1.6 for body, 1.3 for headings — mirroring print book readability.
6. **Text color is always #37352F** (warm near-black), never pure #000000.

---

## 4. Component Stylings

### Buttons

**Primary button**
```
background: #2EAADC
color: #FFFFFF
border-radius: 4px
padding: 6px 12px
font: 500 14px/1 sans-serif
height: 32px
transition: background 120ms ease
```
- Hover: background #299FC7
- Active: background #2491B5, translateY(0.5px)
- Disabled: opacity 0.5, cursor not-allowed

**Secondary button**
```
background: #FFFFFF
color: #37352F
border: 1px solid #E9E9E7
border-radius: 4px
padding: 6px 12px
font: 500 14px/1 sans-serif
height: 32px
```
- Hover: background #FBFBFA, border #D3D3D1
- Active: background #F7F6F3

**Destructive button**
```
background: #EB5757
color: #FFFFFF
border-radius: 4px
padding: 6px 12px
font: 500 14px/1 sans-serif
height: 32px
```
- Hover: background #D14343

**Ghost / Text button**
```
background: transparent
color: #37352F
border: none
border-radius: 4px
padding: 4px 8px
font: 500 14px/1 sans-serif
```
- Hover: background #EBEBEA

**Icon button (32x32)**
```
background: transparent
border: none
border-radius: 4px
width: 32px
height: 32px
display: inline-flex
align-items: center
justify-content: center
```
- Hover: background #EBEBEA
- Active: background #E3E3E2

### Cards

**Page card / Content block**
```
background: #FFFFFF
border: 1px solid #E9E9E7
border-radius: 8px
padding: 16px
```
- Hover: subtle border darkening to #D3D3D1
- No box-shadow in default state — cards sit flat on the surface
- Cover images: 16:9 ratio, border-radius 4px on the image inside the card

**Sidebar card / Nested panel**
```
background: #F7F6F3
border: none
border-radius: 6px
padding: 8px 10px
```

### Inputs / Text Fields

**Standard input**
```
background: #FFFFFF
border: 1px solid #E9E9E7
border-radius: 4px
padding: 8px 10px
font: 400 16px/1.5 sans-serif
color: #37352F
height: 32px
```
- Focus: border #2EAADC, box-shadow 0 0 0 2px #2EAADC33
- Placeholder: color #9B9A97
- Error: border #EB5757, box-shadow 0 0 0 2px #EB575733
- Disabled: background #F7F6F3, color #9B9A97

**Search input**
```
background: #F7F6F3
border: 1px solid transparent
border-radius: 4px
padding: 8px 10px 8px 36px (space for search icon)
font: 400 16px/1.5 sans-serif
color: #37352F
```
- Focus: background #FFFFFF, border #E9E9E7, box-shadow 0 0 0 2px #2EAADC33

**Multi-line / Textarea**
- Same as standard input but min-height 80px, vertical resize only
- Line height 1.6

### Navigation / Sidebar

**Sidebar panel**
```
background: #F7F6F3
width: 240px (collapsible)
padding: 10px 6px
```

**Sidebar item (page link)**
```
padding: 4px 8px
border-radius: 4px
font: 400 14px/1.4 sans-serif
color: #37352F
```
- Hover: background #EBEBEA
- Active: background #2EAADC1A, color #37352F
- Icon + label: 20px icon left, 8px gap to label

**Breadcrumbs**
```
font: 400 14px/1 sans-serif
color: #9B9A97
separator: "/" with 4px margin each side
```
- Current page: color #37352F, font-weight 500

### Toggles & Checkboxes

**Toggle**
- Track: 36x20px, border-radius 10px
- Off: background #E9E9E7
- On: background #2EAADC
- Thumb: 16x16px circle, background #FFFFFF, translateY offset
- Transition: 150ms ease

**Checkbox**
- 16x16px, border-radius 3px
- Unchecked: border 2px solid #9B9A97, background transparent
- Checked: background #2EAADC, border #2EAADC, white checkmark
- Transition: 120ms ease

### Tags / Badges

```
padding: 2px 8px
border-radius: 3px
font: 500 12px/1.3 sans-serif
```
- Uses the Notion color tag pairs (text color on matching 10% opacity background)
- Example: Blue tag = color #2EAADC, background #2EAADC1A

### Tooltips

```
background: #37352F
color: #FFFFFF
padding: 4px 8px
border-radius: 4px
font: 400 12px/1.3 sans-serif
max-width: 240px
```
- Appears 4px below trigger element
- Fade in 100ms ease

---

## 5. Layout Principles

### Spacing Scale

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Inline gaps, icon-to-label |
| sm | 8px | Compact list item padding, badge padding |
| md | 12px | Button padding (horizontal), form field gaps |
| lg | 16px | Card padding, section inner padding |
| xl | 24px | Between related sections |
| 2xl | 32px | Between distinct content blocks |
| 3xl | 48px | Page section separators |
| 4xl | 64px | Top-level page sections |

### Grid & Container

- **Content width:** 708px (Notion's standard page width for readable content)
- **Wide content:** 936px (for tables, kanban boards, media)
- **Full width:** 100% minus sidebar (for databases, galleries)
- **Sidebar:** 240px default, 48px collapsed (icons only)
- **Column gap in multi-column:** 24px
- **No explicit CSS grid for page layout** — content flows vertically with horizontal blocks

### Whitespace Philosophy

1. **Generous top margins on headings.** H1: 32px top margin. H2: 24px. H3: 16px. This creates a clear visual rhythm.
2. **List items breathe.** Minimum 4px vertical padding per item. Nested items indent 24px.
3. **Content never touches edges.** Minimum 16px horizontal padding inside any container.
4. **Section breaks use space, not lines.** Prefer 48–64px vertical spacing between sections over visible dividers. Use dividers (#E9E9E7) only when semantic separation is needed within a tight space.
5. **Inline elements get breathing room.** 4px minimum gap between icon and label, 8px between adjacent actions.

### Alignment

- Content is left-aligned by default. Center alignment only for hero statements or empty states.
- Headings are left-aligned, never centered in body content.
- Labels sit above inputs (stacked), not beside them, to maintain vertical rhythm.

---

## 6. Depth & Elevation

Notion avoids dramatic depth. Surfaces feel like sheets of paper on a desk — some stacked, but all resting flat.

### Shadow Levels

| Level | Shadow | Usage |
|-------|--------|-------|
| Level 0 | none | Cards on page, sidebar items |
| Level 1 | 0 1px 2px rgba(0,0,0,0.06) | Hovered cards, raised panels |
| Level 2 | 0 2px 8px rgba(0,0,0,0.08) | Dropdowns, popovers, tooltips |
| Level 3 | 0 4px 16px rgba(0,0,0,0.1) | Modals, dialogs |
| Level 4 | 0 8px 32px rgba(0,0,0,0.12) | Full-screen overlays, command palette |

### Elevation Rules

1. **Default state: no shadow.** Cards and content blocks sit flush on the background.
2. **Borders do the work shadows usually do.** 1px #E9E9E7 borders delineate boundaries without implying elevation.
3. **Shadows appear on interaction.** A card might gain Level 1 shadow on hover, a dropdown gets Level 2 on open.
4. **Background tint implies depth, not shadow.** The sidebar is #F7F6F3 (cream), the content area is #FFFFFF. This subtle warmth shift creates perceived depth without rendering shadows.
5. **Overlays use opacity, not shadow.** Modal backdrops: rgba(0,0,0,0.4) with no blur. This keeps things warm and accessible.
6. **Never use inset shadows.** Notion surfaces are always convex, never concave.

### Surface Hierarchy (bottom to top)

1. `#F7F6F3` — Sidebar / background panels
2. `#FFFFFF` — Main content area / canvas
3. `#FFFFFF` + Level 1 border — Cards on the canvas
4. `#FFFFFF` + Level 2 shadow — Dropdowns, popovers
5. `#FFFFFF` + Level 3 shadow — Modals
6. `#37352F` at 85% opacity — Full overlay backdrop

---

## 7. Do's and Don'ts

### Do

- Use serif for H1–H3 headings; it is the single most distinctive Notion signature
- Keep backgrounds warm — use #FBFBFA or #F7F6F3 instead of pure #FFFFFF for shells
- Use color tags (10% opacity backgrounds) for inline categorization — they feel native to the writing surface
- Default to no shadows; add them only when an element needs to float (dropdowns, modals)
- Use generous line height (1.6 body, 1.3 headings) for readability
- Keep borders at 1px #E9E9E7 — they should suggest boundaries, not draw attention
- Use 4px border-radius for inputs/buttons, 6–8px for cards, 3px for tags — subtle rounding only
- Preserve ample whitespace above headings (32px, 24px, 16px for H1/H2/H3)
- Use icon buttons at 32x32px with hover backgrounds — not outlined or shadowed buttons
- Animate at 120–200ms with ease timing — fast enough to feel responsive, slow enough to perceive

### Don't

- Don't use pure #000000 for text — always #37352F (warm near-black)
- Don't apply bold colors to large surfaces — accent colors are for small highlights, tags, and interactive elements
- Don't use gradients anywhere — Notion surfaces are flat and solid
- Don't use serif for body text or UI labels — it belongs in headings only
- Don't add box-shadows to resting-state cards — borders are sufficient
- Don't use rounded-full (pill) shapes — maximum border-radius is 8px
- Don't use heavy/filled icons — prefer outlined/thin stroke style at 1.5px
- Don't use dark mode as primary — Notion is fundamentally a light, warm surface product
- Don't use bright saturated backgrounds — all backgrounds are neutral or pastel (10% tint)
- Don't add visible grid lines to layouts — use spacing and alignment instead
- Don't center-align body text or headings in content areas — left alignment is the default rhythm
- Don't use animations longer than 300ms — the interface should feel immediate and paper-like

---

## 8. Responsive Behavior

### Breakpoints

| Name | Width | Layout Behavior |
|------|-------|-----------------|
| Mobile | < 640px | Single column, sidebar hidden (hamburger toggle), stacked cards |
| Tablet | 640–1024px | Sidebar collapsed to 48px icon rail, content at 640px max-width |
| Desktop | 1024–1440px | Sidebar at 240px, content at 708px max-width centered |
| Wide | > 1440px | Same as Desktop, extra whitespace distributed symmetrically |

### Mobile Adaptations (< 640px)

- **Sidebar:** Hidden off-screen, accessed via hamburger button (top-left). Slides in as overlay with Level 2 shadow.
- **Content width:** Full width minus 16px horizontal padding on each side.
- **Headings:** Reduce by 4px. H1: 26px, H2: 20px, H3: 18px. Maintain serif.
- **Cards:** Full-width, stacked vertically with 16px gap between them. No multi-column layouts.
- **Navigation:** Bottom tab bar for primary navigation (replacing sidebar), top bar for breadcrumbs and actions.
- **Tables:** Horizontal scroll with sticky first column. Or convert to list/card view.
- **Buttons:** Minimum touch target 44x44px. Add padding to reach minimum — don't scale font up.
- **Inputs:** Full width, height 44px (increased from 32px for touch).
- **Spacing:** Reduce 3xl/4xl to xl/2xl (48/64px → 24/32px). Maintain xs/sm/md unchanged.

### Tablet Adaptations (640–1024px)

- **Sidebar:** Collapsed to 48px icon rail. Tap icon to expand full sidebar as overlay.
- **Content width:** 640px max, centered.
- **Multi-column:** Maximum 2 columns. 3+ columns collapse to 2 or 1.
- **Cards:** 2-column grid for gallery/grid views.

### Desktop (1024px+)

- Standard layout as described in Section 5.
- Multi-column content allowed at wide width (936px).
- Sidebar fully expanded by default.

### Responsive Transitions

- Sidebar collapse/expand: 200ms ease with width transition
- Content reflow: No animation needed — content should reflow instantly
- Breakpoint changes: Layout shifts at breakpoints with no animation (not fluid) to maintain Notion's crisp, paper-like feel
