# Design System And Experience Principles

Last updated: April 11, 2026 — "Confident Luxe" refinement (see § Brand Direction — Confident Luxe). Migration to the refined token set is tracked as Phase 14 in `docs/WORKFLOW_REFERENCE.md` § Phase History; validation criteria are in `docs/DESIGN_SYSTEM_VALIDATION.md`.

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

The design system is applied uniformly across all surfaces: onboarding, profile analysis/processing, main chat app, profile, wardrobe, results, and catalog admin. The **target** token set (post-Phase 14) is warm ivory (`#F7F3EC`) canvas, deep espresso ink (`#16110E`), oxblood accent (`#5C1A1B`), champagne signal (`#C6A15B`), Fraunces (variable, SIL OFL) for display type, and Inter for body/UI. The **legacy** tokens (`#f6f0ea` cream canvas, `#6f2f45` wine accent, Cormorant Garamond + Avenir Next) are being migrated away — any surface still carrying them is a Phase 14 follow-up, not the reference state.

Key UI patterns implemented:
- **Unified profile page**: Single page with inline edit toggle — view mode shows read-only fields, edit mode switches to inputs/selects in place. Includes style code card and personalized color palette card (base/accent/avoid chips).
- **Chat composer**: `+` button opens a popover with "Upload image" (file picker), "Select from wardrobe" (modal with wardrobe grid), and "Select from wishlist" (modal with wishlisted catalog products). Supports drag-drop and paste.
- **Chat welcome screen with progressive disclosure**: The chat homepage leads with **one dominant primary CTA** (`Dress me for tonight`) and tucks the four secondary prompts behind a `More ways to style` toggle. Accessible `aria-expanded` and `prefers-reduced-motion` support.
- **Chat management**: Conversation sidebar with hover-reveal rename (inline edit) and delete (archive with confirmation) actions per history item. Title column on conversations table.
- **Wardrobe add-item modal**: Photo upload with preview, auto-enrichment (46 attributes via vision API).
- **Wardrobe edit modal**: Full metadata edit form (title, description, category, subtype, colors, pattern, formality, occasion, brand, notes) with image preview. Calls PATCH endpoint.
- **Wardrobe delete**: Per-card delete button with confirmation dialog. Soft-deletes via is_active=false.
- **Wardrobe filters**: Search bar (title/description/brand/category), category chips (All, Tops, Bottoms, Shoes, Dresses, Outerwear, Accessories, Occasion-ready), color filter row (11 colors), and localStorage persistence across page loads. The `Occasion-ready` chip now matches against the enrichment metadata tag set (`wedding`, `cocktail_party`, `office`, `semi_formal` + formality `smart_casual` and above) instead of "any non-empty `occasion_fit`".
- **Outfit PDP card**: Full-width header (title + Like/Hide icons + full stylist reasoning) above 3-column body for recommendations (thumbnails | hero | products + chart) or 2-column body for outfit checks (hero | chart). Products show title / Rs. price / Buy Now + Save — or item names only for outfit checks. **Split polar bar chart** (Nightingale-style): top semicircle = 8-axis style archetype profile (champagne `--signal`), bottom semicircle = dynamic 5-9 axis fit/evaluation profile (oxblood `--accent`), raw evaluator scores (no confidence scaling), dashed horizontal divider. Outfit check cards use the evaluator's descriptive title (not hardcoded "Outfit Check"). Hide opens a feedback modal with reaction chips + textarea before removing the card.
- **Follow-up suggestions as labelled groups**: Quick-reply chips rendered under bucket headers (`Improve It`, `Show Alternatives`, `Shop The Gap`), driven by `follow_up_groups` on response metadata. Clicking a follow-up chip adds a new iteration carousel row within the same intent group (iteration stacking).
- **Wardrobe-first copy**: Wardrobe-first occasion responses name the selected pieces and explain *why* they fit. Hybrid responses name both wardrobe anchors and catalog gap-fillers explicitly.
- **Wishlist tab** (Saved): grid of wishlisted catalog garments with title, price, Buy Now link. Data from `catalog_interaction_history` hydrated with `catalog_enriched`.
- ~~Trial Room tab~~: **removed** — try-on images now live inside their outfit groups in the Outfits tab.

