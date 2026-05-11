# Open Tasks

This file lists what's open **now**. Shipped work history lives in `docs/RELEASE_READINESS.md` § "Recently Shipped". Forward-planning content was intentionally removed 2026-05-11 — the user wants this file to reflect only what's worth focusing on today.

---

## Worth focusing on (today)

**Pure engineering work: none.** The May 2026 session closed the implement-today queue (PRs #246-#264). One trigger-driven item remains — no work needed until the trigger fires:

### 1. Masculine top coverage — largely RESOLVED by the May 2026 re-enrichment

**Status (verified against staging catalog 2026-05-11 post-re-enrichment):** the gap reported in April 2026 has substantially closed. The catalog now carries:

| Subtype | Masculine | Unisex | Combined |
|---|---:|---:|---:|
| `shirt` | 922 | 9 | 931 |
| `tshirt` | 369 | 17 | 386 |
| `sweatshirt` | 63 | 0 | 63 |
| `hoodie` | 39 | 3 | 42 |
| `polo_tshirt` | **0** | 0 | **0** |

Total masculine inventory: **4,298 items across 21 subtypes** (not the 8 reported pre-re-enrichment). The May re-enrichment didn't add new products — it fixed subtype recognition. Items previously miscategorised as `blazer` / `jacket` got accurate `shirt` / `sweatshirt` tags.

**Remaining gap:** `polo_tshirt` is the only top subtype with literally zero items. Likely a vocabulary signal — polos may be getting tagged as either `tshirt` or `shirt` by the vision pipeline. To resolve, the business needs to source dedicated polo-tagged products via the admin tool's per-product ingestion (allowed under frozen-catalog policy).

**Trigger to act.** Only if `polo_tshirt` becomes a request driver and the existing `tshirt` / `shirt` fallback isn't sufficient. Most queries that want polos accept tshirts or shirts as substitutes.

---

## Frozen-catalog policy (2026-05-11)

The catalog AND its embeddings are **frozen** at the 14,242-row state. Both operations below are forbidden under this policy:

| Operation | Cost | Time | Status |
|---|---|---|---|
| Vision re-enrichment (gpt-5-mini batch on existing rows) | $35-40 | ~30h | ⛔ Forbidden |
| Embedding regeneration (text-embedding-3-small on existing rows) | ~$0.50 | ~35 min | ⛔ Forbidden |

**What's still allowed:**
- Per-product enrichment of NEW catalog items at ingestion time (admin tool's vision pipeline). Per-product, not bulk.
- Per-product embedding generation for newly ingested items.
- Schema changes that are pure SQL transforms over existing rows — but note that without embedding regen, such changes only affect SQL-filter behaviour; semantic similarity search keeps encoding the pre-change state, so most aren't worth shipping on SQL-only effect alone.

**Composer engine flag.** `AURA_COMPOSER_ENGINE_ENABLED=true` is a config flip available today — no engineering work needed. Engine acceptance rate is ~4%, so blast radius is small. Recommended posture: flip in staging, watch Panel 18 (rater unsuitable rate) and Panel 25-27 for a week, revert if unsuitable rate climbs >1pp on engine-accepted turns.

---

## Permanently dropped under frozen-catalog policy

Kept here as a guardrail against re-proposing in future sessions.

**Vision-re-enrichment-dependent:**
- ~10 dormant stylist vocab values (`wrap_with_hard_cinching`, `kasavu_border`, `temple_border`, `lightly_padded`, `angled_seam`, `vertical_panel`, `center_gathering`, `textured_yoke`, `epaulettes`, `rigid_tight`, `distributed_heavy`, `hard_cinched` / `soft_defined` / `strategic_defined`, `micro_mini`).
- `FabricTexture` decomposition (split into `FabricTexture` + `SurfaceFinish` + `ConstructionDetail`).
- `SurfaceFinish` axis adoption (`high_shine_metallic` / `antique_metallic` / `brushed_metallic`).
- Wave B ontology surgery (4 deferred ShapeArchitecture axes: `ProjectionType` / `StructuralRhythm` / `EdgeGeometry` / `VolumeIntensity`).
- 4-stage extraction architecture.
- Full Step 4 bodyframe + occasion patches beyond the thin subset already shipped.

**Embedding-regen-dependent (added 2026-05-11 late):**
- Wave A surgical cuts (OccasionSignal / SilhouetteContour / FitEase column drops).
- Color-axes algorithmic switch (Pillow/OpenCV deriving `ContrastLevel` / `ColorTemperature` / `ColorSaturation` / `ColorValue`).
- GarmentSubtype → OutfitStructure carve-out.
- ConstructionDetail cleanup (move `deconstructed` / `utility` / `experimental` to a future `StyleExpression` axis).
- Catalog vocab cleanup Phase 2 (drop `OccasionFit` / `OccasionSignal` / `FormalitySignalStrength` from embedding text).
- Rare-value cleanup (per-row content decisions for ≤5-row subtypes like poncho / leggings / kaftan / tracksuit / dungarees / ethnic_set).

Stylist's prose documentation for the dormant-vocabulary work remains in `knowledge/knowledge_v2/` as a historical reference. If a future policy reversal authorises re-enrichment + embedding regen, those files specify what to add.
