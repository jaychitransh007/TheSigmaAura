# BODYFRAME.YAML — STYLIST REVISION PATCHSET (V1)

## FILE: female.yaml

# Cross-cutting schema additions required for body balancing in Indian occasionwear.
ShoulderExposure:
  Closed:
    flatters: {}
    avoid: {}
    notes: Standard shoulder coverage.

  CapExposed:
    flatters:
      ShoulderStructure: [natural, sculpted]
    avoid: {}
    notes: Slight shoulder exposure; safer than full off-shoulder for family/social events.

  OffShoulder:
    flatters:
      NecklineType: [sweetheart, asymmetric]
      ShoulderStructure: [natural, sculpted]
      StructuralFocus: [shoulder, collarbone]
    avoid:
      ShoulderStructure: [dropped]
    notes: >
      Off-shoulder works best when collarbone and shoulder line are visible
      and stable. Particularly flattering for Pear and Diamond body types.
      Requires movement-safe support for sangeet/reception use.

  OneShoulder:
    flatters:
      NecklineType: [asymmetric]
      StructuralFocus: [shoulder]
      LineDirection: [diagonal]
    avoid: {}
    notes: >
      Strong balancing tool for Rectangle and Diamond frames; diagonal line
      visually slims and elongates.

  Strapless:
    flatters:
      ShoulderStructure: [sculpted]
      StructuralFocus: [neckline, shoulder]
    avoid:
      SupportRequirement: [low]
    notes: >
      Strapless requires structured support and is best reserved for cocktail,
      reception, or editorial styling.

  ColdShoulder:
    flatters:
      ShoulderStructure: [natural]
    avoid: {}
    notes: >
      Transitional exposure category for users uncomfortable with full
      off-shoulder styling.

# Dupatta drape materially changes silhouette balancing in Indian styling.
DupattaDrape:
  VerticalFall:
    flatters:
      LineDirection: [vertical]
    avoid: {}
    notes: Lengthens frame and skims midsection.

  SingleShoulder:
    flatters:
      StructuralFocus: [shoulder]
    avoid: {}
    notes: Draws attention upward; excellent for Pear and Triangle.

  OpenUDrape:
    flatters:
      VolumeProfile: [moderate]
    avoid: {}
    notes: Softer and more romantic silhouette.

  SideFall:
    flatters:
      LineDirection: [vertical]
      StructuralFocus: [side_body]
    avoid: {}
    notes: Excellent for Diamond and Apple silhouettes.

# Layering is central to Indian urban balancing and modesty adaptation.
LayeringStructure:
  OpenFront:
    flatters:
      LineDirection: [vertical]
    avoid: {}
    notes: Creates vertical break and elongation.

  CapeOverlay:
    flatters:
      VolumeProfile: [moderate]
    avoid:
      VolumeProfile: [exaggerated]
    notes: Softens upper body and adds occasion drama.

  LonglineJacket:
    flatters:
      LineDirection: [vertical]
      StructuralFocus: [center_front]
    avoid: {}
    notes: Excellent for Diamond, Apple, and Rectangle balancing.

# Replace over-rigid avoid language with hard/soft distinction.
# Wrap silhouettes are often flattering for moderate Apple frames when soft and fluid.
BodyShape:
  Apple:
    soft_avoid:
      SilhouetteContour: [wrap_with_hard_cinching]

# Mermaid is risky for Pear but not universally wrong in bridal couture.
  Pear:
    soft_avoid:
      SilhouetteContour: [mermaid]

# Diamond body needs stronger vertical engineering and layering support.
  Diamond:
    flatters:
      LayeringStructure: [open_front, longline_jacket]
      DupattaDrape: [side_fall, vertical_fall]
      ConstructionDetail: [angled_seam, vertical_panel]
      LineDirection: [vertical]
      StructuralFocus: [shoulder, neckline]
    avoid:
      ConstructionDetail: [center_gathering]
      WaistDefinition: [hard_cinched]
    notes: >
      Diamond frames require vertical continuity and shoulder architecture.
      Front-open jackets, diagonal drapes, cape overlays, and structured
      shoulder lines work better than aggressive waist emphasis.

# Petite users can still wear statement styling if scale discipline exists.
VerticalProportion:
  Compact:
    soft_avoid:
      EmbellishmentLevel: [distributed_heavy]
    notes: >
      Petite users can successfully wear statement elements when visual
      weight is concentrated rather than spread across the entire look.

# Sweetheart necklines often flatter softer jawlines.
JawlineDefinition:
  Soft:
    flatters:
      NecklineType: [sweetheart]

# Strategic waist definition can slim without aggressive cinching.
WaistDefinition:
  soft_defined:
    notes: Gentle shaping through drape, paneling, or seam placement.

  strategic_defined:
    notes: Waist shaping used to elongate or streamline without compression.

  hard_cinched:
    notes: Strong waist emphasis through belts/corsetry/tight tailoring.

# Support logic required for realistic Indian eventwear recommendations.
SupportRequirement:
  Low:
    notes: Minimal internal support needed.

  Medium:
    notes: Requires stable tailoring or blouse engineering.

  High:
    notes: Requires corsetry, boning, secure blouse structure, or heavy support.