Related docs:
- [`docs/PRODUCT.md`](PRODUCT.md) — product definition and user journey
- [`docs/APPLICATION_SPECS.md`](APPLICATION_SPECS.md) § Live System Reference — **source of truth** for implementation state, runtime, modules, persistence
- [`docs/RELEASE_READINESS.md`](RELEASE_READINESS.md) — 4-gate release checklist + Recently Shipped record
- [`docs/DESIGN_SYSTEM_VALIDATION.md`](DESIGN_SYSTEM_VALIDATION.md) — manual QA checklist a designer must complete before the design gate goes green
- [`docs/WORKFLOW_REFERENCE.md`](WORKFLOW_REFERENCE.md) — per-intent execution flows + Phase History decision log

## Brand Direction — Confident Luxe

Aura's brand direction is **Confident Luxe**: the hushed restraint of a private atelier combined with the personality and wit of a modern fashion-girl house. It is premium without being cold, distinctive without being loud, personal without being precious.

**Mood in one line:** a maison that winks. Quiet where it matters, distinctive where it counts.

**Three anchors** — every design decision should satisfy all three:

1. **Bespoke** — the experience must feel one-of-one for the user. Personalization is never decoration, it is jewelry: small, precise, costly-looking. Champagne (`--signal`) is the colour of *you*, and it is never used anywhere else.
2. **Assured** — the interface never pleads, explains, or apologises. Confidence comes from restraint: hairline borders instead of shadows, uppercase tracked labels instead of pills, one primary action per screen, no decorative micro-interactions, no AI-app visual clichés.
3. **With a point of view** — the personality is concentrated in a few deliberate moments (empty states, verdict cards, the style dossier), not diffused across the surface. Those moments use oversized italic display type and voice-led copy. Everything else is quiet.

**Mood references** (intent only — not direct clones):
- Jacquemus at its most refined (recent campaigns, not the circus), Khaite, Phoebe Philo's new line
- Bottega Veneta under Matthieu Blazy, Alaïa, The Row when it plays
- Mytheresa Personal Shopping, Farfetch Private Client, a maison client studio

**What Confident Luxe is not:**
- A warm-craft boutique (the legacy cream + wine feel). That reads handmade, not maison.
- A magazine or publication aesthetic (SSENSE / The Row cold monochrome, Vogue-style editorial layouts). That reads impersonal — Aura is *your* stylist, not a publication. **This is the direction that was considered and explicitly rejected.**
- A trend-chasing fashion-girl costume (pink overload, glitter, "girlboss" tropes). That reads adolescent.
- A productivity or AI-assistant shell. That reads generic.

The direction sits deliberately between these failure modes: warm but sharp, feminine but unfussy, personal but disciplined.

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
- maison-grade visual composure
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
- bespoke (one-of-one, not a template)
- assured (confident without pleading)
- intimate
- polished
- intelligent
- reassuring
- aspirational
- with a point of view

It should not feel:
- corporate
- sterile
- adolescent
- loud
- mass-market e-commerce
- warm-craft or boutique-artisanal (the legacy direction)
- magazine-like or publication-coded (the rejected "editorial" direction — Aura is a stylist, not a Vogue spread)

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

Use a warm-ivory base, a near-black espresso ink, and one confident accent (oxblood) that carries all the personality. Champagne is reserved exclusively for personal cues — never as decoration.

Primary palette intent:
- warm-ivory canvas (not cream, not pure white, not grey)
- near-black espresso ink for typographic authority
- one confident accent — **oxblood** — used sparingly
- **champagne** reserved *exclusively* for personalized moments (your season, your palette, your matched items, the 1px rule on personalized advice)
- richer dark tones for sophistication
- dark mode parity, not an afterthought

Recommended palette roles:
- `Canvas`: warm ivory — the dominant background
- `Surface`: slightly lifted off-ivory for cards and panels
- `Surface-sunk`: slightly sunk for chips, secondary fills, user message bubbles
- `Primary text`: espresso-black (near-black, not pure)
- `Secondary text`: warm taupe-grey
- `Tertiary text`: soft taupe for metadata, placeholders
- `Line`: hairline warm-neutral for dividers; borders replace shadows on static cards
- `Accent`: oxblood — primary actions, brand wordmark, active nav, 1px rule on personalized advice cards
- `Signal`: champagne — **personal cues only**; never decorative
- `Positive / Negative`: muted olive-green / muted terracotta — never bright

