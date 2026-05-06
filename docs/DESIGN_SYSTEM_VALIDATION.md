# Design System Validation Checklist

Last updated: April 11, 2026 — refreshed for the "Confident Luxe" brand direction (see `docs/DESIGN.md` § Brand Direction — Confident Luxe). Phase 14 in `docs/WORKFLOW_REFERENCE.md` § Phase History tracks the migration from the legacy warm-cream + rose-wine tokens to the refined ivory + oxblood tokens. This checklist is the acceptance gate for Phase 14.

This is the manual QA checklist a designer (not the implementing engineer)
must complete before the first-50 release. It is the artifact behind the
two open items in `docs/RELEASE_READINESS.md` Gate 4 / `docs/DESIGN.md` § Design System Validation:

- Validate all primary screens mobile-first, then desktop
- Ensure the entire surface feels feminine, premium, and fashion-native
  rather than dashboard-like — specifically that it reads as
  **Confident Luxe** (a maison that winks, bespoke + assured + with a
  point of view) rather than the two rejected failure modes: warm-craft
  boutique (the legacy direction) or magazine / publication aesthetic
  (the explicitly-rejected "editorial" direction)

The checklist is split into three layers: device walkthroughs (now
including a dark-mode pass and a Confident Luxe tonal audit), the
"Confident Luxe vs dashboard" tone audit (refreshed for the new tokens),
and the per-screen polish list. Each layer must be fully green for the
doc item to be marked complete. Walk every journey in **both light and
dark mode** at each viewport.

How to run this:

1. Open Aura in a real browser (not just devtools) at the two
   breakpoints below.
2. Walk through the journeys in order. Tick boxes as you go.
3. File any "fail" items as GitHub issues with the screenshot attached
   and the exact viewport width in the title.

Breakpoints:

- **Mobile-first:** 375 × 812 (iPhone SE / 13 mini), then 430 × 932
  (iPhone 14 Pro Max). Real device preferred.
- **Tablet pivot:** 820 × 1180 (iPad).
- **Desktop:** 1280 × 800 minimum, 1440 × 900 preferred. Real laptop.

---

## Layer 1 — Device walkthroughs (mobile-first, then desktop)

For each viewport, walk the journey and confirm every box.

### Journey A — First-time onboarded user lands on `/`

- [ ] Mobile 375 — homepage loads with one dominant primary CTA (`Dress me
      for tonight`) above the fold; secondary actions are hidden behind
      `More ways to style`.
- [ ] Mobile 375 — sticky composer is reachable with one thumb, tap targets
      ≥ 44 × 44 px.
- [ ] Mobile 430 — same as above, no horizontal scroll.
- [ ] Tablet 820 — primary CTA still dominant; cards reflow but stay
      single-column.
- [ ] Desktop 1280 — homepage looks like a stylist hub, not a stacked
      mega-page; no section feels orphaned.

### Journey B — Chat → wardrobe-first occasion answer

- [ ] User can ask "What should I wear to the office tomorrow?" and the
      response renders as a single hero outfit card with named pieces.
