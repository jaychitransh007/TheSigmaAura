# Updated occasion.yaml — stylist review pass

## Key in-place schema upgrades applied

### 1. Added hard / soft weighting convention
All critical occasion guidance now distinguishes:
- hard_flatters / hard_avoid → non-negotiable recommendation constraints
- soft_flatters / soft_avoid → stylistic lean, override allowed

This is essential for:
- bridal vs guest separation
- conservative cultural occasions
- stain-risk events (haldi / holi)
- workplace appropriateness
- regional authenticity

---

# PATCHES TO APPLY IN occasion.yaml

## GLOBAL COMMENT TO INSERT NEAR TOP OF FILE

```yaml
# Weighting convention:
#   hard_flatters / hard_avoid = strong constraints
#   soft_flatters / soft_avoid = stylistic preference
# Engine should prioritize hard constraints before archetype blending.
# Especially important for workplace modesty, bridal hierarchy,
# ritual clothing logic, stain-risk events, and conservative family contexts.
```

---

# 1. WORKPLACE REFINEMENTS

## daily_office_mnc

### Replace:

```yaml
flatters:
```

### With:

```yaml
hard_flatters:
  FormalityLevel:        [smart_casual, formal]
  OccasionFit:           [smart_casual, workwear, formal]
  EmbellishmentLevel:    [none, minimal]
  EmbellishmentType:     [none]

soft_flatters:
```

### Replace avoid block with:

```yaml
hard_avoid:
  OccasionFit:           [festive, traditional, party, active]
  EmbellishmentLevel:    [moderate, heavy, statement]
  EmbellishmentType:     [sequins, mirror_work, distressing, studs]

soft_avoid:
  FabricTexture:         [metallic, embroidered]
```

### Add YAML comment above notes:

```yaml
# Indian MNCs increasingly allow clean Indo-Western fusion,
# but visible festive embellishment still breaks office register.
```

---

## daily_office_startup

### Add under soft_flatters:

```yaml
      LayeringComplexity:    [simple, moderate]
      FitType:               [regular, relaxed, slim]
```

### Add under hard_avoid:

```yaml
      OccasionFit:           [bridal, ceremonial]
```

### Add note sentence:

```yaml
      Clean oversized silhouettes acceptable in Bengaluru/Mumbai startup culture if styling remains intentional.
```

---

# 2. MAJOR FESTIVAL EXPANSION

# Missing regional festival vocabulary was a major gap.
# Add the following occasions.

---

## ADD: onam

```yaml
  onam:
    archetype: festive
    formality: semi_formal
    time: daytime
    seasons: [monsoon]
    hard_flatters:
      OccasionFit:           [traditional, festive]
      PrimaryColor:          [white, off-white, cream, gold]
      FabricTexture:         [smooth, textured]
      EmbellishmentLevel:    [minimal, subtle]

    soft_flatters:
      BorderContrast:        [medium, high]
      FabricWeight:          [light, medium]
      EmbellishmentType:     [kasavu_border, embroidery]

    hard_avoid:
      ColorSaturation:       [very_high]
      EmbellishmentLevel:    [heavy, statement]
      EmbellishmentType:     [sequins, mirror_work]

    notes: >
      Kerala Onam visual language is restraint, ivory-gold balance,
      kasavu borders, jasmine flowers, temple jewellery, mundum-neriyathum,
      kasavu saree, ivory kurta with gold border mundu. Loud North-Indian
      wedding styling feels culturally incorrect here.
```

---

## ADD: pongal