Color usage rules:
- backgrounds should never be flat white
- avoid cold grey-heavy UI and avoid nostalgic warm-cream craft palettes
- avoid strong neon, synthetic gradients, or decorative colour
- use oxblood sparingly and intentionally — never as a fill for large surfaces
- use champagne **only** for personal cues; two surfaces with champagne in the same viewport is a violation
- separate wardrobe and catalog visually through subtle tonal labels (`YOURS` / `SHOP`), not loud colour
- dark mode is not optional — every surface must have a dark token equivalent

### Example Semantic Tokens

These are the target tokens for Phase 14 and beyond. Legacy tokens are listed at the end for traceability during migration only.

```css
:root {
  /* Light (default) */
  --canvas:         #F7F3EC;   /* warm ivory — dominant background */
  --surface:        #FDFBF6;   /* lifted surface for cards / panels */
  --surface-sunk:   #EEE8DD;   /* sunk surface for chips, user bubbles */
  --ink:            #16110E;   /* espresso-black — primary text */
  --ink-2:          #2E2824;   /* body copy */
  --ink-3:          #6B635C;   /* secondary text */
  --ink-4:          #A69C92;   /* tertiary / placeholder */
  --line:           #E1D8C9;   /* hairline dividers */
  --line-strong:    #C9BCA8;   /* stronger hairline for inputs, active chips */
  --accent:         #5C1A1B;   /* oxblood — primary action, brand wordmark */
  --accent-soft:    #7A2A2C;   /* hover / pressed oxblood */
  --signal:         #C6A15B;   /* champagne — PERSONAL CUES ONLY */
  --positive:       #4A6B3A;   /* muted olive */
  --negative:       #8A2A2A;   /* muted terracotta */

  /* Radii */
  --radius-sm:      4px;       /* chips, tags */
  --radius-md:      8px;       /* buttons, inputs, cards */
  --radius-lg:      14px;      /* modals, composer */
  --radius-full:    999px;

  /* Elevation — hairline borders replace shadows on static surfaces */
  --shadow-pop:     0 1px 2px rgba(22,17,14,.04), 0 8px 24px rgba(22,17,14,.06);
  --shadow-modal:   0 24px 80px rgba(22,17,14,.18);

  /* Motion */
  --ease:           cubic-bezier(.2, .7, .1, 1);  /* expo-out, single curve */
  --dur-1:          120ms;     /* micro — hover, press */
  --dur-2:          240ms;     /* standard — modal, drawer */
  --dur-3:          480ms;     /* slow — view transition, hero reveal */
}

[data-theme="dark"] {
  --canvas:         #0E0B09;
  --surface:        #15110E;
  --surface-sunk:   #0A0806;
  --ink:            #F4EFE5;
  --ink-2:          #D8D1C3;
  --ink-3:          #8A8176;
  --ink-4:          #544D45;
  --line:           #2A231D;
  --line-strong:    #3A312A;
  --accent:         #B34548;   /* oxblood lifted for dark-mode contrast */
  --accent-soft:    #C95A5D;
  --signal:         #D6B373;
  --positive:       #6F9356;
  --negative:       #B3544F;
  --shadow-pop:     0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.5);
  --shadow-modal:   0 24px 80px rgba(0,0,0,.65);
}
```

**Legacy tokens being retired in Phase 14** (reference only — do not reintroduce):

```css
/* Legacy — do not use in new work */
--bg-canvas: #f6f0ea;          /* warm cream — too craft, replaced by #F7F3EC ivory */
--accent-editorial: #6f2f45;   /* rose-wine burgundy — replaced by #5C1A1B oxblood */
--accent-wardrobe: #58624d;    /* retired — wardrobe/catalog distinction is now label-based, not colour-based */
--accent-soft: #b98a8f;        /* retired — no rose-smoke in Confident Luxe */
--accent-gold: #b08a4e;        /* replaced by --signal (#C6A15B), and usage is now restricted to personal cues only */
```

### Typography

Typography carries the personality in Confident Luxe. The display face is where the "wink" lives — used oversized, often italic, on a small number of deliberate moments (see § Tonal Moments). Body type is a neutral, disciplined workhorse so that the display can do all the speaking.

