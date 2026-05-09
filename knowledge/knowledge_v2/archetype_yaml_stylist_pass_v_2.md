# archetype.yaml — Stylist Pass Applied Changes

## classic

```yaml
  classic:
    flatters:
      # Classic Indian dressers regularly wear restrained heritage motifs.
      PatternType:           [solid, stripes_vertical, checks, geometric, ethnic]
      PatternScale:          [micro, small]
      EmbellishmentLevel:    [none, minimal, subtle]
      EmbellishmentType:     [none, embroidery]
      # Shift from overt sheen toward restrained silk luster / matte polish.
      FabricTexture:         [smooth, matte, low_luster, pleated]
```

```yaml
    avoid:
      PatternType:           [animal, abstract]
```

```yaml
    notes: >
      Western context: tailored sheath dress, cigarette pant + crisp shirt,
      structured blazer. Indian: well-tailored kurta + churidar in muted
      jewel tones, classic banarasi silk saree (for ceremonies), bandhgala
      with subtle thread embroidery, structured A-line anarkali. Restrained
      ethnic motifs (paisley, buti, woven temple borders, subtle ajrakh)
      work well when kept refined and low-contrast. The classic archetype
      favours timelessness over trend — heavy zardozi reserved for bridal
      contexts only; daily wear leans clean and defined. For male grooms:
      ivory bandhgala or off-white sherwani with subtle pearl detailing,
      never sequinned.
```

---

## minimalist

```yaml
  minimalist:
    flatters:
      PatternType:           [solid]
      PatternScale:          [micro]
      EmbellishmentLevel:    [none, minimal]
      # Indian luxury minimalism often relies on tonal craftsmanship.
      EmbellishmentType:     [none, tonal_embroidery, self_texture, chikankari, kantha]
```

```yaml
    avoid:
      PatternType:           [floral, animal, abstract, ethnic, motif]
      EmbellishmentLevel:    [moderate, heavy, statement]
      EmbellishmentType:     [print, beading, sequins, lace, applique, mirror_work, distressing, mixed]
```

```yaml
    notes: >
      Western: solid colour-blocked shift, plain knit + tailored trouser,
      structured tote. Indian: solid Mysore silk or Chanderi saree with
      tonal blouse, plain handloom kurta with tonal threadwork, refined
      chikankari, self-weave textures, understated kantha edging, bandhi
      over solid kurta, plain dupatta. The minimalist archetype is the
      hardest to pull off in Indian urban contexts because cultural
      expectations push toward embellishment — minimalists deliberately
      under-decorate even at festive occasions.
```

---

## modern_professional

```yaml
  modern_professional:
    flatters:
      SilhouetteType:        [fitted, straight, relaxed_tailored]
      FitType:               [tailored, slim, regular]
```

```yaml
    notes: >
      Tightest archetype for the workplace. Western: pencil skirt + shell
      top + structured blazer; well-cut suit. Indian urban: cigarette pant
      + tucked silk shirt + bandi, structured cotton kurta + slim trouser,
      a saree (in cotton or fine silk) with crisp pleated blouse. Bengaluru
      and Hyderabad startup ecosystems increasingly lean toward relaxed-
      tailored silhouettes, quiet luxury fabrics, softer layering, premium
      co-ords, and clean oversized outerwear rather than rigid corporate
      suiting.
```

---

## romantic

```yaml
  romantic:
    flatters:
      FabricTexture:         [smooth, sheen, embroidered, sheer]
```

```yaml
    notes: >
      Western: floral midi dress, silk wrap blouse, soft tweed jacket,
      lace cami. Indian urban: chikankari kurti (white/pastel) — the
      definitive romantic Indian piece, gota patti work on dupatta,
      pastel anarkali with delicate floral embroidery, soft Mysore-silk
      saree with hand-embroidered border, organza layering, tissue-silk
      softness, translucent sleeves, and net overlays.
```

---

## dramatic

```yaml
  dramatic:
    avoid:
      PatternType:           [floral]
      PatternScale:          [micro, small]
      EmbellishmentLevel:    [none, minimal]
      # Fluid drapes can work when sculptural or directional.
      FabricDrape:           []
```

```yaml
    notes: >
      Western: structured cape coat, bold-shoulder blazer, asymmetric
      drape gown. Indian urban: sculpted asymmetric drape saree (Tarun
      Tahiliani, Anamika Khanna style), structural lehenga choli with
      cape, bandhgala with sharp shoulder construction. Statement
      monochrome embroidery (silver on black, gold on burgundy). Fluid
      drapes are acceptable when directional, sculptural, or architecturally
      styled rather than soft and romantic.
```

