# Airbnb Design System

Warm coral accent over crisp white surfaces. Photography-driven layouts that sell the experience before the interface. Rounded, friendly, human — the UI feels like a trusted travel companion, not a software tool.

---

## 1. Visual Theme & Atmosphere

Clean white canvas with warm photography as the primary visual driver. The coral accent signals action and brand without shouting. Rounded corners everywhere — nothing sharp, nothing aggressive. Micro-copy is conversational. The atmosphere says "welcome" at every touchpoint. Listings, destinations, and people are the visual content; UI chrome stays light and out of the way.

**Keywords:** warm, inviting, human, photographic, friendly, trustworthy, rounded

---

## 2. Color Palette & Roles

| Name | Hex | Role |
|------|-----|------|
| Rausch (Coral) | `#FF385C` | Primary accent, CTAs, brand moments, active states |
| Dark Rausch | `#D70466` | CTA hover, pressed states |
| Foreground | `#222222` | Primary text |
| Secondary Text | `#717171` | Descriptions, subtitles, helper text |
| Tertiary Text | `#B0B0B0` | Placeholders, disabled text |
| Background | `#FFFFFF` | Primary surface |
| Surface Light | `#F7F7F7` | Card backgrounds, section alternation |
| Surface Warm | `#FFFAF5` | Subtle warm tint for featured sections |
| Border | `#DDDDDD` | Dividers, card borders, input borders |
| Border Light | `#EBEBEB` | Subtle dividers, table lines |
| Success | `#008A05` | Booking confirmed, positive status |
| Warning | `#C7B82F` | Pending states |
| Error | `#C13515` | Cancellation, validation errors |

**Rule:** Rausch is the heartbeat. Use it for CTAs, selected states, and brand anchors. Never as a background fill for large areas — it tires the eye. Surface Warm is the secret weapon for making sections feel cozy without adding decoration.

---

## 3. Typography Rules

**Primary:** Cereal (Airbnb custom) / fallback: Nunito Sans
**Display:** Cereal Medium / fallback: Nunito 600

| Element | Weight | Size | Tracking | Case |
|---------|--------|------|----------|------|
| Hero headline | 600 | clamp(32px, 4vw, 64px) | -0.02em | Title |
| Section title | 600 | clamp(22px, 2vw, 32px) | -0.01em | Title |
| Card title | 600 | 16px | 0 | Sentence |
| Body | 400 | 16px | 0 | Sentence |
| Body small | 400 | 14px | 0 | Sentence |
| Caption | 400 | 12px | 0.01em | Sentence |
| CTA | 600 | 16px | 0 | Sentence |
| Price | 800 | 20px | -0.01em | — |

**Rules:**
- Headlines are sentence-case, never all-caps. Warmth > formality.
- Line-height: headlines 1.2, body 1.6, compact lists 1.4.
- Price text is always extra-bold, slightly larger than surrounding body.
- No italic for emphasis. Use weight (600) or color (Rausch for key terms).

---

## 4. Component Stylings

### Buttons
- **Primary CTA:** `#FF385C` background, white text, `border-radius: 8px`, padding `14px 24px`, weight 600. On hover: `#D70466`, slight translateY(-1px). Transition: 200ms ease.
- **Secondary CTA:** `#FFFFFF` background, `#222222` text, 1px `#DDDDDD` border, `border-radius: 8px`. On hover: border `#222222`.
- **Ghost:** Transparent, `#222222` text, no border. On hover: text `#FF385C`, underline.
- **Pill tag:** `border-radius: 999px`, `#F7F7F7` bg, `#222222` text. Active: `#FF385C` bg, white text.

### Navigation
- Fixed top bar, `height: 64px`, white with 1px `#EBEBEB` bottom border.
- Logo left, search bar center, profile right.
- Search bar: pill shape (`border-radius: 999px`), `#F7F7F7` bg, icon + placeholder text.

### Cards (Listing Cards)
- Background: `#FFFFFF`, `border-radius: 12px`, 1px `#DDDDDD` border.
- Image: `border-radius: 12px`, aspect-ratio 3/2, `object-fit: cover`.
- Heart icon (save): top-right, default stroke `#FFFFFF` with shadow, filled `#FF385C`.
- Rating: star icon `#FF385C`, score in `#222222`.
- Price: bold, per-night in secondary text.