**Target pairing** (Phase 14) — **all faces are free / SIL OFL licensed**. No paid dependencies.

- **Display** — `Fraunces` (Undercase Type, SIL OFL, served by Google Fonts). Variable font with `opsz`, `wght`, `SOFT`, and `WONK` axes. Ball terminals, distinctive swash italic, warm curves without magazine-coding — it reads personal and composed, not publication. Used for hero headlines, view titles, verdict cards, style dossier adjectives, and empty states.
- **Body / UI** — `Inter` (Rasmus Andersson, SIL OFL). Neutral grotesque, full weight range, excellent at small sizes. Used for chat body, form fields, buttons, descriptions, metadata.
- **Label / Mono** — `JetBrains Mono` (SIL OFL). Used sparingly for uppercase tracked labels, garment counts, product codes, and system metadata.

**Fallbacks** (for first load and web-font failure):
- Display: `"Cormorant Garamond"`, Georgia, serif
- Body: `-apple-system`, `"Helvetica Neue"`, sans-serif
- Mono: `ui-monospace`, `"SF Mono"`, `Menlo`, monospace

Cormorant Garamond + Avenir Next are the legacy pair being retired. Cormorant remains in the display fallback stack so no surface goes unstyled during the Phase 14 migration, but no new work should specify either directly. The entire target stack is free — no licensing friction, no commercial gate.

**Type ramp** (modular 1.25, pinned tokens):

| Token | Size / line | Weight | Use |
|---|---|---|---|
| `display-xl` | 72 / 76 | Fraunces 400 | Landing hero, empty states, dossier adjectives |
| `display-lg` | 48 / 52 | Fraunces 400 / 400 italic | View titles (Wardrobe, Looks), verdict headlines |
| `display-md` | 32 / 36 | Fraunces 500 | Section leads, profile name |
| `title` | 20 / 28 | Inter 600 | Card titles, modal headers |
| `body` | 15 / 24 | Inter 400 | Chat, descriptions |
| `body-sm` | 13 / 20 | Inter 400 | Meta, captions, follow-up chip text |
| `label` | 11 / 14 | Inter 600, uppercase, 0.08em tracked | Filter chips, source labels, nav |
| `mono` | 12 / 16 | JetBrains Mono 500 | Product codes, counts, system metadata |

Typography principles:
- headlines feel composed and luxurious — rely on size + italic for emphasis, not colour
- body copy remains highly readable at 15px / 24 line-height
- use generous line spacing; avoid tight leading
- rely on hierarchy and spacing, not excessive font-size jumps
- italic display type is a personality moment — do not use it for body copy or chrome
- all uppercase use must have ≥ 0.08em letter-spacing

Usage guidance:
- major page titles: display (serif)
- verdict / personal moments: display italic, oversized
- recommendation titles: `title` (Inter 600)
- controls, chips, labels, form fields: `label` (Inter uppercase tracked) or `body-sm`
- confidence / metadata labels: `mono`

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

The UI uses soft structure, not generic rounded SaaS cards everywhere, and it uses **hairline borders over drop shadows** on static surfaces. This is the single largest visual shift in Confident Luxe.

Rules:
- use the pinned radius tokens: `--radius-sm` (4px) for chips and tags, `--radius-md` (8px) for buttons / inputs / cards, `--radius-lg` (14px) for modals and the composer
- **static surfaces use a 1px `--line` border, not a drop shadow.** Ambient drop shadows on cards is the biggest "warm-craft dashboard" tell and must be removed.
- shadow is reserved for genuinely floating surfaces: modals, popovers, drawers, the composer on focus. Use `--shadow-pop` for popovers, `--shadow-modal` for modals.
- avoid more than 2px of radius difference between siblings in the same module — the shape language should feel precise, not playful
- prefer framed image panels. Garment cards carry no border and no background — just the image + metadata below it. The image *is* the card.
- layer surfaces subtly using `--surface` and `--surface-sunk` rather than with shadow

### Imagery

Fashion product quality depends on image treatment.

Rules:
- imagery should always be given room
- use soft background framing behind garments
- preserve aspect ratio and avoid awkward crops
- main recommendation imagery should feel premium and composed — maison-grade, not catalog-flat
- thumbnails should feel tactile and curated