---

## creative

```yaml
  creative:
    flatters:
      ConstructionDetail:    [asymmetric_hem, draped, gathered, deconstructed]
      SilhouetteType:        [relaxed, a_line, oversized, layered]
```

```yaml
    notes: >
      Western: print-mixing midi dress, eclectic statement jewellery,
      mixed-medium handbag, deconstructed tailoring, Japanese-inspired
      layering, gender-fluid styling, indie monochrome, art-school
      silhouettes. Indian urban: handloom Kalamkari saree with block-print
      blouse, Patola weave, Ikat kurta, kantha-embroidery jacket over plain
      kurta, fusion pieces (kurta + jeans + jacket), layered co-ords,
      asymmetrical drapes, and experimental tailoring. Creative is broader
      than craft-maximalism alone.
```

---

## natural

```yaml
  natural:
    flatters:
      FabricTexture:         [textured, knit, matte, slub]
```

---

## sporty

```yaml
  sporty:
    flatters:
      PatternType:           [solid, abstract, ethnic]
      FabricTexture:         [smooth, ribbed, knit, matte, performance]
      ConstructionDetail:    [none, pleated, utility]
```

```yaml
    avoid:
      PatternType:           [floral]
```

```yaml
    notes: >
      Western: athleisure, performance knit, tenniscore separates,
      technical outerwear, clean sneaker culture. Indian urban:
      knit-fabric kurta + slim ankle trouser, sneaker-friendly ethnic
      fusion, premium co-ords, airportwear layering, luxury athleisure,
      monochrome activewear, sporty Indo-western silhouettes. Sporty users
      may still wear restrained ethnic fusion, but avoid heavily ceremonial
      styling.
```

---

## trend_forward

```yaml
  trend_forward:
    flatters:
      ConstructionDetail:    [asymmetric_hem, ruched, draped, experimental]
      SilhouetteType:        [oversized, mermaid, peplum, sculptural]
```

```yaml
    notes: >
      Western: current-season designer pieces — whatever is on the
      fashion-week runway right now. Indian urban: experimental drape
      saree (concept saree, pre-stitched), modern lehenga shapes,
      directional co-ords, volume experimentation, unusual layering,
      proportion play, and silhouette novelty. Trend-forward today is
      driven more by construction and styling experimentation than by
      embellishment alone.
```

---

## bohemian

```yaml
  bohemian:
    notes: >
      Western: maxi dress with print-mixing, fringe-detail jacket,
      leather waist-tie. Indian urban: Bandhani saree with mirror-work
      border, Patola weave, Ikat kurta, kantha-embroidery jacket,
      embroidered Phulkari dupatta, oxidised jewellery, layered drape
      saree (Bengali style), Goa-luxury boho linen sets, artisanal resort
      wear, relaxed crochet textures, and indie urban layering. Bohemian
      and creative overlap heavily — bohemian leans warmer in palette,
      softer in edge, and more relaxed in spirit.
```

---

## edgy

```yaml
  edgy:
    avoid:
      PatternType:           [floral]
      EmbellishmentType:     [lace, beading]
      FabricTexture:         [knit]
```

```yaml
    notes: >
      Western: leather jacket over column dress, structured oxblood
      blazer, distressed denim, statement boots. Indian urban:
      structural drape saree paired with leather jacket, oxblood/black
      bandhgala, asymmetric kurta with metal hardware, fusion sherwani
      in deep charcoal/oxblood. Polished sheen from leather, coated
      fabrics, satin contrast, or latex-inspired finishes works well;
      avoid ornamental festive shine.
```

---

## risk_tolerance.moderate

```yaml
  moderate:
    avoid:
      EmbellishmentLevel:    [statement]
```

```yaml
    notes: >
      Default risk band. Trusts the archetype's own preferences without
      strong over- or under-correction. Oversized silhouettes are now
      mainstream in Gen Z and urban millennial dressing, especially in
      Bengaluru, Mumbai, and creator-heavy ecosystems.
```

---

## age_band

```yaml
  25_30:
    avoid:
      EmbellishmentType:     []
```

```yaml
  30_35:
    avoid:
      EmbellishmentType:     []
      FitType:               []
      FabricTexture:         []
```

```yaml
    notes: >
      Mature polish. Investment-grade silks, structured cuts,
      intentional styling, and confidence in personal aesthetic become
      more common — but oversized tailoring, relaxed silhouettes,
      experimental styling, and streetwear-inspired proportions remain
      fully viable in Indian urban fashion.
```

---

## profession

