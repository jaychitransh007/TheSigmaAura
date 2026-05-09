# pairing_rules.yaml — STYLIST REVISION PATCHSET (IN-PLACE UPDATES)

pairing_rules:

# ─────────────────────────────────────────────────────────────────────

# 1. FORMALITY ALIGNMENT

# ─────────────────────────────────────────────────────────────────────

formality_alignment:
rule_type: hard_constraint

```
rules:
  formality_within_one_step:
    description: |
      Slots in an outfit must share or be within ±1 step of each
      other on the canonical FormalityLevel scale. Mismatch by 2+
      steps reads as incoherent (formal blazer over t-shirt +
      jeans, ceremonial saree blouse with casual shorts).
    formality_scale: [casual, smart_casual, semi_formal, formal, ceremonial]
    compatibility_matrix:
      casual:        [casual, smart_casual]
      smart_casual:  [casual, smart_casual, semi_formal]
      semi_formal:   [smart_casual, semi_formal, formal]
      formal:        [semi_formal, formal, ceremonial]
      ceremonial:    [formal, ceremonial]
    examples_valid:
      - "casual tee + casual jeans (same level)"
      - "smart_casual kurti + smart_casual palazzo"
      - "smart_casual blouse + semi_formal trouser (one step)"
      - "formal silk saree + ceremonial embroidered blouse"
    examples_invalid:
      - "ceremonial bridal lehenga + casual cotton choli (3-step gap)"
      - "casual tee + formal trouser"
      - "ceremonial sherwani + casual jeans"
    notes: |
      Bridal lehenga rents the FormalityLevel of every accompanying
      slot to ceremonial. Bandhgala formality leads the outfit.

  # Indian urban users frequently intentionally soften one ceremonial slot.
  ceremonial_softening_exception:
    description: |
      One ceremonial anchor may pair with formal accompaniment
      when the styling intent is restrained luxury rather than
      full bridal intensity.
    allowed_pairs:
      - "ceremonial saree + formal blouse"
      - "formal silk kurta + ceremonial dupatta"
      - "ceremonial lehenga skirt + formal minimal blouse"
    notes: |
      Extremely important for modern urban styling in Bengaluru,
      Mumbai, Hyderabad, and intimate wedding contexts.
```

# ─────────────────────────────────────────────────────────────────────

# 2. COLOR STORY

# ─────────────────────────────────────────────────────────────────────

color_story:
rule_type: hard_constraint

```
rules:
  max_dominant_colors:
    value: 3
    description: |
      No more than 3 distinct dominant hues across the outfit.

  palette_anchor_required:
    description: |
      At least one slot must use a color from the user's SubSeason
      palette anchors.

  contrast_alignment:
    description: |
      High-contrast outfits and low-contrast tonal outfits work.
      Avoid mixing very_high contrast with low contrast.
    compatibility_matrix:
      low:        [low, medium]
      medium:     [low, medium, high]
      high:       [medium, high, very_high]
      very_high:  [high, very_high]

  # Indian festivewear often uses metallic as a pseudo-neutral.
  metallic_neutral_exception:
    description: |
      Gold, champagne, antique gold, oxidized silver, bronze,
      and muted metallic embroidery may function as neutral
      support colors rather than dominant hues.
    notes: |
      Prevents unnecessary rejection of Indian festive and
      bridal outfits where zari/metallic thread is pervasive.

  # Bridal and festive Indianwear often intentionally clusters analogous warm tones.
  festive_warm_cluster:
    description: |
      Warm festive combinations (marigold, rust, sindoor red,
      haldi yellow, mehendi green, antique gold) are considered
      culturally coherent even when technically exceeding classic
      Western color-harmony tension limits.
    notes: |
      Indian festive color logic is more culturally associative
      than purely color-wheel based.

color_harmony_types:

  monochromatic:
    description: All slots same hue, varying ColorValue

  analogous:
    description: Adjacent hues on the color wheel.

  complementary:
    description: Opposite hues — pulls visual tension.
    notes: |
      In Indian styling, complementary contrast works best when
      one side is softened via texture, matte finish, or lower saturation.

  tonal:
    description: Same hue, varying ColorValue and ColorSaturation.

  neutral_plus_anchor:
    description: Most slots neutral, one palette anchor slot.

  # Added because Indian festivewear frequently relies on warm metallic anchoring.
  jewel_plus_metallic:
    description: |
      Jewel-tone anchor with restrained metallic accompaniment.
    flatters:
      ColorCount: [two_color, tonal]
    notes: |
      Emerald + antique gold, navy + dull gold, wine + bronze,
      ivory + champagne gold. Extremely common in Indian festivewear.
```