## Motion System

Motion is soft, intentional, and built from a single easing curve and three durations. One curve + three durations = discipline. Variation comes from *what* moves, not *how*.

Tokens (pinned):

```css
--ease:  cubic-bezier(.2, .7, .1, 1);   /* expo-out — the only curve */
--dur-1: 120ms;                          /* micro — hover, press, chip state */
--dur-2: 240ms;                          /* standard — modal, drawer, tab switch */
--dur-3: 480ms;                          /* slow — view transition, hero reveal */
```

Allowed motion patterns:
- fade + slight vertical rise (4–8px) on content reveal
- image crossfade on look switching
- staggered entrance for outfit cards (60ms stagger, `--dur-2`)
- gentle lateral slide for chips, filters, and history drawer
- subtle underline-reveal on nav and history items
- uppercase labels tracking in from the left by 4–6px (the "runway program" detail — used once per view, not everywhere)

Avoid:
- bounce and spring-heavy motion
- scale transforms over 1.02 on hover (no zoom-in cards)
- spinners as primary waiting experience
- excessive shimmer or animated gradients
- decorative micro-interactions that exist for their own sake
- more than one easing curve anywhere in the product

Loading patterns:
- use elegant stage messaging for "stylist is thinking" (see § Voice & Microcopy for the copy rules)
- where possible show partial progress in human language
- loading should reassure, not entertain

Accessibility:
- respect `prefers-reduced-motion: reduce` — fall back to instant opacity changes, disable the tracking-in label detail, disable stagger

## Tonal Moments — Where The Personality Lives

Confident Luxe concentrates its fashion-girl personality in a small number of deliberate moments. Everything outside of these moments is hushed. The discipline is what keeps the product premium — if personality leaks into chrome, the surface becomes costume.

The four sanctioned tonal moments:

1. **Empty states** — oversized italic display type, short confident copy with no question marks.
   - Chat empty state: *"Good evening, Mj. What are we wearing."* (72/76 display italic)
   - Wardrobe empty-category state: *"Your outerwear lives here."* (48/52 display italic) + one ghost "Add a piece" button
   - Looks empty state: *"Nothing saved yet. Let's find something."*

2. **Verdict cards** (buy / skip / pairing) — the verdict word is set in oversized display italic, alone, over a full-bleed product image. No colour fill, no badge, no icon — just type and image.
   - `Worth it.` — 48/52 display italic
   - `Skip.` — 48/52 display italic
   - `Maybe.` — 48/52 display italic (used for conditional verdicts)
   - A single `body` line underneath explains *why* in one sentence.

3. **Style dossier** (profile view) — style adjectives rendered as oversized quote blocks in display italic on the canvas, one per line, no punctuation.
   - *Sculptural*
   - *Unfussy*
   - *Warm*
   - The dossier as a whole is treated as a printed page, not a settings screen.

4. **Motion detail** — the "runway program" track-in on uppercase labels (see § Motion System). Used *once per view*, typically on section labels, never on every element. One tasteful motion detail is the signature; many is noise.

Rules for tonal moments:
- italic display type only appears in these four contexts — never in body copy, nav, buttons, chips, or metadata
- personality moments never carry chrome: no borders, no shadows, no backgrounds. Just type and image.
- never dilute a tonal moment by adding a secondary CTA above or beside it. One idea per moment.

## Voice & Microcopy

Copy is a fashion-native voice, not AI-assistant voice. Short, composed, a little knowing, never cheerful-chatbot.

**Source labels** (uppercase tracked, `label` type):

| Label | Meaning | Where |
|---|---|---|
| `YOURS` | From the user's saved wardrobe | On garment and outfit cards, follow-up chips |
| `SHOP` | From the catalog | On catalog-backed cards |
| `HYBRID` | Mixed wardrobe + catalog | On outfit cards that combine sources |
| `ON YOU` | Virtual try-on render | On try-on gallery tiles |
| `FOR YOU` | Personalized pick keyed to palette / body shape / style code | Reserved for the champagne 1px-rule cards |

**Verdict labels** (display italic):

| Label | Meaning |
|---|---|
| `Worth it.` | Buy verdict |
| `Skip.` | Skip verdict |
| `Maybe.` | Conditional verdict |
| `Not yours.` | Style-mismatch verdict (used gently) |

