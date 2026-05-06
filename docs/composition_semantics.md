# Composition Engine — Semantic Spec

**Status:** v1 spec, May 14 2026. **Implementation SHIPPED 2026-05-06** — see PRs #149 (engine 4.7a-f + 4.8 framework + 4.9 router + 4.10 flag), #151 (4.11 canonicalize layer + threshold recalibration to 0.50), #150 / #152 / #153 / #154 (4.12 observability + operability hardening). Sections marked **🎨 STYLIST SIGN-OFF NEEDED** are still gated on the Phase 4.2 paid-stylist YAML review.

This spec defines how the composition engine reduces 8 YAML mapping tables (`knowledge/style_graph/*.yaml`) into a structured `direction` object that matches the architect's existing `DirectionSpec` schema. Goal: replace the architect's gpt-5.2 LLM call (~19s) with deterministic YAML composition (~500ms) on the common path, falling back to the LLM only for genuine YAML gaps or low-confidence outputs.

**Verified end-to-end on 2026-05-06:** a real flag-on staging turn (`b356a1bf`, "Find me casual outfits for weekend outing") produced `used_engine=true, confidence=1.0, engine_ms=0`. Total turn 83s → 63s vs the flag-off baseline; per-turn cost dropped from ~$0.19 to ~$0.15. The architect stage (`19s` LLM call → ~0ms engine) is the dominant saving; composer + rater also got cheaper because the engine emits fewer items to evaluate.

---

## 1. Inputs

The engine takes the same `CombinedContext` the architect's `_build_user_payload` consumes, plus the planner's resolved fields:

| Input | Source | Cardinality |
|---|---|---|
| `gender` | `UserContext.gender` | feminine \| masculine \| unisex |
| `body_shape` | `analysis_attributes.BodyShape` | 7 canonical (Pear, Hourglass, Apple, Inverted Triangle, Rectangle, Diamond, Trapezoid) |
| `frame_structure` | `derived_interpretations.FrameStructure` | 6 labels (Light/Medium/Solid × Narrow/Balanced/Broad) |
| `seasonal_color_group` | `derived_interpretations.SeasonalColorGroup` | 12 sub-seasons |
| `archetype` | `live_context.style_goal` (if matches a canonical archetype) | 9 from `archetype.yaml`, else `None` |
| `risk_tolerance` | `style_preference.riskTolerance` | conservative \| balanced \| expressive |
| `occasion_signal` | planner output | ~45 from `occasion.yaml` |
| `formality_hint` | planner output | casual \| smart_casual \| semi_formal \| formal \| ceremonial |
| `weather_context` | `live_context.weather_context` | 10 climate buckets from `weather.yaml` |
| `time_of_day` | `live_context.time_of_day` | morning \| daytime \| evening \| night |

The engine **reads but does not write** these inputs. Stochastic-source signals (planner output) are accepted as-is — engine determinism is purely about input → output, not input → input.

## 2. Output

Same shape as `RecommendationPlan` in `agentic_application/schemas.py`:

```python
RecommendationPlan(
    retrieval_count: int,           # determined by direction count + role mix
    directions: List[DirectionSpec],
    plan_source: str = "engine",    # 'engine' | 'engine_fallback_llm'
    resolved_context: ResolvedContextBlock,
)
```

Each `DirectionSpec` carries:
- `direction_id` — A / B / C
- `direction_type` — complete | paired | three_piece (chosen by `query_structure.yaml`)
- `label` — short stylist-flavored title
- `queries` — list of `QuerySpec` per role (top, bottom, complete, etc.)

Each `QuerySpec.query_document` is a generated text string consumed by the embedding model. The engine **renders** the text from the composed attribute set; it does not invoke an LLM.

## 3. Composition algorithm

### 3.1 Per-attribute reduction

For each garment attribute (e.g., `FabricDrape`, `SilhouetteType`, `PatternType`):

