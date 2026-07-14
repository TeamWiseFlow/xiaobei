# Spotify Design System

## 1. Visual Theme & Atmosphere

Spotify's visual identity is built on a tension between darkness and vibrancy. The near-black canvas makes the signature green and album art explode forward. It feels like a club, not a boardroom: confident, rhythmic, and image-forward.

**Atmosphere keywords:** immersive, bold, musical, confident, dark-first, cover-art-driven

**Core tension:** Maximum visual impact from minimal color variation. One accent hue carries the entire brand. All other color comes from content (album art, artist photos, video thumbnails).

**Mood:** Energy at rest. The UI is calm until the user plays something, then the green pulses and the artwork dominates. Surfaces stay out of the way. Content is always the star.

---

## 2. Color Palette & Roles

### Primary

| Token | Hex | Role |
|-------|-----|------|
| `--color-spotify-green` | `#1DB954` | Primary accent, CTAs, active states, brand marks |
| `--color-spotify-green-light` | `#1ED760` | Hover/pressed state for green elements |
| `--color-spotify-green-dark` | `#1AA34A` | Active/pressed variant on dark surfaces |

### Surfaces (Dark Mode -- default)

| Token | Hex | Role |
|-------|-----|------|
| `--color-bg-base` | `#121212` | Page background, root surface |
| `--color-bg-elevated` | `#181818` | Card surfaces, sidebar, containers |
| `--color-bg-highlight` | `#282828` | Hover states on cards, list items |
| `--color-bg-press` | `#333333` | Active/pressed states on interactive items |
| `--color-bg-subtle` | `#1A1A1A` | Subtle surface differentiation |

### Text

| Token | Hex | Role |
|-------|-----|------|
| `--color-text-primary` | `#FFFFFF` | Headlines, primary body text |
| `--color-text-secondary` | `#B3B3B3` | Metadata, descriptions, timestamps |
| `--color-text-subdued` | `#6A6A6A` | Disabled states, placeholder text |
| `--color-text-on-green` | `#000000` | Text on green buttons/badges |

### Semantic

| Token | Hex | Role |
|-------|-----|------|
| `--color-error` | `#E91429` | Error states, destructive actions |
| `color-warning` | `#FFC862` | Warnings, offline indicators |
| `--color-link` | `#1DB954` | Links (same as primary green) |

### Content-Driven Colors

Spotify derives contextual color from album art and artist imagery. Use these as overlay tints on surfaces:

| Token | Usage |
|-------|-------|
| `--color-tint` | Dominant color extracted from current album art, applied as a subtle gradient behind hero sections and now-playing bar |

---

## 3. Typography Rules

### Font Stack

- **Primary:** `Circular`, `-apple-system`, `BlinkMacSystemFont`, `Segoe UI`, `Roboto`, `Helvetica Neue`, `sans-serif`
- **Fallback system stack** is acceptable when Circular is unavailable. Never use decorative or serif faces.

### Scale

| Token | Size | Weight | Line Height | Usage |
|-------|------|--------|-------------|-------|
| `--text-display` | `72px` | 900 (Black) | 1.0 | Hero headlines, landing page statements |
| `--text-title-lg` | `48px` | 700 (Bold) | 1.1 | Section headers, playlist titles |
| `--text-title` | `32px` | 700 (Bold) | 1.2 | Card titles, subsection headers |
| `--text-title-sm` | `24px` | 600 (SemiBold) | 1.25 | List headers, nav items |
| `--text-body-lg` | `18px` | 400 (Regular) | 1.5 | Intro paragraphs, feature descriptions |
| `--text-body` | `14px` | 400 (Regular) | 1.5 | Body text, list items, metadata |
| `--text-caption` | `12px` | 400 (Regular) | 1.4 | Timestamps, track numbers, small labels |
| `--text-overline` | `10px` | 700 (Bold) | 1.6 | Uppercase labels, category tags |

### Rules

- Headlines are always bold or black weight. Regular-weight headlines are forbidden.
- Body text on dark surfaces is `#B3B3B3`, never pure white. White body text causes eye strain on `#121212`.
- Use `text-transform: uppercase` only on overline labels (`10px` bold). Never uppercase headlines.
- Letter-spacing: default for most sizes; `+0.1em` for overline labels only.
- Never center-align body text. Left-align always. Headlines may be center-aligned only in hero sections.