**Follow-up bucket headings** (uppercase tracked, `label` type):

- `IMPROVE IT`
- `SHOW ALTERNATIVES`
- `SHOP THE GAP`
- `EXPLAIN WHY`
- `SAVE FOR LATER`

These replace generic follow-up copy and must be rendered as grouped headers, never a flat list.

**Loading / thinking states** — short stylist-voice lines, no ellipsis animation:

- *Laying pieces on the table.*
- *Looking through your closet.*
- *Pairing this back for you.*
- *Finding something that fits.*

**Copy rules:**
- no exclamation marks anywhere in user-facing copy
- no smileys, no emoji in chrome (emoji is permissible in user messages, not in system UI)
- no "Hi!" / "Hey there!" / chatbot openers — greet by name and go
- end empty-state copy with a period, not a question mark ("What are we wearing.")
- never say "AI", "model", "prompt", "LLM", "agent" in user-facing copy

## Dark Mode

Dark mode is not optional and not an afterthought. Every surface must carry a dark token equivalent (see the `[data-theme="dark"]` block in § Example Semantic Tokens).

Rules:
- canvas is `#0E0B09` (espresso-black, not pure black, not grey) — the warmth must persist in dark mode
- oxblood lifts to `#B34548` for AA contrast on dark surfaces
- champagne lifts to `#D6B373` and remains restricted to personal cues only
- no dark mode uses pure black (`#000`) — it flattens the warmth and reads generic
- drop-shadow tokens shift to heavier opacities on dark (see dark token block) so floating surfaces still read as floating
- all imagery must remain legible — avoid decorative dark-mode overlays or tints on product photos
- the theme toggle is a one-sentence affordance in the profile view, plus a keyboard shortcut; it is not a header icon (we are not a dashboard)
- default: honour `prefers-color-scheme`. Explicit user choice persists in localStorage and overrides the system preference.

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
- Confident Luxe welcome moment (display-italic greeting, see § Tonal Moments)
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

### Primary Navigation Model (Phase 15 — Intent-Organized)

Aura is organized around intent-organized history, not chat threads.

Navigation tabs:
- **Home** — discovery surface: centered input + PDP carousel for the active request + recent intent group previews
- **Outfits** — intent-grouped history: occasion recommendations, pairings, trip planning. Each section = Fraunces italic title + PDP carousel. Try-ons embedded in cards.
- **Checks** — outfit check history cards
- **Wardrobe** — closet grid with filters
- **Saved** — wishlist

This navigation replaces the previous chat-organized model (Chat / Wardrobe / Looks / Saved / Trial Room). There is no conversation sidebar, no chat bubbles, no Trial Room tab.

### Home Experience (Discovery Surface)

The home screen is a discovery surface, not a chat.

It should include:
- Fraunces italic headline ("What are we wearing.")
- centered input bar (search-bar energy, not chat-composer)
- prompt suggestions below the input
- on submit: PDP carousel with context summary + follow-up chips
- recent intent group previews below the active result area

It should not open with:
- a chat box
- a conversation history sidebar
- a technical dashboard

### Input Model

The input bar is the primary interaction point. It replaces the chat composer.

The input should support:
- text queries describing what the user needs
- image attach (upload, paste, wardrobe picker)
- follow-up chips below PDP carousels for iteration within an intent

Responses render as PDP carousels, not chat bubbles. The assistant’s text message becomes a brief context summary above the carousel.

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
- composed, unhurried layout with strong vertical rhythm
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
- does it harmonize with the Confident Luxe palette (ivory / espresso / oxblood / champagne-for-personal-only)
- does it preserve strong typography hierarchy without leaking italic display type into chrome
- does it work on mobile first, with dark-mode parity
- does it avoid generic AI-app design tropes and warm-craft boutique tells (no drop shadows on static cards, no serif-over-serif collisions, no rose-wine accents)

## Non-Negotiables

