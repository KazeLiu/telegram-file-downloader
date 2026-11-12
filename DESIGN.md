---
version: alpha
name: Shicun-private-gallery
description: An image-first private gallery for organizing and reviewing Japanese anime adult-content collections. Pale cherry-pink surfaces, deep rose actions (#A83D68), and plum-gray text create a mature, intimate atmosphere while keeping image browsing, selection, and recovery clear. Images retain their original colors; chrome stays quiet, with no decorative gradients or control shadows.

colors:
  primary: "#A83D68"
  primary-focus: "#8F2D56"
  primary-on-dark: "#F2AFC9"
  selection: "#F7D6E3"
  ink: "#35232D"
  body: "#35232D"
  body-on-dark: "#ffffff"
  body-muted: "#DCCBD3"
  ink-muted-80: "#5C4652"
  ink-muted-48: "#735D69"
  divider-soft: "#F4E8EE"
  hairline: "#E8D7DF"
  canvas: "#FFFAFC"
  canvas-parchment: "#FFF5F8"
  surface-pearl: "#FFFFFF"
  surface-tile-1: "#272729"
  surface-tile-2: "#2a2a2c"
  surface-tile-3: "#252527"
  surface-black: "#000000"
  surface-chip-translucent: "#F7D6E3"
  on-primary: "#ffffff"
  on-dark: "#ffffff"

typography:
  hero-display:
    fontFamily: "SF Pro Display, system-ui, -apple-system, sans-serif"
    fontSize: 56px
    fontWeight: 600
    lineHeight: 1.07
    letterSpacing: -0.28px
  display-lg:
    fontFamily: "SF Pro Display, system-ui, -apple-system, sans-serif"
    fontSize: 40px
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: 0
  display-md:
    fontFamily: "SF Pro Text, system-ui, -apple-system, sans-serif"
    fontSize: 34px
    fontWeight: 600
    lineHeight: 1.47
    letterSpacing: -0.374px
  lead:
    fontFamily: "SF Pro Display, system-ui, -apple-system, sans-serif"
    fontSize: 28px
    fontWeight: 400
    lineHeight: 1.14
    letterSpacing: 0.196px
  lead-airy:
    fontFamily: "SF Pro Text, system-ui, -apple-system, sans-serif"
    fontSize: 24px
    fontWeight: 300
    lineHeight: 1.5
    letterSpacing: 0
  tagline:
    fontFamily: "SF Pro Display, system-ui, -apple-system, sans-serif"
    fontSize: 21px
    fontWeight: 600
    lineHeight: 1.19
    letterSpacing: 0.231px
  body-strong:
    fontFamily: "SF Pro Text, system-ui, -apple-system, sans-serif"
    fontSize: 17px
    fontWeight: 600
    lineHeight: 1.24
    letterSpacing: -0.374px
  body:
    fontFamily: "SF Pro Text, system-ui, -apple-system, sans-serif"
    fontSize: 17px
    fontWeight: 400
    lineHeight: 1.47
    letterSpacing: -0.374px
  dense-link:
    fontFamily: "SF Pro Text, system-ui, -apple-system, sans-serif"
    fontSize: 17px
    fontWeight: 400
    lineHeight: 2.41
    letterSpacing: 0
  caption:
    fontFamily: "SF Pro Text, system-ui, -apple-system, sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.43
    letterSpacing: -0.224px
  caption-strong:
    fontFamily: "SF Pro Text, system-ui, -apple-system, sans-serif"
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.29
    letterSpacing: -0.224px
  button-large:
    fontFamily: "SF Pro Text, system-ui, -apple-system, sans-serif"
    fontSize: 18px
    fontWeight: 300
    lineHeight: 1.0
    letterSpacing: 0
  button-utility:
    fontFamily: "SF Pro Text, system-ui, -apple-system, sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.29
    letterSpacing: -0.224px
  fine-print:
    fontFamily: "SF Pro Text, system-ui, -apple-system, sans-serif"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.0
    letterSpacing: -0.12px
  micro-legal:
    fontFamily: "SF Pro Text, system-ui, -apple-system, sans-serif"
    fontSize: 10px
    fontWeight: 400
    lineHeight: 1.3
    letterSpacing: -0.08px
  nav-link:
    fontFamily: "SF Pro Text, system-ui, -apple-system, sans-serif"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.0
    letterSpacing: -0.12px

rounded:
  none: 0px
  xs: 5px
  sm: 8px
  md: 11px
  lg: 18px
  pill: 9999px
  full: 9999px

spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 17px
  lg: 24px
  xl: 32px
  xxl: 48px
  section: 80px

components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.body}"
    rounded: "{rounded.pill}"
    padding: 11px 22px
  button-primary-focus:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.pill}"
  button-primary-active:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.pill}"
  button-secondary-pill:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.primary}"
    typography: "{typography.body}"
    rounded: "{rounded.pill}"
    padding: 11px 22px
  button-dark-utility:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-dark}"
    typography: "{typography.button-utility}"
    rounded: "{rounded.sm}"
    padding: 8px 15px
  button-pearl-capsule:
    backgroundColor: "{colors.surface-pearl}"
    textColor: "{colors.ink-muted-80}"
    typography: "{typography.caption}"
    rounded: "{rounded.md}"
    padding: 8px 14px
  button-store-hero:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button-large}"
    rounded: "{rounded.pill}"
    padding: 14px 28px
  button-icon-circular:
    backgroundColor: "{colors.surface-chip-translucent}"
    textColor: "{colors.ink}"
    rounded: "{rounded.full}"
    size: 44px
  text-link:
    backgroundColor: transparent
    textColor: "{colors.primary}"
    typography: "{typography.body}"
  text-link-on-dark:
    backgroundColor: transparent
    textColor: "{colors.primary-on-dark}"
    typography: "{typography.body}"
  global-nav:
    backgroundColor: "{colors.canvas-parchment}"
    textColor: "{colors.ink}"
    typography: "{typography.nav-link}"
    height: 44px
  sub-nav-frosted:
    backgroundColor: "{colors.canvas-parchment}"
    textColor: "{colors.ink}"
    typography: "{typography.tagline}"
    height: 52px
  product-tile-light:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.display-lg}"
    rounded: "{rounded.none}"
    padding: 80px
  product-tile-parchment:
    backgroundColor: "{colors.canvas-parchment}"
    textColor: "{colors.ink}"
    typography: "{typography.display-lg}"
    rounded: "{rounded.none}"
    padding: 80px
  product-tile-dark:
    backgroundColor: "{colors.surface-tile-1}"
    textColor: "{colors.on-dark}"
    typography: "{typography.display-lg}"
    rounded: "{rounded.none}"
    padding: 80px
  product-tile-dark-2:
    backgroundColor: "{colors.surface-tile-2}"
    textColor: "{colors.on-dark}"
    rounded: "{rounded.none}"
  product-tile-dark-3:
    backgroundColor: "{colors.surface-tile-3}"
    textColor: "{colors.on-dark}"
    rounded: "{rounded.none}"
  store-utility-card:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.lg}"
    padding: 24px
  configurator-option-chip:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    padding: 12px 16px
  configurator-option-chip-selected:
    backgroundColor: "{colors.selection}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
  search-input:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.pill}"
    padding: 12px 20px
    height: 44px
  floating-sticky-bar:
    backgroundColor: "{colors.canvas-parchment}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    height: 64px
    padding: 12px 32px
  environment-quote-card:
    backgroundColor: "{colors.surface-tile-1}"
    textColor: "{colors.on-dark}"
    typography: "{typography.display-lg}"
    rounded: "{rounded.none}"
    padding: 80px
  footer:
    backgroundColor: "{colors.canvas-parchment}"
    textColor: "{colors.ink-muted-80}"
    typography: "{typography.fine-print}"
    padding: 64px