```
flatters_set(attr)  =  ⋂ over sources S  flatters(S, attr)   ← intersect
avoid_set(attr)     =  ⋃ over sources S  avoid(S, attr)      ← union
final(attr)         =  flatters_set(attr) \ avoid_set(attr)  ← avoid wins
```

In words:
- **Flatters intersect across sources.** A FabricDrape is "flattering" only if every source that has an opinion on it agrees.
- **Avoid unions across sources.** A FabricDrape is "avoid" if any source flags it.
- **Avoid wins over flatters.** If body_frame says `flatters: [fluid]` but archetype says `avoid: [fluid]`, the value is dropped.

### 3.2 Empty intersection

The most common edge case. If `final(attr)` is empty after intersection + avoid-removal:

1. Apply **soft-source relaxation**: drop the lowest-precedence soft contributor (see §4) and recompute. Peers (e.g. archetype and risk_tolerance share precedence at the soft tier) are dropped **one at a time, in declaration order from §3.3**, not simultaneously — each drop gets its own recompute pass before moving to the next.
2. If still empty after dropping all softs, apply **hard-source widening**: re-include the lowest-precedence hard contributor's `flatters` while **preserving all `avoid` constraints from every source**, including the source being widened. Widening relaxes "must be in this set" but never "must NOT be in this set" — the avoid invariant carries the strongest stylist signal and is never softened.
3. If still empty, the attribute is **omitted from the composed direction**. The query_document renders without it; downstream retrieval scopes broader.

Empty-intersection events are logged with full input + attribute + sources for stylist review (Phase 4.7 requirement).

### 3.3 Hard vs soft constraints

| Source | Constraint type | Reason |
|---|---|---|
| `body_shape` | **HARD** | Physical proportion — wrong silhouette reads as wrong outfit regardless of style |
| `frame_structure` | **HARD** | Same as body_shape, lower precedence (per architect prompt line 380) |
| `seasonal_color_group` | **HARD** | Color reads matter for skin/hair harmony; wrong palette ruins the look |
| `gender` | **HARD** | Catalog filtering — garments must exist |
| `formality_hint` + `occasion_signal` | **HARD** | Wrong formality = inappropriate outfit |
| `weather_context` | **HARD** for fabric weight + layering; SOFT for color saturation |
| `archetype` | **SOFT** | Refines within what flatters; never overrides body or palette |
| `risk_tolerance` | **SOFT** | Modulates statement-piece intensity |
| `style_goal` (free-text) | **SOFT** | Per-turn directional cue; can be overridden by hard sources |
| `time_of_day` | **SOFT** | Palette-depth nudge |

**🎨 STYLIST SIGN-OFF NEEDED**: weather_context's split treatment (hard for fabric, soft for color) — needs validation against actual stylist intuition. Default to hard for both if review flags concern.

## 4. Conflict precedence — pair relationships

When two sources disagree on the same attribute, precedence resolves the conflict. Inherited from the architect prompt's rules + extended for the 6 sources not previously formalized.

### 4.1 Established by architect prompt

| Higher precedence | Lower precedence | Source |
|---|---|---|
| `BodyShape` | `FrameStructure` | architect prompt L380: "BodyShape priority on width signals" |
| `BodyShape` | `Archetype` | architect prompt L255 + Style Direction Source of Truth |
| `FrameStructure` | `Archetype` | derived from above by transitivity |
| `SubSeason` | `BaseColors` (individual) | architect prompt — palette is canonical |
| `formality_hint`+`occasion` | `style_goal` | architect prompt: occasion is hard, style_goal is soft |
| `style_goal` | `risk_tolerance` | architect prompt L440-446 |
| `formality_hint`+`occasion` | `risk_tolerance` | hard-source-wins-over-soft (§3.3) — risk_tolerance is soft, formality+occasion is hard. Earlier draft of this spec had this row reversed; fixed in the §4.2 matrix. |

### 4.2 Derived by hard > soft, plus body > color > archetype rule