```yaml
  tech_startup:
    flatters:
      FormalityLevel:        [casual, smart_casual, semi_formal]
      FitType:               [regular, relaxed, tailored]
      SilhouetteType:        [straight, relaxed_tailored, oversized]
      FabricTexture:         [smooth, matte, knit, textured]
      EmbellishmentLevel:    [none, minimal, subtle]
    avoid:
      FormalityLevel:        [ceremonial]
    notes: Bengaluru-style startup dressing prioritises clean comfort,
      premium basics, quiet luxury, technical fabrics, relaxed tailoring,
      sneaker compatibility, and understated polish.
```

```yaml
  luxury_fashion:
    flatters:
      FormalityLevel:        [smart_casual, semi_formal, formal]
      EmbellishmentLevel:    [subtle, moderate, statement]
      ConstructionDetail:    [asymmetric_hem, draped, experimental]
      SilhouetteType:        [fitted, oversized, sculptural]
    avoid: {}
    notes: Fashion, luxury retail, PR, styling, and editorial ecosystems
      permit directional silhouettes, statement styling, and trend-forward
      experimentation even during daytime.
```

```yaml
  healthcare:
    flatters:
      FormalityLevel:        [casual, smart_casual]
      FitType:               [regular, relaxed]
      FabricTexture:         [smooth, knit, matte]
      EmbellishmentLevel:    [none, minimal]
    avoid:
      EmbellishmentLevel:    [heavy, statement]
    notes: Practicality, movement, hygiene, breathable fabrics, and low-
      maintenance styling dominate. Visual polish should remain understated.
```

```yaml
  academia:
    flatters:
      FormalityLevel:        [smart_casual, semi_formal]
      PatternType:           [solid, checks, ethnic, motif]
      FabricTexture:         [textured, matte, handloom]
      EmbellishmentLevel:    [none, minimal, subtle]
    avoid:
      EmbellishmentLevel:    [heavy, statement]
    notes: Academic dressing often leans intellectual, artisanal,
      handloom-friendly, and comfort-oriented rather than trend-driven.
```

```yaml
  hospitality_media_influencer:
    flatters:
      FormalityLevel:        [casual, smart_casual, semi_formal, formal]
      ConstructionDetail:    [draped, asymmetric_hem, experimental]
      EmbellishmentLevel:    [subtle, moderate, statement]
      ColorSaturation:       [medium, high, very_high]
    avoid: {}
    notes: Public-facing industries reward visual identity, trend fluency,
      photogenic styling, and strong silhouette definition.
```

---

# STYLIST_NOTES.md

```md
# STYLIST_NOTES

## Cross-cutting styling decisions

### 1. Indian ethnic motifs should not be treated as inherently anti-classic.
Classic Indian dressing historically includes restrained paisley, buti,
woven zari motifs, temple borders, and heritage geometry. The prior
ethnic avoid rule over-westernised the system.

### 2. Minimalism in India frequently uses tonal craftsmanship.
Indian luxury minimalism relies heavily on low-contrast embroidery,
self-texture, chikankari, tonal weaving, and subtle handwork rather than
true visual absence.

### 3. Modern professional dressing has geographically shifted.
Bengaluru and Hyderabad startup ecosystems now favour relaxed tailoring,
premium basics, soft structure, and quiet luxury over rigid corporate
silhouettes.

### 4. Trend-forward styling is increasingly silhouette-led.
Gen Z and luxury urban consumers now express fashion novelty more through
construction, layering, proportion play, and silhouette experimentation
than through embellishment alone.

### 5. Age should influence calibration, not restrict style categories.
The previous age-band logic risked feeling outdated and overly
prescriptive. Urban Indian consumers in their 30s regularly wear relaxed,
oversized, directional, and experimental silhouettes.

### 6. Sporty fashion in India now includes luxury athleisure.
The sporty archetype was modernised to include tenniscore, airportwear,
clean sneaker culture, premium activewear, and restrained ethnic fusion.

### 7. Creative and bohemian were previously too craft-maximalist.
Creative has been widened toward deconstructed tailoring, Japanese
silhouettes, and gender-fluid layering. Bohemian has been widened toward
luxury resortwear and indie urban styling.

### 8. Sheen needed contextual interpretation.
The prior schema treated all sheen similarly. The stylistic distinction is
between ornamental festive shine and controlled polished sheen such as
leather, satin contrast, coated fabrics, or silk luster.

## Rare-value category cleanup recommendations

- KEEP: kaftan
- KEEP: ethnic_set
- MERGE: dungarees -> jumpsuit
- MERGE: poncho -> outer_layer_relaxed
- DEFER: tracksuit decision to product/catalog s