---

## Overview

拾存采用**淡粉色、成熟暧昧的日系私人画廊**风格。它服务于日本二次元成人向图片的个人收集、整理、筛选与审阅；视觉应贴近收藏内容，而不是通用办公后台。图片是主体，页面用极浅樱粉、深玫瑰色操作和深梅灰文字营造柔和、私密的氛围。

### Why pale pink / 选择原因

- **贴合实际用途。** 用户希望界面具有更成熟、暧昧的成人向收藏氛围。淡粉色比蓝灰色后台更符合这一定位；用配色与轻透工具条表达，而不是堆叠露骨文案、蕾丝、爱心或装饰插画。
- **适合持续筛图。** 极浅粉底和近白面板降低大面积高饱和色的存在感，留出空间给原图；图片不叠加粉色滤镜，也不改变原有色彩。
- **柔和不等于难读。** 淡粉色用于背景与选中填充；主要按钮和浅色背景上的链接用深玫瑰色，正文用深梅灰。不要使用淡粉底配白字来承载主要动作。
- **保留工作台效率。** 延续内容优先、清晰层级、克制留白、可见焦点和明确回收确认。桌面密集图片墙与大图审阅各自保留适合的密度，不套用商品宣传页的大标题、整屏留白或强制明暗交替。

**Key Characteristics:**
- Image-first presentation; preserve the collection's original colors and make the review image dominant.
- Pale pink page canvas, near-white panels, and rose selection fills; neutral dark surfaces only where media viewing benefits.
- One rose brand family: deep rose actions, darker focus rings, and light rose links on dark media surfaces.
- Two button grammars: rose pill CTAs (`{rounded.pill}`) and compact utility rects (`{rounded.sm}`).
- SF Pro Display + SF Pro Text with system-font fallbacks; readable body text and restrained headlines.
- Flat UI chrome; use surface changes, hairlines, and functional backdrop blur rather than control shadows.
- Compact navigation with page context and a clear primary action; menus retain all functional destinations on small screens.
- Express atmosphere through palette and material, not decorative clutter or flirtatious task labels.

