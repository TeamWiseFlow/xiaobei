# Starbucks Design System

Warm Siren green on a cream canvas. The "third place" made digital — not home, not work, but somewhere that feels like both. Starbucks' visual language wraps every surface in the warmth of a coffeehouse: soft cream backgrounds instead of sterile whites, pill-shaped buttons that feel approachable, a family of greens that echo the iconic apron, and typefaces designed to feel like they have always been part of the brand. The Siren is the muse; everything else serves her world.

---

## 1. Visual Theme & Atmosphere

Starbucks' design language translates the physical coffeehouse into a digital experience. The core philosophy is "third place" — a welcoming space between home and work where warmth, craft, and community converge. Every surface should feel like it has been touched by human hands, not stamped by a machine. The warm cream canvas is the coffeehouse wall; the green accents are the barista's apron visible across the room; the rounded corners are the curve of a ceramic cup.

The page is a coffeehouse. Cream and warm neutrals are the walls and wood tables. Starbucks Green is the apron and the Siren — visible from across the room, never wallpapered over every surface. Photography shows real people in real moments: hands around cups, steam rising, morning light through windows. Illustration carries the hand-drawn legacy — the Siren, line art, seasonal artwork — never generic iconography. Typography speaks in Sodo Sans for everyday warmth, Pike for bold menu-board headlines, and Lander for artful expressive moments.

Color is anchored in a family of greens that leverages instant brand recognition. The green is never decorative — it is structural. Expressive seasonal palettes evolve with trends, but brand green is always present, either in the composition or through the Siren logo. The overall feeling is optimistic, joyful, and recognizably Starbucks: calm confidence with artful warmth.

**Keywords:** warm, inviting, community, craft, approachable, coffeehouse, third place, Siren green, natural, artful

---

## 2. Color Palette & Roles

Starbucks' color system centers on a four-tier family of greens — Starbucks Green, Accent Green, Light Green, and House Green — layered over a warm cream canvas. Neutrals are warm, never cool. The dark palette uses deep green and earth tones, never pure black.

### Light Mode

| Token | Hex | Role |
|-------|-----|------|
| `--color-canvas` | `#F2F0EB` | Page background — warm cream, the coffeehouse canvas. Never pure white. |
| `--color-surface` | `#FFFFFF` | Card and container background on cream canvas |
| `--color-surface-warm` | `#FAF8F5` | Subtle warm tint for featured sections, alternating bands |
| `--color-surface-green` | `#D4E9E2` | Light green surface for highlighted content, reward tiers |
| `--color-ink` | `#1E3932` | Primary text — House Green, deep and warm, never pure black |
| `--color-body` | `#2F2E2C` | Default running text — warm black with earth undertone |
| `--color-muted` | `#61605B` | Secondary text, descriptions, helper text |
| `--color-muted-soft` | `#8C8B86` | Tertiary text, placeholder, timestamps |
| `--color-starbucks-green` | `#00704A` | Siren Green — primary brand accent, CTAs, active states, logo. The iconic apron green. |
| `--color-accent-green` | `#00A862` | Accent Green — hover and secondary green actions, progress indicators |
| `--color-light-green` | `#D4E9E2` | Light Green — tinted backgrounds, selected states, subtle brand presence |
| `--color-house-green` | `#1E3932` | House Green — deep green-black, primary text, footer backgrounds |
| `--color-primary-hover` | `#005C3E` | Hover state for Siren Green elements |
| `--color-primary-active` | `#004D34` | Active/pressed state for Siren Green |
| `--color-on-green` | `#FFFFFF` | White text on green buttons and badges |
| `--color-warm-neutral` | `#C8C5BE` | Warm gray borders, subtle dividers |
| `--color-cool-neutral` | `#A7A9AB` | Cool neutral for specific secondary elements, rarely used |
| `--color-gold` | `#C2A461` | Gold/Star accent — Rewards stars, premium tier indicators |
| `--color-success` | `#00704A` | Positive, confirmed — reuses brand green |
| `--color-warning` | `#D4A017` | Caution, pending states |
| `--color-error` | `#C62828` | Destructive, error, unavailable |
| `--color-border` | `#E0DDD6` | Default borders, input borders, card outlines |

