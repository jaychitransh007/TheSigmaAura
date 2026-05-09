# STYLIST_NOTES

Cross-cutting rationale captured during the senior-stylist review of `style_graph/`. Per-rule rationale lives in YAML inline comments next to each change. This file is the place for cross-cutting decisions that don't belong in any single rule, plus content/catalog recommendations the engineering team needs to act on separately.

Source: `knowledge/knowledge_v2/archetype_yaml_stylist_pass_v_2.md` (May 2026 stylist pass v2). Subsequent file reviews (body_frame, palette, occasion, weather, pairing_rules, query_structure) will append here.

---

## Cross-cutting styling decisions — `archetype.yaml` (May 2026)

### 1. Indian ethnic motifs should not be treated as inherently anti-classic.
Classic Indian dressing historically includes restrained paisley, buti, woven zari motifs, temple borders, and heritage geometry. The prior `ethnic` avoid rule on the classic archetype over-westernised the system.

### 2. Minimalism in India frequently uses tonal craftsmanship.
Indian luxury minimalism relies heavily on low-contrast embroidery, self-texture, chikankari, tonal weaving, and subtle handwork rather than true visual absence. The prior schema's blanket `embroidery` avoid was wrong for Indian minimalism.

### 3. Modern professional dressing has geographically shifted.
Bengaluru and Hyderabad startup ecosystems now favour relaxed tailoring, premium basics, soft structure, and quiet luxury over rigid corporate silhouettes. The archetype's silhouette + fit rules were widened accordingly.

### 4. Trend-forward styling is increasingly silhouette-led.
Gen Z and luxury urban consumers now express fashion novelty more through construction, layering, proportion play, and silhouette experimentation than through embellishment alone. Embellishment-heavy framing was rebalanced toward construction + silhouette.

### 5. Age should influence calibration, not restrict style categories.
The prior age-band logic risked feeling outdated and overly prescriptive. Urban Indian consumers in their 30s regularly wear relaxed, oversized, directional, and experimental silhouettes — `25_30` and `30_35` `avoid` lists were cleared accordingly. Age remains a soft modifier on polish + occasion calibration, not a hard restriction on styling categories.

### 6. Sporty fashion in India now includes luxury athleisure.
The sporty archetype was modernised to include tenniscore, airportwear, clean sneaker culture, premium activewear, and restrained ethnic fusion. Previous "ethnic / motif" blanket avoid was wrong — urban sporty Indians wear sporty kurtas, co-ord ethnic, and sneaker ethnic fusion.

### 7. Creative and bohemian were previously too craft-maximalist.
Creative has been widened toward deconstructed tailoring, Japanese silhouettes, gender-fluid layering, indie monochrome, and art-school silhouettes. Bohemian has been widened toward Goa-luxury linen sets, indie urban styling, and Ibiza-influenced resort wear. The two archetypes overlap heavily — bohemian leans warmer in palette and softer in edge.

### 8. Sheen needed contextual interpretation.
The prior schema treated all sheen similarly. The stylistic distinction is between **ornamental festive shine** (avoid for edgy / classic / minimalist) and **polished controlled sheen** like leather, satin contrast, coated fabrics, latex finishes, or silk luster (acceptable for edgy, sometimes for classic). Edits to `classic.flatters.FabricTexture` and `edgy.avoid.FabricTexture` reflect this.

### 9. Risk-tolerance band `moderate` should not block `oversized`.
Oversized silhouettes are now mainstream in Gen Z and urban millennial dressing, especially in Bengaluru, Mumbai, and creator-heavy ecosystems. The avoid was cleared so the moderate band trusts the archetype's own preferences without strong over-correction.

### 10. Five new professions added.
`tech_startup`, `luxury_fashion`, `healthcare`, `academia`, `hospitality_media_influencer` — capture the dress-code divergence in urban India that the original four (`corporate`, `creative`, `entrepreneur`, `student`, `homemaker`, `other`) under-served.

---

## Cross-cutting styling decisions — `weather.yaml` + occasion follow-ups (May 2026)

Source: `knowledge/knowledge_v2/weather_yaml_review_and_updated_occasion_style_notes.md`. 6 in-place edits applied; structural recommendations queued for batch-execute.

