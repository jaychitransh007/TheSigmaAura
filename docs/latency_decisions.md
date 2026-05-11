# Latency decisions

A short ledger of trade-off calls made during the latency push that aren't obvious from reading the code. Each entry: what we picked, what we considered, why we picked it. New entries go to the top.

The intent is to short-circuit "should we do X?" conversations a future engineer would otherwise have to re-litigate from scratch. If a decision here goes stale, update or strike through the entry — don't delete it (the reasoning matters for context).

---

## Wardrobe vision enrichment on `gpt-5.2` / `reasoning_effort=low` (May 12 2026)

**Decision:** the per-item wardrobe vision enrichment call (`modules/user/src/user/wardrobe_enrichment.py`) runs `gpt-5.2` at `reasoning_effort=low`, with `max_retries=0` on the OpenAI client and an explicit 55 s `timeout=` passed to `chat.completions.create()`. Same family the architect and composer already use — different effort knob.

**Considered:**
- `gpt-5.5` at `reasoning_effort=high` (initial pick, to match the profile-image analysis path). Wall-clock was consistently 70-110 s on a single wardrobe item; the user surfaced a hung "Saving…" state.
- `gpt-5-mini` at `reasoning_effort=minimal`. Cheap and fast, but attribute quality dropped on garments with non-trivial structure (sarees, layered Indian sets) — the model under-emitted attributes the architect / composer treat as load-bearing.
- Keeping `gpt-5.5` but raising the per-request timeout. Hides the symptom but doesn't fix the cost or the wall-clock budget; doesn't free the user faster.

**Why we didn't:**
- `gpt-5.2/low` finishes in 12-25 s on the same items where `gpt-5.5/high` was 70-110 s, and the attribute quality is indistinguishable for the 57-attribute (55 enum + 2 text) schema. Architect/composer already validated that gpt-5.2 at low effort is good enough for outfit decisions.
- The OpenAI SDK default `max_retries=2` was silently undoing the 55 s timeout (3 attempts × 55 s ≈ 165 s). Setting `max_retries=0` is non-negotiable on this path — wardrobe ingestion is single-shot user-facing, not a backfill.
- `with_options(timeout=...)` didn't propagate reliably through the `chat.completions.create()` call. Passing `timeout=` directly to `.create()` is the only form we trust here.

**When to revisit:** if user-facing latency on wardrobe save becomes a regression driver (≥ p50 30 s sustained), OR if the rater starts surfacing attribute-quality complaints traceable to wardrobe items (vs catalog items). At that point: re-evaluate gpt-5-mini with a richer prompt OR a smaller, structured-output-only model.

**See also:** [PR #275](https://github.com/jaychitransh007/TheSigmaAura/pull/275) (initial vision-model upgrade), [PR #277](https://github.com/jaychitransh007/TheSigmaAura/pull/277) (widened latency budget), [PR #278](https://github.com/jaychitransh007/TheSigmaAura/pull/278) (`max_retries=0`), [PR #284](https://github.com/jaychitransh007/TheSigmaAura/pull/284) (swap to `gpt-5.2/low`), [PR #285](https://github.com/jaychitransh007/TheSigmaAura/pull/285) (thread-safe lazy init).

---

## Planner extracts `anchor_garment` (structured), not regex (May 12 2026)

**Decision:** the copilot planner emits a typed `anchor_garment: {category, subtype, confidence}` field. The orchestrator gates wardrobe-anchor flow on `anchor_garment.is_usable(threshold=0.5)`, not on a keyword regex match against the user's raw message.

**Considered:** keeping the keyword/regex extractor (`extract_garment_hint_from_text`) and continuing to grow its vocabulary as new categories appeared. Cheap, no extra prompt tokens, zero model-call risk.

**Why we didn't:**
- The regex couldn't handle paraphrases ("ye saree ke saath kya pehnu", "what goes with this floral midi", "pair my new lehenga with"), non-English, or multi-word subtypes without per-phrase coverage. Every gap was a silent fallback that produced a catalog-pipeline turn when the user clearly wanted a wardrobe-anchor pairing.
- The planner already classifies intent and pulls structured signals out of the message. Asking it to *also* identify the anchor garment costs almost nothing on the prompt budget (~250 tokens of instruction + ~15 tokens of output) and benefits from the same paraphrase-handling that the rest of the planner output already has.
- Confidence is now explicit. The 0.5 threshold means borderline mentions ("this is fine I guess" — confidence 0.2) don't accidentally hijack the pipeline.

**When to revisit:** if planner cost or latency becomes a bottleneck AND the anchor_garment block is implicated. The block is small enough that this seems unlikely.

**See also:** [PR #287](https://github.com/jaychitransh007/TheSigmaAura/pull/287) (planner anchor_garment + drop regex), [PR #292](https://github.com/jaychitransh007/TheSigmaAura/pull/292) (recovered the prompt instructions missed in the #287 squash), `aura_planner_anchor_confidence` histogram for tuning the threshold over time.

---

## Rater → tryon stays sequential (May 8 2026)

**Decision:** keep the existing pipeline shape — outfit_rater finishes before tryon_render starts. Within the tryon stage the 3 renders run in parallel via `ThreadPoolExecutor(max_workers=3)`, but the entire stage waits for the rater LLM to return.

**Considered:** parallel-to-rater speculation. Pick top-3 by composer order, kick off Gemini renders in parallel with the rater LLM call, patch up afterwards if rater veto changes the picks. Would save ~7-11s wall-clock per turn (the longest of the rater + first parallel render, vs sequential addition).

**Why we didn't:**
- The rater applies a veto + threshold gate (`unsuitable=false` AND `fashion_score >= 50`) BEFORE tryon today — i.e., we keep outfits that are NOT marked unsuitable and clear the threshold; everything else is dropped. The gate exists to avoid burning Gemini calls on outfits that would be dropped. Speculative renders would either (a) waste $0.04 per vetoed outfit, or (b) need a synchronization step that adds back most of the latency win.
- After PR #185 (`AURA_TRYON_ENABLED` flag, default off), tryon stage cost during dev iteration is already $0.00 / 0s. Production / demos with the flag on still pay ~22s for tryon, but that's now a deliberate UX choice rather than a hidden tax.
- The 7-11s perceived-latency win is a real user-visible difference on the cards-vs-blank-screen scale, but Phase 6 (streaming delivery) addresses that more cleanly: cards stream as they finish, no need to interleave stages within the request lifetime.

**When to revisit:** if Phase 6 streaming gets deferred AND tryon flag becomes consistently on in production AND the 7-11s is the bottleneck users complain about. Until then, the trade-off favors the simpler shape.

**See also:** [`composer_semantics.md`](composer_semantics.md) §7 (composer engine acceptance gates), [PR #185](https://github.com/jaychitransh007/TheSigmaAura/pull/185) (tryon flag).

---

## Format

```
## <decision in one line> (<date>)
**Decision:** what we ended up doing
**Considered:** the alternatives we evaluated
**Why we didn't:** the reasoning, in bullets
**When to revisit:** the conditions under which the trade-off changes
**See also:** PRs / docs that contextualize the decision
```
