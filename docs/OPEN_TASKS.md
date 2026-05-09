# Open Tasks

This file is the running list of known follow-ups: not blocking any release today, but worth tracking so they don't get lost. Each entry is a one-paragraph brief — enough to remember the context, not a full plan.

When a task is picked up, replace the brief with a link to the PR/branch. When it's done, delete the entry (the git history of this file is the audit trail).

For per-PR record of what's already shipped, see `RELEASE_READINESS.md` § Recently Shipped.

The bottom half of this file is the **Sub-3s latency push** — the anchor execution plan we work from. All operations and development going forward thread through that plan.

---

## Catalog vocabulary cleanup — Phase 2 of the May-3 occasion-tag refactor

**Status:** queued · **Cost:** small (~$3 + 1 hour) · **Risk:** low

Phase 1 (May 3, 2026) stopped the architect from emitting `OccasionFit` / `OccasionSignal` / `FormalitySignalStrength` in query documents — the catalog still carries them on every row but they no longer pollute the architect's queries. That gives most of the latency / score-quality win without a catalog re-run.

Phase 2 finishes the cleanup on the catalog side:
1. Drop `OccasionFit`, `OccasionSignal`, `FormalitySignalStrength` from the text that gets fed into `text-embedding-3-small`. The columns can stay in the table for historical compatibility but they stop contributing to the embedding vector.
2. Re-run `ops/scripts/embed_catalog.py` (or equivalent) over the existing 14,296 enriched rows. Vision enrichment is **not** re-run — only the embedding text changes.
3. Verify on a handful of test queries (daily-office, date-night, wedding-engagement) that cosine similarity scores stabilize at or above today's post-Phase-1 baseline.

**Trigger to do this:** if the daily-office / casual-occasion confidence-gate failure rate stays elevated after Phase 1 ships, or if Panel 16 in `OPERATIONS.md` shows >5% `catalog_low_confidence` rate sustained.

**Cost:** ~14,296 items × ~500–2,000 tokens × $0.02/1M ≈ $3–5. Re-embed takes 30–60 minutes depending on rate limits. No vision API calls.

---

## Catalog content gap — masculine top coverage

**Status:** queued · **Cost:** content task (catalog enrichment) · **Risk:** low

Surfaced May 8 2026 during the turn `9abaf4d4` audit. Masculine `catalog_enriched` carries only 8 subtypes:

| subtype | count |
|---|---|
| trouser | 327 |
| blazer | 315 |
| jeans | 274 |
| track_pants | 41 |
| shorts | 34 |
| kurta | 7 |
| co_ord_set | 1 |
| kurta_set | 1 |

There are zero tshirts / polos / sweatshirts / hoodies / shirts in the masculine catalog. So when a male user asks for "loungewear" or "casual day-out" outfits, the architect emits reasonable subtype guesses (tshirt, hoodie) that retrieval can't satisfy — total products = 0 across all queries. PR #192 (empty-retrieval auto-relaxation) routes around the gap by dropping the subtype filter; PRs #186/#187 route around it by binding `OccasionFit ∈ {very_casual, active}` to find the 39 matching items. Both are workarounds — the underlying gap is content.

**Trigger to act:** when the masculine cohort hits production and we see empty-result rates / auto-relax rates for masculine users above some threshold.

**Acceptance:** at least 50 masculine items each across `tshirt`, `polo_tshirt`, `shirt`, `sweatshirt`, `hoodie` subtypes — enough that browse-by-garment and loungewear-style requests have a real catalog to draw from before relaxation kicks in.

**Note:** this is NOT a latency-optimization task even though it surfaced in latency review. It's content / catalog work. Filed here under general catalog hygiene, not under the sub-3s latency push below.

---

## Catalog vocabulary consolidation — rare-value cleanup (Phase 3 follow-up)

**Status:** parked · **Cost:** small · **Risk:** low

Phase 3 (May 3, 2026) consolidated the four near-duplicate values: `pants`→`trouser` (107), `jeggings`→`jeans` (9), `androgynous`→`unisex` (12), `night`→`evening` (8). Architect vocabulary list updated to match.

What's left: the rare values with ≤5 rows each — `poncho` (5), `leggings` (4), `kaftan` (4), `tracksuit` (3), `ethnic_set` (2), `dungarees` (1). Each is a per-row content decision (re-tag to nearest valid subtype, or drop the row entirely from `catalog_item_embeddings`). Not vocabulary cleanup — content cleanup. Defer until a content reviewer can decide row by row.

**Trigger to do this:** if any of the rare subtypes appears in `tool_traces.composer_decision` outputs (i.e., the LLM ranker actually picks one) or surfaces in a user complaint.

---

## Catalog `OccasionFit` column — keep for now

**Status:** decided (May 3, 2026) — **keep populating, do not drop**

