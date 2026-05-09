"""Embedding-based input canonicalization for the composition engine.

The planner emits free-text-ish values (``occasion_signal``,
``weather_context``, etc.) that don't always match the YAML's canonical
keys. Without canonicalization, every realistic turn lands on a
``yaml_gap`` and falls through to the LLM — defeating the engine's
latency win.

This module bridges the vocabulary gap with pre-computed
``text-embedding-3-small`` vectors over each axis's YAML keys + notes.
At runtime the router collects every input value that doesn't
exact-match its YAML and embeds them in a single batched call;
nearest-neighbor (cosine ≥ ``threshold``) wins. Below threshold →
return the original value unchanged so the engine still flags it as
a YAML gap (which is now a *genuine* "engine doesn't know" signal,
not a vocabulary mismatch).

Properties:

- **Determinism preserved.** Same input string → same embedding (model
  is deterministic for a fixed `model` + `dimensions`) → same nearest
  neighbor. Cache keys stay stable.
- **Cheap when canonical.** Exact-match path adds 0ms; embedding only
  fires for non-matching inputs. The same string is also cached
  per-process so "casual" gets embedded once.
- **Per-process embedding bank.** Loaded once from
  ``canonical_embeddings.json`` (next to this module). Cold start =
  one file read, no API call.
- **Failure-tolerant.** Embed API failure or timeout → fall back to
  the raw value (engine still produces output, falls through to LLM
  if the value isn't found).
"""
from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .yaml_loader import StyleGraph


_log = logging.getLogger(__name__)


# Default cosine threshold below which we DON'T pick the nearest
# neighbour. Calibrated empirically on the four worked-example axes —
# 0.5 cleanly separates "casual"→"everyday_casual" (≈0.65) from
# noise like "balcony" (≈0.3 against any occasion). Tunable via
# the ``threshold`` parameter on canonicalize_inputs.
DEFAULT_THRESHOLD = 0.50


# ─────────────────────────────────────────────────────────────────────────
# Canonical aliases — short-circuit common informal occasion words
# ─────────────────────────────────────────────────────────────────────────
#
# May 8 2026 (engine-acceptance RCA): the planner emits free-text
# occasion vocabulary that's semantically clear to humans but doesn't
# exact-match a YAML key, e.g. "wedding". The embedding fallback then
# nearest-neighbours against the bank — and the bank doesn't have a
# generic "wedding" entry, only specific cycle stages (wedding_ceremony,
# wedding_reception, sangeet, mehndi, sagai_engagement, ...). Cosine
# similarity from "wedding" can land highest on `sagai_engagement`
# (engagement ceremony — ~0.55-0.60) just because both descriptions
# share marriage-related vocabulary, which is semantically wrong: a
# generic "wedding" should map to the wedding *ceremony* itself.
#
# The alias table below short-circuits these picks with explicit human
# judgment. Aliases run BEFORE the embedding pass; an exact alias hit
# is treated identically to an exact YAML-key match (no API call). Keep
# the table conservative — only add entries the team has chosen for
# unambiguous everyday phrasings, not for fine-grained nuance the
# embedding fallback handles fine on its own.
#
# Format: free-text token (lowercased on lookup) → YAML key. Both
# sides must match exactly in case (left lowercased, right matches
# YAML literal).
_OCCASION_ALIASES: dict[str, str] = {
    # Generic wedding → ceremony itself (the central, most formal stage
    # of the cycle). Specific stages stay under their own keys.
    "wedding": "wedding_ceremony",
    "shaadi": "wedding_ceremony",
    "marriage": "wedding_ceremony",
    "beach_wedding": "wedding_ceremony",
    "destination_wedding": "wedding_ceremony",
    # Generic office → daily office MNC (the most common modern
    # workplace vibe; planner emits this when no sub-cue exists).
    # Specific sub-occasions (interview, business_meeting, formal_office)
    # stay under their own keys.
    "office": "daily_office_mnc",
    "work": "daily_office_mnc",
    "workplace": "daily_office_mnc",
    "everyday_office": "daily_office_mnc",
    "daily_office": "daily_office_mnc",
    # Generic casual → everyday casual. Embedding sometimes picks
    # casual_lunch which over-narrows to a meal context.
    "casual": "everyday_casual",
    "daily_wear": "everyday_casual",
    "everyday": "everyday_casual",
}


