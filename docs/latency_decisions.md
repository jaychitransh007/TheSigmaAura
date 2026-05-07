# Latency decisions

A short ledger of trade-off calls made during the latency push that aren't obvious from reading the code. Each entry: what we picked, what we considered, why we picked it. New entries go to the top.

The intent is to short-circuit "should we do X?" conversations a future engineer would otherwise have to re-litigate from scratch. If a decision here goes stale, update or strike through the entry — don't delete it (the reasoning matters for context).

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