`OccasionFit` is no longer read by retrieval (Option A in PR #20 stripped user-side sections from the architect's query_document; the LLM ranker doesn't filter on it either). But `build_catalog_document()` still emits it in the metadata dict and the `occasion_fit` SQL column on `catalog_item_embeddings` is still populated.

**Decision:** keep. Cost of populating is negligible (a single field write per enrichment), and dropping the column would force a migration + a downstream impact audit (response payloads, CSV exports, ops dashboards may all reference `occasion_fit`). The cleaner schema is not worth the churn until we have a concrete second use for the schema slot. Revisit only if there's a load-bearing reason.

---

## Phase out `archetypal_preferences` from the composer

**Status:** queued · **Cost:** small · **Risk:** low

Post-PR-#89 the rater no longer reads `archetypal_preferences` — past likes/dislikes flow upstream through the architect's episodic memory (`recent_user_actions`, PR #90). The composer still reads it as a **soft preference** ("when the user has disliked an attribute at least twice, prefer to avoid it" — see `prompt/outfit_composer.md`). This is the last consumer of the aggregate signal.

Two ways to clean up:
1. **Drop the soft preference from the composer**, fall back entirely on episodic memory at the architect (which biases retrieval queries). Smallest code change; bet is the architect's bias is enough.
2. **Switch the composer to also read `recent_user_actions`** (the raw 30-day timeline, not the aggregate). Symmetric with the architect; lets the composer reason on context-dependent patterns the same way.

**Trigger to act:** if (a) Panel 18 (rater unsuitable rate) holds <5% over a stable post-#101 week — meaning episodic memory at the architect is producing acceptable retrieval + composer item selection without needing the aggregate signal — or (b) the `aggregate_archetypal_feedback` repo method becomes a maintenance burden (it has its own catalog_enriched hydration that overlaps with `list_recent_user_actions`).

---

## Stylist YAML review — aggregated downstream work

**Status:** in progress · **Process:** stylist completes review of all 8 files first; we accumulate downstream work here; batch-execute once all files are received.

**Why batched not incremental:** each stylist file introduces vocabulary the catalog can't yet produce. Re-enriching after every file is expensive (~$300-700 per run × 14,296 rows × ~10-15 hours compute) and disruptive. One batched re-enrichment after all 8 files is reviewed amortises the cost and avoids retagging the same row repeatedly.

**Working agreement (2026-05-09):**
- Stylist reviews each file → posts findings to `knowledge/knowledge_v2/`.
- We pin every source review file there for audit.
- We apply YAML edits that don't depend on schema or catalog changes (notes, vocabulary already in canonical, reordering).
- Items needing new code or new catalog enrichment accumulate in this section, marked by dependency.
- Once all 8 stylist files received: batch-execute the engineering + enrichment in one coordinated effort; then apply pending YAML patches.

### Per-file status

| Stylist file | Source pinned | YAML applied | Pending downstream work |
|---|---|---|---|
| [archetype_yaml_stylist_pass_v_2.md](../knowledge/knowledge_v2/archetype_yaml_stylist_pass_v_2.md) | ✅ | ✅ ([PR #226](https://github.com/jaychitransh007/TheSigmaAura/pull/226)) | New vocabulary not yet in catalog (queued below) |
| [bodyframe_stylist_revision_patchset_v_1.md](../knowledge/knowledge_v2/bodyframe_stylist_revision_patchset_v_1.md) | ✅ | ⏳ HOLD — pending engine extension + catalog re-enrichment | See dependency lists below |
| [updated_occasion_yaml_review_with_stylist_notes.md](../knowledge/knowledge_v2/updated_occasion_yaml_review_with_stylist_notes.md) | ✅ | ⏳ HOLD — pending hard/soft yaml_loader + new attribute axes + bridal-role engine support | See dependency lists below |
| [weather_yaml_review_and_updated_occasion_style_notes.md](../knowledge/knowledge_v2/weather_yaml_review_and_updated_occasion_style_notes.md) | ✅ | ✅ partial — 3 weather edits + 3 occasion edits using existing canonical applied | Schema decomposition (FabricTexture / SurfaceFinish / ConstructionDetail) + 5 new performance attribute axes deferred to batch |
| [palette_yaml_stylist_review_and_style_notes.md](../knowledge/knowledge_v2/palette_yaml_stylist_review_and_style_notes.md) | ✅ | ✅ partial — black-handling cleanup, neutral luxury vocabulary additions, monochrome ColorCount, Deep Winter `stark white` removal, notes refreshes (Clear Spring jewel tones, Clear Winter monochrome, Deep Winter contrast styling) | Metallic decomposition (high_shine vs antique vs brushed) folds into the SurfaceFinish split queued from weather review |
| [updated_query_structure_review_and_style_notes.md](../knowledge/knowledge_v2/updated_query_structure_review_and_style_notes.md) | ✅ | ✅ fully applied — 10 occasion mappings updated to allow modern Indo-Western `complete` retrieval; Navratri gets `cultural_variants` (traditional/fusion); `anchor_complete` now layerable | Future schema metadata (`style_energy`, `mobility_requirement`, `climate_sensitivity`) noted only — not urgent |
| `pairing_rules_*` | — | — | — |

### Catalog enrichment queue (Type A — vision-extractable garment properties)

These are visible from product images. Need: (1) vision-enrichment prompt updated to ask for them, (2) re-run on the 14,296 catalog rows, (3) backfill `catalog_enriched`, (4) regenerate embeddings.

**From `archetype.yaml` (PR #226 — applied to canonical schema, not yet in catalog):**
- `SilhouetteType`: relaxed_tailored, layered, sculptural
- `FabricTexture`: low_luster, sheer, slub, performance, handloom
- `ConstructionDetail`: deconstructed, utility, experimental
- `EmbellishmentType`: tonal_embroidery, self_texture, chikankari, kantha

**From `bodyframe_stylist_revision_patchset_v_1.md` (received 2026-05-09, not yet applied to canonical):**
- `ShoulderStructure`: lightly_padded
- `ConstructionDetail`: angled_seam, vertical_panel, center_gathering, textured_yoke, epaulettes
- `SilhouetteContour`: wrap_with_hard_cinching
- `WaistDefinition`: soft_defined, strategic_defined, hard_cinched
- `FabricDrape`: rigid_tight
- `EmbellishmentLevel`: distributed_heavy

**From `updated_occasion_yaml_review_with_stylist_notes.md` (received 2026-05-09):**
- `EmbellishmentType`: kasavu_border, temple_border (region-specific border treatments — Kerala / Tamil Nadu)
- `GarmentLength`: micro_mini (stylist used `HemLength` — same axis, vocabulary alignment needed; new value)

**From `weather_yaml_review_and_updated_occasion_style_notes.md` (received 2026-05-09 — 6 in-place edits already shipped):**
- No new vocabulary added. The big finding here is structural: **`FabricTexture` decomposition.** Stylist flagged that today's `FabricTexture` enum mixes tactile texture (smooth, ribbed, textured), optical finish (sheen, metallic, matte), and construction detail (embroidered) — semantically overloaded; creates contradictory weather-reasoning rules. Proposed split:
  - Keep in `FabricTexture`: smooth, ribbed, textured (tactile only)
  - Move to new `SurfaceFinish` axis: sheen, metallic, matte
  - Move to existing `ConstructionDetail`: embroidered
  - Migration affects: garment_attributes.json schema, all 8 YAMLs, catalog enrichment for the 14,296 rows (re-tagged from old → new axes), embeddings regenerated. Higher cost than a simple value addition because *every* row's FabricTexture cell needs interpretation.

**From `palette_yaml_stylist_review_and_style_notes.md` (received 2026-05-09 — black handling, neutral luxury, monochrome, Deep Winter cleanup applied in-place):**
- **Metallic decomposition** — folds into the SurfaceFinish split above. The stylist wants the future `SurfaceFinish` axis to distinguish:
  - `high_shine_metallic` (mirror-shine; muted palettes typically fail under this)
  - `antique_metallic` (oxidized, brushed, dull champagne, aged bronze; muted palettes succeed with these)
  - `brushed_metallic` (matte gold, brushed steel)
  Today's single `metallic` value forces a binary that over-bans muted-palette users from a category they can absolutely wear. Resolve in the same batch as the FabricTexture decomposition.
- Vocabulary adds — all PrimaryColor / SecondaryColor (free-form text, no canonical schema impact). Catalog enrichment for these neutral-luxury tones (espresso, mushroom, greige, cocoa, tobacco, etc.) means the vision-enrichment prompt should be updated to recognize them when re-running enrichment. Currently catalog rows skew toward festive vocabulary; neutral-luxury palette rows may be undertagged.

**New top-level canonical axes** (need schema work in addition to enrichment):
- `ShoulderExposure`: Closed, CapExposed, OffShoulder, OneShoulder, Strapless, ColdShoulder *(from bodyframe)*
- `SleeveVolume`: Slim, Moderate, Puff, Bishop, Dramatic *(from bodyframe)*
- `BlouseLength`: Cropped, Standard, Longline *(from bodyframe)*
- `BorderContrast`: low, medium, high *(from occasion — used on Onam for `kasavu` border emphasis)*
- `FabricTransparency`: low, medium, high *(from occasion — used on Holi to keep wet color from soaking through)*
- `SurfaceFinish` *(from weather — see FabricTexture decomposition above)*
- **5 performance axes** *(from weather — Indian-monsoon-driven; not strictly visible from images, may need garment-spec data or partial vision inference):*
  - `BreathabilityLevel`: low, moderate, high
  - `DryTime`: slow, moderate, fast
  - `WaterResistance`: none, low, medium, high
  - `ThermalInsulation`: low, moderate, high
  - `WrinkleResistance`: low, moderate, high
- `LayeringVisibility`: hidden, integrated, statement *(from weather — North Indian ceremonial layering: shawl over lehenga vs thermal under sherwani)*

(More from upcoming stylist files will append here.)

### Engine extension queue (Type B — composition-time concepts, NOT catalog)

These are decisions the engine makes at composition time. They don't go on individual garment rows. Each needs new code in the composition engine + reduction logic.

**From `bodyframe_stylist_revision_patchset_v_1.md`:**
- `DupattaDrape` (VerticalFall, SingleShoulder, OpenUDrape, SideFall) — how the user drapes the dupatta when wearing the outfit. Composition emits this per outfit, not per garment.
- `LayeringStructure` (OpenFront, CapeOverlay, LonglineJacket, SoftOvershirt) — pairing decision (e.g., "include a longline jacket"), not a property of any single garment.
- `SupportRequirement` (Low, Medium, High) — depends on garment fit + occasion combination.
- `MovementSecurity` (Secure, Moderate, Delicate) — same.

**From `updated_occasion_yaml_review_with_stylist_notes.md`:**
- `MovementEase` (low, moderate, high) — used on Sangeet + Navratri (dance-heavy occasions). **Vocabulary alignment with bodyframe's `MovementSecurity`** — same concept, different name. Pick one canonical name during the batch-execute pass.
- **`bridal_priority` role-aware dressing** — entirely new structural concept. Wedding occasions need bride / groom / guest sub-roles with different rule sets per role (guests must NEVER receive equivalent embellishment recommendations as bridal participants attending the same wedding). Engine currently treats all attendees uniformly. Needs schema support for "role within occasion" context + role-conditional rule lookup.
- **External yearly Navratri color-sequence config** — Navratri has a 9-night designated daily color sequence that changes yearly. Should be an external config the engine reads at runtime, not hardcoded in YAML. Stylist flagged this explicitly.

**Vocabulary mismatch with existing canonical** (note for batch-execute):
- Stylist's `SkinExposureLevel: [modest, balanced, elevated]` — canonical already has `SkinExposureLevel: [very_low, low, medium, high, very_high]`. Resolve during batch-execute (likely keep canonical's 5-band scale, alias stylist's labels in canonicalize).
- Stylist's `HemLength` — canonical uses `GarmentLength` (with values cropped, waist, hip, mid_thigh, thigh, knee, calf, ankle, floor). Same axis, different name. Add `micro_mini` to GarmentLength.

(More from upcoming stylist files will append here.)

### Engineering flags surfaced by stylist (cross-cutting)

Items the stylist explicitly flagged as engineering work that no single YAML can express:

1. **External yearly Navratri color-sequence config** — see Engine extension queue above.
2. **Bridal-role engine support** — see Engine extension queue above (`bridal_priority`).
3. **Exposure / modesty attribute family audit** — `SkinExposureLevel` exists; `ShoulderExposure` is queued. Stylist also wants `NecklineDepth` enforced as hard rules in conservative contexts (in_laws_first_meeting, daily_office_mnc) — already canonical, just needs hard/soft routing.
4. **Canonical enum registry audit** — stylist flagged inconsistencies across YAMLs in how `OccasionFit`, `OccasionSignal`, `EmbellishmentType`, `FabricTexture`, `PrimaryColor` values are spelled / scoped (e.g., `formal` vs `semi_formal` vs `smart_casual`; `traditional` vs `festive`; `party` vs `night_out`; `workwear` vs `office`). Worth a one-pass canonicalization sweep before batch-applying patches.
5. **Fabric-pairing compatibility layer** — silk × cotton, brocade × handloom, etc. Stylist already flagged this as the major content gap that the upcoming `pairing_rules.yaml` review will address. Carrying as a forward-looking note here so the engineering work isn't surprise-discovered then.

### Hard / soft rule key support — Phase 4.3 (engineering, gates body_frame application)

Stylist's body_frame patch uses `hard_flatters` / `hard_avoid` / `soft_flatters` / `soft_avoid` keys throughout. Current yaml_loader only recognizes `flatters` / `avoid` ([yaml_loader.py:271-276](../modules/agentic_application/src/agentic_application/composition/yaml_loader.py:271-276)) — `hard_*` / `soft_*` keys would be silently ignored.

Required code work:
1. yaml_loader extended to read both naming styles (back-compat) and surface hard/soft separately.
2. Reduction logic in `composition.engine` updated to enforce hard rules unconditionally and treat soft rules as scoring penalties (matches the `PENALTY_*` pattern in composer_engine).
3. Validators updated to permit the new keys.
4. Tests covering hard violation = drop, soft violation = score penalty.

Estimated ~3 days of engineering. Independent of catalog re-enrichment; can ship in parallel.

### Plan once all 8 stylist files received

1. Consolidate full vocabulary additions in this section.
2. Ship Phase 4.3 hard/soft yaml_loader + engine extensions (~3 days).
3. Ship new canonical axes for Type B concepts (~3-5 days, depends on count).
4. Update vision-enrichment prompt with all Type A additions (~1 day).
5. Run vision enrichment on 14,296 catalog rows (~10-15 hours compute, ~$300-700).
6. Backfill database; regenerate `catalog_item_embeddings` (~3-5 days end-to-end including QA).
7. Apply pending YAML patches (body_frame + later files) in one coordinated PR per file.
8. Validate via Phase 4.6 eval set (gated on its own delivery).

---
---

# Sub-3s latency push — phased execution plan

**The anchor document for the latency-reduction work.** Replaces the prior pre-launch / launch / post-launch framing with a 7-phase execution plan, each with explicit test gates. We test query response after every phase before progressing. Phases 6–7 (added 2026-05-09) are the architectural shifts that finish the sub-3s push on the slow side of the cache; Phases 1–5 are runtime wins on the existing hot-path topology.

## Status as of 2026-05-08

| Phase | Status | Notes |
|---|---|---|
| Phase 1 — Operational quick wins | ✅ **SHIPPED + verified** | Rater parallelization, retrieval RPC fix, planner shadow infra (dormant), gpt-5.4 → gpt-5.2 architect/composer swap. ~6s saved per turn. |
| Phase 2 — Caching layer | ✅ **SHIPPED + applied to staging** | All 4 migrations live on Aura-Staging. Hit rate jumped from ~0% (non-deterministic planner output) toward the design target as Phase 4.7+4.11 made engine inputs canonical. |
| Phase 3 — Prompt compression (3.0+3.1+3.2+3.4) | ✅ **SHIPPED** (PR #202, May 8 2026) | MIGRATED sections compressed in architect + composer prompts, `_RECENT_USER_ACTIONS_MAX` 30→20, structured output verified, audit harness (`ops/scripts/audit_prompt_tokens.py`) + budget regression guard. ~2K input tokens off the LLM-fallback path per turn. Aggressive 14K→5K via YAML-row injection (3.3/3.5) deferred to post-4.6. |
| Phase 4 prep (4.1, 4.4, 4.5) | ✅ **SHIPPED** | Composition semantics spec, bootstrap grid YAML loader, MIGRATED prompt markers. |
| Phase 4.7 — Engine implementation | ✅ **SHIPPED** (PR #149) | 6 sub-PRs (4.7a-f) bundled: yaml_loader, reduction, relaxation, engine, render, worked-example tests. Architect stage drops 19s → ~0ms on engine-accepted turns. Verified end-to-end with confidence=1.0 on a real staging query. |
| Phase 4.8 — Quality validator | ✅ **Framework SHIPPED** (PR #149) | `composition/quality.py` + `ops/scripts/composition_quality_eval.py` ready to consume Phase 4.6 eval set. Real comparison run gated on 4.6. |
| Phase 4.9 — Hot-path router | ✅ **SHIPPED** (PR #149) | `composition/router.py` with §9 fall-through gates + `extract_engine_inputs` + `is_engine_acceptable`. Wired into orchestrator. |
| Phase 4.10 — Manual flag rollout | ✅ **Manual flag SHIPPED** (PRs #149, #151) | `AURA_COMPOSITION_ENGINE_ENABLED` bool env var (default false). Bucketed-pct rollout deferred — flip flag for testing; switch to bucket-based ramp once 4.6 calibration data lands. |
| Phase 4.11 — Input canonicalization | ✅ **SHIPPED** (PR #151) | Two-phase canonicalize: exact-match against YAML keys → batched text-embedding-3-small fallback. 256-dim pre-computed embeddings (350KB JSON) co-shipped. Unblocked the engine on real planner output. |
| Phase 4.12 — Observability + operability hardening | ✅ **SHIPPED** (PRs #150, #152, #153, #154) | Pre-flag instrumentation, tool_traces constraint fix, model_call_logs origin stamping, full panel set (21-24) + runbook + `ops/scripts/turn_forensics.py`. |
| Phase 4.2 — Stylist YAML review | 🔒 Blocked on human | Paid consultant pass. Output: revised YAMLs + canonical-schema fixes. |
| Phase 4.6 — Eval set curation | 🔒 Blocked on human | 100-500 hand-curated queries with hand-rated outputs. Gates Phase 4.8 actual run, Phase 1.4 model A/B, Phase 4.10 bucketed ramp. |
| Phase 5 — Composer engine | ✅ **SHIPPED** (PRs #158-#163) | 6 sub-PRs (5a-5f): semantic spec, loader+evaluator, engine, router+flag, quality+shadow, dashboards+runbook. 154 tests added. Engine dormant behind `AURA_COMPOSER_ENGINE_ENABLED`; flag-on validation gated on Phase 4.6 eval set + 4.2 stylist review. |
| Phase 6 — Pre-composed Outfit Library | 📋 **Planned** (post-4.6) | Move composition entirely offline. Hot path becomes profile-clustered vector retrieval against a pre-rated `outfit_library`. Sub-500ms on library hits; the actual sub-3s lever on the slow side of the cache. ~3-4 weeks of work, gated on Phases 4.2 + 4.6. |
| Phase 7 — Layer C learned compatibility | 📋 **Planned** (post-Phase-6 + feedback volume) | Replace zero-shot Rater with a small learned model on accepted/rejected feedback events tagged with the sub-score vector at recommendation time. Inference <50ms vs Rater's ~4s. |

**Production model lineup:** architect + composer on **gpt-5.2** (was gpt-5.4); planner + rater on **gpt-5-mini**; style advisor on **gpt-5.4**. All five env-configurable via `PLANNER_MODEL`, `ARCHITECT_MODEL`, `COMPOSER_MODEL`, `RATER_MODEL`, `STYLE_ADVISOR_MODEL`.

**See also:** `docs/composition_semantics.md` for the Phase 4 engine spec; `~/.claude/projects/.../memory/project_phase_2_4_status.md` for full handoff context.

**Foundation already shipped:**
- **PR #109** — `distillation_traces` table + `record_stage_trace` context manager wired into 5 stages (production-ready trace pipeline; full I/O captured per turn for future distillation training).
- **PR #110** — bootstrap intent grid + synthetic profile pool (5,424 cells, regenerable via `ops/scripts/generate_bootstrap_grid.py`; available as Phase 4 input). Phase 4.4: generator reads from `occasion.yaml` directly — drift vector eliminated.
- **PRs #111–#117** — 8-file style graph (~5,500 lines of Indian-urban fashion knowledge as YAMLs) covering body_frame (M+F), archetype, palette, occasion, weather, query_structure, pairing_rules. Plus 2 reusable validators (`ops/scripts/validate_style_graph_yaml.py`, `validate_style_graph_conflicts.py`).

**Phase 4 engine + operability — shipped 2026-05-06 / 2026-05-07:**
- **PR #149** — composition engine (Phases 4.7a-4.7f bundled: yaml_loader, reduction, relaxation, engine, render, worked-example tests) + Phase 4.8 quality-validator framework + Phase 4.9 hot-path router + Phase 4.10 boolean feature flag.
- **PR #150** — pre-flag observability: router decision counter, engine latency histogram, YAML gap surfacer, YAML-load-failure alert.
- **PR #151** — Phase 4.11 input canonicalization layer + canonical_embeddings.json artifact + bug fix for seasonal_color_group dual-dimension lookup.
- **PR #152** — `tool_traces` CHECK-constraint coercion fix (cache_hit / skipped_no_urls were tripping the DB; observability data was being silently dropped).
- **PR #153** — `model_call_logs.model` origin stamping (`cache` / `composition_engine` / LLM model id) so per-model rollups stay honest on engine-served turns.
- **PR #154** — comprehensive observability follow-up: 4 new metrics (canonicalize result counter, embed-duration histogram, tool_traces failure counter, attribute-status counter), 4 new dashboard panels (21-24), provenance summary plumbed into traces, OPERATIONS.md "A4: Composition engine flag-on regressions" runbook, `ops/scripts/turn_forensics.py`.

A real flag-on staging turn (`b356a1bf`, 2026-05-06) confirmed the win: architect stage 19s → ~0ms, total turn 83s → 63s, $0.04/turn cheaper, engine accepted at confidence 1.0.

These foundations remain available; their consumers (the composition engine in Phase 4, the cache layer in Phase 2) ship below.

**Strategic context:**
The composition engine (Phase 4) is the architectural endpoint that makes the YAMLs runtime-load-bearing on the hot path. Phases 1–3 are operational wins. Phase 5 extends the wins to the composer. **Phase 6** moves composition entirely offline — pre-rated outfits indexed in `outfit_library`, retrieved via vector + filter on the hot path — which is the only architectural path to sub-3s on the slow side of the cache, since even at full engine acceptance the cold path stays at ~25-30s (composer LLM ~12s + rater ~4s + retrieval ~3s). **Phase 7** replaces the zero-shot LLM Rater with a learned model on feedback signals; that's a quality + cost refinement on top of Phase 6, not a separate latency lever.

**Critical-path priority (2026-05-09):**

1. 🔒 **Phase 4.2 stylist YAML review (in progress, file 1 of 8 done)** — paid consultant pass on the 8 style-graph YAMLs. Status table + downstream-work queue tracked under "Stylist YAML review — aggregated downstream work" above. **Why this matters most:** the stylist's reviews drive both Phase 4.6 ground-truth and the catalog re-enrichment scope. The downstream work (engine extensions, Type B axes, hard/soft yaml_loader, vision-enrichment prompt update, batched re-enrichment) gates on completing all 8 file reviews so the work can be batched.
2. 🔒 **Phase 4.6 eval set curation** — 100-500 hand-curated queries with hand-rated outputs. **Why this matters:** every downstream item (composer engine flag-on, Phase 6 library quality validation, Phase 7 learned model held-out evaluation, threshold calibration on both routers) gates on having ground truth.
3. ⏳ **EAR-1 data accumulation** (~2-3 days from 2026-05-09) — composer router decisions persisting since [PR #222](https://github.com/jaychitransh007/TheSigmaAura/pull/222). **Why this matters:** the composer engine's actual ~4% acceptance driver (`MIN_PICKS` / `pool_too_sparse` / pre-engine eligibility / `low_confidence`) is currently invisible. The next composer-side fix can't be picked correctly until this data shows the breakdown.
4. 📋 **Phase 6 — Outfit Library** (post-4.6 + post-stylist-and-enrichment, ~3-4 weeks). **Why this matters:** the engines are ~done; the question is whether they run on the hot path (current design, ~25s floor) or offline (library design, sub-500ms hits). Phase 6 is the architectural shift that finishes the sub-3s anchor target. Also gated on the catalog re-enrichment landing (otherwise the library would be built against stale vocabulary).
5. 📋 **Phase 7 — Layer C** (post-Phase-6 + ~50 feedback events/user). **Why this matters:** at sufficient volume, a learned model on real feedback should outperform zero-shot Rater calibration AND drop the 4s Rater stage to <50ms inference. But it has to come after the library because the library is where every recommendation naturally carries its sub-score vector for training; retrofitting feedback enrichment without it is harder.

Items NOT on the critical path right now (deferred — see Phase headers for trigger conditions): planner model swaps (Phase 1.3/1.4 dropped), composer model swaps (Phase 1.4 dropped), prompt-compression aggressive tier (Phase 3.3/3.5 gated on 4.6), bucketed engine rollout machinery (waits for 4.6).

---

## Phase 1 — Operational quick wins (P0, Week 1)

**Goal:** 64s → ~25-30s without architectural changes. All tasks are independent, parallelizable, low-risk.

### 1.1 Parallelize the rater (1 day)

Replace the single 6-outfit `outfit_rater.rate()` call with `asyncio.gather` over 6 parallel calls. Each call rates one outfit independently against the absolute 75-threshold. If composer produces 6 and we pick top 3 (rather than just gate-keep), add a tie-breaking comparative pass (~500ms) after parallel scoring. Verify in production: same scores within tolerance, latency drops from 13.4s to ~2-3s.

### 1.2 Fix retrieval (hours)

Profile the current 2.9s pgvector query — likely missing HNSW index, doing pre-filtering wrong, or re-running embedding model on query without caching. Add HNSW index if absent: `CREATE INDEX ON catalog_item_embeddings USING hnsw (embedding vector_cosine_ops)`. Cache the query embedding model in memory; don't reload per request. Move metadata filters (size, gender, in-stock) to indexed columns; apply at SQL level not Python loop. Expected: retrieval drops from 2.9s to <100ms.

### 1.3 / 1.4 — DROPPED (2026-05-07)

Further planner / architect / composer model-swap work is no longer on the plan.

What stays shipped and in production:
- Planner shadow infrastructure (`AURA_PLANNER_SHADOW_MODEL`, `aura.planner.shadow` logger). Dormant unless the env var is set; not being actively iterated on.
- The `gpt-5.4 → gpt-5.2` architect + composer swap (shipped May 13 2026).
- Env-configurable model strings (`PLANNER_MODEL`, `ARCHITECT_MODEL`, `COMPOSER_MODEL`, `RATER_MODEL`, `STYLE_ADVISOR_MODEL`).

The previously planned next steps — promoting a non-reasoning planner and A/B-ing claude-sonnet-4-7 / gemini-2.5-pro for architect+composer — are not being pursued. The architect path is mostly moot post-engine (Phase 4.7 ships engine-accepted turns at ~0ms architect), and the planner promotion didn't justify the calibration work given the engine's larger end-to-end win. Composer-side latency is now better attacked by Phase 5 (composer engine) than by a model swap.

### Phase 1 test gate

- Cold-path latency p95: ≤30s (from 64s, after 1.1 rater + 1.2 retrieval RPC ship)
- Quality on eval set: ≥95% agreement with current production (deferred until eval set exists)
- No regressions on the 50 hand-picked test queries

> **Note:** streaming card delivery (NDJSON/SSE + frontend) was previously scoped here as 1.5 and later as Phase 6. Both are dropped from the latency push — perceived-latency UX work is no longer planned under this anchor.

---

## Phase 2 — Caching layer (P0, Weeks 2-3)

**Goal:** cache architect + composer outputs keyed on profile cluster. Hit rate grows organically from real traffic. Replaces the bootstrap-then-cache plan from the earlier draft — runtime cache is lighter weight and learns from real distribution.

### 2.1 Define profile clustering function (2 days)

~20-50 buckets across `(body_frame_class × archetype × palette_class × gender × formality_lean)` for cache key generation. Coarse buckets to start; refine if hit rate too low. Don't over-engineer.

### 2.2 Build architect output cache (3-4 days)

Postgres table `architect_direction_cache` with JSONB output. Cache key: hash of `(intent, profile_cluster, occasion, season, formality, architect_prompt_version)`. TTL 7-14 days; invalidation on `architect_prompt_version` bump. Wrap architect call: hit → skip architect entirely; miss → run architect → cache the output. Expected hit rate: 0% on day 1, ~40% by day 7, ~70% by week 4 as cache populates.

### 2.3 Build composer output cache (2-3 days)

Same pattern as 2.2 with key: hash of `(architect_direction, retrieval_result_fingerprint, profile_cluster, composer_prompt_version)`. Fingerprint retrieval results by sorted SKU IDs (different SKUs = different cache key, prevents stale outfits).

### 2.4 Cache invalidation strategy (included in 2.2, 2.3)

Invalidate on prompt-version bump (the `architect_prompt_version`, `composer_prompt_version` in cache keys handle this automatically). No per-entry TTL needed beyond default. Keep entries for 7-14 days; refresh on access.

### 2.5 Cache hit/miss metrics dashboard (1 day)

Monitor hit rate by cluster. Surface low-hit clusters as "needs more traffic" or "clustering too granular". Track cache miss latency to confirm Phase 1 baseline holds.

### Phase 2 test gate

- Cache hit rate after 1 week of alpha traffic: ≥30%
- Cache hits: <100ms architect + composer combined latency
- Cache misses: same as Phase 1 baseline (~25s on cold path)
- Quality unchanged on cache hits (cached output = original architect/composer output)
- p95 across mixed traffic: ≤15s

---

## Phase 3 — Prompt compression (P1)

**Goal:** shrink architect + composer prompts; reduce cold-path latency on the LLM-fallback path.

**Important context (May 8 2026):** with the architect engine accepting ~70-80% of turns and 7-of-7 follow-up intents engine-friendly, the architect LLM is now a **fallback** path (<30% of turns), not the common path. Compression saves real time on the cases that fall through, but the headline win has shifted from "every turn" to "the hard edge cases."

Phase re-scoped May 8 2026 into a ship-now bundle and a post-4.6 follow-up tier:

### 🟢 Ship-now bundle (3.0 + 3.1 + 3.2 + 3.4)

Low-risk cuts that don't depend on Phase 4.6 ground truth:

#### 3.0 Audit (1 day)
Add token-counting telemetry; one-time measure on 50 production turns; produce per-section breakdown so subsequent cuts target real heavy-hitters, not assumed ones.

#### 3.1 Easy cuts in architect prompt (1-2 days)
Delete the `<!-- MIGRATED -->` sections from `prompt/outfit_architect.md` (Occasion Calibration, BodyShape Visual Direction, Pattern Calibration — all already encoded in YAML and consumed by the engine). Trim translation examples to 2 per category. Cap `recent_user_actions` at 20 (was 30). Cap `conversation_history` to last 2 turns (was 4). Estimated savings: ~3-4K tokens.

#### 3.2 Verify structured output (hours)
Confirm architect's `_PLAN_JSON_SCHEMA` is in use via OpenAI `response_format=json_schema` (already in place per `outfit_architect.py:_PLAN_JSON_SCHEMA`). Trim any redundant in-prompt schema description. Estimated savings: ~500-800 tokens.

#### 3.4 Composer trim (1 day)
Apply the same pattern to `prompt/outfit_composer.md`: drop redundant prose, prune examples. Estimated savings: ~500 tokens.

**Combined target:** architect ~14K → ~9-10K, composer ~3-5K → ~2.5-4K. Aggressive 14K → 5K target deferred to 3.3 + 3.5 (next).

### 🔒 Post-4.6 follow-up tier (3.3 + 3.5)

Gated on Phase 4.6 eval set landing — cannot validate quality regression without ground truth.

#### 3.3 Conditional prompt injection (3-4 days, post-4.6)

Load `outfit_architect_followup.md` ONLY when `is_followup=true`. Same idea for occasion-specific rules — only inject the active occasion's calibration. Saves ~500-1,000 tokens per applicable turn but requires routing logic in the architect agent + per-occasion eval coverage.

#### 3.5 YAML row injection (5-7 days, post-4.6)

Replace the deleted MIGRATED prose with structured per-user YAML row injection (palette for their sub-season, body_frame for their shape, archetype for their style). Adds a per-turn YAML rendering pipeline plus an ongoing YAML↔prompt sync burden. Biggest single token win (~1-2K) but the highest engineering cost AND the highest quality risk on the LLM-fallback path. Worth doing only if (a) 3.0+3.1 prove out the easy cuts hold quality on the eval set and (b) the LLM-fallback rate doesn't drop further (if engine acceptance keeps climbing, the LLM path becomes too rare to justify the YAML-injection investment).

### Phase 3 test gate

- Architect input tokens: ≤5K
- Composer input tokens: ≤4K
- Cold-path architect latency: ~8-10s (with the shipped gpt-5.2 swap stacked)
- Quality regression on eval set: <2%
- Cache hits (~60-70%): <100ms
- Cache misses: ~25-30s p95 (down from ~50s)

---

## Phase 4 — Composition engine for architect (P0 strategic, Weeks 5-7)

**Goal:** replace architect with YAML-driven composition on the common path. The architectural endpoint that makes the 8 YAMLs runtime-load-bearing.

### Pre-work (Week 4, parallel with Phase 2/3)

#### 4.1 Composition semantics spec (3-5 days)

Write `docs/composition_semantics.md` covering:
- Empty-intersection handling (most common case across 7 mappings)
- Soft vs hard constraint distinction
- Weighted preferences within `flatters` lists (currently flat — need ordering or explicit weights)
- Conflict precedence: 28 pair relationships including BodyShape > FrameStructure, SubSeason > individual color attrs, etc.
- Worked examples for each conflict type

#### 4.2 Stylist review of 8 YAMLs (1-2 weeks, parallel)

Paid consultant pass focused on edge cases: Diamond body type (genuinely tricky), `off_shoulder` workarounds (canonical schema gap), regional festival variants (Onam, Navratri day-color sequence by year), bridal vs non-bridal calls, Indian fabric pairing rules. Output: revised YAMLs + list of canonical-schema fixes needed.

#### 4.3 Add `hard:` / `soft:` distinction to YAML schema (2 days)

Extend the 8 YAMLs with constraint-type markers; update validators (`ops/scripts/validate_style_graph_yaml.py`). Migrate existing entries (most defaults: physical-frame is hard, archetype is soft).

#### 4.4 Refactor bootstrap grid generator (1 day)

Update `ops/scripts/generate_bootstrap_grid.py` to read occasion list from `knowledge/style_graph/occasion.yaml` (currently has 31; YAML has 45+). Eliminates the stale-grid drift vector flagged in PR #114.

#### 4.5 Begin one-way prompt → YAML migration (ongoing)

Add `MIGRATED:` markers in `prompt/outfit_architect.md` next to rules now in YAML. New rules go to YAML directly. Once composition engine ships and replaces the architect, the prompt's migrated sections get pruned. **Decision committed: one-way migration — no dual updates.**

#### 4.6 Manual eval set curation (1-2 weeks human curation, parallel)

100-500 representative test queries spanning the launch grid (mix of common, edge, novel). Run the slow pipeline against each; capture full outputs (architect plan + 6 composed outfits + rater scores + try-on for top 3). Hand-rate each output on the same 6 axes the rater uses. Store as `eval_set.jsonl` versioned in `tests/eval/`. Inter-rater agreement spot-checked on ≥20 cases by a second reviewer.

This is **not** training data — it's the eval ground truth used for Phase 4.8 quality validation, Phase 5.4 composer A/B testing, and ongoing regression detection.

### Engine work (Weeks 5-6)

#### 4.7 Implement composition engine — ✅ SHIPPED (PR #149)

Bundled all six sub-PRs (4.7a–4.7f) into a single merge: yaml_loader → reduction → relaxation → engine → render → worked-example tests. Module `modules/agentic_application/src/agentic_application/composition/`. Reads 8 YAMLs from `knowledge/style_graph/`. Applies intersect/union semantics with precedence rules from `docs/composition_semantics.md` (PR #144 + #147). Empty-intersection fallback per spec §3.2; on full failure, falls through to LLM architect via the router (4.9).

Verified end-to-end on 2026-05-06: architect stage 19s → ~0ms on engine-accepted turns; engine itself runs in <1ms wall-clock; confidence=1.0 on a real staging "casual outfits for weekend outing" query.

#### 4.8 Quality validator — ✅ FRAMEWORK SHIPPED (PR #149)

`composition/quality.py` implements `compare_queries`, `compare_directions`, `compare_plans`, `aggregate_eval` — pure-function comparators with token Jaccard on `query_document`, set Jaccard on `(key, value)` hard-filter items, role-based query pairing, direction_id-based pairing, median-not-mean reduction. `ops/scripts/composition_quality_eval.py` is the CLI driver; reads an eval JSONL, runs engine + LLM per cell, emits markdown.

**Real run gated on Phase 4.6** (eval set curation). Until then the framework sits dormant.

#### 4.9 Hot-path router — ✅ SHIPPED (PR #149)

`composition/router.py:route_recommendation_plan()` encodes spec §9 fall-through criteria (`confidence < 0.50` per the recalibration in PR #151, `no_direction`, `yaml_gap`, `excessive_widening`, `needs_disambiguation`) plus pre-engine eligibility gates (`anchor_present`, `followup_request`, `has_previous_recommendations`). Returns a `RouterDecision` envelope with `used_engine`, `fallback_reason`, `engine_confidence`, `yaml_gaps`, `engine_ms`, `provenance_summary` — wired into the orchestrator's cache-miss path.

### Cutover

#### 4.10 Manual flag rollout — ✅ SHIPPED (PRs #149, #151); bucketed ramp deferred

Single boolean env var `AURA_COMPOSITION_ENGINE_ENABLED` (default false). The earlier int-percent rollout machinery (`is_user_in_rollout_bucket` SHA-256 mod-100) was reverted in favor of the simpler flag for manual testing — bucketed ramp comes back as its own change once Phase 4.6 calibration data tells us where to start the percentage curve.

Engine plans intentionally do NOT write to the architect cache during flag-on testing (the cache key is profile/cluster-scoped, not user-scoped, so cached engine plans would persist across flag-on/flag-off transitions and leak the engine path into control traffic). LLM plans cache normally.

#### 4.11 Input canonicalization — ✅ SHIPPED (PR #151)

The pivotal piece that made the engine actually work on real planner output. Two-phase: (1) exact-match against YAML keys (cheap, no API call), (2) batched `text-embedding-3-small` call for non-matching values, nearest-neighbour cosine ≥ 0.50 wins. Below threshold → keep raw value (engine flags YAML gap → router falls through to LLM cleanly).

Pre-computed `composition/canonical_embeddings.json` (350KB, 256-dim, 85 keys × 5 axes) ships in-repo so production cold starts don't need an API call. Regenerated by `ops/scripts/build_canonical_embeddings.py` when YAMLs change. `aura_composition_canonicalize_result_total{axis, result}` counter (PR #154) tracks per-axis hit rate.

Confidence threshold dropped from spec §8's 0.60 to 0.50 because (a) downstream composer + rater rerank by score so an engine plan that's "merely passable" still surfaces good outfits, (b) at 0.60 the engine almost always fell through on real Indian inputs (4-5 of ~35 attributes typically need relaxation, accumulating penalties below the threshold). YAML gaps still always trigger fallback regardless of threshold via the explicit `has_yaml_gap` branch.

Bundled bug fix: engine's `seasonal_color_group` lookup now tries both `palette.SubSeason` (12-entry) and `palette.SeasonalColorGroup` (4-entry) before flagging a gap — profile data sometimes stores the 4-entry form (`Autumn`) instead of the 12-entry form (`Soft Autumn`).

#### 4.12 Observability + operability hardening — ✅ SHIPPED (PRs #150, #152, #153, #154)

- **PR #150** — pre-flag observability: `aura_composition_router_decision_total{used_engine, fallback_reason}` counter, engine latency under `aura_turn_duration_seconds{stage="composition_engine"}`, YAML gap metadata in `distillation_traces.full_output.router_decision`, `aura_composition_yaml_load_failure_total` counter + alert.
- **PR #152** — `tool_traces` CHECK-constraint fix: helper `_coerce_tryon_trace_db_status()` maps the rich path enum (`cache_hit`/`skipped_no_urls`/`tryon_failed`/...) to the constrained `'ok'`/`'error'` domain. Every cache-hit try-on previously dropped its trace row silently.
- **PR #153** — `model_call_logs.model` origin stamping: `_resolve_architect_origin_model()` picks `cache` / `composition_engine` / LLM model id; non-LLM paths force token columns to 0 (prevents stale `last_usage` bleed from prior turns).
- **PR #154** — comprehensive follow-up: 4 new metrics (`aura_composition_canonicalize_result_total`, `aura_composition_canonicalize_duration_seconds`, `aura_tool_traces_insert_failure_total`, `aura_composition_attribute_status_total`); 4 new dashboard panels (21 plan-source distribution, 22 yaml-gap distribution, 23 per-attribute status, 24 single-turn diagnostic); panel_17 patched to exclude sentinel rows; `RouterDecision.provenance_summary` plumbed into traces; OPERATIONS.md "A4: Composition engine flag-on regressions" runbook (env-var-didn't-export, yaml_gap dominance, YAML-load failure); `ops/scripts/turn_forensics.py` codifies the per-turn comparison report.

### Phase 4 test gate

| Criterion | Target | Status |
|---|---|---|
| Engine handles ≥80% of cache-miss requests without LLM fallback | post-rollout target | needs traffic + 4.6 calibration |
| Engine latency p95: <500ms | <500ms | ✅ verified ~0ms on the one staging turn (sub-1ms compose_direction; ~150ms canonicalize embed call) |
| Quality on eval set: ≥90% agreement with LLM architect | ≥90% | gated on 4.6 + `composition_quality_eval.py` run |
| Cold-path architect avg: <2s on engine hit, ~10s on engine miss | hit/miss target | ✅ verified ~2s engine-stage on the staging turn (mostly trace-write + cache-touch overhead; LLM never ran) |
| Cache layer <100ms on cache hit regardless of origin | <100ms | architect cache untouched; behavior unchanged |

---

## Engine acceptance recovery (May 9, 2026 RCA)

**Status:** queued · **Cost:** small · **Risk:** low / medium

RCA on May 9, 2026 surfaced that engine acceptance is far below the ≥80% architect / ≥70% composer targets:

| Engine | 14-day rate | 3-day rate |
|---|---:|---:|
| Architect | 22 / 97 = 22.7% | 22 / 56 = 39.3% |
| Composer | 2 / 70 = 2.9% | 2 / 50 = 4.0% |

Cross-tab: on 24 turns where the **architect engine accepted**, the composer engine fired **0 times**. The two routers' gating is misaligned. Three items, in this order:

### EAR-1 Composer router persistence to `tool_traces`

The architect router writes `composition_router_decision` rows ([orchestrator.py:5944-5976](modules/agentic_application/src/agentic_application/orchestrator.py:5944-5976), PR #207). The composer router only emits Prometheus + `_log.info` ([orchestrator.py:6605-6630](modules/agentic_application/src/agentic_application/orchestrator.py:6605-6630)) — no DB row. Result: zero database visibility into composer fall-through reasons (`yaml_gap`, `low_picks`, `pool_too_sparse`, `low_confidence`, eligibility gates). Mirror the architect persistence block for the composer. ~30 LOC, no behavior change. **Unblocks every other composer-engine RCA.**

### EAR-2 Add `risk_tolerance:expressive` to YAML canonical values

Across all yaml_gap fall-throughs, `risk_tolerance` is the leading missing axis (10 of 21 axis-mentions). The specific value that keeps firing is `expressive` — planner emits it; canonicalize doesn't have a key for it. One YAML entry (or alias to an existing key) plus regenerate `composition/canonical_embeddings.json` via `ops/scripts/build_canonical_embeddings.py`. No behavior change beyond closing the gap.

### EAR-3 Soften composer hard `yaml_gap` fall-through to confidence penalty

[composer_engine.py:654-656](modules/agentic_application/src/agentic_application/composition/composer_engine.py:654-656) sets `fallback_reason = "yaml_gap"` unconditionally if any gap exists — short-circuiting the confidence path. The architect router doesn't behave that way (it scores then decides). Lift the hard gate so the existing `PENALTY_YAML_GAP = 0.45` + `CONFIDENCE_THRESHOLD = 0.50` machinery decides. This is the only behavioural change and the real lever for moving composer engine acceptance off 4%. Risk medium — gates that previously short-circuited will now produce engine plans on borderline turns. Validate with a side-by-side staging eval before flipping.

**Trigger:** ship-now. EAR-1 unblocks visibility, EAR-2 is content, EAR-3 is the lever.

---

## Phase 5 — Composition engine for composer (P1, Weeks 8-10)

**Goal:** replace `OutfitComposer.compose()` (gpt-5.2, ~12-14s, $0.036/turn — second-largest LLM line post-4.7) with deterministic tuple scoring against `pairing_rules.yaml`. Engine emits up to 6 outfits in the existing `ComposerResult` shape; rater contract unchanged. Spec mirrors Phase 4.7's pattern (composition_semantics.md → composer_semantics.md, pure-function engine, hot-path router with eligibility + acceptance gates, `AURA_COMPOSER_ENGINE_ENABLED` boolean flag, LLM kept as permanent fallback).

### Locked decisions (2026-05-07)

| # | Decision | Rationale |
|---|---|---|
| 1 | **All-or-nothing per turn**, not per-outfit hybrid | Single `ComposerResult.overall_assessment`; hybrid doubles debugging surface. Mirror of architect router. |
| 2 | **Hard violation drops tuple; soft violation = -0.1 score penalty per violation; base score 1.0** | Clean binary; matches architect spec's hard/soft model. If <3 tuples survive across all directions → low-confidence fall-through. No precedence ordering among hard categories needed. |
| 3 | **Hardcode `pairing.py:is_statement()`**, docstring references `scale_balance.statement_definition` as source of truth | Same call architect made on its precedence matrix. Statement definition is a 4-clause OR; rare stylist edits. |
| 4 | **Defer anchor turns** to a follow-up | Pre-engine eligibility gate declines `anchor_present`/`followup_request`/`has_previous_recommendations`/`pool_too_sparse`. Mirror of architect router. Anchor support added post-validation. |
| 5 | **`bridal_specific.triggers_on: [occasion keys]`** new YAML field | Engine matches `formality_hint == 'ceremonial' AND occasion_signal in triggers_on`. Stylist-editable, no hardcoded occasion names in Python. |
| 6 | **Keep LLM `OutfitComposer` as permanent fallback** | Engine target hit rate ≥70%, not 100%. Same as architect pattern. The LLM stays as the permanent fallback path. |

### Sub-PR decomposition — ALL SHIPPED (2026-05-07)

| PR | Lands | Status |
|---|---|---|
| **5a** | `docs/composer_semantics.md` spec | ✅ #158 |
| **5b** | `composition/pairing_loader.py` + `pairing.py`; `bridal_specific.triggers_on` YAML field; 69 unit tests | ✅ #159 |
| **5c** | `composition/composer_engine.py` — `compose_outfits()`; tuple enumeration + scoring + diversity top-K + confidence; 49 tests | ✅ #160 |
| **5d** | `composition/composer_router.py` + `AURA_COMPOSER_ENGINE_ENABLED` flag + orchestrator wiring + `aura_composer_router_decision_total` counter; 17 tests | ✅ #161 |
| **5e** | Quality validator extension (`compare_composer_outputs`) + `ops/scripts/composer_quality_eval.py` + shadow-mode hook on router; 15 tests | ✅ #162 |
| **5f** | Panels 25-28 in OPERATIONS.md + auto-extracted SQL files + A5 runbook + `maxItems: 10` LLM schema cap + spec §9 worked-example tests | ✅ #163 |

Total: 154 new tests across the 6 PRs, 902/902 passing post-5f. Engine is dormant (default-false flag); ready for operational rollout once Phase 4.2 stylist YAML review + Phase 4.6 eval-set ground truth land.

**Composer-side `model_call_logs.model="composer_engine"` origin stamping** — ✅ shipped in PR #180 (Phase 5x.4a). `_resolve_composer_origin_model()` writes a synthetic row stamped `composer_engine` / `cache` on engine and cache paths, mirroring the architect's pattern.

### Phase 5 test gate

- Composer engine hit rate: ≥70% of cache misses
- Engine latency p95: <300ms
- Quality on eval set: ≥85% agreement with LLM composer
- Cold-path composer average: <500ms on engine hit, ~6s on engine miss

---

## Phase 6 — Pre-composed Outfit Library (P0 strategic, post-4.6)

**Goal:** move outfit composition entirely off the hot path. Pre-rate outfits offline against `(profile_cluster × occasion × season × weather × formality)`, index with `mood_embedding` + structured filters, and serve them via vector lookup. Hot path becomes: User State Vector lookup → vector + filter retrieval against `outfit_library` → fast LLM templating → stream. Sub-500ms achievable on library hits; live composition is the fallback (slow path, unchanged from Phases 1-5).

**Why this is on the plan:** the existing composition engines (Phase 4.7 + 5) are deterministic functions that take a profile + intent and return scored outfits. The natural endpoint isn't "engine on hot path" — it's "engine offline populating a library, hot path retrieval-only." Even at full engine acceptance the cold path stays at ~25s (composer LLM ~12s + rater ~4s + retrieval ~3s). Library-based retrieval is the architectural lever that gets us under 3s on the slow-path side of the cache.

**Gated on:**
- Phase 4.6 (eval set) — need ground truth before bulk-running engines offline against the intent grid; otherwise we're scaling unvalidated quality
- Phase 4.2 (stylist YAML review) — same rationale, applied to the engine inputs
- Stable composer engine acceptance (~70% target; currently 4%) — premature if engines reject most inputs

### 6.1 `outfit_library` schema + HNSW index (3-4 days)

`outfit_library` table: `id`, `tenant_id`, `profile_cluster`, `item_ids[]`, `compatibility_score`, `sub_scores jsonb`, `rater_dim_scores jsonb`, `mood_embedding vector(1536)`, `occasion`, `season`, `weather`, `formality`, `engine_version`, `rater_prompt_version`, `freshness_at`, `stale_after`. HNSW on `mood_embedding` (`m=16, ef_construction=64` initial, calibrate against Phase 4.6 set). `gin` index on `sub_scores jsonb` for filterable queries. RLS keyed on `tenant_id`.

### 6.2 Offline Composer worker (4-5 days)

Python worker on the existing `record_stage_trace` pattern, polls a `library_build_jobs` table with `FOR UPDATE SKIP LOCKED`. Iterates the bootstrap intent grid (PR #110, 5,424 cells) × representative profile clusters. Runs the existing `composition.engine.compose_directions` + `composition.composer_engine.compose_outfits` per cell. No time pressure — runs nightly initially, then on-demand for cold-start.

### 6.3 Offline Rater + library indexer (3-4 days)

For each composed outfit, run the existing `OutfitRater` once at compose time, store rater scores + threshold-pass flag. Drop sub-threshold outfits. Generate `mood_embedding` per surviving outfit using `text-embedding-3-small` over a deterministic outfit description. Write to `outfit_library`.

### 6.4 Hot-path retrieval-first router (3-4 days)

New router stage in orchestrator, BEFORE architect: given canonicalized planner output, vector-search `outfit_library` filtered by `profile_cluster + occasion + season + freshness`. If top-K is high-confidence (cosine ≥ threshold + sub-score threshold), skip architect + composer + rater entirely and emit those outfits to the formatter. Templated explanation via fast LLM streaming on the result.

### 6.5 Live-composition fallback path (no new code)

When library miss / low-confidence: fall through to the current `architect → catalog_search → composer → rater` path. Existing slow path is unchanged; the library tries to skip it.

### 6.6 Cold-start library build (2-3 days)

Onboarding completion event triggers a library-build job for the user's specific profile cluster across the 20-30 most-common cells of the intent grid. Builds a starter library before the user's first query, so cold-start latency benefits from the library too.

### 6.7 Library refresh / staleness (2 days)

`stale_after` driven by archetype-preference changes, wardrobe edits, season transitions. Stale entries trigger on-demand recompose for that one query (slow path) AND background refresh job. Library rows tagged with `engine_version + rater_prompt_version`; bumps trigger re-rate.

### Phase 6 test gate

| Criterion | Target |
|---|---|
| Library hit rate after 1 week post-launch | ≥50% |
| Hit-path latency p95 | <500ms |
| Quality on eval set: library outfit vs equivalent live-composed | ≥95% agreement |
| Library size per user post-cold-start | 100-300 outfits |
| Storage cost per active user (scores + embeddings) | <$0.01/user/month |

---

## Phase 7 — Layer C learned compatibility model (P1, post-Phase-6 + feedback volume)

**Goal:** replace the zero-shot LLM Rater (or augment it on a flag) with a small learned model — logistic regression first, 2-layer MLP later — over the sub-score vector that Layer B (`pairing.py` evaluators) already produces. Trained on accepted/rejected feedback events. Per-user personalization activated past ~50 events/user.

**Why this is on the plan:** Rater is currently zero-shot LLM judgment (gpt-5-mini, 6 dims on 1/2/3 — PR #101). A learned model trained on real accept/reject signals should outperform zero-shot calibration once feedback volume is sufficient — particularly on per-user calibration where the LLM has no signal. Drops the ~4s Rater stage to <50ms inference. Per-turn cost falls accordingly.

**Gated on:**
- Phase 4.6 (eval set) for held-out evaluation ground truth
- Phase 6 outfit_library landed — natural place where every recommendation carries the sub-score vector at recommendation time, which is the training feature; without library, retrofitting feedback enrichment is harder
- ~50 feedback events per active user (volume threshold for personalization layer)

### 7.1 Feedback enrichment with sub-score vector (1 day, can ship early)

Extend `feedback_events` rows to also store the Layer-B sub-score vector + Rater dimension scores at recommendation time. Purely additive; ships before the model itself so feedback events accumulate the right features.

### 7.2 Bootstrap Layer C with stylist priors (3-4 days)

Hand-set logistic-regression weights based on stylist intuition (formality variance high penalty, pattern density medium, color harmony high, etc.). Inference path runs alongside the LLM Rater on a feature flag. Quality validated on the Phase 4.6 eval set.

### 7.3 Periodic retraining job (2-3 days)

Nightly batch on accumulated feedback. Stores versioned model artifact + held-out eval metrics. Production loads the latest passing version.

### 7.4 Per-user personalization layer (3-5 days, gated on volume)

Once a user crosses ~50 feedback events, augment Layer C with user-specific weight adjustments (or a user embedding feature). Until then, falls back to global model.

### Phase 7 test gate

| Criterion | Target |
|---|---|
| Layer C agreement with stylist eval (Phase 4.6 set), global model | ≥85% |
| Layer C agreement, with personalization | ≥90% |
| Inference latency p95 | <50ms |
| Held-out eval accuracy after 1k feedback events | ≥80% |
| Replacement of LLM Rater | optional — Layer C augments first, replaces only after sustained ≥85% agreement on eval set |

---

## Cross-cutting — Multi-tenancy data hooks

**Status:** parked (guidance applied to all phase work) · **Cost:** trivial if done now; expensive to retrofit · **Risk:** low

Multi-tenancy is deferred from this latency push, but five hooks are zero-cost now and save a painful migration when Shopify multi-tenancy lands:

1. Every new table (caches, future compat tables) includes `tenant_id TEXT NOT NULL DEFAULT 'default'`.
2. Cached architect / composer outputs stay catalog-independent ("structured navy blazer, formality 3-4" — never product_ids). Keeps cache reusable across tenants.
3. Prompts stay catalog-neutral (no "Aura's catalog" or brand-specific framing). Lets per-tenant prompt overlays slot in cleanly later.
4. Logs and traces tag with `tenant_id` from day one.
5. **Do not** migrate user-scoped tables (`users`, `conversations`, `feedback_events`) — that's a real migration owed when multi-tenancy actually ships, not now.

**Trigger:** apply continuously to all phase work above.

**Acceptance:** no new table created without `tenant_id`; no cached output references SKUs; no prompt references catalog identity; user-scoped tables left alone.

---

## End-state latency budget

After Phase 5 (estimated Week 10):

| Path | Frequency | Latency p95 |
|---|---|---|
| Cache hit (warm) | ~70% | <500ms |
| Cache miss → engine compose | ~25% | <2s |
| Cache miss → engine miss → LLM fallback | ~5% | ~10s |
| **Average user experience** | — | **2-3s** |