### 11. Climate modifies, never replaces, cultural intent.
Weather adjusts fabric weight, layering, sleeve length, and practicality, but does not override occasion identity. A bridal lehenga in Delhi-cold-dry adds a pashmina shawl; it doesn't become a parka. Monsoon officewear swaps fabric, not occasion formality. Hill-station festivewear layers outerwear over ceremonial silhouettes.

### 12. Indian dry heat does not mean maximum skin exposure.
In North Indian dry heat, increased coverage with breathable natural fibres performs better than minimal clothing. Loose full-sleeve kurtas, kaftans, and relaxed silhouettes are often more thermally practical than exposed synthetic garments. The current `hot_dry` rule (`SkinExposureLevel: [very_low, low, medium]`) correctly inverts the Western "hot = minimal clothing" assumption — keep as-is.

### 13. Monsoon styling prioritizes drying behavior over pure aesthetics.
During Indian monsoon: quick-dry synthetics may outperform luxury natural fibres; white fabrics become transparency risks when wet; embroidery and heavy embellishment become maintenance burdens; fitted garments cling uncomfortably in humidity. Synthetic blends are pragmatic, not a downgrade.

### 14. Bangalore climate increases silhouette flexibility.
Warm-temperate plateau climates support the widest silhouette range in India. Recommendation engines should bias selection more heavily using occasion and archetype because weather contributes less restriction. `warm_temperate` is intentionally permissive; the entropy is real and should be tightened by *occasion* rather than weather.

### 15. `FabricTexture` is semantically overloaded.
Today's enum mixes tactile texture (smooth, ribbed, textured), optical finish (sheen, metallic, matte), and construction detail (embroidered). Future schema split: `FabricTexture` (tactile) + `SurfaceFinish` (optical) + `ConstructionDetail` (already exists, expand). Filed under the catalog enrichment queue for the batch-execute pass.

---

## Cross-cutting styling decisions — `palette.yaml` (May 2026)

Source: `knowledge/knowledge_v2/palette_yaml_stylist_review_and_style_notes.md`. Subset applied in-place; structural recommendations queued.

### 16. Palette flexibility over seasonal-color-analysis orthodoxy.
Traditional seasonal-color-analysis hard-banned black for warm palettes and metallics for muted palettes. Indian urban reality is more nuanced — soft / textured / washed black works in lower-body, layering, accessories, and Indo-Western styling even for warm palettes. Absolute prohibitions were softened to "pure jet-black near the face overpowers; everywhere else is fine" framing. Specifically applied across Warm Spring, Light Spring, Warm Autumn, Deep Autumn (and similar cleanup for Clear Spring).

### 17. Modern Indian neutral luxury vocabulary.
Expanded palette vocabulary beyond festive/traditional color theory to include contemporary Indian premium neutrals — espresso, mushroom, greige, cocoa, tobacco, stone, soft charcoal, mocha, sand, dusty cocoa rose. Added across Soft Autumn (mushroom, greige, cocoa), Deep Autumn (espresso, tobacco, dark olive, cocoa brown), Cool Summer (soft charcoal, steel blue, smoky navy), Soft Summer (smoky mauve, mushroom grey), Warm Autumn (tobacco, cinnamon, teak brown), Cool Winter (ink navy, charcoal), Deep Winter (graphite, ink navy in secondary). These are dominant in Bengaluru / Mumbai luxury minimalism, premium D2C fashion, Gen Z monochrome dressing, workwear, and quiet luxury.

### 18. Reduce bridal bias in winter palettes.
Clear Winter / Cool Winter / Deep Winter notes were over-indexed on bridal lehenga logic. Modern Indian winter dressing also includes monochrome black tailoring, sharp Indo-Western, satin shirts, dark minimalism, architectural solids, and clean contrast dressing. Notes updated for Clear Winter and Deep Winter to call this out alongside the bridal references.

### 19. Monochrome and tonal dressing support.
Added `single` to ColorCount across Soft Autumn, Deep Autumn, Cool Summer, Soft Summer (where it was missing) so the engine can surface tonal monochrome co-ord sets, tonal sarees, and Indo-Western tailoring more readily. Modern Indian urban styling heavily uses single-color and tonal combinations, especially in premium casual + co-ord categories.