MovementSecurity:
  Secure:
    notes: Suitable for dancing and long-duration events.

  Moderate:
    notes: Some adjustment may be needed during movement.

  Delicate:
    notes: Editorial or low-movement styling only.

# Sleeve volume materially affects body balancing.
SleeveVolume:
  Slim:
    notes: Minimal added volume.

  Moderate:
    notes: Controlled shaping suitable for most frames.

  Puff:
    notes: Adds shoulder and upper-body emphasis.

  Bishop:
    notes: Soft romantic volume with vertical drape.

  Dramatic:
    notes: Editorial/high-fashion sleeve treatment.

# Blouse length affects torso proportion and modesty calibration.
BlouseLength:
  Cropped:
    notes: Modern lehenga and saree styling.

  Standard:
    notes: Most versatile proportion.

  Longline:
    notes: Elongates torso and adds modesty.

---

## FILE: male.yaml

# Avoid over-structuring younger urban users; softer tailoring is now mainstream.
BodyShape:
  Rectangle:
    soft_flatters:
      ShoulderStructure: [sculpted, lightly_padded]
    notes: >
      Younger urban users increasingly prefer softer tailoring rather than
      aggressive shoulder architecture.

# Pear balancing in urban menswear should avoid costume-coded military details.
  Pear:
    flatters:
      LayeringStructure: [open_front, longline_jacket]
      ConstructionDetail: [textured_yoke, vertical_panel]
    avoid:
      ConstructionDetail: [epaulettes]
    notes: >
      Use layering, textured yokes, and visual shoulder balance rather than
      theatrical military styling.

# Medium-weight structure often improves Apple balancing.
  Apple:
    soft_avoid:
      FabricDrape: [rigid_tight]
    notes: >
      Structured fabrics can actually improve silhouette when fit remains
      relaxed and skim-not-cling.

# Diamond male body requires stronger vertical engineering.
  Diamond:
    flatters:
      LayeringStructure: [open_front, longline_jacket]
      ConstructionDetail: [vertical_panel, angled_seam]
      LineDirection: [vertical]
    avoid:
      ConstructionDetail: [center_gathering]
    notes: >
      Vertical breaks and structured shoulder balancing are more effective
      than aggressive tailoring.

# Gen Z Indian menswear increasingly uses relaxed tailoring and luxury streetwear.
LayeringStructure:
  OpenFront:
    flatters:
      LineDirection: [vertical]
    avoid: {}
    notes: Elongates torso and softens midsection.

  LonglineJacket:
    flatters:
      StructuralFocus: [center_front]
    avoid: {}
    notes: Modern indo-western balancing layer.

  SoftOvershirt:
    flatters:
      VolumeProfile: [moderate]
    avoid:
      VolumeProfile: [exaggerated]
    notes: Urban smart-casual layering for Gen Z and millennial styling.

---

# STYLIST_NOTES.md ADDITIONS

## Cross-cutting styling decisions

### Hard vs soft rule distinction
The previous schema treated all avoid/flatters guidance equally, which risks over-constraining outfit generation. Body styling rules contain both structural truths (e.g., very prominent bust + halter often creates support imbalance) and aesthetic tendencies (e.g., Minimalist users usually prefer low embellishment). The engine should distinguish hard constraints from soft preferences.

Recommended engine direction:
- hard_flatters / hard_avoid = structural fit, proportion, support, mobility
- soft_flatters / soft_avoid = taste direction, archetype leaning, trend guidance

### Off-shoulder and exposed-shoulder modeling
Existing neckline taxonomy was insufficient for Indian occasionwear. Off-shoulder, one-shoulder, cold-shoulder, and strapless behave differently in terms of:
- support requirement
- movement stability
- modesty calibration
- body balancing
- jewelry interaction
- dupatta compatibility

A dedicated ShoulderExposure taxonomy has been added.

### Dupatta drape as silhouette engineering
Dupatta placement materially changes body perception in Indian styling and cannot remain implicit. Vertical drapes slim and elongate; side-fall drapes soften midsection; single-shoulder drapes create upper-body emphasis. Dupatta logic should eventually integrate with occasion and modesty layers.

### Diamond body-type overhaul
Diamond body types were previously under-modeled and treated similarly to Apple. In practice, Diamond users benefit most from:
- vertical continuity
- shoulder architecture
- diagonal/side draping
- open-front layering
- reduced center gathering

The revised guidance introduces layering and vertical panel logic.

### Structured vs sculpted vocabulary
The term “sculpted” was overloaded and used inconsistently across:
- shoulder construction
- garment architecture
- volume placement
- fabric behavior

Future schema normalization should separate:
- structured
- shaped
- architectural
- padded
- sculptural

### Petite styling clarification
Petite/compact users can successfully wear statement dressing when visual weight is concentrated rather than distributed. The actual issue is scale management and visual interruption, not embellishment itself.

### Urban Indian menswear shift
Menswear guidance has been updated to better reflect current urban Indian styling trends:
- softer tailoring
- luxury casual layering
- monochrome co-ords
- overshirts
- open-front layering
- reduced dependence on hard shoulder structuring

This is particularly important for younger users in Bengaluru, Mumbai, and Hyderabad tech/luxury circles.