# ─────────────────────────────────────────────────────────────────────

# 3. PATTERN MIXING

# ─────────────────────────────────────────────────────────────────────

pattern_mixing:
rule_type: hard_constraint

```
rules:

  solid_plus_pattern:
    description: Solid + 1 patterned slot. Always OK.

  two_patterns:
    description: |
      2 patterned slots are acceptable only when:
      - scale contrast exists
      - color family aligns
      - one pattern visually dominates

  # Indian ethnicwear often uses woven motifs that should not count
  # as full competing patterns.
  woven_motif_exception:
    description: |
      Traditional woven motifs (Banarasi buti, Kanjeevaram zari border,
      chikankari shadow motifs, ikat texture variation) may coexist
      with one additional patterned slot.
    notes: |
      These read as texture heritage rather than loud pattern collision.

  # Large ethnic prints require silhouette restraint.
  oversized_ethnic_control:
    description: |
      Oversized ethnic motifs require clean silhouette balancing
      and low embellishment elsewhere.
    notes: |
      Important for contemporary resort ethnicwear and coord sets.

  three_patterns:
    description: Avoid except editorial / runway styling.
    notes: |
      Urban Indian consumers rarely execute three-pattern mixing successfully.

  pattern_scale_with_body_frame:
    description: |
      PatternScale on top vs bottom relates to body frame.
```

# ─────────────────────────────────────────────────────────────────────

# 4. SILHOUETTE BALANCE

# ─────────────────────────────────────────────────────────────────────

silhouette_balance:
rule_type: soft_constraint

```
rules:

  no_all_fitted:
    description: Avoid fitted top + fitted bottom + fitted outerwear.
    notes: |
      Exception:
      - Hourglass
      - fashion-forward nightlife styling
      - structured monochrome eveningwear

  no_all_relaxed:
    description: Avoid relaxed top + relaxed bottom + relaxed outerwear.
    notes: |
      Exception:
      - luxury resortwear
      - coordinated oversized streetwear
      - intentional draped ethnic silhouettes

  fitted_relaxed_pair:
    description: Default winning combination.

  structured_outerwear_anchor:
    description: Outerwear should usually be the most structured slot.

  # Layering is one of the strongest balancing tools in Indian urban styling.
  vertical_layering_rule:
    description: |
      Open-front layers, longline jackets, shrugs, bandhgalas,
      and cape overlays should create vertical continuity rather
      than width expansion.
    notes: |
      Especially important for Apple, Diamond, Petite,
      and midsection-conscious users.

  # Modern Indian coord sets require dedicated balancing logic.
  co_ord_balance:
    description: |
      Co-ord sets require at least one balancing element:
      - texture variation
      - layering
      - footwear contrast
      - jewellery interruption
      - silhouette contrast
    notes: |
      Prevents coord sets from reading flat or pajama-like.
```

# ─────────────────────────────────────────────────────────────────────

# 5. SCALE BALANCE

# ─────────────────────────────────────────────────────────────────────

scale_balance:
rule_type: hard_constraint

```
statement_definition: |
  A slot is "statement" if ANY of the following:
  - EmbellishmentLevel >= moderate
  - PatternScale >= large
  - ColorSaturation == very_high
  - PatternType in [animal, ethnic, abstract] AND PatternScale >= medium

rules:

  one_statement_per_outfit:
    description: Maximum one dominant statement zone per outfit.

  bridal_exception:
    description: Wedding ceremony styling suspends statement cap.

  jewellery_doesnt_count:
    description: Jewellery is separate visual layer.

  # Indian styling often distributes visual intensity intentionally.
  distributed_statement_exception:
    description: |
      Multiple moderate-intensity zones are acceptable when:
      - all belong to same color family
      - embellishment density is controlled
      - silhouette remains clean
    notes: |
      Important for contemporary Indian weddingwear where blouse,
      dupatta border, and jewellery often all carry coordinated emphasis.
```