### Dark Mode

| Token | Hex | Role |
|-------|-----|------|
| `--color-canvas` | `#1E3932` | Page background — House Green, deep and warm, not pure black |
| `--color-surface` | `#2A4A40` | Card and container background on dark canvas |
| `--color-surface-elevated` | `#345C4F` | Elevated container — modals, dropdowns |
| `--color-surface-warm` | `#243D35` | Subtle warm differentiation on dark canvas |
| `--color-surface-green` | `#1A3B30` | Dark green tint for highlighted content |
| `--color-ink` | `#F2F0EB` | Primary text on dark — warm cream |
| `--color-body` | `#D4D1CB` | Default running text on dark |
| `--color-muted` | `#A0A08C` | Secondary text on dark |
| `--color-muted-soft` | `#7A7A6E` | Tertiary text on dark |
| `--color-starbucks-green` | `#00A862` | Siren Green shifts lighter on dark — Accent Green becomes the primary interactive color |
| `--color-accent-green` | `#1DB954` | Brighter accent on dark — hover states, secondary green |
| `--color-light-green` | `#1A3B30` | Dark green tint background |
| `--color-house-green` | `#1E3932` | Unchanged — this IS the dark canvas |
| `--color-primary-hover` | `#00C070` | Hover on dark — shifted lighter |
| `--color-primary-active` | `#00D480` | Active on dark — shifted lighter still |
| `--color-on-green` | `#FFFFFF` | White text on green buttons (unchanged) |
| `--color-warm-neutral` | `#4A5E55` | Borders on dark |
| `--color-gold` | `#D4B46A` | Gold on dark — shifted lighter for contrast |
| `--color-success` | `#1DB954` | Positive on dark — shifted lighter |
| `--color-warning` | `#E6B422` | Warning on dark |
| `--color-error` | `#EF5350` | Error on dark — shifted lighter |
| `--color-border` | `#3A5A4D` | Borders on dark surfaces |

**Rule:** Starbucks Green (`#00704A`) is the brand's most identifiable asset — visible for blocks, as they say. On dark surfaces it shifts to Accent Green (`#00A862`) for legibility. The warm cream canvas (`#F2F0EB`) is never replaced with pure white in light mode, and pure black (`#000000`) is never used as a dark background — House Green (`#1E3932`) carries the warmth into darkness. The green family must always be present, either within the composition or through the Siren logo.

### Seasonal Expression Palettes

Starbucks evolves expressive colors with seasonal trends while keeping brand greens constant:

| Season | Accent Tones | Usage |
|--------|-------------|-------|
| Spring | Soft pinks, fresh yellows, sage | Promotional banners, seasonal menus, app highlights |
| Summer | Bright corals, turquoise, sunny gold | Cold beverage promotions, Frappuccino campaigns |
| Fall | Burnt orange, deep burgundy, warm brown | Pumpkin spice, holiday countdown, warm beverage imagery |
| Winter/Nitro | Deep navy, icy blue, silver | Nitro Cold Brew, holiday red cup season, gift guides |

---

## 3. Typography Rules

### Font Stack

- **Primary (body, UI):** `Sodo Sans`, `-apple-system`, `BlinkMacSystemFont`, `Segoe UI`, `Roboto`, `Helvetica Neue`, `sans-serif`
- **Display (headlines, wayfinding):** `Pike`, `Sodo Sans Condensed`, `Impact`, `Arial Narrow`, `sans-serif`
- **Expressive (accent moments):** `Lander`, `Georgia`, `Cambria`, `Times New Roman`, `serif`