---

## 4. Component Stylings

### Buttons

| Variant | Background | Text | Border | Radius |
|---------|-----------|------|--------|--------|
| Primary | `#1DB954` | `#000000` | none | `500px` (pill) |
| Primary hover | `#1ED760` | `#000000` | none | `500px` |
| Secondary | `transparent` | `#FFFFFF` | `2px solid #FFFFFF` | `500px` |
| Secondary hover | `#FFFFFF` `1a` | `#FFFFFF` | `2px solid #FFFFFF` | `500px` |
| Ghost | `transparent` | `#B3B3B3` | none | `500px` |
| Ghost hover | `#333333` | `#FFFFFF` | none | `500px` |

- Padding: `12px 32px` for standard, `8px 20px` for compact.
- Font: `14px bold` with `letter-spacing: 0.02em`.
- All buttons are pill-shaped (`border-radius: 500px`). Rounded rectangles are forbidden for CTAs.
- Icon + label buttons: `8px` gap, icon at `20px` size.

### Cards

- Background: `#181818`
- Border: none
- Radius: `8px`
- Padding: `16px`
- Hover: background transitions to `#282828` over `300ms ease`
- Image: square aspect ratio for album/playlist art, `4px` radius on the image
- Title: `16px bold`, single line with `text-overflow: ellipsis`
- Subtitle: `14px regular`, `#B3B3B3`, single line ellipsis

### Now Playing Bar

- Position: fixed bottom, full width
- Height: `80px`
- Background: `#181818` with `1px` top border `#282828`
- Progress bar: track `#535353`, filled `#FFFFFF`, hover filled `#1DB954`
- Progress bar height: `4px` default, `6px` on hover
- Thumb: `12px` white circle, appears on hover only

### Navigation / Sidebar

- Background: `#000000`
- Width: `280px` (collapsible to `72px`)
- Active item: `#282828` background, `#FFFFFF` text, `3px` left border `#1DB954`
- Inactive item: `transparent` background, `#B3B3B3` text
- Icon size: `24px`
- Item height: `40px`, padding `0 16px`

### Input Fields

- Background: `#333333`
- Border: `2px solid transparent`
- Focus border: `2px solid #1DB954`
- Text: `#FFFFFF` `14px`
- Placeholder: `#6A6A6A`
- Radius: `4px`
- Padding: `12px 16px`

### Toggles / Switches

- Track off: `#535353`, on: `#1DB954`
- Knob: `#FFFFFF` `20px` circle
- Track size: `40px x 20px`, radius `10px`

### Chips / Pills

- Background: `#333333`
- Text: `#FFFFFF` `13px regular`
- Selected: background `#1DB954`, text `#000000` `13px bold`
- Radius: `500px`
- Padding: `6px 16px`

---

## 5. Layout Principles

### Grid

- 12-column grid with `16px` gutters on desktop.
- Sidebar occupies fixed columns; main content fills remaining space.
- Card grids: auto-fill with `minmax(180px, 1fr)`.

### Spacing Scale

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xs` | `4px` | Tight internal gaps |
| `--space-sm` | `8px` | Icon gaps, inline spacing |
| `--space-md` | `16px` | Standard padding, card gutters |
| `--space-lg` | `24px` | Section internal padding |
| `--space-xl` | `32px` | Between sections |
| `--space-2xl` | `48px` | Page-level vertical rhythm |
| `--space-3xl` | `64px` | Hero section vertical padding |

### Album-Art-Driven Layout

Content grids are organized around cover art. The image is the primary visual anchor:

1. Image occupies the top or left of every content card.
2. Card hierarchy: image > title > subtitle. No card is without an image.
3. In hero contexts (playlist header, artist page), the cover art spans large and the background is tinted with the dominant color of the artwork.
4. List views use a `56px x 56px` thumbnail; grid views use square cards starting at `180px`.

### Z-Pattern for Landing Pages

Hero with bold headline and green CTA on the left, visual on the right. Alternate sections follow a zigzag. Always end with a green CTA section.

---

## 6. Depth & Elevation

Spotify uses minimal elevation. The dark palette does most of the separation work.

| Level | Shadow | Usage |
|-------|--------|-------|
| 0 | none | Default surface, page background |
| 1 | `0 2px 8px rgba(0,0,0,0.3)` | Cards at rest, sidebar |
| 2 | `0 4px 16px rgba(0,0,0,0.4)` | Hovered cards, tooltips |
| 3 | `0 8px 32px rgba(0,0,0,0.6)` | Modals, dropdown menus, now-playing bar |

### Rules

- No colored shadows. Shadows are always pure black with opacity.
- No borders on elevated surfaces. Use shadow alone for separation.
- The now-playing bar uses elevation level 3 because it must float above all scrolling content.
- Card hover transitions: shadow rises from level 1 to level 2 over `300ms ease`.
- Background color transitions on hover (`#181818` to `#282828`) happen simultaneously with shadow changes.

