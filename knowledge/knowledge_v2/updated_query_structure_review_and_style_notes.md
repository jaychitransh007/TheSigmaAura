# Updated `query_structure.yaml` Review + Stylist Revisions

## High-Level Stylist Review

This file is already structurally strong and culturally grounded. The main improvements required are:

1. Reduce over-rigidity around Indian-vs-Western structures in urban Gen-Z/Millennial contexts.
2. Improve realism for Bengaluru / Mumbai / Delhi startup-professional dressing.
3. Add Indo-Western fusion acceptance where modern Indian users already normalize it.
4. Reduce hard bans where user intent and styling execution matter more than structure.
5. Improve gender neutrality and category flexibility.
6. Better align “complete vs paired vs three_piece” with actual retrieval realities in Indian fashion catalogs.

---

# Cross-Cutting Stylist Decisions

## STYLIST_NOTES.md Additions

### 1. Avoid Over-Banning `complete`

Earlier mappings over-used:

```yaml
avoid:
  StylingCompleteness: [complete]
```

This creates retrieval brittleness and suppresses modern urban dressing patterns.

Modern Indian users frequently wear:
- co-ord sets
- elevated jumpsuits
- shirt dresses
- structured kurta sets
- minimal sarees
- Indo-Western complete silhouettes

…even in environments previously marked as “paired-only”.

Updated principle:

> Prefer structures rather than hard-ban alternatives unless the outfit would be culturally or functionally implausible.

---

### 2. Startup + Urban Casual Is More Fashion-Forward Than Current Mapping

The original file assumes startup culture = extremely basic casualwear.

This underestimates:
- Bengaluru startup fashion
- creator economy aesthetics
- design/tech founder dressing
- elevated minimalism
- smart co-ords
- utility layering
- Indo-Western smart casual

Updated mappings now allow:
- selective complete silhouettes
- relaxed layering
- smart overshirts/jackets
- elevated casual structure

without drifting into formalwear.

---

### 3. Fusion Wear Should Be Explicitly Supported In More Festive Occasions

Urban Indian users increasingly prefer:
- saree + blazer
- corset + saree
- kurta + trousers
- draped skirts
- Indo-Western jackets
- co-ord festive sets

Original mapping sometimes over-indexed on traditional-only complete sets.

Updated principle:

> Traditional remains the default cultural register, but fusion becomes an accepted alternative structure in urban contexts.

---

### 4. Practicality Should Override Tradition In Functional Contexts

Travel, Holi, coffee meetups, startup officewear, beachwear, etc. should prioritize:
- movement
- climate
- comfort
- repeat wear
- maintenance reality

Some original notes were culturally correct but operationally too rigid.

---

### 5. Retrieval System Alignment

Some mappings unintentionally reduced retrieval diversity.

Example:
- banning `complete` entirely blocks jumpsuits, dresses, co-ords
- excessive dependence on `needs_innerwear`
- some wedding/festive structures assumed category purity that catalog taxonomies often lack

Updated mappings increase retrieval flexibility while preserving aesthetic intent.

---

# Updated YAML Sections

## 1. daily_office_startup

### Updated

```yaml
daily_office_startup:
  default_structure: paired
  alternative_structures: [complete]
  flatters:
    StylingCompleteness: [needs_topwear, needs_bottomwear, complete]
  avoid:
    StylingCompleteness: [dual_dependency]
  notes: >
    Startup dressing in urban India is relaxed but increasingly style-
    aware. Tee + jeans, oversized shirt + trouser, kurti + denim,
    elevated co-ord sets, jumpsuits, and minimalist dresses all work.
    Avoid highly formal suiting or ceremonial complete silhouettes.
```

### Stylist rationale

Original file treated startupwear as too basic. Modern Bengaluru startup ecosystems normalize elevated casual complete silhouettes.

---

## 2. coffee_meetup

### Updated

```yaml
coffee_meetup:
  default_structure: paired
  alternative_structures: [complete]
  flatters:
    StylingCompleteness: [needs_topwear, needs_bottomwear, complete]
  avoid:
    StylingCompleteness: [dual_dependency]
  notes: >
    Relaxed urban casual. Denim + shirt, kurti + jeans, casual dress,
    jumpsuit, or soft co-ord sets work. Avoid heavily ceremonial or
    sharply formal layering.
```

### Stylist rationale

Urban café dressing frequently includes dresses, jumpsuits, and relaxed co-ords.

---

## 3. travel_day

### Updated

```yaml
travel_day:
  default_structure: paired
  alternative_structures: [complete]
  flatters:
    StylingCompleteness: [needs_topwear, needs_bottomwear, complete]
  avoid:
    StylingCompleteness: [dual_dependency]
  notes: >
    Comfort-first dressing with movement and climate adaptability.
    Stretch trousers, oversized shirts, knit sets, athleisure co-ords,
    breathable jumpsuits, and wrinkle-resistant layers work best.
    Avoid ceremonial or maintenance-heavy garments.
```

### Stylist rationale

Modern airportwear increasingly includes coordinated complete silhouettes.

---

## 4. rooftop_bar

### Updated