Sodo Sans is a geometric sans with a friendly character — double-storey 'g' for legibility, symmetrical 'u' echoing the brand logotype. It comes in three widths: Normal, Narrow, and Condensed, providing finer control in typesetting. Pike is a condensed display face with an increased x-height, designed for impactful headlines and menu boards — it shares DNA with Sodo Sans but has its own stance. Lander is a serif with 1970s warmth, drawn in three optical sizes: Grande (large display), Tall (headlines), and Short (text). It provides artful, expressive contrast to the sans families.

### Scale

| Token | Size | Weight | Line Height | Tracking | Font | Usage |
|-------|------|--------|-------------|----------|------|-------|
| `--text-hero` | `clamp(40px, 5vw, 72px)` | 700 | 1.05 | `-0.02em` | Pike | Hero headlines, campaign statements, splash pages |
| `--text-display` | `clamp(32px, 3.5vw, 56px)` | 700 | 1.1 | `-0.015em` | Pike | Section heroes, major announcements |
| `--text-headline` | `clamp(24px, 2vw, 36px)` | 700 | 1.15 | `-0.01em` | Sodo Sans | Section headers, card hero titles |
| `--text-title` | `clamp(20px, 1.5vw, 28px)` | 600 | 1.2 | `-0.005em` | Sodo Sans | Subsection headers, feature titles |
| `--text-title-sm` | `18px` | 600 | 1.25 | `0` | Sodo Sans | List headers, nav items, card titles |
| `--text-body-lg` | `16px` | 400 | 1.6 | `0` | Sodo Sans | Intro paragraphs, feature descriptions, menu descriptions |
| `--text-body` | `14px` | 400 | 1.5 | `0` | Sodo Sans | Body text, list items, product details |
| `--text-caption` | `12px` | 400 | 1.4 | `0.01em` | Sodo Sans | Nutritional info, timestamps, small labels |
| `--text-overline` | `11px` | 700 | 1.6 | `0.08em` | Sodo Sans | Uppercase labels, category tags, section markers |
| `--text-expressive` | `clamp(28px, 3vw, 48px)` | 400 | 1.15 | `0` | Lander | Expressive moments, editorial headlines, seasonal features |

### Rules

- Headlines are always bold (700) or semibold (600). Regular-weight headlines are forbidden.
- Sodo Sans is the default for everything. Pike is reserved for display headlines where impact is needed — hero sections, menu boards, campaign banners. Lander is for artful, expressive moments — editorial features, seasonal storytelling, accent pull quotes.
- Body text on cream canvas uses `#2F2E2C` (warm black), never pure `#000000`. Pure black on warm cream creates visual tension.
- Use `text-transform: uppercase` only on overline labels and Pike display headlines. Sodo Sans headlines are always title-case or sentence-case.
- Letter-spacing: negative for headlines ( Pike at `-0.02em` to `-0.01em`), zero for body, positive only for overline labels and all-caps Pike treatments.
- Pike is frequently set in all-caps with generous tracking for menu boards and wayfinding — this is a signature Starbucks typographic treatment.
- Never center-align body text. Left-align always. Headlines may be center-aligned only in hero sections and campaign banners.
- Lander optical sizes: Grande for >48px display, Tall for 24-48px headlines, Short for <24px text. Using the wrong optical size produces either spindly hairlines or overly thick strokes.

---

## 4. Component Stylings

### Buttons

| Variant | Background | Text | Border | Radius |
|---------|-----------|------|--------|--------|
| Primary | `#00704A` | `#FFFFFF` | none | `50px` (pill) |
| Primary hover | `#005C3E` | `#FFFFFF` | none | `50px` |
| Primary active | `#004D34` | `#FFFFFF` | none | `50px` |
| Secondary | `transparent` | `#00704A` | `2px solid #00704A` | `50px` |
| Secondary hover | `#D4E9E2` | `#005C3E` | `2px solid #005C3E` | `50px` |
| Ghost | `transparent` | `#1E3932` | none | `50px` |
| Ghost hover | `#D4E9E2` | `#1E3932` | none | `50px` |
| Floating CTA (Frap) | `#00704A` | `#FFFFFF` | none | `999px` (circle) |