Below is the full 28-pair matrix. **🎨 STYLIST SIGN-OFF NEEDED** — these are derived rather than direct quotes; review pass should validate before engine ships.

```
Sources (rows = higher precedence, cols = lower):

                  body  frame palet occas  form  weath  arche  risk  style time
body_shape         —     >    ⊥     ⊥      ⊥     ⊥      >     >     >     >
frame_structure    <     —    ⊥     ⊥      ⊥     ⊥      >     >     >     >
seasonal_palette   ⊥     ⊥    —     ⊥      ⊥     ⊥      >     >     >     >
occasion_signal    ⊥     ⊥    ⊥     —      =     >      >     >     >     >
formality_hint     ⊥     ⊥    ⊥     =      —     >      >     >     >     >
weather_context    ⊥     ⊥    ⊥     <      <     —      >     >     >     >
archetype          <     <    <     <      <     <      —     =     <     >
risk_tolerance     <     <    <     <      <     <      =     —     <     =
style_goal         <     <    <     <      <     <      >     >     —     >
time_of_day        <     <    <     <      <     <      <     =     <     —
```

Legend:
- `>` row wins over column on conflict
- `<` column wins (mirror of upper triangle)
- `=` peers — neither wins; engine emits both as flatters and a "needs_disambiguation" signal for the LLM fallback to resolve
- `⊥` orthogonal — these sources operate on disjoint attribute namespaces (e.g., body_shape never opines on color saturation), so conflicts are impossible by construction

### 4.3 Resolution algorithm

1. Compute `flatters_set(attr)` per §3.1.
2. If empty, apply §3.2 relaxation in this order:
   a. Drop softs by ascending precedence: time_of_day, then archetype/risk_tolerance/style_goal (each separately), then weather color guidance.
   b. If still empty, widen by hard-source precedence reverse: relax frame_structure first, then body_shape, etc.
3. Return final set + provenance trail (which sources contributed, which were dropped).

Provenance is logged so downstream stylist review (4.2) can audit decisions.

## 5. Weighted preferences within `flatters` lists

YAMLs currently have flat lists: `FabricDrape: [fluid, soft_structured]`. No declared preference between fluid and soft_structured.

**Decision:** treat as ordered. **Position 0 is the strongest "flatters" signal**, later entries are weaker preferences. This is consistent with how stylists naturally write the lists (best-first).

When the engine needs to pick a single value (e.g., for a query_document that says "fluid blouse" rather than enumerating options), it picks position 0 of the intersected set. When position 0 is unavailable due to avoid-removal, it falls through to position 1, and so on.

**🎨 STYLIST SIGN-OFF NEEDED**: confirm position-0-is-strongest is the right reading of the existing YAMLs, OR add explicit weights as `flatters: {fluid: 0.9, soft_structured: 0.6}` if review prefers explicit weighting. Engine implementation supports both shapes via the schema change in 4.3.

## 6. Worked examples

### 6.1 Daily-office, feminine, Hourglass + Light-and-Narrow + Soft Autumn + Modern Professional

**Inputs:**
- gender=feminine, body_shape=Hourglass, frame_structure=Light and Narrow, seasonal=Soft Autumn, archetype=modern_professional, risk_tolerance=balanced, occasion=daily_office_mnc, formality=smart_casual, weather=warm_dry, time=daytime

**Per-attribute reduction (FabricDrape):**

| Source | flatters | avoid |
|---|---|---|
| body_shape (Hourglass) | [fluid, soft_structured] | [rigid, oversized] |
| frame_structure (Light/Narrow) | [fluid, soft_structured, lightweight] | [heavy, sculpted] |
| archetype (modern_professional) | [structured, soft_structured] | [draped, distressed] |
| occasion (daily_office_mnc) | (no FabricDrape opinion — orthogonal) | — |

