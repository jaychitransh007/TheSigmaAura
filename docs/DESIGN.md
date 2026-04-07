# Design System And Experience Principles

Last updated: April 8, 2026

## Purpose

This document is the centralized design source of truth for Sigma Aura.

It defines:
- the product design principles
- the visual language
- the UX patterns
- the interaction rules
- the component behaviors
- the fashion-specific experience standards

All new web and mobile UI work should align with this document unless an explicit product decision overrides it.

The design system is now applied uniformly across all surfaces: onboarding, profile analysis/processing, main chat app, profile, wardrobe, results, and catalog admin. All share the same warm/burgundy accent (`#6f2f45`), background gradients, Cormorant Garamond serif headings, and Avenir Next sans-serif body text.

Key UI patterns implemented:
- **Unified profile page**: Single page with inline edit toggle — view mode shows read-only fields, edit mode switches to inputs/selects in place. Includes style code card and personalized color palette card (base/accent/avoid chips).
- **Chat composer**: `+` button opens a popover with "Upload image" (file picker) and "Select from wardrobe" (modal with wardrobe grid). Supports drag-drop and paste.
- **Chat welcome screen with progressive disclosure**: The chat homepage leads with **one dominant primary CTA** (`Dress me for tonight`) and tucks the four secondary prompts behind a `More ways to style` toggle. Accessible `aria-expanded` and `prefers-reduced-motion` support.
- **Chat management**: Conversation sidebar with hover-reveal rename (inline edit) and delete (archive with confirmation) actions per history item. Title column on conversations table.
- **Wardrobe add-item modal**: Photo upload with preview, auto-enrichment (46 attributes via vision API).
- **Wardrobe edit modal**: Full metadata edit form (title, description, category, subtype, colors, pattern, formality, occasion, brand, notes) with image preview. Calls PATCH endpoint.
- **Wardrobe delete**: Per-card delete button with confirmation dialog. Soft-deletes via is_active=false.
- **Wardrobe filters**: Search bar (title/description/brand/category), category chips (All, Tops, Bottoms, Shoes, Dresses, Outerwear, Accessories, Occasion-ready), color filter row (11 colors), and localStorage persistence across page loads. The `Occasion-ready` chip now matches against the enrichment metadata tag set (`wedding`, `cocktail_party`, `office`, `semi_formal` + formality `smart_casual` and above) instead of "any non-empty `occasion_fit`".
- **Outfit PDP card**: Full-width header (title + like/dislike icons + stylist summary) above 3-column body (thumbnails | hero | products + radars). Products show title / Rs. price / Buy Now + wishlist heart — or "From your wardrobe" for owned items. Dual radar charts: style archetypes (purple) + evaluation criteria × analysis_confidence_pct (burgundy). Virtual try-on images in 2:3 aspect ratio.
- **Follow-up suggestions as labelled groups**: Quick-reply chips are rendered under bucket headers (`Improve It`, `Show Alternatives`, `Shop The Gap`), driven by the `follow_up_groups` field on response metadata emitted by `response_formatter.py`. The UI prefers the structured payload and only falls back to substring bucketing if it's absent.
- **Wardrobe-first copy**: Wardrobe-first occasion responses name the selected pieces and explain *why* they fit ("For office, your Navy Blazer and Cream Trousers from your saved wardrobe is the strongest fit…"). The stock "Built from your saved wardrobe for X" line has been removed. Hybrid responses name both the wardrobe anchors *and* the catalog gap-fillers explicitly.
- **Results grid**: 2-column card grid with outfit preview thumbnails, user message, occasion chips, and relative timestamps.

Related docs:
- [`docs/PRODUCT.md`](PRODUCT.md) — product definition and user journey
- [`docs/CURRENT_STATE.md`](CURRENT_STATE.md) — **source of truth** for implementation state
- [`docs/RELEASE_READINESS.md`](RELEASE_READINESS.md) — 4-gate release checklist
- [`docs/DESIGN_SYSTEM_VALIDATION.md`](DESIGN_SYSTEM_VALIDATION.md) — manual QA checklist a designer must complete before the design gate goes green
- [`docs/APPLICATION_SPECS.md`](APPLICATION_SPECS.md) — runtime contract (⚠️ *partially deprecated*)
- [`docs/WORKFLOW_REFERENCE.md`](WORKFLOW_REFERENCE.md) — human-facing per-intent execution flows (not loaded at runtime)