```yaml
  pongal:
    archetype: festive
    formality: smart_casual
    time: daytime
    seasons: [winter]
    hard_flatters:
      OccasionFit:           [traditional, festive]
      FabricTexture:         [smooth, textured]
      FabricWeight:          [light, medium]

    soft_flatters:
      PrimaryColor:          [mustard, rust, green, cream, maroon]
      EmbellishmentLevel:    [subtle, moderate]
      EmbellishmentType:     [temple_border, embroidery]

    hard_avoid:
      EmbellishmentLevel:    [heavy, statement]
      EmbellishmentType:     [sequins, metallic]

    notes: >
      Tamil harvest festival. Kanjeevaram cotton-silk, checked sarees,
      temple-border veshti, jasmine flowers, earthy harvest palette.
      Styling should feel rooted and daytime-functional.
```

---

## ADD: bihu

```yaml
  bihu:
    archetype: festive
    formality: smart_casual
    time: daytime
    seasons: [spring]
    hard_flatters:
      OccasionFit:           [traditional, festive]
      ColorTemperature:      [warm]

    soft_flatters:
      PrimaryColor:          [red, cream, off-white]
      FabricTexture:         [textured, woven]
      EmbellishmentLevel:    [subtle, moderate]

    hard_avoid:
      EmbellishmentLevel:    [heavy, statement]
      FabricTexture:         [metallic]

    notes: >
      Assamese Bihu visual language centers woven mekhela chador,
      red-white combinations, folk textures, handcrafted weave identity.
      Heavy sequinned styling breaks authenticity.
```

---

# 3. NAVRATRI FIXES

## navratri

### Replace note block with:

```yaml
    notes: >
      9 nights × designated daily color sequence (changes yearly;
      engine should support external yearly mapping instead of hardcoding).
      Gujarati mirror-work, Kutch embroidery, chaniya choli, kediyu,
      oxidised jewellery, stacked bangles, tassels, movement-heavy
      silhouettes for Garba/Dandiya rotation. Outfit must optimize for
      dance mobility as much as ornamentation.
```

### Add:

```yaml
    soft_flatters:
      MovementEase:          [moderate, high]
```

### Add engineering flag comment:

```yaml
# Requires external yearly color-sequence config.
```

---

# 4. WEDDING HIERARCHY FIXES

# Current schema incorrectly treats guests and bride/groom too similarly.
# Need ceremonial hierarchy.

## wedding_ceremony

### Add:

```yaml
    bridal_priority:
      bride:
        hard_flatters:
          EmbellishmentLevel: [heavy, statement]
          OccasionFit:        [bridal, traditional]

      groom:
        hard_flatters:
          OccasionFit:        [bridal, ceremonial]

      guest:
        hard_avoid:
          OccasionFit:        [bridal]
          EmbellishmentLevel: [statement]
```

### Add YAML comment:

```yaml
# Guests should never visually compete with bride/groom.
```

---

## sangeet

### Add under soft_flatters:

```yaml
      MovementEase:          [moderate, high]
```

### Add under hard_avoid:

```yaml
      FitType:               [restrictive]
```

### Add note sentence:

```yaml
      Dance-heavy functionality matters as much as visual drama.
```

---

## haldi

### Replace:

```yaml
EmbellishmentLevel:    [statement]
```

### With:

```yaml
EmbellishmentLevel:    [heavy, statement]
```

### Add:

```yaml
      FabricTexture:         [metallic]
```

### Add note sentence:

```yaml
      Fresh florals and lightweight gota are preferred over expensive surface work.
```

---

# 5. HOLI FIXES

## holi

### Add under hard_avoid:

```yaml
      FabricWeight:          [heavy]
      FabricTransparency:    [high]
```

### Add note sentence:

```yaml
      Wet-color environments require opacity-aware fabrics despite white palette traditions.
```

---

# 6. IN-LAWS MEETING REFINEMENT

## in_laws_first_meeting

### Add under hard_avoid:

```yaml
      NecklineDepth:         [deep]
      HemLength:             [micro_mini]
```

### Add under soft_flatters:

```yaml
      FabricTexture:         [smooth, embroidered, matte]
```

### Replace note ending:

```yaml
      Avoid overtly bodycon or nightlife-coded styling.
```

---