```
flatters_set = {fluid, soft_structured} ∩ {fluid, soft_structured, lightweight} ∩ {structured, soft_structured}
             = {soft_structured}
avoid_set    = {rigid, oversized} ∪ {heavy, sculpted} ∪ {draped, distressed}
             = {rigid, oversized, heavy, sculpted, draped, distressed}
final        = {soft_structured} \ {avoid} = {soft_structured}  ✓ singleton
```

Engine picks `soft_structured` for FabricDrape in the rendered query.

### 6.2 Empty intersection, soft-relax saves it

Same user, same occasion, but archetype=glamorous (clashes with modern_professional defaults).

**Per-attribute reduction (EmbellishmentLevel):**

| Source | flatters | avoid |
|---|---|---|
| occasion (daily_office_mnc) | [minimal, subtle] | [maximalist] |
| archetype (glamorous) | [moderate, statement] | [minimal] |

```
flatters_set = {minimal, subtle} ∩ {moderate, statement} = ∅
```

§3.2 step 1: drop softs. archetype is soft (per §3.3 table), occasion is hard. Drop archetype:

```
flatters_set = {minimal, subtle}  ✓
```

Engine emits EmbellishmentLevel: minimal (position 0). Provenance logs `dropped_source=archetype` for stylist audit — does the user really want a "glamorous office" outfit reduced to "minimal embellishment"? The composer's `style_goal` text gets the original archetype intent passed through the query_document so the retrieval can still surface lightly-embellished options if the catalog has them.

### 6.3 Hard-source widening

Same user, hypothetical archetype=ultra-conservative + body_shape=Inverted Triangle + occasion=cocktail_event.

**Per-attribute reduction (NecklineType):**

| Source | flatters | avoid |
|---|---|---|
| body_shape (Inverted Triangle) | [v_neck, scoop, soft_v] | [boat, off_shoulder, square] |
| archetype (ultra-conservative) | [crew, mock, high] | [v_neck, scoop, deep_v] |
| occasion (cocktail_event) | [v_neck, scoop, halter] | [crew, mock, high] |

```
flatters_set = {v_neck, scoop, soft_v} ∩ {crew, mock, high} ∩ {v_neck, scoop, halter} = ∅
```

§3.2 step 1: drop softs. archetype is soft → drop:

```
flatters_set = {v_neck, scoop, soft_v} ∩ {v_neck, scoop, halter} = {v_neck, scoop}
avoid_set    = {boat, off_shoulder, square} ∪ {crew, mock, high} ∪ {} = ...
final        = {v_neck, scoop}  ✓
```

Resolved without needing widening. archetype's preference for high necklines was incompatible with both body and occasion — engine correctly drops it and surfaces a flag.

### 6.4 Full failure → LLM fallback

Construct a pathological case: hyper-restrictive style_goal contradicting hard sources on multiple attributes simultaneously. After step 1 (drop all softs) and step 2 (widen hards), the final set is still empty for ≥3 attributes.

**Decision:** engine returns `low_confidence: true` and a partial direction. The hot-path router (4.9) consults `low_confidence` and falls through to the LLM architect for the full plan. Cache layer (Phase 2) writes the LLM result on miss.

## 7. Engine API

```python
# modules/agentic_application/src/agentic_application/composition/engine.py

@dataclass
class CompositionResult:
    direction: Optional[DirectionSpec]   # None on full failure
    confidence: float                    # 0.0 (full LLM fallback) → 1.0 (clean compose)
    needs_disambiguation: bool           # True when at least one peer-pair conflict
                                         # surfaced during composition (§4.2 = entries).
                                         # Hot-path router treats this as a fall-through
                                         # signal even if confidence ≥ threshold.
    provenance: List[ProvenanceEntry]    # per-attribute trail for ops audit
    fallback_reason: Optional[str]       # why we returned low_confidence


def compose_direction(
    *,
    user: UserContext,
    live: LiveContext,
    direction_id: str,           # A / B / C
    occasion_yaml: dict,
    archetype_yaml: dict,
    body_frame_yaml: dict,
    palette_yaml: dict,
    weather_yaml: dict,
    pairing_rules_yaml: dict,
    query_structure_yaml: dict,
) -> CompositionResult:
    """Reduce the 8 YAMLs to one DirectionSpec.

    Pure function — no I/O, no clock, no randomness. Determinism is
    the entire value proposition. Same inputs → same output.
    """
```