## Product Design Goal

Aura should feel like a personal stylist studio, not a generic AI tool and not a commodity shopping app.

The target emotional response is:
- understood
- guided
- elevated
- tasteful
- calm
- confident

For the primary audience, women 20–35, the product must balance:
- editorial beauty
- everyday usefulness
- emotional softness
- practical trust

## Core Experience Principles

### 1. Stylist, Not Dashboard

The interface should feel like guidance from a stylist.

Avoid:
- enterprise control-panel layouts
- KPI-first presentation
- technical or robotic framing
- excessive exposed model/process language

Prefer:
- stylist summaries
- image-led guidance
- curated choices
- elegant explanation layers

### 2. Image-First, Text-Second

Fashion decisions are visual decisions.

Rules:
- lead with imagery where possible
- use text to interpret, guide, and reassure
- avoid dense text walls before visual orientation
- recommendation modules should always feel visual first

### 3. Wardrobe-First Trust

The UI must make it obvious when Aura is using the user’s wardrobe, the catalog, or both.

Every recommendation surface should clearly expose source mode:
- wardrobe-first
- catalog-only
- hybrid

Users should never have to guess whether Aura is helping them use what they own or pushing them to buy.

### 4. Taste Over Activity

Motion, color, and layout should signal refinement.

Avoid:
- noisy interactions
- exaggerated motion
- gamified microinteractions
- “AI assistant” visual clichés

Prefer:
- deliberate transitions
- restrained emphasis
- soft reveal patterns
- luxurious pacing

### 5. Guidance Over Metrics

Confidence and scoring matter, but they should support the answer, not dominate it.

Use scores:
- as secondary detail
- in expandable layers
- for trust and explanation

Do not use scores:
- as the primary visual story
- as the first thing the user sees

### 6. Discovery Must Be Designed

Users should not need to invent the product.

The UI must proactively reveal that Aura can help with:
- occasion dressing
- pairing a garment
- outfit checks
- buy / skip
- style discovery
- trip / capsule planning

### 7. Premium Femininity Without Cliche

The product should feel feminine, refined, and modern without relying on:
- pink overload
- “girlboss” visual tropes
- glitter / gloss gimmicks
- trend-chasing graphic noise

The tone should be:
- chic
- warm
- composed
- intelligent

## Brand Expression

### Brand Personality

Aura should feel:
- editorial
- intimate
- polished
- intelligent
- reassuring
- aspirational

It should not feel:
- corporate
- sterile
- adolescent
- loud
- mass-market e-commerce

### Visual Metaphor

Aura is closer to:
- a personal stylist’s private studio
- a fashion editor’s notebook
- a premium wardrobe planning companion

Aura is not:
- a marketplace homepage
- a chatbot utility shell
- a productivity dashboard

## Visual System

### Color Principles

Use a warm, fashion-forward neutral base with restrained dramatic accents.

Primary palette intent:
- light, soft, warm backgrounds
- strong ink contrast for elegance
- muted romantic accent colors
- richer dark tones for sophistication

Recommended palette roles:
- `Background`: bone, porcelain, soft sand
- `Surface`: warm ivory, cream, oat
- `Primary text`: espresso, softened black
- `Secondary text`: taupe-gray, warm slate
- `Accent 1`: mulberry / oxblood
- `Accent 2`: olive ink / moss slate
- `Accent 3`: rose smoke
- `Highlight`: muted antique gold, used sparingly

Color usage rules:
- backgrounds should not be flat white by default
- avoid cold gray-heavy UI
- avoid strong neon or synthetic gradients
- use accent color sparingly and intentionally
- separate wardrobe and catalog visually through subtle tonal signals, not loud labels

### Example Semantic Tokens