# 7. MISSING INDIAN URBAN OCCASIONS

## ADD: housewarming

```yaml
  housewarming:
    archetype: festive
    formality: smart_casual
    time: daytime
    seasons: [spring, summer, autumn, winter]
    hard_flatters:
      OccasionFit:           [traditional, smart_casual, festive]
      EmbellishmentLevel:    [subtle, moderate]

    soft_flatters:
      FabricTexture:         [smooth, embroidered]
      PrimaryColor:          [cream, yellow, green, rust]

    hard_avoid:
      EmbellishmentLevel:    [heavy, statement]

    notes: >
      Griha-pravesh / housewarming sits between family pooja and festival lunch.
      Traditional but daytime-practical.
```

---

## ADD: college_farewell

```yaml
  college_farewell:
    archetype: night_out
    formality: semi_formal
    time: evening
    seasons: [spring, summer]
    hard_flatters:
      OccasionFit:           [semi_formal, party]
      EmbellishmentLevel:    [subtle, moderate]

    soft_flatters:
      FabricTexture:         [sheen, smooth, embroidered]
      ColorSaturation:       [medium, high]

    hard_avoid:
      EmbellishmentLevel:    [statement]
      OccasionFit:           [bridal, ceremonial]

    notes: >
      Common Indian GenZ styling milestone. Sarees dominate for women;
      blazers, bandhgalas, shirts with tailored trousers for men.
      Aspirational glamour without bridal heaviness.
```

---

# 8. VOCABULARY / TAXONOMY ISSUES FLAGGED

## Potential schema mismatches

### Existing values used inconsistently across files:

```yaml
formal vs semi_formal vs smart_casual
traditional vs festive
party vs night_out
workwear vs office
```

### Strong recommendation

Create canonical enums for:
- OccasionFit
- OccasionSignal
- EmbellishmentType
- FabricTexture
- PrimaryColor

Current schema risks silent rule misses.

---

# 9. OFF-SHOULDER GAP

# Occasion file currently has no mechanism for exposure appropriateness.
# This affects:
# - office
# - family pooja
# - in-laws meeting
# - wedding guest modesty

## Recommended new attribute family

```yaml
SkinExposureLevel:
  [modest, balanced, elevated]

ShoulderExposure:
  [covered, partial, off_shoulder]
```

Needed because:
- off-shoulder is acceptable at cocktail/sangeet/date-night
- often inappropriate for pooja/work/interview/in-laws contexts
- currently impossible to encode deterministically

---

# STYLIST_NOTES.md ADDITIONS

## Occasion-system rationale additions

### Ceremonial hierarchy
Indian wedding systems require role-aware dressing hierarchy. Bride/groom visual dominance is culturally important across most communities. Guests should never receive equivalent embellishment recommendations as bridal participants even if attending the same occasion.

### Regional authenticity
Indian festivals are not interchangeable. Onam minimal ivory-gold styling and Navratri mirror-work maximalism sit at opposite ends of the festive spectrum. Regional authenticity should override generic “Indian festive” styling.

### Dance-aware occasion logic
Sangeet and Navratri are movement-centric occasions. Outfit recommendations must optimize for rotational movement, heat tolerance, and comfort — not just visual glamour.

### Ritual stain-risk events
Haldi and Holi require material survivability logic. Heavy embroidery, expensive metallic work, and delicate fabrics conflict with real user behavior.

### Exposure appropriateness
Indian urban users strongly modulate neckline depth, shoulder exposure, transparency, and bodycon fit based on social context. Current schema lacks exposure controls and will produce culturally tone-deaf recommendations unless added.

---

# ENGINEERING FLAGS

1. Need yearly external Navratri color mapping source.
2. Need explicit bridal-role support in recommendation engine.
3. Need exposure/modesty attribute family.
4. Need canonical enum registry across all YAML files.
5. Need fabric-pairing compatibility layer for silk/cotton/brocade/handloom mixing.