### Reference scope

Apple's homepage, environment, store, iPhone 17 Pro buy page, and accessories index supplied the original typography, shape, and component vocabulary below. For 拾存, the pink palette and private-gallery direction in this document govern implementation. Legacy keys such as `product-tile` and `store-utility-card` describe reusable visual shapes; they do not require shopping features, promotional copy, or a marketing layout in the workbench.

## Colors

The palette applies across the workbench, local image views, deduplication, cloud albums, settings, and dialogs. Pale pink defines the theme through large surfaces; deeper rose provides readable interaction contrast.

### Brand & Accent
- **Action Rose** (`{colors.primary}` — #A83D68): Main action fills, links, and active controls on light surfaces. Pair filled buttons with `{colors.on-primary}`; pale pink is not a substitute for this readable action color.
- **Focus Rose** (`{colors.primary-focus}` — #8F2D56): Visible keyboard focus rings (`outline: 2px solid`, with separation from the control).
- **Rose Link On Dark** (`{colors.primary-on-dark}` — #F2AFC9): Links and focus signals on neutral dark media surfaces, where Action Rose would be too dark.
- **Selection Pink** (`{colors.selection}` — #F7D6E3): Selected tabs, chips, and selection fills. Pair with plum-gray or deep rose content and an outline, checkmark, or other non-color selection cue.

### Surface
- **Gallery White** (`{colors.canvas}` — #FFFAFC): Near-white panels, forms, dialogs, and utility containers. Keeps the theme soft without competing with images.
- **Cherry Pink Canvas** (`{colors.canvas-parchment}` — #FFF5F8): Default page background, navigation, footer, and frosted toolbars; the dominant expression of the pale pink theme.
- **Pearl White** (`{colors.surface-pearl}` — #FFFFFF): Secondary capsules and neutral image backdrops. Keep image-review backgrounds untinted when color comparison matters.
- **Neutral Dark 1** (`{colors.surface-tile-1}` — #272729), **2** (`{colors.surface-tile-2}` — #2a2a2c), and **3** (`{colors.surface-tile-3}` — #252527): Optional media-viewing surfaces, not mandatory alternating page sections.
- **Pure Black** (`{colors.surface-black}` — #000000): Video or image-viewer void only; the default navigation is pale pink, not black.
- **Translucent Pink Chip** (`{colors.surface-chip-translucent}` — #F7D6E3): Circular controls over imagery. Increase opacity when needed to keep icons readable over arbitrary image content.

### Text
- **Plum Gray Ink** (`{colors.ink}` — #35232D): Headlines, primary text, and dark utility fills; softer than pure black and related to the rose palette.
- **Body** (`{colors.body}` — #35232D): The same plum-gray tone for readable paragraphs and form values.
- **Body On Dark** (`{colors.body-on-dark}` — #ffffff): Text on dark media surfaces.
- **Body Muted** (`{colors.body-muted}` — #DCCBD3): Secondary text on dark surfaces only.
- **Ink Muted 80** (`{colors.ink-muted-80}` — #5C4652): Supporting text on light panels.
- **Ink Muted 48** (`{colors.ink-muted-48}` — #735D69): Metadata and fine print on light surfaces; do not use low-contrast pale pink for instructions.

### Hairlines & Borders
- **Divider Soft** (`{colors.divider-soft}` — #F4E8EE): Quiet separators and capsule borders, not shadows.
- **Hairline** (`{colors.hairline}` — #E8D7DF): Subtle 1px container borders. Use Action Rose or Focus Rose when a boundary must identify an interactive control or selection.

### Semantic States
Rose is the only brand accent, not a replacement for error or danger semantics. Preserve distinct destructive-action and error styling, pair state colors with text or icons, and keep recovery conditions beside the affected action. The theme must not make a recycle confirmation look like an ordinary selection.

### Brand Gradient
**No decorative gradients.** The collection supplies the imagery; pale pink surfaces and restrained frosted toolbars supply the atmosphere. Do not add a rose color wash, tint, or filter over thumbnails, originals, or comparison images.

## Typography

### Font Family
- **Display**: `SF Pro Display, system-ui, -apple-system, sans-serif` — Apple's proprietary display face, optimized for sizes ≥ 19px. Defines the voice of every headline.
- **Body / UI**: `SF Pro Text, system-ui, -apple-system, sans-serif` — the text-optimized variant used for body copy, captions, buttons, and links below 20px.
- **OpenType features**: `font-variant-numeric: numerator` is enabled on numeric links (pricing tables, spec sheets). Display sizes rely on tight tracking rather than contextual ligatures.

### Hierarchy

| Token | Size | Weight | Line Height | Letter Spacing | Use |
|---|---|---|---|---|---|
| `{typography.hero-display}` | 56px | 600 | 1.07 | -0.28px | Hero headline; the signature "Apple tight" tracking |
| `{typography.display-lg}` | 40px | 600 | 1.10 | 0 | Tile headlines atop every product tile |
| `{typography.display-md}` | 34px | 600 | 1.47 | -0.374px | Section heads (SF Pro Text at display proportions) |
| `{typography.lead}` | 28px | 400 | 1.14 | 0.196px | Product tile subcopy |
| `{typography.lead-airy}` | 24px | 300 | 1.5 | 0 | Environment-page lead paragraphs (the rare weight 300) |
| `{typography.tagline}` | 21px | 600 | 1.19 | 0.231px | Sub-tile tagline; sub-nav category name |
| `{typography.body-strong}` | 17px | 600 | 1.24 | -0.374px | Inline strong emphasis |
| `{typography.body}` | 17px | 400 | 1.47 | -0.374px | Default paragraph |
| `{typography.dense-link}` | 17px | 400 | 2.41 | 0 | Footer / store utility link lists (relaxed leading) |
| `{typography.caption}` | 14px | 400 | 1.43 | -0.224px | Secondary captions, button text |
| `{typography.caption-strong}` | 14px | 600 | 1.29 | -0.224px | Emphasized captions |
| `{typography.button-large}` | 18px | 300 | 1.0 | 0 | Store hero CTAs (the rare weight 300) |
| `{typography.button-utility}` | 14px | 400 | 1.29 | -0.224px | Utility/nav button labels |
| `{typography.fine-print}` | 12px | 400 | 1.0 | -0.12px | Fine-print, footer body |
| `{typography.micro-legal}` | 10px | 400 | 1.3 | -0.08px | Micro legal disclaimers |
| `{typography.nav-link}` | 12px | 400 | 1.0 | -0.12px | Global nav menu items |

### Principles

- **Negative letter-spacing at display sizes.** Every headline at 17px and up carries a slight tracking tighten (`-0.12 → -0.374px`). This produces the iconic "Apple tight" headline cadence. Never used at 12px or below.
- **Body copy at 17px, not 16px.** Apple breaks the SaaS convention and runs paragraph text at 17px. The extra pixel gives the page an unmistakable "reading, not scanning" pace.
- **Weight 300 is real and rare.** Used deliberately on a handful of large-size reads (`{typography.button-large}` at 18px/300 and `{typography.lead-airy}` at 24px/300). It's not an accident — it's a light-atmosphere cue reserved for moments where the content should feel airy.
- **Weight 600, not 700, for headlines.** Apple's headlines sit at weight 600. Weight 700 is used sparingly for `{typography.tagline}` (21px) when a touch more assertion is needed.
- **Line-height is context-specific.** Display sizes use 1.07–1.19 (tight). Body uses 1.47. Utility link stacks in the footer/store use an unusually relaxed 2.41 (`{typography.dense-link}`). The 2.41 is not a bug — it's how the footer's dense link columns breathe.
- **Weight 500 is deliberately absent.** The ladder is 300 / 400 / 600 / 700. Mid-weight readings always use 600.

### Note on Font Substitutes
SF Pro is Apple's proprietary system font. When building off-system:

- Use `system-ui, -apple-system, BlinkMacSystemFont` as the first stack entry — on macOS/iOS/Safari this resolves to the real SF Pro.
- For non-Apple platforms, **Inter** (Google Fonts, variable) is the closest open-source equivalent. Inter at weight 600 with `font-feature-settings: "ss03"` approximates SF Pro's rounded "a" character.
- Nudge `letter-spacing` down by `-0.01em` on display sizes to re-create the Apple tight feel; Inter's default tracking runs slightly wider than SF Pro.
- For body text, tighten line-height by `0.03` (from 1.47 → 1.44) when substituting Inter — Inter's taller x-height needs less leading.

## Layout

### Spacing System
- **Base unit:** 8px. Sub-base values (2, 4, 5, 6, 7) are used for tight typographic adjustments; structural layout snaps to 8/12/16/20/24.
- **Tokens:** `{spacing.xxs}` 4px · `{spacing.xs}` 8px · `{spacing.sm}` 12px · `{spacing.md}` 17px · `{spacing.lg}` 24px · `{spacing.xl}` 32px · `{spacing.xxl}` 48px · `{spacing.section}` 80px.
- **Section vertical padding:** `{spacing.section}` (80px) inside a product tile; tiles stack edge-to-edge with 0 gap (the color change provides the break).
- **Card padding:** `{spacing.lg}` (24px) inside utility grid cards.
- **Button padding:** 8–11px vertical, 15–22px horizontal.
- **Universal rhythm constants:** the 17px body line-height multiplier (~25px line) and 21px tagline size show up on every analyzed page.

### Grid & Container
- **Max content width:** ~980px on text-heavy sections (environment), ~1440px on product grids (store, accessories), full-bleed for product tiles (homepage).
- **Column patterns:** 3 to 5 column utility card grid on store/accessories; 2-column side-by-side tiles on homepage occasional sections; single-column centered stack on product tile heroes.
- **Gutters:** 20–24px between cards in a utility grid.

### Whitespace Philosophy
Whitespace separates actions from the collection without wasting the browsing area. The original large-tile spacing is reserved for an intentional introductory surface; task lists and image walls use compact spacing. Keep controls away from the review image, but preserve dense thumbnail browsing where it helps selection. Do not add empty hero sections to express the pink theme.

## Elevation & Depth

| Level | Treatment | Use |
|---|---|---|
| Flat | No shadow, no border | Full-bleed tiles, global nav, footer, body sections |
| Soft hairline | 1px `rgba(0, 0, 0, 0.08)` border | Utility cards, sub-nav frosted-glass separator |
| Backdrop blur | `backdrop-filter: blur(N)` on Cherry Pink Canvas at 80% | Sub-nav and selection/action bars |
| Product shadow | `rgba(0, 0, 0, 0.22) 3px 5px 30px 0` | Product renders resting on a surface (the only true "shadow" in the system) |

**Shadow philosophy.** Apple uses **exactly one** drop-shadow, and it is applied to photographic product imagery — never to cards, never to buttons, never to text. Elevation in the UI comes from (a) surface-color change (light tile ↔ dark tile) and (b) backdrop-blur on sticky bars. The single shadow is about giving the product weight, not about UI hierarchy.

### Decorative Depth
- **Collection imagery** supplies the visual subject; no decorative image or CSS gradient is needed.
- **Near-white panels on pale pink canvas** separate functional regions without heavy borders or shadows. Dark media regions are optional, not a required alternating rhythm.
- **Backdrop-filter blur** on `{component.sub-nav-frosted}` and `{component.floating-sticky-bar}` creates a "floating over content" effect that's functional, not decorative.

## Shapes

### Border Radius Scale

| Token | Value | Use |
|---|---|---|
| `{rounded.none}` | 0px | Full-bleed product tiles (no corner rounding) |
| `{rounded.xs}` | 5px | Inline links when styled as subtle chips (rare) |
| `{rounded.sm}` | 8px | Dark utility buttons (Sign In, Bag), inline card imagery |
| `{rounded.md}` | 11px | White Pearl Button capsules |
| `{rounded.lg}` | 18px | Store utility cards, accessories grid cards |
| `{rounded.pill}` | 9999px | Primary rose CTAs, selection chips, search input, and sticky-bar actions |
| `{rounded.full}` | 9999px / 50% | Circular control chips floating over photography |

### Photography Geometry
- **Hero imagery**: full-bleed, 21:9 or taller on the homepage; 16:9 on environment and shop pages. Product renders are photographic-realistic, often shot on a tinted surface that becomes the tile background.
- **Product renders**: PNG/WebP with transparency; rest on a surface tile and pick up the system shadow.
- **Accessory grid**: square 1:1 crops at `{rounded.lg}` (18px) radius, light neutral backgrounds, product centered with 20–40px internal padding.
- **No rounded imagery in hero tiles** — images are full-bleed rectangular. Rounding (`{rounded.sm}`, `{rounded.lg}`) appears only on inline card imagery.
- Lazy-loading via responsive `srcset` and `sizes` across all breakpoints; CDN-optimized WebP.

## Components

### Top Navigation

**`global-nav`** — Compact navigation on `{colors.canvas-parchment}` with `{colors.ink}` text, 44px high. Active destinations use Action Rose and a non-color state cue. Keep the 拾存 brand and existing functional destinations; on mobile, show a clear menu rather than compressing all destinations into tiny labels. Do not restore the source reference's black navigation bar as the default theme.

**`sub-nav-frosted`** — Page context and tools beneath global navigation. Background `{colors.canvas-parchment}` at 80% opacity with functional backdrop blur, height 52px. Left: the current page name in `{typography.tagline}` (21px / 600). Right: related controls in `{typography.button-utility}` (14px) and one clear primary action. Ensure the translucent surface still makes text readable over arbitrary collection imagery.

### Buttons

**`button-primary`** — Main workbench action. Background `{colors.primary}` (Action Rose #A83D68), text `{colors.on-primary}` in `{typography.body}` (SF Pro Text 17px / 400), rounded `{rounded.pill}`, padding 11px × 22px. Use a plain action label such as "保存设置" or "上传所选", not mood-setting copy.
- Active state: `{component.button-primary-active}` — `transform: scale(0.95)` (the system-wide micro-interaction).
- Focus state: `{component.button-primary-focus}` — 2px solid `{colors.primary-focus}` outline.

**`button-secondary-pill`** — Secondary action beside a primary action. Background `{colors.canvas}` or transparent, text `{colors.primary}`, 1px solid `{colors.primary}` border, rounded `{rounded.pill}`, padding 11px × 22px. Keep the main action visually dominant.

**`button-dark-utility`** — Compact utility action where a dark fill is useful. Background `{colors.ink}` (#35232D), text `{colors.on-dark}` in `{typography.button-utility}` (14px / 400 / -0.224px tracking), rounded `{rounded.sm}` (8px), padding 8px × 15px. Active state shrinks via `transform: scale(0.95)`.

**`button-pearl-capsule`** — Quiet utility button. Background `{colors.surface-pearl}` (#FFFFFF), text `{colors.ink-muted-80}` in `{typography.caption}` (14px), 3px solid `{colors.divider-soft}` border, rounded `{rounded.md}` (11px), padding 8px × 14px. The soft border is not a shadow.

**`button-store-hero`** — Larger primary-action variant for a standalone entry or connection screen. Same Action Rose and white text as `{component.button-primary}`, but with `{typography.button-large}` (18px / 300) and padding 14px × 28px. Do not use it throughout task toolbars.

**`button-icon-circular`** — Floats over imagery. 44 × 44px, background `{colors.surface-chip-translucent}` with sufficient opacity for icon contrast, icon in `{colors.ink}`, rounded `{rounded.full}`. Use for review navigation, close buttons, and in-image controls; do not tint the image beneath it.

**`text-link`** — Inline body links in `{colors.primary}` (Action Rose). Underlined or non-underlined per context.

**`text-link-on-dark`** — Inline links on dark media surfaces in `{colors.primary-on-dark}` (Rose Link On Dark #F2AFC9). Use the lighter rose for contrast; Action Rose is reserved for light-surface links and filled actions.

### Cards & Containers

**`product-tile-light`** — Optional full-bleed introductory surface. Background `{colors.canvas}` (Gallery White), text `{colors.ink}`, rounded `{rounded.none}`, vertical padding `{spacing.section}` (80px). Reserve the large centered composition for an entry screen; it is not the template for image walls or task pages.

**`product-tile-parchment`** — Same optional large surface on `{colors.canvas-parchment}` (#FFF5F8). Do not add extra sections merely to alternate background colors.

**`product-tile-dark`** — Optional media-viewing surface. Background `{colors.surface-tile-1}` (#272729), text `{colors.on-dark}`, with `{component.text-link-on-dark}` for links. Keep the image dominant; do not require dark bands on every page. Large introductory compositions may use `{spacing.section}` padding, while image review uses the available viewport.

**`product-tile-dark-2`** — Variant on `{colors.surface-tile-2}` (#2a2a2c). Used where a dark tile sits directly above or below `{component.product-tile-dark}` to create the faintest separation through micro-step lightness change.

**`product-tile-dark-3`** — Variant on `{colors.surface-tile-3}` (#252527). Used at the bottom of the stack and in embedded video/player frames.

**`store-utility-card`** — Utility container or album card. Background `{colors.canvas}` (Gallery White), 1px solid `{colors.hairline}` border, rounded `{rounded.lg}` (18px), padding `{spacing.lg}` (24px). Use a clear name and relevant metadata, with secondary actions in Action Rose. No shadow; dense image walls do not need a separate card around every thumbnail.

**`configurator-option-chip`** — Pill-shaped filter or option. Background `{colors.canvas}`, text `{colors.ink}` in `{typography.caption}`, rounded `{rounded.pill}`, padding 12px × 16px. Keep labels concise and related options together.

**`configurator-option-chip-selected`** — Selected state. Background `{colors.selection}`, border 2px solid `{colors.primary-focus}`; retain the label and expose selected state semantically. Use a checkmark or another visible cue where selection would otherwise depend only on pink fill.

**`environment-quote-card`** — Reference-only large image-backed composition. It is not needed in the regular workbench; do not introduce decorative scenery, logos, or promotional sections to create atmosphere.

**`floating-sticky-bar`** — Selection/action bar near the viewport bottom. Background `{colors.canvas-parchment}` at 80% opacity with functional backdrop blur, minimum height 64px, padding 12px × 32px. Left: selection count or processing status. Right: the relevant action; preserve distinct danger styling for destructive confirmation and reserve space for the bottom safe area.

### Inputs & Forms

**`search-input`** — The accessories search input. Background `{colors.canvas}`, text `{colors.ink}` in `{typography.body}` (17px), 1px solid `rgba(0, 0, 0, 0.08)` border, rounded `{rounded.pill}` (full pill — search is also pill-shaped, matching the CTA grammar), padding 12px × 20px, height 44px. Leading icon: search glyph at 14px, muted tint.

Error and validation states were not surfaced in the analyzed pages.

### Footer

**`footer`** — When needed, background `{colors.canvas-parchment}` (#FFF5F8), text `{colors.ink-muted-80}`. Supporting links use `{typography.caption}` (14px), fine print uses `{typography.fine-print}` (12px). Keep it compact on functional pages rather than adding the source reference's large shopping footer.

## Do's and Don'ts

### Do
- Use Action Rose `{colors.primary}` (#A83D68) for brand actions and light-surface links, Focus Rose for keyboard outlines, and `{colors.selection}` for selection fills.
- Set headlines in `{typography.hero-display}` or `{typography.display-lg}` with negative letter-spacing (`-0.28 → -0.374px`) to get the signature "Apple tight" cadence.
- Run body copy at `{typography.body}` (17px / 400 / 1.47 / -0.374px) — not 16px. The extra pixel defines the brand's reading pace.
- Use near-white panels on pale pink canvas to establish hierarchy; reserve neutral dark surfaces for media where useful.
- Reserve `{rounded.pill}` for the primary rose CTA and related action shapes (filter chips, search input, sticky-bar CTA).
- Apply the single product-shadow (`rgba(0, 0, 0, 0.22) 3px 5px 30px`) only to product renders resting on a surface — never on cards, buttons, or text.
- Use `transform: scale(0.95)` as the active/press state on every button — it's the system-wide micro-interaction.
- Keep default navigation pale pink with readable plum-gray text and rose active states.
- Keep labels literal and operational: "上传", "回收", "还原", "保存设置". Mature atmosphere belongs in the visual treatment, not in ambiguous action wording.

### Don't
- Don't reintroduce blue or another brand accent alongside rose; retain distinct semantic colors for errors and destructive operations.
- Don't add shadows to cards, buttons, or text — shadow is reserved for product imagery.
- Don't use gradients, lace frames, repeated hearts, decorative illustrations, or image tints to amplify the theme; pale pink surfaces and the collection carry the atmosphere.
- Don't set body copy at weight 500 — Apple's ladder is 300 / 400 / 600 / 700, with 500 deliberately absent. Body is always 400; strong inline is 600; display is 600.
- Don't round full-bleed tiles — tiles are rectangular and edge-to-edge; the color change is the divider.
- Don't tighten line-height below 1.47 for body copy — the editorial leading is part of the brand.
- Don't mix radii grammars — use `{rounded.sm}` for compact utility, `{rounded.lg}` for utility cards, `{rounded.pill}` for pills, and nothing in between (except the rare `{rounded.md}` Pearl Button).
- Don't use `{colors.primary-on-dark}` (Rose Link On Dark) as text on light surfaces, or pale selection pink behind white button labels. Use Action Rose on light surfaces.

## Responsive Behavior

### Breakpoints

| Name | Width | Key Changes |
|---|---|---|
| Small phone | ≤ 419px | Single-column tiles; sub-nav collapses to category name + primary CTA only; hero typography drops to 28px |
| Phone | 420–640px | Single-column stack; product renders scale to 80% of tile width; hero h1 drops to 34px |
| Large phone | 641–735px | Tiles transition to tighter padding (48px vertical vs 80px); fine-print wraps |
| Tablet portrait | 736–833px | Global nav collapses to hamburger; sub-nav hides category chips, keeps primary CTA |
| Tablet landscape | 834–1023px | Global nav returns fully expanded; 3-column utility grids become 2-column |
| Small desktop | 1024–1068px | Product tiles use 2/3 width with margin gutters; hero h1 stays at 40px |
| Desktop | 1069–1440px | Full layout; 4–5 column store grids; 1440px content max |
| Wide desktop | ≥ 1441px | Content locks at 1440px, margins absorb extra width |

The structural breakpoints that matter for agents: 1440px (content lock), 1068px (small-desktop), 833px (tablet landscape switch), 734px (tablet portrait), 640px (phone), 480px (small phone).

### Touch Targets
- Minimum 44 × 44px. `{component.button-primary}` lands at ~44 × 100px (with the full-pill radius making the visible hit area more generous than the label suggests).
- `{component.button-icon-circular}` is exactly 44 × 44px.
- Global nav utility links are smaller (~32 × 80px) — they deliberately sit at a tighter target because they're precision desktop actions, and the mobile hamburger replaces them at ≤ 833px.

### Collapsing Strategy
- **Global nav**: full functional navigation on desktop → 拾存 brand, clear menu control, and account action at 833px and below.
- **Sub-nav**: category name + inline links + primary CTA → category name + primary CTA only at mobile; inline links move into a hamburger tray.
- **Product tiles**: stack from 2-column to 1-column at 834px; vertical padding tightens from 80px → 48px at small-phone.
- **Utility grids** (store, accessories): 5-col → 4-col (1440px) → 3-col (1068px) → 2-col (834px) → 1-col (640px).
- **Hero typography**: `{typography.hero-display}` (56px) → `{typography.display-lg}` (40px) at 1068px → 34px at 640px → 28px at 419px.

### Image Behavior
- All product imagery uses responsive `srcset` with breakpoint-matched crops.
- Hero photography may switch art direction at mobile (e.g., the environment page's vista crops to a taller aspect ratio on mobile, framing the subject differently).
- Product renders maintain their 1:1 or 4:3 aspect ratios across breakpoints; only scale changes.
- Lazy-loading is default; the above-fold hero loads eagerly.

## Iteration Guide

1. Focus on ONE component at a time. Reference its YAML key directly (`{component.product-tile-dark}`, `{component.search-input}`).
2. Variants of an existing component (`-active`, `-focus`, `-2`, `-3`) live as separate entries in `components:`.
3. Use `{token.refs}` everywhere — never inline hex.
4. Never document hover. Default and Active/Pressed states only.
5. Display headlines stay SF Pro Display 600 with negative letter-spacing. Body stays SF Pro Text 400 at 17px. The boundary is unbreakable.
6. The single drop-shadow (`rgba(0, 0, 0, 0.22) 3px 5px 30px`) is reserved for product photography only.
7. When in doubt about emphasis: use spacing, near-white versus pale pink surfaces, and one clear action before adding chrome. Keep image colors unchanged.

## Known Gaps

- Form validation and error states were not surfaced on the analyzed pages; only the neutral search input is documented.
- The homepage's embedded video/player frame uses `{colors.surface-black}`; interior player controls are not documented (they're a platform widget, not a web-design token).
- Some component imagery is dynamic (rotating product hero) and its specific copy varies per surface — component specs name the structure, not the rotating content.
- A complete dark-mode workbench is not specified. The default is the pale pink light theme; neutral dark media surfaces do not imply a second app theme.
- Atmospheric photography (environment page mountain vista) is a content asset, not a design token; the documented `{component.environment-quote-card}` describes the structural surface only.
- The exact backdrop-filter blur radius on `{component.sub-nav-frosted}` and `{component.floating-sticky-bar}` is platform-dependent; production CSS uses `saturate(180%) blur(20px)` as a typical baseline but the value isn't formalized as a token.