- Padding: `14px 32px` for standard, `10px 24px` for compact.
- Font: Sodo Sans `14px` weight 600 with `letter-spacing: 0.02em`.
- All buttons are pill-shaped (`border-radius: 50px`). Starbucks uses a universal 50px pill button — this is a defining signature.
- The floating circular CTA (Frap button) is used for primary single-action moments — order button, reorder, add to cart. It is a circle (not pill), typically 50px diameter, positioned floating bottom-right on mobile.
- Icon + label buttons: `8px` gap, icon at `20px` size.
- Transition: `200ms ease-out` for all state changes.

### Navigation

- Fixed top bar, `height: 60px`, `#FFFFFF` background with 1px `#E0DDD6` bottom border.
- Logo (Siren) left, navigation center or left-aligned, cart/account right.
- Siren logo preferred unlocked from wordmark — used by itself for a more modern, open presentation.
- Nav items: Sodo Sans `14px` weight 600, `#1E3932` text, `#00704A` active state.
- Hover: text color transitions to `#00704A` over `150ms ease`.
- Mobile: hamburger menu, Siren logo center, cart icon right.

### Cards (Product / Menu Item)

- Background: `#FFFFFF`, `border-radius: 16px`, no border (shadow-based depth on cream canvas).
- Image: `border-radius: 16px` matching card, aspect-ratio 1/1 for beverages, 3/2 for food/lifestyle.
- Product title: Sodo Sans `16px` weight 600, `#1E3932`, single line with `text-overflow: ellipsis`.
- Description: Sodo Sans `14px` weight 400, `#61605B`, two-line clamp.
- Price: Sodo Sans `16px` weight 700, `#1E3932`, positioned bottom-right.
- Hover: subtle lift (`translateY(-2px)`) + shadow increase over `200ms ease-out`.
- Featured cards: `border-radius: 20px`, larger padding, lifestyle imagery.

### Image Treatments

- **Lifestyle photography:** Warm lighting, natural settings, community moments. Hands holding cups, baristas at work, morning rituals. Never sterile studio shots.
- **Product photography:** Clean but warm — beverages on natural surfaces (wood, marble, canvas). Shallow depth of field, soft directional lighting.
- **Illustration:** Rooted in brand heritage. The Siren, line art, seasonal artwork. Texture, photo collage, composition, and graphic details give a custom, handcrafted feel. Never generic flat icons.
- **Image radius:** `16px` for standard, `20px` for hero/featured, `12px` for thumbnails, `8px` for inline images.
- **Overlay:** When text overlays imagery, use a gradient overlay from `rgba(30,57,50,0.7)` to `transparent` — House Green, not black.

### Data / Specs (Nutritional, Order Details)

- Background: `#FFFFFF`, `border-radius: 12px`, 1px `#E0DDD6` border.
- Header row: `#D4E9E2` light green background, Sodo Sans `12px` weight 700.
- Data rows: alternating `#FFFFFF` and `#FAF8F5`.
- Values: Sodo Sans `14px` weight 600 for numbers, `14px` weight 400 for labels.
- Divider: 1px `#E0DDD6` between rows.

### Rewards / Loyalty Elements

- Star icon: `#C2A461` gold fill, animated on earn.
- Progress bar: track `#E0DDD6`, filled `#C2A461` gradient to `#D4B46A`.
- Tier badges: circular with Sodo Sans Condensed all-caps label.
- Points/Stars display: Pike `24px` weight 700, `#C2A461` color.

---

## 5. Layout Principles

### Grid

- 12-column grid with `24px` gutters on desktop.
- Content max-width: `1200px`, centered.
- Card grids: `auto-fill, minmax(260px, 1fr)` for product listings.
- Menu/product layouts often use asymmetric grids — a hero feature card spanning 2 columns alongside standard single-column cards.

