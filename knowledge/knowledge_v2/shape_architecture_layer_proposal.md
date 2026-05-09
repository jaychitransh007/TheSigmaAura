# Shape Architecture Layer — Stylist Proposal (May 2026)

7th stylist deliverable. Followed the original 6 stylist files
(archetype, bodyframe, occasion, weather, palette, pairing_rules,
query_structure) as a follow-up architectural recommendation.

## Premise

The current schema is too "garment-category-centric." Modern fashion —
especially Indian urban Gen Z / millennial styling — increasingly
depends on **shape behavior**, not just garment type.

A puff sleeve, sculptural drape, hanging sash, cape panel, waterfall
layer, asymmetrical hem, side train, attached scarf panel, exaggerated
shoulder, cocoon silhouette, or ruched extension all create *visual
geometry* independent of garment category.

Today the schema partially captures this via:
- `FitType`
- `FabricDrape`
- `SilhouetteContour`
- `LineDirection`
- `StructuralFocus`

…but these are insufficient because they don't model:
- localized volume,
- asymmetry,
- projection,
- movement behavior,
- architectural extensions, or
- silhouette interruption.

## Recommended schema extension

A new high-level namespace **`ShapeArchitecture`** sitting alongside
`FitType` / `FabricDrape` / `ConstructionDetail` / `SilhouetteContour`
as orthogonal metadata.

### 1. VolumePlacement (most important — currently missing primitive)

```yaml
VolumePlacement:
  - none
  - shoulder
  - sleeve
  - bust
  - waist
  - hip
  - hem
  - asymmetric_side
  - back
  - global
```

**Examples:** puff sleeve → `sleeve`; peplum → `waist`; dhoti drape →
`hip`; mermaid flare → `hem`; cape gown → `back`; one-sided drape →
`asymmetric_side`.

**Why important:** directly affects visual balance for Pear, Inverted
Triangle, Diamond, Petite, and heavy upper-arm users. Volume placement
is THE variable AI styling systems most often flatten.

### 2. VolumeIntensity

```yaml
VolumeIntensity:
  - flat
  - soft
  - moderate
  - exaggerated
  - sculptural
```

**Examples:** slight bishop sleeve → `soft`; oversized puff →
`exaggerated`; couture cocoon sleeve → `sculptural`.

Without this, the engine treats all puff sleeves equally.

### 3. AsymmetryType

```yaml
AsymmetryType:
  - none
  - neckline
  - hem
  - drape
  - closure
  - panel
  - sleeve
  - shoulder
  - layered
```

**Examples:** one-shoulder blouse, high-low kurta, side-draped saree
gown, asymmetric jacket zip, cape attached on one side.

**Why important:** asymmetry strongly affects perceived height, visual
movement, slimming effect, modernity perception, fashion-forwardness.

### 4. ProjectionType

```yaml
ProjectionType:
  - none
  - structured_outward
  - fluid_outward
  - architectural
  - floating
```

**Examples:** pannier lehenga → `structured_outward`; organza cape →
`floating`; cocoon jacket → `architectural`; layered drape →
`fluid_outward`.

**Why important:** projection changes body width perception, luxury
perception, editorialness, mobility.

### 5. MotionBehavior

```yaml
MotionBehavior:
  - static
  - fluid
  - swish
  - flutter
  - trail
  - bounce
  - dramatic_motion
```

**Examples:** fringe saree, tassel dupatta, organza cape, sharara
flare, pleated skirt, layered anarkali.

**Why important:** sangeet, cocktail, reel-friendly styling, Gen Z
eventwear, dance contexts. Some garments activate during movement;
others stay static. Today the engine can't distinguish.

### 6. EdgeGeometry

```yaml
EdgeGeometry:
  - clean
  - sharp
  - scalloped
  - irregular
  - cascading
  - layered
  - pointed
```

**Examples:** waterfall shrug → `cascading`; handkerchief hem →
`pointed`; scalloped lehenga border; layered tulle hem.