---

## 7. Do's and Don'ts

### Do

- Use `#1DB954` sparingly. It is an accent, not a fill color for large areas.
- Let album art and imagery carry the visual weight. The UI frame should disappear.
- Use pill-shaped buttons for all CTAs.
- Show progress with the green-to-gray bar pattern.
- Use `#B3B3B3` for secondary text on dark backgrounds.
- Transition hover states with `300ms ease` or `200ms ease-out`.
- Make image thumbnails square for music content.
- Extract tint color from album art for atmospheric backgrounds.
- Use bold/black weight for any text above `20px`.

### Don't

- Never use `#1DB954` as a background for large sections. Green surfaces beyond buttons and badges feel garish.
- Never use rounded-rectangle buttons. Spotify buttons are always pill-shaped.
- Never place white body text on `#121212` for paragraphs longer than one line.
- Never add colored borders or outlines to cards. Cards are borderless.
- Never use drop shadows on text. Spotify text is always flat.
- Never use serif fonts or decorative typefaces.
- Never animate more than one property at a time on interactive elements (hover = background color OR shadow, not both in conflicting directions).
- Never use `#1DB954` and `#E91429` adjacent to each other. The green-red clash is visually jarring.
- Never use placeholder images or empty states without a clear icon and label. The `#282828` card with a centered `#6A6A6A` icon and label is the standard empty state.

---

## 8. Responsive Behavior

### Breakpoints

| Name | Min Width | Layout |
|------|-----------|--------|
| Mobile | `0` | Single column, bottom nav, no sidebar |
| Tablet | `768px` | Two-column, collapsible sidebar |
| Desktop | `1024px` | Full sidebar + main content |
| Wide | `1440px` | Max-width container `1680px`, centered |

### Mobile Adaptations

- Sidebar becomes a bottom tab bar with 5 items (Home, Search, Library, Premium, icon-only).
- Cards switch to a horizontal scroll row instead of a grid.
- Now-playing bar shrinks to `64px` with artwork thumbnail, track name, and play/pause only. Full controls expand on tap.
- Hero sections collapse: headline drops to `--text-title` (`32px`), image scales down.
- Pill buttons stretch to full width with `16px` horizontal margin.
- Search input is full width with `16px` horizontal padding.

### Tablet Adaptations

- Sidebar collapses to icon-only (`72px` width) by default, expands on tap.
- Card grid uses `minmax(150px, 1fr)`.
- Now-playing bar remains at `80px`.

### Desktop Adaptations

- Sidebar is fully expanded (`280px`) with text labels.
- Card grid uses `minmax(180px, 1fr)`.
- Hover states are active (no hover on mobile/tablet touch).

### Image Sizing

| Context | Mobile | Tablet | Desktop |
|---------|--------|--------|---------|
| Hero cover art | `128px` | `192px` | `232px` |
| Grid card thumbnail | `100%` width, square | `100%` width, square | `100%` width, square |
| List thumbnail | `48px` | `56px` | `56px` |
| Now-playing art | `48px` | `56px` | `56px` |

### Touch Targets

- Minimum `44px x 44px` on mobile and tablet.
- Minimum `32px x 32px` on desktop.
- Playback controls (play/pause, skip): minimum `48px x 48px` on all sizes.