```yaml
rooftop_bar:
  default_structure: paired
  alternative_structures: [complete, three_piece]
  flatters:
    StylingCompleteness: [needs_topwear, needs_bottomwear, complete, needs_innerwear]
  avoid: {}
  notes: >
    Fashion-forward evening dressing. Structured separates, dresses,
    jumpsuits, light layering, statement jackets, and Indo-Western
    silhouettes all work depending on venue energy.
```

### Stylist rationale

Urban rooftop venues frequently involve layering and statement outerwear.

---

## 5. gala_dinner

### Updated

```yaml
gala_dinner:
  default_structure: complete
  alternative_structures: [three_piece, paired]
  flatters:
    StylingCompleteness: [complete, dual_dependency, needs_innerwear, needs_topwear, needs_bottomwear]
  avoid: {}
  notes: >
    High-formality statement dressing. Gowns, embellished sarees,
    couture lehengas, tuxedos, bandhgalas, elevated separates, and
    fashion-forward Indo-Western layering all work when execution feels
    intentional and luxurious.
```

### Stylist rationale

Luxury fashion increasingly includes couture separates rather than only fully complete silhouettes.

---

## 6. navratri

### Updated

```yaml
navratri:
  default_structure: complete
  alternative_structures: [three_piece]
  cultural_variants:
    indian_traditional: complete
    indian_fusion: three_piece
  flatters:
    StylingCompleteness: [complete, dual_dependency, needs_topwear, needs_bottomwear, needs_innerwear]
  avoid: {}
  notes: >
    Traditional mirror-work lehenga sets remain dominant, but urban
    fusion dressing now includes jacket lehengas, crop-top + skirt +
    cape combinations, and Indo-Western layering built for Garba
    movement.
```

### Stylist rationale

Fusion Navratri fashion is now mainstream in metro India.

---

## 7. mehndi

### Updated

```yaml
mehndi:
  default_structure: complete
  alternative_structures: [three_piece]
  flatters:
    StylingCompleteness: [complete, dual_dependency, needs_innerwear]
  avoid: {}
  notes: >
    Mirror-work lehengas, sharara sets, draped skirts, cape sets,
    jacket layering, and playful Indo-Western festive silhouettes work
    well. Movement and visual energy matter more than strict
    traditional purity.
```

### Stylist rationale

Modern Mehndi styling is highly fusion-oriented across urban weddings.

---

## 8. first_date

### Updated

```yaml
first_date:
  default_structure: paired
  alternative_structures: [complete, three_piece]
  flatters:
    StylingCompleteness: [needs_topwear, needs_bottomwear, complete, needs_innerwear]
  avoid:
    StylingCompleteness: [dual_dependency]
  notes: >
    Smart-casual with personality. Structured denim, dresses,
    lightweight layering, relaxed tailoring, and understated Indo-
    Western styling all work. Aim for approachable polish rather than
    over-formality.
```

### Stylist rationale

Layering and light jackets are extremely common in urban dating contexts.

---

## 9. in_laws_first_meeting

### Updated

```yaml
in_laws_first_meeting:
  default_structure: complete
  alternative_structures: [paired, three_piece]
  flatters:
    StylingCompleteness: [complete, needs_topwear, needs_bottomwear, needs_innerwear]
  avoid:
    StylingCompleteness: [dual_dependency]
  notes: >
    Conservative-polished dressing with modest silhouettes. Soft sarees,
    pastel anarkalis, elegant kurta sets, refined Indo-Western layering,
    and subtle embroidery work best.
```

### Stylist rationale

Urban families increasingly accept refined Indo-Western layering if styling remains respectful.

---

## 10. anchor_complete

### Updated

```yaml
anchor_complete:
  default_structure: complete
  alternative_structures: [three_piece]
  fills_slots: [outerwear]
  flatters:
    StylingCompleteness: [complete, needs_innerwear]
  avoid:
    StylingCompleteness: [needs_topwear, needs_bottomwear]
  notes: >
    Complete anchors primarily require styling augmentation rather than
    reconstruction. Optional layering pieces such as jackets, shrugs,
    capes, belts, or bandhgalas may be added when aesthetically
    compatible.
```

### Stylist rationale

Modern styling often layers over sarees, dresses, lehengas, and jumpsuits.

---

# Additional Recommended Global Improvements

## Add Optional Metadata

Recommended future schema additions:

```yaml
style_energy:
  - relaxed
  - elevated
  - statement
  - ceremonial

mobility_requirement:
  - low
  - medium
  - high

climate_sensitivity:
  - breathable
  - layered
  - weather_resistant
```

These would significantly improve Indian climate-aware styling.

---

# Overall Assessment

The original file had:
- strong cultural grounding
- excellent structure taxonomy
- realistic Indian occasion mapping
- strong retrieval semantics

Main weakness:
- excessive rigidity around structure purity
- under-representation of modern Indo-Western urban styling
- too many hard bans

The revised mappings preserve:
- Indian cultural correctness
- retrieval clarity
- occasion hierarchy

while improving:
- realism
- fashion relevance
- catalog flexibility
- Gen-Z/Millennial urban alignment
- fusion styling support
- modern Indian dressing behavior