**Why important:** dramatically changes perceived softness vs sharpness
of the silhouette boundary.

### 7. AttachmentStructure

```yaml
AttachmentStructure:
  - none
  - attached_dupatta
  - attached_cape
  - attached_drape
  - attached_sash
  - attached_panel
  - detachable_layer
```

**Examples:** pre-draped saree with attached pallu, cape lehenga, sari
gown trail, attached shoulder drape, hanging sash panel.

**Why important:** solves the longstanding "some part hanging which
isn't a dupatta" problem for couture and Indo-Western. Critical for
ceremonial styling.

### 8. StructuralRhythm

```yaml
StructuralRhythm:
  - minimal
  - repetitive
  - layered
  - interrupted
  - chaotic
```

**Examples:** tiered sharara → `repetitive`; layered ruffle saree →
`layered`; deconstructed jacket → `interrupted`.

**Why important:** maximalism scoring, visual complexity, sensory
load, archetype matching.

## What this unlocks

| Garment | Why current schema fails | New schema fix |
|---|---|---|
| Puff-sleeve blouse | only "blouse" exists | `VolumePlacement: sleeve` |
| Cape saree | no attachment modeling | `AttachmentStructure: attached_cape` |
| One-sided drape gown | asymmetry invisible | `AsymmetryType: drape` |
| Dramatic sharara | motion ignored | `MotionBehavior: swish` |
| Cocoon coord set | projection ignored | `ProjectionType: architectural` |
| Waterfall shrug | edge geometry absent | `EdgeGeometry: cascading` |
| Organza trail | floating structure absent | `ProjectionType: floating` + `MotionBehavior: trail` |

## Architectural advice from stylist

> Do NOT encode these into:
> - garment categories
> - silhouette names
> - occasion tags
>
> That becomes combinatorial hell.
>
> Instead:
>
>     Garment
>       ├── Category
>       ├── FitType
>       ├── Fabric
>       └── ShapeArchitecture
>
> where ShapeArchitecture is orthogonal metadata.
> That keeps the engine composable.

> Add this entire new layer:
>     `shape_architecture.yaml`
> instead of polluting:
> - body_frame
> - pairing_rules
> - archetype
>
> because these are cross-cutting, reusable, orthogonal, highly composable.

## Engineering implications

This is a substantial schema extension layered on top of Step 2a (which
just shipped 12 new axes — PR #237). The full scope:

1. **Canonical schema additions** to `garment_attributes.json` —
   8 new enum axes, ~50+ new enum values total.
2. **Database migration** — 16 new columns on `catalog_enriched`
   (8 axes × value + confidence each).
3. **Vision-enrichment prompt updates** — descriptions for all 8 axes
   with disambiguation rules (especially `VolumePlacement`,
   `AttachmentStructure`, `MotionBehavior` which require careful
   image reasoning).
4. **New YAML file** `knowledge/style_graph/shape_architecture.yaml`
   defining body-shape × ShapeArchitecture flatters/avoid rules
   (separate stylist content pass — not engineering).
5. **yaml_loader extension** to load the new top-level YAML file as
   another dimension of the style graph.
6. **Composer engine integration** to score outfits using the new
   axes (long-term, not Step 2a).

## Recommendation

Integrate items 1-3 into Step 2a (extending the just-shipped PR #237)
**before** Step 2b (the vision re-enrichment) fires. This way the
re-enrichment captures all 20 new axes in one run instead of two,
saving ~$300-700 + ~10-15 hours compute and avoiding two cycles of
catalog drift.

Items 4-6 are larger work that lands in subsequent passes:
- Item 4 needs a separate stylist content pass (define body-shape ×
  ShapeArchitecture rules) — file the request.
- Item 5 is small yaml_loader work, can ship anytime after item 4 lands.
- Item 6 (engine integration) is the biggest piece and lands after
  the held YAML patches in Step 4.
