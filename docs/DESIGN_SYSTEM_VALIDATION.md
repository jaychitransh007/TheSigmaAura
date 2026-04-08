# Design System Validation Checklist

This is the manual QA checklist a designer (not the implementing engineer)
must complete before the first-50 release. It is the artifact behind the
two open items in `docs/CURRENT_STATE.md` § Design System Validation:

- Validate all primary screens mobile-first, then desktop
- Ensure the entire surface feels editorial, feminine, premium, and
  fashion-native rather than dashboard-like

The checklist is split into three layers: device walkthroughs, the
"editorial vs dashboard" tone audit, and the per-screen polish list.
Each layer must be fully green for the doc item to be marked complete.

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
      welcome screen and outfit cards.
- [ ] Tab order through the homepage hits primary CTA → "More ways to
      style" toggle → secondary cards in order.
- [ ] Outfit card split polar bar chart (Nightingale-style: 8 archetype axes top + 4-7 fit profile axes bottom) has a `role="img"` + `aria-label` so screen readers can interpret it.
- [ ] All interactive elements have visible focus rings.

---

## Layer 2 — "Editorial vs dashboard" tone audit

Walk the same screens with a fashion designer's eye and check that the
*feel* is right, not just that the boxes work. A "fail" here means the
surface looks like a SaaS dashboard, not a stylist's studio.

- [ ] **Typography:** Cormorant Garamond renders for all headlines (not
      Times New Roman fallback). Hairline contrast in body type is
      preserved on mobile.
- [ ] **Color:** the warm/burgundy palette is dominant. No leftover
      Bootstrap blue, no leftover greys from earlier prototypes.
- [ ] **Imagery:** every outfit card leads with the image. Price and CTA
      are de-emphasised; image takes ≥ 60% of card height.
- [ ] **Whitespace:** sections breathe. No two CTAs touching.
- [ ] **Copy:** assistant messages read like a stylist ("For dinner
      tonight, your navy blazer + cream trousers from your saved wardrobe
      is the strongest fit because…"), not a database ("results: 1").
- [ ] **Hierarchy:** there is exactly **one** dominant action per screen.
      No competing primary buttons.
- [ ] **Source labels:** wardrobe-first / catalog / hybrid is always
      visible — never inferred.
- [ ] **No dashboard tells:** no "stats panels with sparklines", no "total
      items: 47", no "last updated 5 min ago" timestamps as primary
      content. These can exist in admin views, never in user-facing ones.

---

## Layer 3 — Per-screen polish

Quick visual checks. Each row is one screen × one viewport.

| Screen                            | Mobile 375 | Mobile 430 | Tablet 820 | Desktop 1280 |
|-----------------------------------|------------|------------|------------|--------------|
| `/` homepage (chat)               | [ ]        | [ ]        | [ ]        | [ ]          |
| `/?view=wardrobe`                 | [ ]        | [ ]        | [ ]        | [ ]          |
| `/?view=profile` (style code)     | [ ]        | [ ]        | [ ]        | [ ]          |
| `/?view=results`                  | [ ]        | [ ]        | [ ]        | [ ]          |
| Outfit check response             | [ ]        | [ ]        | [ ]        | [ ]          |
| Trip planner response             | [ ]        | [ ]        | [ ]        | [ ]          |
| Wardrobe Add Item modal           | [ ]        | [ ]        | [ ]        | [ ]          |
| Onboarding (`/onboard`)           | [ ]        | [ ]        | [ ]        | [ ]          |
| Admin catalog (`/admin/catalog`)  | n/a        | n/a        | [ ]        | [ ]          |

---

## Sign-off

This checklist must be filled in by an actual designer (not the
engineer who shipped the feature). Two consecutive "fail" items on any
single journey blocks the release.

- [ ] Designer reviewer: ____________
- [ ] Date: ____________
- [ ] Build / commit reviewed: ____________
- [ ] Outstanding issues filed (count): ____

If this checklist is fully green, the two design-system items in
`docs/CURRENT_STATE.md` can be ticked off and the design gate in
`docs/RELEASE_READINESS.md` Gate 4 can be marked complete.