### Spacing Scale

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xs` | `4px` | Tight internal gaps, icon-text spacing |
| `--space-sm` | `8px` | Inline spacing, chip padding |
| `--space-md` | `16px` | Standard padding, card internal spacing |
| `--space-lg` | `24px` | Card gutters, section internal padding |
| `--space-xl` | `32px` | Between sections |
| `--space-2xl` | `48px` | Major section separation |
| `--space-3xl` | `64px` | Hero section vertical padding |
| `--space-4xl` | `96px` | Page-level vertical rhythm on desktop |

### Alignment Rules

- Left-align all body text and data. Center-align only hero headlines and campaign statements.
- Product imagery is typically center-aligned within its card container.
- Price and CTA are right-aligned or bottom-aligned within cards.
- The Siren logo is always centered within its container — never cropped, never rotated, never tilted.
- Menu items follow a consistent pattern: image left (or top), text content right (or bottom), price/CTA bottom-right.

### Coffeehouse Rhythm

Layout should breathe like a coffeehouse — not cramped like a fast-food menu board, and not sparse like a corporate lobby. Sections have generous vertical spacing. Content areas feel like distinct "seating zones" — the rewards area feels different from the menu area, separated by warmth and spacing rather than hard dividers. Warm cream (`#F2F0EB`) backgrounds alternate with white (`#FFFFFF`) sections to create natural flow without visible borders.

---

## 6. Depth & Elevation

Starbucks uses gentle, warm shadows on the cream canvas. The cream background does most of the separation work; shadows add subtle lift, not dramatic floating.

| Level | Shadow | Usage |
|-------|--------|-------|
| 0 | none | Default surface, cream canvas background |
| 1 | `0 2px 8px rgba(30,57,50,0.08)` | Cards at rest on cream canvas |
| 2 | `0 4px 16px rgba(30,57,50,0.12)` | Hovered cards, elevated inputs |
| 3 | `0 8px 24px rgba(30,57,50,0.16)` | Modals, dropdown menus, sticky elements |
| 4 | `0 12px 40px rgba(30,57,50,0.20)` | Full-screen overlays, prominent floating CTAs |

### Rules

- Shadows use House Green (`rgba(30,57,50,...)`) as the shadow color instead of pure black — this produces a warmer, more natural shadow that sits harmoniously on the cream canvas. Pure black shadows create cold contrast against warm surfaces.
- No colored shadows beyond the warm green tint. No green glow effects.
- Card hover: shadow rises from level 1 to level 2, combined with `translateY(-2px)` over `200ms ease-out`.
- Elevated surfaces (modals, dropdowns) on cream canvas use white (`#FFFFFF`) backgrounds — the contrast between white surface and cream canvas provides inherent separation even without shadow.
- On dark mode, shadows use deeper green tints: `rgba(0,0,0,0.3)` through `rgba(0,0,0,0.6)`.
- Borders and shadows are never used together on the same element. Choose one method of separation.

---

## 7. Do's and Don'ts

### Do

- Always maintain a presence of brand green — either within the composition or through the Siren logo. A page without green is not Starbucks.
- Use the warm cream canvas (`#F2F0EB`) as the default light background. Pure white is for cards and elevated surfaces only.
- Use pill-shaped buttons (`border-radius: 50px`) for all CTAs. This is a Starbucks signature.
- Let lifestyle photography carry the warmth — real moments, real people, natural light, community settings.
- Use Sodo Sans for body and UI text, Pike for impactful headlines and menu boards, Lander sparingly for expressive accent moments.
- Round everything generously — 16px for cards, 12px for inputs, 50px for buttons. Nothing sharp, nothing aggressive.
- Write conversationally — "What can we get started for you?" not "Begin Order". Warmth extends to copy.
- Use warm-tinted shadows (`rgba(30,57,50,...)`) instead of cold black shadows on the cream canvas.
- Feature the Siren logo unlocked from the wordmark for a modern, open presentation.
- Use seasonal expression palettes to stay relevant while keeping brand greens constant.
- Show the gold star (`#C2A461`) prominently in Rewards contexts — loyalty is a core experience.
- Design for mobile-first. The Starbucks app is the primary digital touchpoint for most customers.

### Don't