# ─────────────────────────────────────────────────────────────────────

# 6. FABRIC COMPATIBILITY

# ─────────────────────────────────────────────────────────────────────

fabric_compatibility:
rule_type: soft_constraint

```
rules:

  texture_mixing:
    description: |
      Texture pairing must maintain a coherent visual register.

  weight_pairing:
    description: |
      FabricWeight should generally match within ±1 level.

  drape_compatibility:
    description: |
      Fluid + rigid works only when hierarchy is intentional.

  # Major missing area in original file.
  indian_weave_compatibility:
    description: |
      Traditional Indian weaves and fabric families carry
      cultural weight and should pair thoughtfully.
    compatibility_guidelines:
      compatible:
        - "Banarasi silk + raw silk blouse"
        - "Chanderi + tissue silk"
        - "cotton handloom + matte silver jewellery"
        - "linen kurta + soft Nehru jacket"
        - "organza dupatta + structured silk lehenga"
        - "Ajrakh + solid handloom cotton"
        - "chikankari + tonal fluid fabrics"
      avoid:
        - "heavy brocade + distressed denim"
        - "raw silk + athletic jersey"
        - "Banarasi + neon athleisure"
        - "heavy Kanjeevaram + casual flip-flops"
        - "multiple competing heritage weaves"
    notes: |
      Indian users strongly perceive weave coherence even when
      they cannot verbally articulate it.

  # Sheen layering needs more nuance.
  sheen_hierarchy:
    description: |
      Multiple sheen surfaces require hierarchy:
      - one dominant sheen
      - one supporting matte/soft texture
    notes: |
      Satin + sequins + metallic embroidery + glossy heels
      quickly becomes visually noisy outside bridalwear.
```

# ─────────────────────────────────────────────────────────────────────

# 7. CULTURAL COHERENCE

# ─────────────────────────────────────────────────────────────────────

cultural_coherence:
rule_type: soft_constraint

```
fusion_rules:

  indian_traditional_only:
    description: Pure traditional outfit.

  indo_western_fusion:
    description: |
      Fusion combinations require intentional hierarchy:
      one side Indian, one side neutral-modern.
    notes: |
      Fusion fails when BOTH sides compete for cultural dominance.

  western_only:
    description: All slots Western.

  heavy_traditional_no_western_fusion:
    description: |
      Heavy ceremonial Indianwear MUST NOT pair with casual Westernwear.

  # Urban India increasingly accepts softened fusion ceremonialwear.
  elevated_fusion_exception:
    description: |
      Elevated fusion is acceptable when Western elements are:
      - tailored
      - monochrome
      - minimal
      - occasion-aligned
    examples_valid:
      - "ivory lehenga skirt + structured ivory shirt"
      - "bandhgala + tailored trouser"
      - "saree + clean full-sleeve bodysuit blouse"
      - "kurta + wide-leg tailored trouser"
    examples_invalid:
      - "bridal lehenga + distressed jeans"
      - "Kanjeevaram saree + graphic hoodie"
```

# ─────────────────────────────────────────────────────────────────────

# 8. BRIDAL / HEAVY-TRADITIONAL SPECIFIC RULES

# ─────────────────────────────────────────────────────────────────────

bridal_specific:
rule_type: hard_constraint

```
triggers_on:
  - wedding_ceremony
  - sangeet
  - mehendi
  - haldi
  - reception
  - engagement

rules:

  bridal_lehenga_pairing:
    description: |
      Bridal lehenga pairs with bridal-weight accompaniments.

  heavy_banarasi_pairing:
    description: |
      Heavy Banarasi / Kanjeevaram pairings require structured traditional support.

  sherwani_pairing:
    description: |
      Sherwani requires coherent ceremonial accompaniment.

  bandhgala_versatility:
    description: |
      Bandhgala remains the most versatile Indian formal layer.

  # Added because modern bridalwear increasingly uses restrained styling.
  modern_bridal_restraint:
    description: |
      Contemporary luxury bridal styling may intentionally reduce:
      - dupatta weight
      - jewellery density
      - blouse embellishment
      while maintaining ceremonial coherence.
    notes: |
      Particularly relevant for Bengaluru minimal luxury weddings,
      destination weddings, and daytime ceremonies.

  # Important for guests vs bride distinction.
  guest_vs_bridal_separation:
    description: |
      Non-bridal guests should not visually compete with bridal focal intensity.
    notes: |
      Applies through:
      - lower embellishment density
      - reduced veil/dramatic dupatta usage
      - lower jewellery hierarchy
      - simpler silhouette engineering
```