These are platform direction tokens, not implementation-locked values.

```css
:root {
  --bg-canvas: #f6f0ea;
  --bg-soft: #efe6dc;
  --surface-primary: #fffaf5;
  --surface-secondary: #f7f1eb;
  --ink-primary: #1f1a17;
  --ink-secondary: #5f5853;
  --ink-tertiary: #8b847d;
  --line-subtle: #ddd2c7;
  --accent-editorial: #6f2f45;
  --accent-wardrobe: #58624d;
  --accent-soft: #b98a8f;
  --accent-gold: #b08a4e;
  --success-soft: #6f8a72;
  --warning-soft: #9b7b5a;
}
```

### Typography

Typography must carry style authority.

Recommended structure:
- Display: serif with fashion/editorial character
- UI/body: refined sans serif
- Utility/meta: compact sans or restrained mono in rare cases

Typography principles:
- headlines should feel composed and luxurious
- body copy should remain highly readable
- use generous line spacing
- rely on hierarchy and spacing, not excessive font-size jumps

Recommended pairing direction:
- Display: Canela, Cormorant Garamond, Ivar, Editorial New, or similar
- Body/UI: Avenir Next, Neue Haas Grotesk, Suisse, Manrope, or similar

Usage guidance:
- major page titles: serif
- recommendation titles: serif or strong sans depending on layout
- controls, chips, labels, form fields: sans
- confidence / metadata labels: compact sans

### Spacing And Layout

Use generous spacing. Aura should breathe.

Rules:
- prefer larger outer margins and calmer grouping
- avoid cramped cards
- avoid dense sidebars with tiny controls
- recommendation content should have clear vertical rhythm

Layout principle:
- one strong focal area per screen
- one clear supporting rail at most
- one obvious action area

### Shape Language

The UI should use soft structure, not generic rounded SaaS cards everywhere.

Rules:
- use medium-to-large radii on primary surfaces
- use cleaner, slightly tighter radii inside content modules
- layer surfaces subtly
- prefer framed image panels and elevated cards over plain bordered boxes

### Imagery

Fashion product quality depends on image treatment.

Rules:
- imagery should always be given room
- use soft background framing behind garments
- preserve aspect ratio and avoid awkward crops
- main recommendation imagery should feel premium and editorial
- thumbnails should feel tactile and curated

## Motion System

Motion should feel soft and intentional.

Allowed motion patterns:
- fade + slight rise on content reveal
- image crossfade on look switching
- staggered entrance for outfit cards
- gentle slide for chips and filters
- subtle hover lift

Avoid:
- bounce
- spring-heavy motion everywhere
- spinners as primary waiting experience
- excessive shimmer

Loading patterns:
- use elegant stage messaging for “stylist is thinking”
- where possible show partial progress in human language
- loading should reassure, not entertain

## UX Architecture Principles

### End-To-End Journey Model

Aura’s canonical product journey is:

1. Discovery
- the user understands Aura as a stylist studio
- the interface reveals core jobs before the user types anything

2. Onboarding
- OTP, profile, images, and style preference establish the personalization contract
- chat remains blocked until the required profile state is complete

3. Unlock
- the user lands in a stylist dashboard, not an empty conversation shell
- the dashboard should expose profile value, wardrobe value, and one clear next action

4. First Value
- the user completes one meaningful styling task with visible profile grounding
- the first answer should establish source trust: wardrobe, catalog, or hybrid

5. Repeat Usage
- the user returns through saved looks, recent threads, wardrobe studio, and guided flows
- the experience should shorten time-to-next-decision with every session

6. Wardrobe Growth
- the user adds pieces, edits closet metadata, and gradually shifts from catalog dependence to wardrobe confidence

7. WhatsApp Return Loop
- the user comes back through WhatsApp for fast lightweight decisions
- handoff back to web should preserve task, tone, and context

### First-Run Experience

Post-onboarding first run must feel like:
- your stylist studio is ready
- your profile is already doing useful work
- here is the smartest next thing to do

It must not feel like:
- chat unlocked
- blank page, now ask something
- generic assistant shell