# Same idea for weather: planners sometimes emit free-text weather
# descriptions. Canonical YAML keys are bucket names like hot_humid,
# warm_temperate, etc. Embedding usually picks well, but a few common
# mismatches benefit from explicit aliases.
_WEATHER_ALIASES: dict[str, str] = {
    "hot": "hot_humid",
    "humid": "hot_humid",
    "tropical": "hot_humid",
    "beach": "hot_humid",
    "warm": "warm_temperate",
    "mild": "mild_pleasant",
    "cool": "cool_dry",
    "cold": "cold_dry",
    "rainy": "monsoon_warm",
    "monsoon": "monsoon_warm",
}


# May 9 2026 (engine-acceptance RCA): the architect prompt declares
# risk_tolerance as ``conservative | balanced | expressive`` but the
# archetype.yaml ``risk_tolerance`` block uses
# ``conservative | moderate | adventurous``. ``conservative`` matches
# exactly; ``balanced`` and ``expressive`` always fall through the
# exact-match phase. The embedding fallback then has to nearest-
# neighbour against the YAML keys, which is unstable for this short,
# stylistically-overloaded vocabulary — May 9 RCA showed
# ``risk_tolerance:expressive`` as the leading yaml_gap (10 of 21
# axis-mentions across all yaml_gap fall-throughs).
#
# These aliases pin the prompt vocabulary to the YAML keys directly:
#   balanced   → moderate     (centre band, default)
#   expressive → adventurous  (bold options, statement embellishment,
#                              oversized patterns — exactly what
#                              "expressive" implies stylistically)
#
# The longer-term fix is to align the prompt and the YAML on a single
# vocabulary; until then the alias keeps the engine path open.
_RISK_TOLERANCE_ALIASES: dict[str, str] = {
    "balanced": "moderate",
    "expressive": "adventurous",
}


# Path to the pre-computed embeddings file shipped alongside this
# module. Generated by ops/scripts/build_canonical_embeddings.py and
# committed as a static artifact — cold starts don't need an API call.
_DEFAULT_EMBEDDINGS_PATH = Path(__file__).resolve().parent / "canonical_embeddings.json"


# Embedding dimension width — kept narrower than text-embedding-3-small's
# 1536 native dim to shrink the artifact to ~400KB (vs ~2.5MB at 1536).
# 256 dims is enough for occasion / weather / archetype semantic
# distinctions; the keys are short and the notes are stylistically
# distinct enough that the lower-dim space still separates cleanly.
EMBEDDING_DIMENSIONS = 256
EMBEDDING_MODEL = "text-embedding-3-small"


# ─────────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────────


# An EmbedClient is anything that takes a list of strings and returns
# a list of vectors of the same length. Tests pass a Mock; production
# wraps OpenAI's embeddings endpoint at the call site.
EmbedClient = Callable[[Sequence[str]], list[list[float]]]


@dataclass(frozen=True)
class CanonicalEmbeddings:
    """Pre-computed YAML-key embeddings, per axis.

    The four axes correspond to the input fields that need
    canonicalization (per the design discussion that drove this
    module). Keys are the canonical YAML keys; values are the
    embedding vectors. Loaded once from disk; module-cached.
    """

    occasion: Mapping[str, tuple[float, ...]]
    weather: Mapping[str, tuple[float, ...]]
    archetype: Mapping[str, tuple[float, ...]]
    risk_tolerance: Mapping[str, tuple[float, ...]]
    seasonal: Mapping[str, tuple[float, ...]]
    """SubSeason ∪ SeasonalColorGroup keys flattened into one bank.
    Both palette dimensions co-exist as candidates; the engine's
    dual-dimension exact-match runs before this fallback. When this
    fires it returns the YAML key as-is and the engine looks it up
    in whichever palette dimension contains it."""


@dataclass(frozen=True)
class CanonicalizationResult:
    """The output of canonicalize_inputs(). Carries the canonicalized
    values plus a per-axis trail (``what was raw → what was matched``,
    or None when a gap remained). The trail lets the router/orchestrator
    surface the same signal to dashboards as direct YAML gaps."""

    occasion_signal: str
    weather_context: str
    archetype: str | None
    risk_tolerance: str
    seasonal_color_group: str
    embed_calls: int
    """0 when every value exact-matched (no API call), 1 when at least
    one value needed the batched embed lookup."""

    matches: Mapping[str, tuple[str | None, float | None]]
    """{axis: (matched_key_or_None, cosine_score_or_None)} — one entry
    per axis that went through the embedding path. Empty when every
    axis exact-matched."""