- [ ] The reasoning text names the actual wardrobe pieces (not "Built from
      your saved wardrobe for office").
- [ ] Follow-up suggestions render as labelled groups (`Improve It`,
      `Show Alternatives`, `Shop The Gap`), not a flat list.
- [ ] All three buckets are visually distinct from each other.

### Journey C — Chat → hybrid pivot when wardrobe is incomplete

- [ ] When the wardrobe is incomplete, the response explicitly says which
      pieces came from the catalog and which roles they filled.
- [ ] The wardrobe-vs-catalog distinction is visually clear on each card
      (source label + colour).
- [ ] The "Save these catalog picks to my wardrobe" follow-up is reachable.

### Journey D — Wardrobe view

- [ ] Mobile 375 — closet grid is 2-up, cards are square, image leads.
- [ ] Filter chips wrap cleanly; none overflow off-screen.
- [ ] `Occasion-ready` chip filters by enrichment metadata (not by item
      title). Verify by toggling and confirming an item with `occasion_fit
      = wedding` appears while a `everyday` item does not.
- [ ] Add Item modal opens, fills the screen on mobile, and closes
      cleanly.
- [ ] Desktop 1280 — closet grid is 4-up minimum, no clipped cards.

### Journey E — Style code (`/?view=profile`)

- [ ] Mobile 375 — palette + archetypes + body shape are stacked, each
      readable without zoom.
- [ ] Desktop 1280 — same surface uses a 2-column layout without feeling
      empty.

### Journey F — Outfit check

- [ ] User can upload a photo and ask "How does this look?" → response
      renders as a stylist consultation, not a grading rubric.
- [ ] Suggested swaps from the wardrobe are visually distinct from the
      "you wore" original.

### Journey G — Trip / capsule planner

- [ ] User can ask "Plan my wardrobe for a 5-day beach vacation" → outputs
      multiple outfit cards with daypart labels.
- [ ] Subtype/color diversity is visible: looks should not look like the
      same shirt + same trouser × 5. (This is the architect-level diversity
      pass — verify with a real wardrobe.)
- [ ] Packing list is reachable from the same response.

### Journey H — Error / fallback states

- [ ] Force a pipeline failure (e.g. point at an empty catalog environment)
      and confirm the user sees the catalog-unavailable guardrail message,
      not an empty bubble.
- [ ] Force the silent-empty-response guard by mocking an empty
      `assistant_message` — confirm the fallback copy renders.
- [ ] Network offline → composer shows a clear inline error, not a hung
      spinner.

### Journey I — Reduced motion / accessibility

- [ ] System-level "reduce motion" disables all animations on the chat
      welcome screen and outfit cards, including the "runway program"
      uppercase-label track-in and the outfit card staggered entrance.
- [ ] Tab order through the homepage hits primary CTA → "More ways to
      style" toggle → secondary cards in order.
- [ ] Outfit card rater radar (post-R7, May 2026: 6-axis hexagon — Occasion / Body / Color / Pairing / Formality / Statement; 5-axis pentagon for `complete` single-item outfits where Pairing drops) has a `role="img"` + `aria-label` so screen readers can interpret it.
- [ ] All interactive elements have visible focus rings.
- [ ] No animation uses a curve other than `--ease` (`cubic-bezier(.2, .7, .1, 1)`).
- [ ] No duration outside `--dur-1 / --dur-2 / --dur-3` (120 / 240 / 480 ms).

### Journey J — Dark mode parity (new for Phase 14)

Walk every surface in dark mode at 375 mobile and 1280 desktop. Use
both `prefers-color-scheme: dark` at the OS level and the in-product
theme toggle in the profile view.

- [ ] Theme toggle is reachable from the profile view and persists to
      `localStorage.aura_theme`. On first load, the product honours
      `prefers-color-scheme` unless the user has set an explicit choice.
- [ ] Canvas in dark mode is `#0E0B09` (espresso-black), **not** pure
      `#000`. Verify by eye — pure black reads generic.
- [ ] Oxblood lifts to `#B34548` on dark surfaces and passes AA contrast
      on body copy and on primary buttons.
- [ ] Champagne lifts to `#D6B373` and remains restricted to personal
      cues only. Count champagne surfaces on any single viewport — two
      champagne surfaces in the same viewport is a fail.
- [ ] Every modal, popover, drawer, and floating surface still reads as
      floating in dark mode — shadows must be visibly heavier than in
      light mode (see `--shadow-pop` / `--shadow-modal` dark variants).
- [ ] Product and wardrobe imagery remains legible — no decorative
      overlay or tint is applied to photos in dark mode.
- [ ] Chat bubbles: user bubble uses `--surface-sunk` dark equivalent;
      agent messages have no background and sit directly on `--canvas`.
- [ ] No surface in dark mode reveals a leftover light-mode literal
      (e.g. `#FFFAF5`, `#F6F0EA`, `#FFFFFF` as a background fill).

### Journey K — Confident Luxe tonal audit (new for Phase 14)

Walk the product with the brand direction in hand and verify the four
sanctioned tonal moments are rendering correctly. This audit is what
distinguishes Confident Luxe from the legacy warm-craft direction.

- [ ] **Chat empty state** leads with a 72/76 display italic greeting in
      the voice defined in `docs/DESIGN.md` § Voice & Microcopy
      (*"Good evening, {name}. What are we wearing."*). No question
      mark. No "Hi!" or chatbot greeting.
- [ ] **Wardrobe empty-category state** uses 48/52 display italic
      (*"Your outerwear lives here."*) with one ghost CTA below.
- [ ] **Verdict cards** (buy / skip / pairing) render the verdict word
      in 48/52 display italic (`Worth it.` / `Skip.` / `Maybe.` /
      `Not yours.`) over a full-bleed product image, with one body-line
      of reasoning underneath. No badge, no icon, no colour fill.
- [ ] **Style dossier** in the profile view renders the user's style
      code adjectives as oversized display-italic quote blocks, one per
      line, no punctuation.
- [ ] **Runway motion detail** (uppercase labels tracking in from 4–6px
      left) appears *once per view*, not on every element. Zero
      occurrences on a primary view is a fail; two or more is also a
      fail.
- [ ] **Italic display type** appears **only** in the four sanctioned
      tonal moments above. Verify by searching every primary surface
      for italic display — any italic in chrome, nav, buttons, chips,
      body copy, or metadata is a violation.
- [ ] **Source labels** use the refreshed vocabulary: `YOURS`, `SHOP`,
      `HYBRID`, `ON YOU`, `FOR YOU`. Legacy copy like "From Wardrobe"
      or "From your wardrobe" is a fail.
- [ ] **Follow-up buckets** render under uppercase headings (`IMPROVE IT`,
      `SHOW ALTERNATIVES`, `SHOP THE GAP`, `EXPLAIN WHY`, `SAVE FOR
      LATER`) — never as a flat list.
- [ ] **Loading copy** uses the stylist-voice lines (*"Laying pieces on
      the table."*, *"Looking through your closet."*, *"Pairing this
      back for you."*, *"Finding something that fits."*). No spinner
      with generic "Loading…" text.
- [ ] **Exclamation marks**, **emoji in chrome**, and the words "AI",
      "model", "prompt", "LLM", "agent" do not appear in any
      user-facing copy.

---

## Layer 2 — "Confident Luxe vs dashboard" tone audit

Walk the same screens with a fashion designer's eye and check that the
*feel* is right, not just that the boxes work. A "fail" here means the
surface looks like a SaaS dashboard, or leans into either of the two
rejected failure modes (warm-craft boutique, or magazine / publication
aesthetic), instead of reading as a maison client studio.

- [ ] **Typography (target):** Fraunces (variable, SIL OFL from Google
      Fonts) renders for all display headlines — check the italic
      variants on tonal moments to confirm the web font is active and
      not falling back to the Cormorant fallback. Inter renders for
      all body copy and UI chrome. Cormorant Garamond and Avenir Next
      appear **only** as font fallbacks in the stack, never as the
      active family.
- [ ] **Typography (italic discipline):** italic display type appears
      only in the four sanctioned tonal moments (see Journey K). No
      italic body copy anywhere.
- [ ] **Color (dominant):** `--canvas` warm ivory (`#F7F3EC`) is the
      dominant background on every primary surface. `--ink` espresso
      (`#16110E`) is the dominant text colour. `--accent` oxblood
      (`#5C1A1B`) is used sparingly — primary CTAs, brand wordmark,
      active nav underline, 1px rule on personalized advice.
- [ ] **Color (retired tokens):** **zero** occurrences of the legacy
      literals `#f6f0ea`, `#efe6dc`, `#fffaf5`, `#6f2f45`, `#b88b96`,
      `#5f6a52`, `#b08a4e` in the live CSS. Verify with:
      `rg '#f6f0ea|#6f2f45|#b88b96|#efe6dc|#fffaf5|#5f6a52|#b08a4e' modules/**/ui.py`
      — result must be empty.
- [ ] **Color (champagne discipline):** `--signal` (`#C6A15B`) appears
      only on personal cues — season badge, base/accent/avoid
      swatches, personalized advice 1px rule, `FOR YOU` label. No two
      champagne surfaces in the same viewport.
- [ ] **Shape (hairlines, not shadows):** every static card (outfit
      card, closet card, profile card, verdict card, follow-up bucket)
      carries a 1px `--line` border and **zero** box-shadow. Shadows
      are reserved for modals, popovers, drawers, and the composer on
      focus.
- [ ] **Shape (radii):** every surface uses a pinned radius token
      (`--radius-sm` 4px, `--radius-md` 8px, `--radius-lg` 14px). No
      literal `border-radius: 10px / 12px / 18px / 20px` values left
      in the CSS.
- [ ] **Imagery:** every outfit and closet card leads with the image.
      Price and CTA are de-emphasised; image takes ≥ 60% of card
      height. Garment cards have **no** border or background —
      just the photo and metadata below.
- [ ] **Whitespace:** sections breathe. No two CTAs touching. Stylist
      content column caps at 720px on desktop for chat and reasoning
      body.
- [ ] **Copy:** assistant messages read like a stylist ("For dinner
      tonight, your navy blazer and cream trousers from your saved
      wardrobe is the strongest fit because…"), not a database
      ("results: 1"). Source labels in the new uppercase vocabulary
      (`YOURS` / `SHOP` / `HYBRID`).
- [ ] **Hierarchy:** there is exactly **one** dominant action per screen.
      No competing primary buttons.
- [ ] **Source labels:** wardrobe-first / catalog / hybrid is always
      visible via the uppercase label vocabulary — never inferred and
      never encoded only in colour.
- [ ] **Motion discipline:** every transition uses `--ease`; every
      duration is one of `--dur-1 / --dur-2 / --dur-3`. No bounce, no
      spring, no scale-over-1.02 hover.
- [ ] **No dashboard tells:** no "stats panels with sparklines", no
      "total items: 47", no "last updated 5 min ago" timestamps as
      primary content. These can exist in admin views, never in
      user-facing ones.
- [ ] **No legacy warm-craft tells:** no drop shadow on a static card,
      no rose-wine accent, no cream background, no serif-over-serif
      collision. Any of these is a Phase 14 regression.

---

## Layer 3 — Per-screen polish

Quick visual checks. Each row is one screen × one viewport × one
theme. Every primary surface must be validated in **both** light and
dark mode at 375 mobile and 1280 desktop before the Phase 14 gate can
go green.

| Screen                            | 375 Light | 375 Dark | 430 Light | 820 Light | 1280 Light | 1280 Dark |
|-----------------------------------|-----------|----------|-----------|-----------|------------|-----------|
| `/` homepage (chat)               | [ ]       | [ ]      | [ ]       | [ ]       | [ ]        | [ ]       |
| Chat empty state (new thread)     | [ ]       | [ ]      | [ ]       | [ ]       | [ ]        | [ ]       |
| Chat verdict card (buy / skip)    | [ ]       | [ ]      | [ ]       | [ ]       | [ ]        | [ ]       |
| `/?view=wardrobe`                 | [ ]       | [ ]      | [ ]       | [ ]       | [ ]        | [ ]       |
| Wardrobe empty-category state     | [ ]       | [ ]      | [ ]       | [ ]       | [ ]        | [ ]       |
| `/?view=profile` (style code)     | [ ]       | [ ]      | [ ]       | [ ]       | [ ]        | [ ]       |
| Profile style dossier adjectives  | [ ]       | [ ]      | [ ]       | [ ]       | [ ]        | [ ]       |
| `/?view=wishlist`                 | [ ]       | [ ]      | [ ]       | [ ]       | [ ]        | [ ]       |
| `/?view=trialroom`                | [ ]       | [ ]      | [ ]       | [ ]       | [ ]        | [ ]       |
| Looks lookbook full-screen view   | [ ]       | [ ]      | [ ]       | [ ]       | [ ]        | [ ]       |
| Outfit check response             | [ ]       | [ ]      | [ ]       | [ ]       | [ ]        | [ ]       |
| Trip planner response             | [ ]       | [ ]      | [ ]       | [ ]       | [ ]        | [ ]       |
| Wardrobe Add Item drawer          | [ ]       | [ ]      | [ ]       | [ ]       | [ ]        | [ ]       |
| Wardrobe Edit / Delete modal      | [ ]       | [ ]      | [ ]       | [ ]       | [ ]        | [ ]       |
| Chat history drawer (⌘K)          | [ ]       | [ ]      | [ ]       | [ ]       | [ ]        | [ ]       |
| Onboarding (`/onboard`)           | [ ]       | [ ]      | [ ]       | [ ]       | [ ]        | [ ]       |
| Admin catalog (`/admin/catalog`)  | n/a       | n/a      | n/a       | [ ]       | [ ]        | [ ]       |

---

## Sign-off

This checklist must be filled in by an actual designer (not the
engineer who shipped the feature). Two consecutive "fail" items on any
single journey blocks the release.

- [ ] Designer reviewer: ____________
- [ ] Date: ____________
- [ ] Build / commit reviewed: ____________
- [ ] Outstanding issues filed (count): ____
- [ ] Phase 14 Confident Luxe gate (light + dark, all journeys J and K green): ____________

If this checklist is fully green, the two design-system items in
`docs/RELEASE_READINESS.md` Gate 4 can be ticked off, the Phase 14
success criteria in `docs/WORKFLOW_REFERENCE.md` § Phase History
(Phase 14) can be marked complete, and the design gate in
`docs/RELEASE_READINESS.md` Gate 4 can be marked complete.