Required first-run components:
- editorial welcome state
- quick-entry styling actions
- visible style profile summary
- visible wardrobe status or next wardrobe action
- one obvious first-value route

### Ideal First-Session Paths By Job

#### Occasion Outfit
1. user enters through `Dress Me`
2. user provides occasion and optional source preference
3. Aura returns source-labeled looks with a stylist summary
4. user pivots into alternatives, explanation, or wardrobe/catalog refinement

#### Pairing
1. user enters through `Style This` or uploads a garment image
2. Aura treats the garment as the anchor
3. pairing options appear around the anchor
4. user pivots into catalog upgrades, explanation, or look saving

#### Outfit Check
1. user enters through `Check Me` or uploads a current look
2. Aura critiques the outfit in a stylist voice
3. wardrobe swaps appear before catalog suggestions
4. user either improves the look or escalates into catalog help

#### Shopping Decision
1. user pastes a product URL
2. Aura gives buy / skip guidance
3. user pivots into pairing, safer alternatives, or wardrobe integration

#### Style Advice
1. user enters through `Know Me`
2. Aura answers through profile evidence, not generic styling content
3. user pivots into narrower attribute questions
4. user moves from knowledge into an outfit or shopping action

#### Trip Planning
1. user enters through `Trips`
2. user provides duration and context
3. Aura returns a wardrobe-first plan with hybrid fillers when needed
4. user pivots into shopping list, day-specific edits, or packing logic

### Primary Navigation Model

Aura should be organized around user jobs, not internal modules.

Primary experience categories:
- Dress Me
- Style This
- Check Me
- Know Me
- Wardrobe
- Trips

These can appear as tabs, entry cards, or navigation anchors depending on screen size.

This navigation model should remain stable across web entry points, mobile layouts, and WhatsApp handoff destinations.

### Home Experience

The home screen should be a stylist hub.

It should include:
- editorial hero
- quick entry actions
- today’s recommended action
- wardrobe health insight
- style profile summary
- recent threads / saved looks

It should not open with:
- a blank chat box alone
- a technical dashboard
- a dense settings-first layout

### Chat Experience

Chat is the engine, not the entirety of the product.

The chat surface should:
- make mode switching easy
- support image, URL, and text-first input naturally
- expose contextual chips before and after responses
- keep the composer premium and prominent

The composer should support:
- text
- image attach
- paste URL
- context chips
- source preference toggles when relevant

Recommended context chips:
- Use My Wardrobe
- Catalog Only
- For Work
- For Dinner
- Explain Why
- Show Swaps

### Recommendation Experience

Every recommendation answer should be layered:

1. Stylist summary
- short
- warm
- opinionated
- high-confidence in tone without sounding absolute

2. Look cards
- image-first
- source-labeled
- clearly grouped

3. Why it works
- expandable
- includes rationale, confidence, wardrobe/catalag basis, and feedback hooks

### Wardrobe Experience

The wardrobe should feel like a living closet, not a product database.

Required qualities:
- highly visual
- easy to browse
- easy to style from any item
- easy to understand gaps

Wardrobe UX should support:
- browse all items
- edit metadata
- delete
- filter by occasion / role / color
- start “Style This”
- start “Pack For Trip”

### Outfit Check Experience

Outfit check should feel like a stylist consultation.

Response structure:
- overall verdict
- what works
- what to tweak
- wardrobe swap suggestions
- optional catalog improvement path

Do not present it like:
- a grading rubric first
- a cold scorecard

### Style Discovery Experience

Style discovery should feel educational and intimate.

Questions like:
- what collar suits me
- what colors suit me
- what patterns suit me
- which archetypes fit me

should ideally be answered with:
- direct advice
- profile evidence
- visual examples when possible
- next useful question

### Trip / Capsule Experience

Trip planning should feel like itinerary + wardrobe planning.

Required UX outputs:
- trip summary
- daypart / context-labeled looks
- packing list
- gaps
- catalog-supported fillers

Avoid:
- a flat repeated list of similar looks
- no timeline or context labeling

