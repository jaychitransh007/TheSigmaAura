# Composer Engine — Semantic Spec

**Status:** v1 spec, 2026-05-07. **Implementation SHIPPED behind flag** (Phase 5, PRs #158–#163, May 2026). Engine code lives in `modules/agentic_application/src/agentic_application/composition/` (composer module); router gate in `composer_router.py`. Behind `AURA_COMPOSER_ENGINE_ENABLED` env flag (default false). Flag-on validation gated on Phase 4.6 eval-set curation + Phase 4.2 paid-stylist YAML review (both blocked on human work). Sections marked **🎨 STYLIST SIGN-OFF NEEDED** below indicate semantics that will be confirmed by 4.2.

This spec defines how the composer engine consumes the architect's `RecommendationPlan` plus the retrieved garment pools and emits up to 6 `ComposedOutfit`s by scoring slot tuples against `pairing_rules.yaml`. Goal: replace `OutfitComposer.compose()` (gpt-5.2, ~12-14s, $0.036/turn) with deterministic tuple scoring (~300ms p95) on the common path, falling back to the LLM only on low confidence, sparse pools, or pre-engine eligibility misses.

The composer engine is **relational** where the architect engine was per-attribute: it operates on slot-pair compatibility (formality matrix, color harmony, pattern mixing matrix, etc.) rather than reducing user-attribute → garment-attribute mappings. The architect engine produced *what to look for*; the composer engine picks *which retrieved items go together*.

---

## 1. Inputs

The engine takes the architect's `RecommendationPlan`, the retrieved item pools per direction-and-role, and the same `CombinedContext` the LLM composer consumes:

| Input | Source | Cardinality |
|---|---|---|
| `directions` | `plan.directions` (1-3) | each carries `direction_id`, `direction_type`, `queries` per role |
| `retrieved_sets` | per-direction-per-role `RetrievedSet` | up to 5 items per role typically |
| `combined_context` | architect's `CombinedContext` | full user + live context |
| `style_graph` | parsed YAMLs from process start | shared with architect engine |
| `formality_hint` | `combined_context.formality_hint` | casual \| smart_casual \| semi_formal \| formal \| ceremonial |
| `occasion_signal` | `combined_context.occasion_signal` | ~45 from `occasion.yaml` |
| `intent` | `combined_context.intent` | recommendation_request \| pairing_request (anchor turns deferred — see §11) |

Every input is read; nothing is mutated. Engine determinism is purely input → output.

## 2. Output

Same shape as the existing `ComposerResult` in `agentic_application/schemas.py` so the rater contract is unchanged:

```python
ComposerResult(
    outfits: List[ComposedOutfit],     # up to 6 outfits, hard-capped (matches LLM's "up to 10" but composer engine targets 6 — see §7.4)
    overall_assessment: str,           # strong | moderate | weak | unsuitable
    pool_unsuitable: bool,             # True when no direction has ≥1 valid tuple
    raw_response: str,                 # JSON-rendered engine state for audit
    usage: Dict[str, int],             # {"input_tokens": 0, "output_tokens": 0} — engine has no LLM tokens
    attempt_count: int = 1,            # engine never retries; always 1
)
```

Each `ComposedOutfit` carries the existing fields (`composer_id`, `direction_id`, `direction_type`, `item_ids`, `rationale`, `name`). Engine generates `composer_id` as `E1`, `E2`, ... (rather than `C1`, `C2`, ...) so ops can distinguish engine-emitted from LLM-emitted outfits in `tool_traces.composer_decision` and `model_call_logs`. `rationale` summarizes the deterministic rule decisions ("formality smart_casual ✓, color analogous warm ✓, single statement at top ✓"). `name` is generated from a deterministic title template per direction-type — see §7.5.

## 3. Composition algorithm

### 3.1 Tuple enumeration

Per direction, the engine enumerates candidate tuples by Cartesian product across roles:

- `direction_type=complete` → 1-slot tuple per item (a complete outfit like a saree-set or jumpsuit)
- `direction_type=paired` → 2-slot tuple: (top, bottom)
- `direction_type=three_piece` → 3-slot tuple: (top, bottom, outerwear)

Cap: enumerate at most `MAX_POOL_PER_ROLE = 5` items per role (matches today's typical retrieval). Worst case for `three_piece` direction: 5×5×5 = 125 tuples; with 3 directions, 375 tuples. Each tuple costs O(|categories|) hashmap lookups — comfortably inside the 300ms budget. If retrieval pools grow past 5/role in future, switch to greedy beam search over top-3/role with backtracking on hard-rule violation (Phase 5 follow-up).

### 3.2 Per-tuple scoring

```
score(tuple) = 1.0
             - 0.10 * count(soft_violations)         # silhouette_balance, fabric_compatibility, cultural_coherence
             - drop_if_any(hard_violation)            # formality_alignment, color_story, pattern_mixing, scale_balance, bridal_specific
```

A tuple is **dropped** the moment any hard rule reports a violation. Soft rules accumulate as score penalties; the soft-penalty floor is bounded by the number of soft rules (no clamping — extremely soft-violating tuples can score below 0 and rank last but aren't dropped on softs alone).

The 9 categories in `pairing_rules.yaml` and their type:

| Category | Type | Drop on violation? |
|---|---|---|
| formality_alignment | hard | yes |
| color_story | hard | yes |
| pattern_mixing | hard | yes |
| scale_balance | hard | yes (with bridal exception — §6) |
| silhouette_balance | soft | no, -0.10 per violation |
| fabric_compatibility | soft | no, -0.10 per violation |
| cultural_coherence | soft | no, -0.10 per violation |
| bridal_specific | hard | yes (only applies in bridal contexts) |
| anchor_constraints | hard | gate, not engine — anchor turns fall through pre-engine (§11) |

**No precedence ordering among hard categories is needed.** A tuple violating *any* hard rule is dropped regardless of which rule. (Architect needed precedence because conflicts had to be *resolved*; composer just drops and moves on.) When *every* tuple in a direction violates some hard rule, the engine emits a low-confidence signal (§8) and the router falls through to the LLM.

### 3.3 Top-K with diversity penalty

Surviving tuples are ranked by score, then a multiplicative diversity penalty is applied during selection (not scoring) to prevent near-duplicate outfits:

```
diversity_multiplier(candidate, already_picked) =
    × 0.6  if same direction_id as any already-picked outfit
    × 0.7  if dominant color_story matches any already-picked
    × 0.8  if statement-piece slot matches any already-picked
    × 1.0  otherwise
effective_score = base_score * diversity_multiplier
```

**Multipliers stack.** A candidate that triggers multiple penalties pays the product, not the smallest. So a tuple that's same direction AND same dominant color as an already-picked outfit gets `0.6 × 0.7 = 0.42` (below `MIN_OUTFIT_SCORE` 0.50 → not picked). The implementation computes a per-already-picked multiplier and takes the worst across already-picked outfits, so the candidate is constrained by its closest neighbor in the picked set — not by an aggregate similarity.

Greedy selection: pick the highest `effective_score` tuple, append to picks, recompute multipliers for the rest, repeat. Stop when 6 picks are made or no candidate has `effective_score >= MIN_OUTFIT_SCORE` (default 0.5). Direction coverage is encouraged by the 0.6 same-direction multiplier but not strictly enforced; if Direction A produced the cleanest tuples, picking 4 from A and 2 from B is preferable to forcing one weak C.

**🎨 STYLIST SIGN-OFF NEEDED** on the three diversity multipliers (0.6 / 0.7 / 0.8) and the `MIN_OUTFIT_SCORE` floor — these are calibration guesses to be tightened against the Phase 4.6 eval set.

### 3.4 Sparse-pool detection

Before enumeration, the engine checks each direction for pool sufficiency:

- `direction_type=complete` → pool size ≥ 2
- `direction_type=paired` → both `top` and `bottom` pools have ≥ 2 items
- `direction_type=three_piece` → all three role pools have ≥ 2 items

If any direction fails, that direction is skipped. If *all* directions fail, the engine returns `confidence=0.0, fallback_reason="pool_too_sparse"` and the router falls through.

## 4. Per-category rule application

Rule descriptions below are summary form; the YAML at `knowledge/style_graph/pairing_rules.yaml` is the authoritative source.

### 4.1 formality_alignment (hard)

For each ordered pair of slots in the tuple, check `compatibility_matrix[slot_a.formality][slot_b.formality]` includes `slot_b.formality`. (Matrix is symmetric; one direction suffices.) Bridal lehenga as an item of any slot rents the formality of every other slot to `ceremonial` regardless of declared formality (the YAML's notes call this out explicitly).

### 4.2 color_story (hard, with metallic_neutral_exception)

Three sub-rules:

- **`max_dominant_colors=3`.** Aggregate `DominantColor` across all slots; if distinct count > 3, violate. Patterned slots count their primary `DominantColor` only. **`metallic_neutral_exception`** (PR #251, 2026-05-11): items with `dominant_color` in the metallic-neutral set (gold / rose_gold / antique_gold / champagne / silver / oxidized_silver / bronze / copper / brass / pewter + metallic_* variants — hardcoded in `pairing.py:_METALLIC_NEUTRAL_COLORS`) OR `fabric_texture == "metallic"` are **excluded from the count**. They function as neutral support colors, not competing dominant hues. Critical for Indian festive outfits where zari / metallic dupatta would otherwise blow the cap. When the exception fires, `aura_composer_rule_exception_applied_total{rule="max_dominant_colors", exception="metallic_neutral_exception"}` ticks and the violation detail string surfaces `(excluded N metallic-neutral)`.
- **`palette_anchor_required`.** At least one slot's `DominantColor` must be in the user's `SubSeason.PaletteAnchors` (from `palette.yaml`). Pure-neutral outfits where every slot is `cream`/`navy`/`charcoal` satisfy this iff the user's palette includes the corresponding neutral.
- **`contrast_alignment`.** For each ordered pair of slots, check `compatibility_matrix[a.contrast][b.contrast]` includes `b.contrast`. Mid-contrast pairings always allowed; high-with-low pairings forbidden.

**Color harmony classification.** The five harmony types (`monochromatic`, `analogous`, `complementary`, `tonal`, `neutral_plus_anchor`) are *descriptive*, not prescriptive — a tuple isn't required to belong to a named harmony. The classification is computed once per accepted tuple for the rationale string and the diversity penalty's "dominant color_story" heuristic.

### 4.3 pattern_mixing (hard)

Sub-rules apply by pattern count across the tuple:

- **0-1 patterned slots:** `solid_plus_pattern` always passes.
- **Exactly 2 patterned slots:** check `two_patterns.compatibility_matrix[a.scale][b.scale]` includes `b.scale`. Forbidden pairs (per the YAML matrix as written): `medium+medium`, `large+large`, `large+oversized`, `large+mixed`, `oversized+medium`, `oversized+large`, `oversized+oversized`, `oversized+mixed`, `mixed+large`, `mixed+oversized`, `mixed+mixed`. Plus a same-color-family OR same-`ContrastLevel` requirement: at least one of the two must hold.
- **3+ patterned slots:** always violate.

`pattern_scale_with_body_frame` is a **soft-recommendation** rule that lives in `pairing_rules.yaml` for documentation but is **not enforced by the composer engine** — body-frame guidance was already baked into the architect's per-direction queries (Phase 4.7 reduction), so re-applying it here would double-count. Note in YAML.

### 4.4 scale_balance (hard, with bridal exception + distributed_statement_exception)

Apply `is_statement(item)` (§5) per slot. Count statement slots in the tuple.

- **0 or 1 statement slots:** pass.
- **2+ statement slots:** violate, **unless** bridal exception applies (§6) **OR** `distributed_statement_exception` applies (below).

**`distributed_statement_exception`** (PR #248, 2026-05-11) — multiple moderate-emphasis zones are acceptable when they read as a coordinated visual register rather than competing focal points (typical contemporary Indianwear: blouse + dupatta border + jewellery all coordinated). Eligibility (`_is_distributed_statement_exception_eligible`):

1. Every item has a known `color_temperature` AND all match (single family: warm-only, cool-only, or neutral-only).
2. No item has `embellishment_level` in `{heavy, statement}` — individual zones stay at moderate density at most.

When eligible, the violation is suspended AND `aura_composer_rule_exception_applied_total{rule="one_statement_per_outfit", exception="distributed_statement_exception"}` ticks once for observability.

`jewellery_doesnt_count` is moot for the engine because retrieval pools never include jewellery — the composer's input is garment slots only. Document this in YAML notes.

### 4.5 silhouette_balance (soft)

Three sub-rules:

- **`no_all_fitted`.** If every slot's `FitType` ∈ {slim, tailored}, -0.10. Exception: `body_shape == Hourglass` — no penalty.
- **`no_all_relaxed`.** If every slot's `FitType` ∈ {boxy, loose, relaxed}, -0.10. Exception: `body_shape ∈ {Apple, Diamond}` — no penalty.
- **`structured_outerwear_anchor`.** If outerwear slot present AND `outerwear.FabricDrape == fluid`, -0.10. (Casual contexts where fluid outerwear is intentional get the penalty but rarely fail to be picked, since other tuples are often weaker.)

`fitted_relaxed_pair` is the *positive* case; not a separate violation, just the absence of `no_all_fitted` and `no_all_relaxed`.

### 4.6 fabric_compatibility (soft)

Three sub-rules, each potentially -0.10:

- **`texture_mixing`.** For each ordered pair of slots, check `compatibility_matrix[a.texture][b.texture]` includes `b.texture`. Per-pair violation accumulates (a 3-slot outfit has 3 ordered pairs; up to -0.30).
- **`weight_pairing`.** For each ordered pair, `compatibility_matrix[a.weight][b.weight]` membership.
- **`drape_compatibility`.** Pure documentation in the YAML — `flatters` lists every drape value, `avoid` is empty. No engine-enforced violation.
- **`sheen_hierarchy`** (PR #250, 2026-05-11). Outside the bridal exception, count items with `fabric_texture ∈ {sheen, metallic, embroidered}` (canonical "sheen-bearing surfaces"). When `count > rule.value` (default `1`), -0.10. Bridal contexts (`bridal_exception_active`) bypass — multi-sheen Indianwear at ceremonial weddings is the cultural norm. Hardcoded set lives in `pairing.py:_SHEEN_TEXTURES` and must stay in sync with `garment_attributes.json`'s `FabricTexture` enum.

### 4.7 cultural_coherence (soft)

Classify each slot's `CulturalRegister ∈ {indian_traditional, indo_western, western}` from enrichment. Then:

- All slots same register → pass.
- Mix of `indian_traditional` and `western` (no `indo_western` bridge) → -0.10 (`indo_western_fusion` rule allows this only at lower formalities; the soft penalty captures the contextual cost without a hard drop).
- `heavy_traditional_no_western_fusion` → if any slot has `EmbellishmentLevel ∈ {heavy, statement}` AND register is `indian_traditional` AND any other slot is `western` → -0.10. (Could be hard, but the YAML declares the whole `cultural_coherence` category as `soft_constraint`, and stylist judgment varies; keep soft for v1.)

### 4.8 bridal_specific (hard)

Applies in two distinct modes — bridal-exception-active and bridal-role-aware (post-PR #249).

**Mode A — bridal exception active (subtype rules):** when `bridal_exception_active(ctx, graph)` per §6, for each slot, check the relevant pairing rule (`bridal_lehenga_pairing`, `heavy_banarasi_pairing`, `sherwani_pairing`, `bandhgala_versatility`) by garment subtype. Each rule's `flatters`/`avoid` on `OccasionFit` and `FormalityLevel` is enforced as a hard membership check on every slot in the tuple.

**Mode B — `guest_vs_bridal_separation` (PR #249, 2026-05-11):** when `ctx.bridal_role` is set AND not in `{bride, groom}` AND `is_bridal_role_occasion(ctx.occasion_signal)` (per Step 1's `composition/styling_decisions.py:is_bridal_role_occasion`), any item whose `embellishment_level` is in the rule's YAML `avoid: EmbellishmentLevel` block (default `[heavy, statement]`) fires a hard `guest_vs_bridal_separation` drop. Bride / groom roles bypass entirely. Guests at non-bridal occasions also bypass.

The matcher reads `ctx.bridal_role` which is plumbed from `user.occasion_role` via the orchestrator. Default empty (`""`) → the matcher is a no-op, which is the safe production state for upstream callers that haven't been updated to populate the field. Persisted in `_summarize_provenance.bridal_role` (or `"unset"`) for Panel 26 RCA.

When the bridal exception is *not* active AND `bridal_role` is unset, this category is a no-op.

### 4.9 anchor_constraints (hard, gate-only)

Anchor turns are declined at the pre-engine eligibility gate (§11) for the initial Phase 5 ship. The composer engine never sees anchor inputs in v1. The YAML rules stay documented for the eventual anchor-handling follow-up.

## 5. Statement-piece detection

Hardcoded in `composition/pairing.py:is_statement(item, rules)` to avoid YAML-DSL parsing complexity:

```python
def is_statement(item: Item, rules: PairingRules) -> bool:
    """Statement-piece per scale_balance.statement_definition.

    Source of truth: knowledge/style_graph/pairing_rules.yaml,
    `scale_balance.statement_definition`. When that block changes,
    update this function in the same PR.
    """
    if item.embellishment_level in {"moderate", "heavy", "statement"}:
        return True
    if item.pattern_scale in {"large", "oversized"}:
        return True
    if item.color_saturation == "very_high":
        return True
    if (item.pattern_type in {"animal", "ethnic", "abstract"}
            and item.pattern_scale == "medium"):
        return True
    return False
```

The fourth clause only adds `medium` scale because `large` and `oversized` are already handled by the second clause — `pattern_type ∈ {animal, ethnic, abstract}` only adds something on top when the scale is the borderline `medium` value.

The function takes `rules` as a parameter for forward compatibility (in case a future stylist edit shifts the definition into runtime configuration), but v1 ignores it and uses the hardcoded thresholds.

## 6. Bridal exception

The `scale_balance.bridal_exception` and `bridal_specific` rules suspend the one-statement-per-outfit cap and apply bridal-context-only pairing rules. Detector:

```python
def bridal_exception_active(ctx: CombinedContext, rules: PairingRules) -> bool:
    if ctx.formality_hint != "ceremonial":
        return False
    triggers = rules.bridal_specific.triggers_on  # NEW YAML field, added in 5b
    return ctx.occasion_signal in triggers
```

`triggers_on` is added to `pairing_rules.yaml` as part of PR 5b (loader + scorer); proposed initial list (**🎨 STYLIST SIGN-OFF NEEDED**):

```yaml
bridal_specific:
  rule_type: hard_constraint
  triggers_on: [wedding_ceremony, sangeet, mehendi, haldi, reception, engagement]
  rules: ...
```

This keeps bridal occasions stylist-editable without Python changes.

## 7. Engine API

```python
# modules/agentic_application/src/agentic_application/composition/composer_engine.py

@dataclass
class ComposerEngineResult:
    composer_result: Optional[ComposerResult]   # None on full failure
    confidence: float                            # 0.0 (full LLM fallback) → 1.0 (every direction had clean tuples)
    fallback_reason: Optional[str]               # "pool_too_sparse" | "low_confidence" | "yaml_gap" | None
    yaml_gaps: List[str]                         # canonical gaps surfaced (mirrors architect engine)
    provenance: List[ProvenanceEntry]            # per-tuple drop/keep trail for ops audit
    engine_ms: float                             # wall-clock duration


def compose_outfits(
    *,
    plan: RecommendationPlan,
    retrieved_sets: List[RetrievedSet],
    ctx: CombinedContext,
    graph: StyleGraph,
) -> ComposerEngineResult:
    """Reduce architect plan + retrieved pools to a ComposerResult.

    Pure function — no I/O, no clock (engine_ms is computed externally
    by the router and passed in via a wrapper), no randomness. Same
    inputs → same output, byte-identical.
    """
```

### 7.1 Confidence scoring

```
confidence = 1.0
           - 0.20 * (count(directions_skipped_for_sparse_pool) / total_directions)
           - 0.30 * (1 - count(directions_with_picks) / total_directions)
           - 0.10 * (max(0, 6 - count(picks)) / 6)        # short of 6-outfit target
           - 0.45 * (1 if any_yaml_gap else 0)
clamped to [0.0, 1.0]
```

Threshold for engine acceptance: **confidence ≥ 0.50** (mirrors architect's runtime threshold; rationale identical — downstream rater reranks by score, an engine plan that's "merely passable" still surfaces good outfits). YAML gaps contribute to confidence via the `0.45 * any_yaml_gap` term and fall through only when that penalty (combined with any others) drops confidence below threshold — there is no separate hard-veto branch (EAR-3, May 9 2026 RCA: aligns composer with architect's "score then decide" rule; previously a single gap on any axis triggered fallback regardless of how strong the picks were).

### 7.2 Fall-through criteria summary

The composer router falls through to the LLM `OutfitComposer` when ANY of:

1. Engine returns `confidence < 0.50` (yaml_gap-triggered: surfaced as `fallback_reason="yaml_gap"`; otherwise `"low_confidence"`)
2. Engine returns `composer_result is None` (full failure)
3. Engine returns fewer than 3 picks across all directions (`pool_too_sparse` or aggregate hard-violation rate too high)

Plus the pre-engine eligibility gates (§10): anchor-bearing turns, follow-up turns, and turns with `previous_recommendations` all skip the engine. **Cache-served architect plans do NOT skip the composer engine** — the architect cache stores `RecommendationPlan` objects, which are valid composer inputs regardless of how they were produced. Skipping the composer engine on architect cache hits would force the slow LLM composer on every cache-served turn and defeat the latency win.

### 7.3 What the engine does NOT do

- **Does not retrieve.** Pools come from the architect-driven retrieval stage, unchanged.
- **Does not score by aesthetic merit.** Score is mechanical-rule-based; the rater (next stage, unchanged) applies aesthetic judgment.
- **Does not invoke any LLM.** Engine output is keyword-only; rationales are templated.
- **Does not write to the composer cache during flag-on testing** (mirror of architect path — cache key is profile/cluster-scoped, not user-scoped, so cached engine plans would persist across flag-on/flag-off and leak the engine path into control traffic). LLM plans cache normally.

### 7.4 Hard cap of 6 outfits

The LLM composer's prompt says "up to 10" but production typically emits 6-8. The engine targets 6 as the hard cap because:

- The rater's R7 rubric was calibrated against 6-outfit ComposerResults (typical T13 size).
- More than 6 saturates the user's UI without adding selection value.
- Diversity penalty starts to flatten beyond 6 picks anyway.

PR 5f bundles `maxItems: 10` on the existing LLM composer's JSON schema (the long-queued task) to keep the LLM-fallback path consistent with the engine's bound.

### 7.5 Outfit name generation

Engine generates `name` deterministically from the dominant color_story + a direction-type modifier:

- `complete` → `"{dominant_color_word} {direction_label_short}"` e.g. `"Soft Cream Daywear"`
- `paired` → `"{contrast_descriptor} {dominant_color_word} Pair"` e.g. `"Sharp Navy Pair"`
- `three_piece` → `"{outerwear_descriptor} {dominant_color_word} Layered"` e.g. `"Bandhgala Charcoal Layered"`

Templates live in `composition/composer_engine.py`. Stylist polish of the templates is deferred to a follow-up PR — the v1 names are functional-but-bland, and the LLM-fallback path (which produces stylist-flavored names today) handles the visible-to-user case until then.

## 8. Diversity penalty calibration

The 0.6 / 0.7 / 0.8 multipliers (§3.3) are picked so that:

- A second tuple from the same direction needs to score ~67% better than a first tuple from a fresh direction to win.
- Same-color-story candidates need to score ~43% better.
- Same-statement-slot candidates need to score ~25% better.

Order of penalty severity reflects expected user perception of redundancy: same-direction outfits feel most repetitive, color-story repetition is noticeable, statement-slot match is subtle. **🎨 STYLIST SIGN-OFF NEEDED** on this ordering and the magnitudes once eval-set ground truth lands.

## 9. Worked examples

### 9.1 Daily-office paired tuple, clean win

**Inputs:**
- 1 direction (Direction A, `paired`), pools: top=[T1..T5], bottom=[B1..B5]
- Tuple (T1=`structured navy blouse, formality=smart_casual, color=navy, pattern=solid, fabric_drape=crisp`, B1=`tailored cream trouser, formality=smart_casual, color=cream, pattern=solid, fabric_drape=structured`)

**Hard checks:**
- formality_alignment: smart_casual + smart_casual ✓ (matrix membership)
- color_story: 2 dominants {navy, cream} ≤ 3 ✓; navy is in user's SubSeason anchors ✓; contrast medium+medium ✓
- pattern_mixing: 0 patterned slots → solid_plus_pattern ✓
- scale_balance: 0 statement slots ✓

**Soft checks:**
- silhouette_balance: tailored+tailored = `no_all_fitted` violation, but `body_shape=Hourglass` exempts → no penalty
- fabric_compatibility: crisp+structured weight & texture both compatible ✓
- cultural_coherence: both western → ✓

**Score:** 1.00. Bridal exception inactive. Tuple kept; first pick. Diversity multipliers don't apply yet. Engine outputs this as outfit E1.

### 9.2 Two-pattern violation, dropped

**Inputs:** Direction B `paired`, tuple (T2=`large-floral kurti, pattern_scale=large`, B2=`large-check palazzo, pattern_scale=large`).

**Hard checks:**
- pattern_mixing: 2 patterned slots; `compatibility_matrix[large][large]` does not include `large` → **violate**, drop tuple.

Engine moves to next candidate. If no tuple in Direction B survives all hard checks, that direction contributes 0 picks and the confidence score takes a -0.30/total_directions penalty per §7.1.

### 9.3 Bridal exception saves a tuple that would otherwise violate scale_balance

**Inputs:** ceremonial wedding ceremony, tuple (T3=`heavy zardozi choli, statement`, B3=`bridal lehenga, statement`, OW=`heavy embroidered dupatta, statement`).

**Hard checks:**
- formality_alignment: ceremonial+ceremonial+ceremonial ✓
- color_story: presume 2 dominants ✓
- pattern_mixing: depends on items; presume ✓
- scale_balance: 3 statement slots → would violate, **but** `bridal_exception_active(ctx, rules) == True` because `formality_hint=ceremonial AND occasion_signal=wedding_ceremony in triggers_on` → exception applies, no violation.
- bridal_specific: bridal_lehenga_pairing rule applies — choli must be bridal-weight (statement ✓), dupatta must be lighter weight (NOT in this tuple — embroidered dupatta is statement). Whether this is a violation depends on enrichment of the dupatta's `EmbellishmentLevel`; if it's `statement` not just `heavy`, it's still acceptable per the YAML's "matching embellishment level" guidance. Conservative read: pass.

**Soft checks:** assume all clean.

**Score:** 1.00. Outfit kept.

### 9.4 Pool too sparse → fall through

**Inputs:** 1 direction, `three_piece` direction_type, pools: top=[T1, T2], bottom=[B1, B2], outerwear=[OW1] (only 1 item).

**Pre-enumeration check:** outerwear pool has <2 items → direction skipped. Total directions=1, skipped=1, picks=0 → `confidence = 1.0 − 0.20·(1/1) − 0.30·(1 − 0/1) − 0.10·(6/6) = 1.0 − 0.20 − 0.30 − 0.10 = 0.40`. Below 0.50 threshold → `fallback_reason="pool_too_sparse"`, router falls through to LLM composer. (LLM composer has historically tolerated single-item outerwear pools by emitting paired outfits and skipping the third slot, so the LLM path handles this case differently.)

## 10. Pre-engine eligibility gates

Before the engine is even invoked, the router checks these gates. Any TRUE → fall through to LLM:

| Gate | Source | Why fall through |
|---|---|---|
| `anchor_present` | `combined_context.anchor_garment is not None` | Engine doesn't handle anchor turns in v1 (see §4.9). |
| `followup_request` | `combined_context.intent_classification.is_followup` | Follow-up turns reference prior outfits; engine has no episodic context. |
| `has_previous_recommendations` | `combined_context.previous_recommendations` non-empty | Same as above — engine doesn't reason about prior turns. |

**No `architect_plan_from_cache` gate.** Earlier drafts of this spec proposed skipping the engine when the architect plan came from cache; that was a copy-paste error from the architect router. The composer engine consumes a `RecommendationPlan` regardless of whether the LLM, the architect engine, or the architect cache produced it — they're all valid inputs of the same shape. Skipping the composer engine on architect-cache turns would force the slow LLM composer to run on every cache-served turn, eliminating the latency win we paid for.

Mirrors the architect router's pre-engine gates exactly.

## 11. Out of scope (Phase 5 v1)

- **Anchor turns.** `pairing_request` intent with a user-provided anchor garment. Architect router defers; composer router defers similarly. Future PR adds anchor-driven scoring per §4.9.
- **Per-direction routing.** All-or-nothing per turn (§Locked-decisions in OPEN_TASKS.md). Per-direction routing (engine handles A and B, LLM handles C) is a future possibility if telemetry shows bimodal confidence.
- **Run-time YAML reload.** Same as architect — YAMLs load at process start; redeploy to refresh.
- **Stylist-flavored outfit names.** v1 generates functional-but-bland names; LLM-fallback handles this in user-visible cases. Follow-up PR upgrades engine name generation.
- **Composer cache writes from engine path.** During flag-on testing, engine plans don't write to the composer cache (mirror of architect path — same rationale).
- **Confidence-formula calibration.** Coefficients in §7.1 are picked to match architect's calibration shape; tighten against Phase 4.6 eval-set ground truth in a post-rollout PR.

## 12. Open questions for stylist review (4.2 input)

1. **Diversity multipliers (0.6/0.7/0.8 in §3.3).** Are these the right severity ordering? Should same-color-story be more or less penalized than same-statement-slot?
2. **`MIN_OUTFIT_SCORE = 0.5` floor (§3.3).** Below this, surviving tuples don't get picked. Too lenient or too strict?
3. **`bridal_specific.triggers_on` list (§6).** The proposed list `[wedding_ceremony, sangeet, mehendi, haldi, reception, engagement]` — comprehensive? Missing any?
4. **Cultural coherence soft vs hard (§4.7).** YAML declares `soft_constraint` but the `heavy_traditional_no_western_fusion` rule reads more like a hard prohibition. Promote to hard?
5. **Pattern-scale-with-body-frame (§4.3).** Documenting that the rule lives in `pairing_rules.yaml` but is *not* enforced by the engine because architect already applied body-frame logic. Is this the right decoupling, or should the composer engine also enforce as a soft check (defense in depth)?
6. **Confidence threshold 0.50 (§7.1).** Inherited from architect's calibration. Composer-specific calibration coming with eval-set data.

---

## Revision history

**2026-05-07 (v1)** — initial spec, scoped to composer engine. Locks the six decisions called out in OPEN_TASKS.md Phase 5. Implementation begins with PR 5b (loader + scorer).

**2026-05-11** — Step 4 pairing-matcher additions documented in §4.2, §4.4, §4.6, §4.8:
- §4.2 — `metallic_neutral_exception` (PR #251) now excludes metallic-neutral colors / metallic-textured items from the `max_dominant_colors=3` count.
- §4.4 — `distributed_statement_exception` (PR #248) suspends `one_statement_per_outfit` when items share `color_temperature` family AND none individually exceeds moderate embellishment.
- §4.6 — `sheen_hierarchy` (PR #250) caps sheen-bearing fabric textures at 1 per outfit outside the bridal exception.
- §4.8 — `guest_vs_bridal_separation` (PR #249) drops tuples carrying bridal-participant embellishment levels when the user's `ctx.bridal_role` is `guest` or `attendee` on a bridal-role occasion. New field `bridal_role` on `TupleContext` (default empty).

Each new matcher emits to `aura_composer_rule_violation_total{rule, is_hard}` per Violation; each exception ticks `aura_composer_rule_exception_applied_total{rule, exception}` once when triggered. Both counters added in PR #257.