# ─────────────────────────────────────────────────────────────────────────
# Loader
# ─────────────────────────────────────────────────────────────────────────


_EMBEDDINGS_CACHE: dict[Path, CanonicalEmbeddings] = {}


def load_canonical_embeddings(
    path: Path | None = None,
) -> CanonicalEmbeddings:
    """Load the pre-computed embeddings file. Module-cached.

    Returns an empty ``CanonicalEmbeddings`` if the file is missing —
    canonicalization then becomes a no-op (engine sees the raw value,
    falls through to LLM if it doesn't match a YAML key). Logged once.
    """
    p = (path or _DEFAULT_EMBEDDINGS_PATH).resolve()
    if p in _EMBEDDINGS_CACHE:
        return _EMBEDDINGS_CACHE[p]
    if not p.exists():
        _log.warning(
            "Canonical embeddings file missing at %s; canonicalization "
            "will be inert until ops/scripts/build_canonical_embeddings.py "
            "regenerates it.",
            p,
        )
        empty = CanonicalEmbeddings(
            occasion={}, weather={}, archetype={},
            risk_tolerance={}, seasonal={},
        )
        _EMBEDDINGS_CACHE[p] = empty
        return empty
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    def _to_bank(axis: str) -> Mapping[str, tuple[float, ...]]:
        return {
            str(k): tuple(float(x) for x in v)
            for k, v in (data.get(axis) or {}).items()
        }

    out = CanonicalEmbeddings(
        occasion=_to_bank("occasion"),
        weather=_to_bank("weather"),
        archetype=_to_bank("archetype"),
        risk_tolerance=_to_bank("risk_tolerance"),
        seasonal=_to_bank("seasonal"),
    )
    _EMBEDDINGS_CACHE[p] = out
    return out


def clear_embeddings_cache() -> None:
    """Drop the module-level embeddings cache. Tests use this when
    swapping a fixture file."""
    _EMBEDDINGS_CACHE.clear()


# ─────────────────────────────────────────────────────────────────────────
# Cosine helpers
# ─────────────────────────────────────────────────────────────────────────


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def _nearest(
    query: Sequence[float],
    bank: Mapping[str, Sequence[float]],
) -> tuple[str | None, float]:
    """Find the highest-cosine neighbour in the bank. Returns
    (key, score) or (None, 0.0) on an empty bank."""
    best_key: str | None = None
    best_score = -1.0
    for key, vec in bank.items():
        score = _cosine(query, vec)
        if score > best_score:
            best_score = score
            best_key = key
    if best_key is None:
        return None, 0.0
    return best_key, best_score


# ─────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────


def _record_metric_duration_safely(latency_ms: int) -> None:
    """Best-effort emit of the canonicalize duration histogram. Imports
    are local so a missing platform_core dependency in tests doesn't
    crash the canonicalize module at import time."""
    try:
        from platform_core.metrics import (
            observe_composition_canonicalize_duration,
        )
        observe_composition_canonicalize_duration(latency_ms)
    except Exception:  # noqa: BLE001 — metrics never break the pipeline
        pass


def _record_metric_axis_result_safely(axis: str, result: str) -> None:
    """Best-effort emit of the canonicalize per-axis result counter."""
    try:
        from platform_core.metrics import (
            observe_composition_canonicalize_result,
        )
        observe_composition_canonicalize_result(axis=axis, result=result)
    except Exception:  # noqa: BLE001
        pass


def _record_metric_axis_result_safely_for_all(pending, result: str) -> None:
    """When the embed API fails, every pending axis gets the same
    'api_error' result label."""
    for axis, _raw, _bank in pending:
        _record_metric_axis_result_safely(axis, result)


def _exact_match_seasonal(value: str, graph: StyleGraph) -> str | None:
    """Spec-special: seasonal_color_group can be either a 12-entry
    SubSeason key or a 4-entry SeasonalColorGroup key. Either matches."""
    if not value:
        return None
    if value in (graph.palette.get("SubSeason") or {}):
        return value
    if value in (graph.palette.get("SeasonalColorGroup") or {}):
        return value
    return None