# ─────────────────────────────────────────────────────────────────────

# 9. ANCHOR CONSTRAINTS

# ─────────────────────────────────────────────────────────────────────

anchor_constraints:
rule_type: hard_constraint

```
description: |
  Anchor item drives formality, palette, embellishment,
  and cultural register.

rules:

  anchor_heavy_filler_simple:
    description: Heavy anchor requires restrained fillers.

  anchor_simple_filler_can_carry:
    description: Simple anchor allows filler emphasis.

  anchor_color_pivot:
    description: Fillers must harmonize with anchor color story.

  anchor_cultural_register:
    description: Anchor cultural register drives outfit direction.

  # Anchor layering logic is crucial in Indian styling systems.
  anchor_visual_hierarchy:
    description: |
      The anchor item must remain the visual focal point.
      Supporting slots should reinforce rather than compete.
    notes: |
      Extremely important for:
      - saree-first styling
      - statement jacket styling
      - bridal dupatta anchoring
      - luxury handbag anchors
      - sneaker-led streetwear outfits

  # Prevents overmatching.
  anchor_exact_match_avoidance:
    description: |
      Supporting slots should coordinate with anchor rather than
      identically replicate every attribute.
    notes: |
      Slight variation in texture, value, saturation, or finish
      creates depth and prevents catalog-mannequin styling.
```


# STYLIST_NOTES.md — Pairing Rules Additions

## Pairing-rules philosophy shift

The original pairing system was structurally strong but overly optimized around “avoid incoherence.” Real Indian urban styling also relies on controlled tension:

* ceremonial softened with restraint
* fusion balanced through hierarchy
* metallics behaving as neutrals
* coordinated multi-zone embellishment
* intentional texture contrast

The revised pairing rules preserve coherence while allowing modern luxury styling behavior.

## Indian weave coherence

Indian users perceive weave and textile-family harmony instinctively. Banarasi, Chanderi, Kanjeevaram, Ajrakh, chikankari, organza, linen, and handloom cotton each carry:

* cultural weight
* regional identity
* perceived formality
* texture expectations

Outfit engines must validate weave compatibility, not only color and silhouette.

## Metallics are not standard accent colors in Indianwear

Gold zari, antique gold embroidery, champagne metallics, oxidized silver, and bronze often function as pseudo-neutrals in Indian festivewear. Treating them as dominant competing colors causes false-negative outfit rejection.

## Fusion styling requires hierarchy

Indo-Western styling succeeds only when:

* one side acts as anchor,
* the other acts as restraint.

The most common failure mode in AI styling systems is “double-dominant fusion,” where both Indian and Western elements aggressively compete.

## Coord-set balancing

Indian urban consumers increasingly wear monochrome or matching coord sets, but successful execution requires interruption:

* texture variation
* layering
* contrasting footwear
* jewellery hierarchy
* makeup/hair contrast
* structured bag/shoe anchor

Otherwise coord outfits read sleepwear-like.

## Bridal intensity calibration

Modern Indian bridalwear is no longer universally maximalist. Bengaluru, destination, luxury-minimal, and daytime weddings increasingly use:

* lighter dupattas
* restrained jewellery
* monochrome ivory palettes
* matte embroidery
* cleaner silhouettes

The system must support both:

* maximal ceremonial styling
* restrained luxury bridal styling

without forcing either aesthetic universally.

## Statement distribution logic

The previous “one statement item only” logic was too rigid for Indian occasionwear. In practice, coordinated medium-intensity embellishment across:

* blouse
* border
* dupatta
* jewellery

can work beautifully if:

* color family is unified
* silhouette remains controlled
* embellishment density is balanced.

The actual issue is uncontrolled competing focal points, not multiple decorative zones themselves.