- Aura must not look like a generic chatbot.
- Aura must not look like a generic shopping marketplace.
- Aura must not rely on flat white screens and default UI kits.
- Aura must not reintroduce the legacy warm-cream + rose-wine palette. `#f6f0ea` and `#6f2f45` are retired.
- Aura must not use drop shadows on static cards. Hairline borders only.
- Aura must not use italic display type outside the four sanctioned tonal moments (empty states, verdicts, dossier, runway motion detail).
- Aura must not use champagne (`--signal`) anywhere that is not a personal cue. Two champagne surfaces in the same viewport is a violation.
- Aura must not ship a light-only surface. Dark mode parity is required for every new screen.
- The wardrobe must feel central to the product.
- Recommendation answers must prioritize taste and guidance before metrics.
- The experience must feel aspirational but usable in everyday life.

---

# Outfit Card UI Reference (migrated May 3, 2026)

_Migrated from `CURRENT_STATE.md`. The Composer + 3-Column PDP layout specs previously lived in CURRENT_STATE.md and are consolidated here so DESIGN.md owns the UI specification._

## Chat UI: Composer + Outfit Cards

Chat composer features:
- `+` button popover with two options: "Upload image" (triggers file picker) and "Select from wardrobe" (opens wardrobe picker modal)
- image chip preview with remove button for attached images
- paste support for images from clipboard
- drag-and-drop image attach onto composer area
- wardrobe picker modal loads user's wardrobe items as a grid; selecting an item attaches its image

## Chat UI: Outfit Card — 3-Column PDP Layout + Feedback CTAs

Status:
- implemented

Current UI behavior (implemented):
- one unified PDP-style card per outfit (`.outfit-card` CSS class)
- desktop: 3-column grid (`80px | flex | 40%`)
  - Col 1: vertical thumbnail rail (product images + try-on, 64×64px, active accent border)
  - Col 2: hero image viewer (full height, default to try-on when present)
  - Col 3: info panel (title, stylist summary ≤100 chars, product specs with Rs. price + Buy Now, style archetype radar chart, evaluation criteria radar chart scaled by analysis_confidence_pct, icon feedback buttons)
- mobile (`max-width: 900px`): hero image → horizontal thumbnail strip → info panel

Thumbnail ordering:
- paired outfit: topwear, bottomwear, virtual try-on
- single-piece: garment, virtual try-on
- default hero: try-on when present, otherwise first garment

Feedback behavior:
- `Like This` — sends `event_type: "like"` immediately via POST to `/v1/conversations/{id}/feedback`
- `Didn't Like This` — expands textarea + Submit; cancel collapses
- loading spinner and success/error state on submission
- feedback hides CTAs after successful submission

Feedback persistence:
- UI is outfit-level; backend fans out to one `feedback_events` row per garment
- `recommendation_run_id` has been removed from `feedback_events`; turn-level correlation now uses `turn_id` + `outfit_rank`
- correlation: `conversation_id` + `turn_id` + `outfit_rank`
- `feedback_events` columns: `turn_id` (FK to conversation_turns), `outfit_rank` (int)
- `turn_id` injected into `response.metadata` by the orchestrator

Data flow (implemented):
- `response_formatter._build_item_card()` passes through 16 fields including 6 enrichment attributes
- `response_formatter` passes through all 16 `_pct` fields (8 criteria + 8 archetype) from `EvaluatedRecommendation` to `OutfitCard`
- `api_schemas.OutfitCard.tryon_image` aligned with internal `schemas.OutfitCard.tryon_image`
- `api_schemas.OutfitCard` carries all 16 `_pct` fields aligned with internal schema
- `api_schemas.OutfitItem` carries all enrichment attributes
- `api_schemas.FeedbackRequest` validates `event_type` via regex pattern `^(like|dislike)$`

Current catalog weakness:
- some source catalogs do not persist canonical absolute `url`
- some rows only provide `store` and `handle`

Current ingestion behavior:
- `catalog_enriched.url` and `catalog_enriched.product_url` are now canonicalized during ingestion
- if a row lacks an absolute URL but has known `store + handle`, ingestion synthesizes the canonical absolute product URL
- catalog admin and ops now expose an explicit URL backfill path for older stored rows missing canonical URLs

Current runtime behavior:
- runtime now trusts canonical persisted `url` values and only normalizes already-present URLs
- local and staging backfill checks returned zero rows needing repair at the time of cleanup

Correct long-term fix:
- keep catalog ingestion/backfill healthy so runtime can remain dependent on canonical persisted URLs only