The hot-path router (4.9) calls `compose_direction` 1-3 times (per direction the architect would have emitted) and assembles them into a `RecommendationPlan`. On any direction returning `confidence < threshold`, the entire plan falls through to LLM.

## 8. Confidence scoring

Confidence per direction is computed from:

```
confidence = 1.0
           - 0.10 * count(soft_sources_dropped)
           - 0.20 * count(hard_sources_widened)
           - 0.30 * count(attributes_omitted)
           - 0.45 * (any genuine YAML gap)
clamped to [0.0, 1.0]
```

Threshold for engine acceptance: **confidence ≥ 0.50** (current runtime value; spec originally specified 0.60 — see calibration note below). YAML gaps always trigger fallback regardless of threshold via the explicit `has_yaml_gap` branch in `compose_direction()` — they're a genuine "engine doesn't know" signal handled outside the formula.

**Calibration note (May 2026):** the runtime threshold was lowered from the spec's original 0.60 to 0.50 because (a) downstream composer + rater rerank by score, so an engine plan that's "merely passable" still surfaces good outfits, and (b) at 0.60 the engine almost always falls through on real Indian inputs (4-5 of ~35 attributes typically need relaxation, accumulating penalties below the threshold). The 0.45 YAML-gap penalty + the formula coefficients themselves are still calibration guesses to be tightened against eval-set ground truth (Phase 4.6).

**🎨 STYLIST SIGN-OFF NEEDED** on the final threshold value once eval data lands.

## 9. Fall-through criteria summary

The hot-path router falls through to the LLM architect when ANY of:

1. Engine returns `confidence < 0.50` (current runtime threshold; see §8 calibration note)
2. Engine returns no `DirectionSpec` (full failure)
3. Genuine YAML gap (input value not in any YAML — e.g., a new occasion not yet added)
4. Provenance shows ≥2 hard-source widenings on a single attribute (semantic drift risk)
5. Engine emits `needs_disambiguation` (§7) — peer-pair conflict the engine can't resolve

Plus the router's pre-engine eligibility gates: anchor-garment turns, follow-up turns, and `previous_recommendations`-bearing turns all skip the engine and go straight to the LLM. The engine doesn't yet handle those flows.

Every fall-through is logged with the input that didn't compose, feeding the YAML expansion backlog (4.2 stylist review pass after each rollout step).

## 10. Out of scope (Phase 4)

- **Composer engine** — Phase 5 ships the equivalent for the composer.
- **Run-time YAML reload** — engine reads YAMLs at process start. Editing a YAML and restarting is the deploy path; hot-reload is unnecessary complexity for now.
- **Multi-tenant YAMLs** — the per-tenant YAML overlay system arrives with Shopify multi-tenancy. For now all tenants share the canonical 8 YAMLs.
- **Confidence calibration via real traffic** — initial threshold 0.60 is a guess; calibrate after 4.6 eval-set ground truth lands.

---

## Open questions for stylist review (4.2 input)

1. weather's split treatment — hard for fabric, soft for color (§3.3). Does this match real stylist intuition?
2. Position-0-is-strongest reading of `flatters` lists vs explicit weight notation (§5).
3. The 28-pair precedence matrix (§4.2) — every pair not directly quoted from the architect prompt needs validation.
4. Confidence threshold 0.60 (§8) — too lenient? too strict?
5. Empty-intersection relaxation order — drop softs first, then widen hards. Reverse order ever appropriate?

---

## Revision history

**May 14 2026 (v1)** — initial spec, scoped to architect engine. Composer engine spec follows when Phase 5 starts.