- Never use pure `#000000` as a background in dark mode. House Green (`#1E3932`) is the dark canvas. Pure black feels cold and corporate, not warm and inviting.
- Never use Siren Green (`#00704A`) as a background fill for large areas. Green is an accent and brand anchor, not a surface color.
- Never apply sharp corners (`border-radius: 0`) to any interactive element or card. Sharp corners contradict the warm, approachable brand.
- Never use cool gray palettes or blue undertones in neutrals. Starbucks neutrals are warm — cream, warm gray, earth tones.
- Never use generic stock photography or flat vector icons. Every image should feel like a real coffeehouse moment; every illustration should carry the handcrafted quality of the Siren tradition.
- Never center-align body text paragraphs. Left-align always.
- Never use regular weight (400) for headlines. Headlines demand weight — semibold (600) minimum, bold (700) preferred.
- Never rotate, distort, crop, or tilt the Siren logo. She always faces forward, centered, and complete.
- Never use more than two of the three typeface families (Sodo Sans, Pike, Lander) in a single view. Three is acceptable only in hero/campaign layouts where Lander provides a deliberate expressive accent.
- Never place white body text on `#F2F0EB` cream backgrounds — insufficient contrast. Use `#1E3932` House Green for text on cream.
- Never use green and red adjacent as equal-weight accents. The green-red clash reads as Christmas, not coffeehouse.
- Never hide pricing in product cards. Price visibility builds trust.

---

## 8. Responsive Behavior

### Breakpoints

| Name | Min Width | Layout |
|------|-----------|--------|
| Mobile | `0` | Single column, bottom nav, stacked cards, floating CTA |
| Tablet | `768px` | Two-column grid, collapsible side menu, wider cards |
| Desktop | `1024px` | Three-to-four column grid, full navigation, side panels |
| Wide | `1440px` | Max-width container `1200px`, centered, breathing room |

### Mobile Adaptations

- Navigation collapses to bottom tab bar (Home, Order, Rewards, Stores, Account) — the Starbucks app pattern.
- The floating circular CTA (Frap button) appears bottom-right for primary order/reorder actions.
- Product cards switch to horizontal scroll rows ("Featured Drinks", "Popular Near You") instead of grid.
- Hero sections collapse: headline drops to `--text-headline` size, imagery scales to single-column full-width.
- Pill buttons stretch to full width with `16px` horizontal margin.
- Menu browsing uses a vertically scrollable category list on the left or top chips for filtering.
- Order details become a bottom sheet that slides up, with a sticky "Checkout" pill at the bottom.
- Search input is full width with `16px` horizontal padding.
- Touch targets: minimum `44px x 44px` on all interactive elements.

### Tablet Adaptations

- Product grid uses `minmax(220px, 1fr)` — typically 2-3 columns.
- Navigation may use a compact top bar with icon + label.
- Order flow uses a split view: menu browsing left, cart summary right.
- Cards show slightly more content (three-line descriptions instead of two).

### Desktop Adaptations

- Full four-column product grid with `minmax(260px, 1fr)`.
- Top navigation with full text labels, Siren logo, and search bar.
- Hero sections use asymmetric layouts: large image + overlaid text, or split 60/40 text-image.
- Hover states are active (not available on touch devices).
- Footer expands with full link columns and Siren logo.

### Image Sizing

| Context | Mobile | Tablet | Desktop |
|---------|--------|--------|---------|
| Hero beverage image | `200px` | `280px` | `360px` |
| Product card thumbnail | `100%` width, 1:1 | `100%` width, 1:1 | `100%` width, 1:1 |
| Category icon | `48px` | `56px` | `64px` |
| Store/location thumbnail | `80px` | `96px` | `120px` |
| Rewards star | `24px` | `28px` | `32px` |

### Touch Targets

- Minimum `44px x 44px` on mobile and tablet.
- Minimum `32px x 32px` on desktop.
- Order/Add-to-cart buttons: minimum `50px` height on all sizes (matching the pill button signature).
- The floating CTA (Frap button): `56px` diameter on mobile, `50px` on desktop.