### 20. Crisp white usable in Deep Winter.
Removed `stark white` from Deep Winter avoid. Deep Winter users frequently wear white shirts, ivory-black contrast, white embroidery on black, monochrome contrast styling — washed-out icy pastels are the real concern, not true white.

### 21. Metallics — distinguish mirror-shine from antique/brushed.
The system over-penalizes metallics for muted palettes. The actual issue is mirror-shine high-reflective metallic surfaces. Brushed, oxidized, antique, matte, dull champagne, and aged-bronze metallic finishes work well for muted palettes (Soft Summer, Cool Summer, Soft Autumn). Engineering item: future `SurfaceFinish` decomposition (queued via weather review #15) should split `metallic` into `high_shine_metallic` / `antique_metallic` / `brushed_metallic`.

---

## Rare-value category cleanup recommendations

These are catalog / schema decisions that need engineering action — not YAML edits the stylist can make in place.

| Subtype | Decision | Rationale |
|---|---|---|
| `kaftan` | **KEEP** | Huge in Indian commerce now (resort wear, festive layering, modest summer). |
| `ethnic_set` | **KEEP** | Co-ord ethnic is a major Gen Z and millennial category. |
| `dungarees` | **MERGE** → `jumpsuit` (or `casual_onepiece` / `workwear` parent) | Low catalog volume, semantically overlapping. |
| `poncho` | **MERGE** → `outer_layer_relaxed` (parent category for relaxed outerwear) | Low catalog volume; better captured as a relaxed-outer subset. |
| `tracksuit` | **DEFER** to product/catalog team | Keep only if sporty / airportwear / Gen Z streetwear matter to business goals. Otherwise low-value to maintain rules for. |

---

## Forward-looking / unresolved

Items the stylist surfaced but that need engineering input before they can be applied:

1. **`hard:` / `soft:` distinction at the rule level.** Currently every entry under `flatters:` / `avoid:` is treated uniformly. Some rules are absolute (Pear should never wear hip-emphasizing patterns); some are preferences (a Modern Professional usually leans clean lines, but exceptions are fine). Filed under Phase 4.3 in `docs/OPEN_TASKS.md`.

2. **`ShoulderExposureLevel` axis.** `[none, partial, visible, full]` — fixes the off-shoulder / cold-shoulder / one-shoulder / spaghetti / strapless gap that today's `covers_shoulders` boolean can't represent. Indian modesty logic is not binary. Filed under Phase 4.3a.

3. **`EmbellishmentVisibility` axis.** `[hidden, subtle, visible, statement]` — captures Indian luxury minimalism's low-contrast craftsmanship that today's `EmbellishmentLevel` flattens. Filed under Phase 4.3b.

4. **`VisualAuthority` axis (deferred — large lift).** `[understated, polished, festive, regal, avant_garde]` — captures Indian textile hierarchy in a way fabric/embellishment alone don't (Kanjeevaram > sequinned georgette by authority, not by embellishment). Filed under Phase 4.3d as a future schema extension.

5. **Vocabulary cleanups (gated on Phase 4.6 eval set).** Three terms doing too much semantic work: `sheen` (luxury silk glow vs metallic shine vs satin gloss), `ethnic` PatternType (woven motifs vs folk prints vs artisanal vs festive), `soft_structured` FabricDrape (semi-fluid tailoring vs controlled drape vs polished ease). Disambiguation needs joint stylist + engineering pass once eval-set ground truth lands.

6. **New archetypes (deferred — trigger-based).** `Quiet Luxury` is currently split awkwardly across minimalist / classic / modern_professional. `Sensual` is split across glamorous / romantic / edgy. Trigger to act: when eval-set cells consistently misroute between the parent archetypes for the same query.

7. **Fabric pairing intelligence (next file: `pairing_rules.yaml`).** Indian styling is textile-driven — raw silk tolerates structure, georgette tolerates drape, organza amplifies volume, brocade increases visual density, handloom softens formality. The pairing engine currently thinks in silhouette + embellishment terms; textile hierarchy is the single most important missing sophistication layer. Will be addressed in the next stylist pass.