### Search Bar
- Pill container with segmented inputs: "Where" | "Check in" | "Check out" | "Who".
- Dividers: 1px `#DDDDDD` between segments.
- Active segment: `#222222` text, others `#717171`.
- Search button: circle with Rausch bg, white magnifying glass.

### Image Gallery
- Full-width hero on listing detail, `border-radius: 12px` for individual images.
- Grid: 1 large (left 50%) + 4 small (right 50%, 2x2).
- Hover: subtle overlay with "Show all photos" CTA.

### Reviews
- Avatar: 40px circle, `border-radius: 999px`.
- Star rating in Rausch. Review text in `#222222`, date in `#717171`.
- Divider between reviews: 1px `#EBEBEB`.

---

## 5. Layout Principles

- **Max content width:** 1128px (Airbnb standard), centered.
- **Listing grid:** responsive, 2 cols at 640px, 3 at 768px, 4 at 1024px, no fixed column count — let cards fill naturally with `auto-fill, minmax(280px, 1fr)`.
- **Card gutters:** 16px on mobile, 24px on desktop.
- **Section spacing:** 48px between sections, 32px between section title and content.
- **Listing detail:** two-column layout (left 60% content, right 40% sticky booking card).
- **Photography always leads.** Hero images are never decorative — they are the first impression of the experience.

---

## 6. Depth & Elevation

Airbnb uses subtle shadows and surface color for depth — never dramatic:

| Level | Surface | Shadow | Use |
|-------|---------|--------|-----|
| 0 | `#FFFFFF` | none | Page background, resting cards |
| 1 | `#FFFFFF` | `0 1px 2px rgba(0,0,0,0.08)` | Cards on hover, elevated inputs |
| 2 | `#FFFFFF` | `0 4px 12px rgba(0,0,0,0.12)` | Dropdowns, popovers |
| 3 | `#FFFFFF` | `0 8px 24px rgba(0,0,0,0.16)` | Modals, booking card sticky |

- Shadows are always soft and wide-spread — never tight or directional.
- No blur/glass effects. Surfaces are opaque.
- Sticky booking card uses Level 2 shadow to float above scroll content.

---

## 7. Do's and Don'ts

**Do:**
- Let photography dominate — listings without great images fail
- Use Rausch sparingly but consistently — CTAs, active states, brand marks
- Round everything — 8px for inputs, 12px for cards, 999px for pills and avatars
- Write conversationally — "Where to?" not "Destination"
- Use warm Surface Warm tint for featured or promoted sections
- Show ratings prominently — trust is the product
- Provide clear empty states with friendly illustration and CTA

**Don't:**
- Use Rausch as a background color for sections or panels
- Apply sharp corners (border-radius: 0) to any interactive element
- Use heavy shadows at rest — they should only appear on interaction
- Write in formal or corporate tone
- Stack more than 3 cards vertically without a grid
- Use icons without labels for primary navigation
- Hide pricing — it should be visible in every listing card

---

## 8. Responsive Behavior

| Breakpoint | Behavior |
|-----------|----------|
| < 640px | Single column. Listing grid: 2 columns, smaller images. Booking card becomes bottom sticky bar. Search bar simplifies to single pill input. Nav: logo + profile icon only. |
| 640–768px | 2–3 column listing grid. Side-by-side content begins. Search bar keeps pill shape. |
| 768–1024px | 3–4 column grid. Listing detail: two-column layout appears. Booking card sticky in right column. |
| 1024–1440px | Full desktop grid (4 columns). Full search bar with segments. All navigation visible. |
| > 1440px | Content max-width 1128px, centered. Grid columns max out at 4 — do not add a 5th column. |

**Mobile-specific rules:**
- Listing images become horizontally swipeable (one at a time with dot indicators)
- Bottom sticky bar for booking: Rausch CTA, price preview, dates
- Map view: full-screen map with bottom sheet for listings
- Filter bar: horizontal scroll chips instead of dropdown
- Touch targets: minimum 44x44px
- Heart/save icon: 44x44px hit area (larger than visual)