## Response Design Rules

### Source Clarity

Every styling answer must expose source mode:
- wardrobe-first
- catalog-only
- hybrid

This should be visible in:
- metadata-backed badges
- section labels
- recommendation grouping

### Follow-Up Design

Follow-ups should be structured by user intent.

Preferred follow-up groups:
- Improve It
- Show Alternatives
- Explain Why
- Shop The Gap
- Save For Later

### Feedback Design

Feedback should feel fashion-native.

Preferred signals:
- Love this
- Too safe
- Too much
- Not me
- Weird pairing
- Show softer
- Show sharper

Avoid reducing all feedback to only generic thumbs up/down in the main experience.

## Accessibility And Usability Rules

Aura must remain elegant without sacrificing usability.

Rules:
- minimum readable text contrast
- clear focus states
- tap targets large enough for mobile
- not color-only meaning
- keyboard accessibility for primary actions
- motion reduction support

## Responsive Design Rules

### Mobile

Mobile is not a reduced desktop dashboard.

Mobile priorities:
- strong single-column hierarchy
- image-first stacking
- sticky composer or bottom action zone
- easy thumb access
- minimal side-by-side dense comparison

Required mobile variants:
- Home: single-column stylist hub with quick actions near the top
- Chat: sticky composer, compact grouped follow-ups, and visually stacked recommendation modules
- Wardrobe: chip filters above a 1-column or 2-column closet grid
- My Style Code: stacked facts and guidance cards
- Outfit Check / Trips: summary first, actions second, supporting detail below

### Desktop

Desktop should feel like a studio workspace.

Desktop priorities:
- editorial composition
- generous whitespace
- image focus with one supporting rail
- clean task switching between chat, wardrobe, and look details

Required desktop variants:
- Home: hero-led hub with supporting insights and memory modules
- Chat: central conversation workspace with surrounding mode and source context
- Wardrobe: closet grid plus supporting health / gap rail
- My Style Code: split profile summary and guidance layout
- Outfit Check / Trips: consultation layout with clear summary, actions, and context modules

### Viewport Validation Standard

Before marking a major surface complete, validate it at minimum in:
- mobile-first width: 390px to 430px
- desktop-studio width: 1280px to 1440px

Every primary surface must be checked for:
- hierarchy clarity
- no clipped text or overlapping controls
- readable recommendation modules
- reachable follow-up actions
- visible source labels
- usable composer behavior
- no post-onboarding empty-state confusion

Primary surfaces to validate:
- stylist hub home
- chat workspace
- wardrobe studio
- My Style Code
- outfit check flow
- trip planner flow

## Fashion-Specific Product Rules

### 1. Never Echo The Anchor As The Whole Answer

If a user asks for pairing or outfit completion around a garment, the UI and logic must present complementary pieces, not just the garment itself.

### 2. Never Hide Source Intent

If Aura uses the catalog after a wardrobe-first request, the UI must make that clear.

### 3. Do Not Force Shopping

Wardrobe-first flows must feel complete even if the user never buys anything.

### 4. Teach Taste Gently

Style advice should feel like stylish guidance, not correction.

### 5. Preserve Emotional Safety

Outfit check and style discovery should never feel shaming, clinical, or harsh.

## Implementation Guidance For Future UI Work

Before adding or changing a screen, validate:
- what user job it supports
- whether the source mode is clear
- whether the visual hierarchy is image-first
- whether the interface feels premium enough for a fashion product
- whether the screen teaches the user what Aura can do

Before shipping a new component, validate:
- does it feel stylist-led, not dashboard-led
- does it harmonize with the warm editorial palette
- does it preserve strong typography hierarchy
- does it work on mobile first
- does it avoid generic AI-app design tropes

## Non-Negotiables

- Aura must not look like a generic chatbot.
- Aura must not look like a generic shopping marketplace.
- Aura must not rely on flat white screens and default UI kits.
- The wardrobe must feel central to the product.
- Recommendation answers must prioritize taste and guidance before metrics.
- The experience must feel aspirational but usable in everyday life.