def canonicalize_inputs(
    inputs,  # CompositionInputs — circular-import safe via duck typing
    *,
    graph: StyleGraph,
    embeddings: CanonicalEmbeddings,
    embed_client: EmbedClient | None,
    threshold: float = DEFAULT_THRESHOLD,
):
    """Return a new CompositionInputs with values canonicalized against
    the YAML key vocabulary.

    Algorithm:
    1. For each canonicalized axis, exact-match against the relevant
       YAML keys. Exact matches keep their value (no API call).
    2. Collect remaining values into a single batched embed call.
    3. For each batched value, nearest-neighbour against its axis's
       pre-computed bank. If cosine ≥ threshold, replace the input
       value with the matched YAML key. Below threshold, leave the
       raw value (engine flags it as YAML gap, router falls through
       to LLM).
    4. On embed-API failure or empty bank, leave the raw value.

    Pure-ish: the only side effect is the batched embed call, which is
    injected via ``embed_client``. Tests pass a Mock that returns
    deterministic vectors.
    """
    from .engine import CompositionInputs  # local import to avoid cycle

    raw_occasion = inputs.occasion_signal
    raw_weather = inputs.weather_context
    raw_archetype = inputs.archetype
    raw_risk = inputs.risk_tolerance
    raw_seasonal = inputs.seasonal_color_group

    # --- Exact-match phase (no API call) ---------------------------------
    # Order: YAML exact-match → alias-table fallback. Alias hits are
    # treated identically to exact matches downstream so the embedding
    # pass is skipped. The May 8 RCA finding ("wedding" → sagai_engagement
    # via cosine similarity) motivated the alias table — see
    # _OCCASION_ALIASES / _WEATHER_ALIASES above for rationale.
    exact_occasion: str | None = (
        raw_occasion if raw_occasion in graph.occasion else None
    )
    if exact_occasion is not None:
        _record_metric_axis_result_safely("occasion", "exact")
    elif raw_occasion:
        _alias = _OCCASION_ALIASES.get(raw_occasion.strip().lower())
        if _alias and _alias in graph.occasion:
            exact_occasion = _alias
            _record_metric_axis_result_safely("occasion", "alias")

    exact_weather: str | None = (
        raw_weather if raw_weather in graph.weather else None
    )
    if exact_weather is not None:
        _record_metric_axis_result_safely("weather", "exact")
    elif raw_weather:
        _w_alias = _WEATHER_ALIASES.get(raw_weather.strip().lower())
        if _w_alias and _w_alias in graph.weather:
            exact_weather = _w_alias
            _record_metric_axis_result_safely("weather", "alias")
    archetype_dim = graph.archetype.get("primary_archetype") or {}
    exact_archetype = (
        raw_archetype if raw_archetype and raw_archetype in archetype_dim else None
    )
    if exact_archetype is not None:
        _record_metric_axis_result_safely("archetype", "exact")
    risk_dim = graph.archetype.get("risk_tolerance") or {}
    exact_risk = raw_risk if raw_risk in risk_dim else None
    if exact_risk is not None:
        _record_metric_axis_result_safely("risk_tolerance", "exact")
    elif raw_risk:
        _r_alias = _RISK_TOLERANCE_ALIASES.get(raw_risk.strip().lower())
        if _r_alias and _r_alias in risk_dim:
            exact_risk = _r_alias
            _record_metric_axis_result_safely("risk_tolerance", "alias")
    exact_seasonal = _exact_match_seasonal(raw_seasonal, graph)
    if exact_seasonal is not None:
        _record_metric_axis_result_safely("seasonal", "exact")

    # --- Collect non-matching values for the batched embed call ----------
    pending: list[tuple[str, str, Mapping[str, Sequence[float]]]] = []
    if exact_occasion is None and raw_occasion:
        pending.append(("occasion", raw_occasion, embeddings.occasion))
    if exact_weather is None and raw_weather:
        pending.append(("weather", raw_weather, embeddings.weather))
    if exact_archetype is None and raw_archetype:
        # Archetype is optional — only canonicalize if it was set.
        pending.append(("archetype", raw_archetype, embeddings.archetype))
    if exact_risk is None and raw_risk:
        pending.append(("risk_tolerance", raw_risk, embeddings.risk_tolerance))
    if exact_seasonal is None and raw_seasonal:
        pending.append(("seasonal", raw_seasonal, embeddings.seasonal))

    matches: dict[str, tuple[str | None, float | None]] = {}
    embed_calls = 0

    if pending and embed_client is not None:
        texts = [v for _, v, _ in pending]
        # Count the attempt regardless of outcome so telemetry can
        # distinguish "embed succeeded but no match cleared threshold"
        # from "embed wasn't tried" (e.g. all values exact-matched).
        embed_calls = 1
        _embed_t0 = time.monotonic()
        try:
            vectors = embed_client(texts)
        except Exception as exc:  # noqa: BLE001 — never break a turn
            _log.warning(
                "canonicalize embed call failed (%d values): %s",
                len(texts), exc,
            )
            vectors = []
            _record_metric_axis_result_safely_for_all(pending, "api_error")
        _embed_ms = int((time.monotonic() - _embed_t0) * 1000)
        _record_metric_duration_safely(_embed_ms)

        if len(vectors) == len(texts):
            for (axis, _raw, bank), vec in zip(pending, vectors):
                if not bank:
                    matches[axis] = (None, None)
                    _record_metric_axis_result_safely(axis, "matched_below_threshold")
                    continue
                nearest, score = _nearest(vec, bank)
                if nearest is not None and score >= threshold:
                    matches[axis] = (nearest, score)
                    _record_metric_axis_result_safely(axis, "matched_above_threshold")
                else:
                    matches[axis] = (None, score)
                    _record_metric_axis_result_safely(axis, "matched_below_threshold")

    # --- Apply canonicalized values ---------------------------------------
    def _resolve(axis: str, exact: str | None, raw: str) -> str:
        if exact is not None:
            return exact
        if axis in matches and matches[axis][0] is not None:
            return matches[axis][0]  # type: ignore[return-value]
        return raw

    new_occasion = _resolve("occasion", exact_occasion, raw_occasion)
    new_weather = _resolve("weather", exact_weather, raw_weather)
    new_risk = _resolve("risk_tolerance", exact_risk, raw_risk)
    new_seasonal = _resolve("seasonal", exact_seasonal, raw_seasonal)

    # archetype is special: when raw is None or empty, keep it None
    # rather than substituting a canonicalized value (which would
    # promote a non-archetype free-text into an archetype).
    if exact_archetype is not None:
        new_archetype: str | None = exact_archetype
    elif raw_archetype and "archetype" in matches and matches["archetype"][0] is not None:
        new_archetype = matches["archetype"][0]
    else:
        new_archetype = raw_archetype  # may be None

    return (
        CompositionInputs(
            gender=inputs.gender,
            body_shape=inputs.body_shape,
            frame_structure=inputs.frame_structure,
            seasonal_color_group=new_seasonal,
            archetype=new_archetype,
            risk_tolerance=new_risk,
            occasion_signal=new_occasion,
            formality_hint=inputs.formality_hint,
            weather_context=new_weather,
            time_of_day=inputs.time_of_day,
            style_goal=inputs.style_goal,
            direction_id=inputs.direction_id,
            direction_label=inputs.direction_label,
            intent=inputs.intent,
        ),
        CanonicalizationResult(
            occasion_signal=new_occasion,
            weather_context=new_weather,
            archetype=new_archetype,
            risk_tolerance=new_risk,
            seasonal_color_group=new_seasonal,
            embed_calls=embed_calls,
            matches=dict(matches),
        ),
    )


# ─────────────────────────────────────────────────────────────────────────
# Default OpenAI-backed embed client (lazy-init)
# ─────────────────────────────────────────────────────────────────────────


_DEFAULT_CLIENT_HOLDER: dict[str, EmbedClient] = {}


def default_embed_client() -> EmbedClient:
    """Lazy-init OpenAI embed client wrapped as an EmbedClient callable.
    Reuses the catalog retrieval pattern (text-embedding-3-small at
    EMBEDDING_DIMENSIONS).

    Module-singleton so the OpenAI client cost is paid once per process.
    """
    if "client" in _DEFAULT_CLIENT_HOLDER:
        return _DEFAULT_CLIENT_HOLDER["client"]

    from openai import OpenAI
    from user_profiler.config import get_api_key

    raw = OpenAI(api_key=get_api_key())

    def _embed(texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = raw.embeddings.create(
            model=EMBEDDING_MODEL,
            input=list(texts),
            dimensions=EMBEDDING_DIMENSIONS,
        )
        return [list(item.embedding) for item in response.data]

    _DEFAULT_CLIENT_HOLDER["client"] = _embed
    return _embed
