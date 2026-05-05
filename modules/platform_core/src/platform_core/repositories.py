import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from .request_context import get_request_id
from .supabase_rest import SupabaseError, SupabaseRestClient

_log = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _maybe_request_id(explicit: Optional[str]) -> str:
    """Item 2 (May 1, 2026): pull the active request_id contextvar when
    the caller hasn't supplied one explicitly. Empty string when neither
    is set so the column persists a stable type."""
    if explicit:
        return explicit
    return get_request_id() or ""


class ConversationRepository:
    def __init__(self, client: SupabaseRestClient):
        self.client = client

    def get_or_create_user(self, external_user_id: str) -> Dict[str, Any]:
        row = self.client.select_one("users", filters={"external_user_id": f"eq.{external_user_id}"})
        if row:
            return row
        return self.client.insert_one("users", {"external_user_id": external_user_id})

    def get_user_by_external_user_id(self, external_user_id: str) -> Optional[Dict[str, Any]]:
        return self.client.select_one("users", filters={"external_user_id": f"eq.{external_user_id}"})

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self.client.select_one("users", filters={"id": f"eq.{user_id}"})

    def create_conversation(self, user_id: str, initial_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {
            "user_id": user_id,
            "status": "active",
            "session_context_json": initial_context or {},
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        return self.client.insert_one("conversations", payload)

    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        return self.client.select_one("conversations", filters={"id": f"eq.{conversation_id}"})

    def get_latest_conversation_for_user(
        self,
        user_id: str,
        *,
        status: str = "active",
    ) -> Optional[Dict[str, Any]]:
        rows = self.client.select_many(
            "conversations",
            filters={
                "user_id": f"eq.{user_id}",
                "status": f"eq.{status}",
            },
            order="updated_at.desc",
            limit=1,
        )
        return rows[0] if rows else None

    def merge_external_user_identity(
        self,
        *,
        canonical_external_user_id: str,
        alias_external_user_id: str,
    ) -> Dict[str, Any]:
        canonical_external = str(canonical_external_user_id or "").strip()
        alias_external = str(alias_external_user_id or "").strip()
        if not canonical_external:
            raise ValueError("canonical_external_user_id is required")
        if not alias_external or alias_external == canonical_external:
            return self.get_or_create_user(canonical_external)

        canonical_user = self.get_or_create_user(canonical_external)
        alias_user = self.get_user_by_external_user_id(alias_external)
        if not alias_user:
            return canonical_user

        alias_user_id = str(alias_user.get("id") or "").strip()
        canonical_user_id = str(canonical_user.get("id") or "").strip()
        if alias_user_id and canonical_user_id and alias_user_id != canonical_user_id:
            self.client.update_one(
                "conversations",
                filters={"user_id": f"eq.{alias_user_id}"},
                patch={"user_id": canonical_user_id, "updated_at": _now_iso()},
            )

        for table in (
            "catalog_interaction_history",
            "confidence_history",
            "policy_event_log",
            "dependency_validation_events",
        ):
            self.client.update_one(
                table,
                filters={"user_id": f"eq.{alias_external}"},
                patch={"user_id": canonical_external},
            )

        return canonical_user

    def update_conversation_context(self, conversation_id: str, session_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.client.update_one(
            "conversations",
            filters={"id": f"eq.{conversation_id}"},
            patch={"session_context_json": session_context, "updated_at": _now_iso()},
        )

    def update_user_profile(self, user_id: str, profile_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.client.update_one(
            "users",
            filters={"id": f"eq.{user_id}"},
            patch={"profile_json": profile_json, "profile_updated_at": _now_iso(), "updated_at": _now_iso()},
        )

    def create_turn(self, conversation_id: str, user_message: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "conversation_id": conversation_id,
            "user_message": user_message,
            "assistant_message": "",
            "resolved_context_json": {},
            "created_at": _now_iso(),
        }
        return self.client.insert_one("conversation_turns", payload)

    def finalize_turn(
        self,
        *,
        turn_id: str,
        assistant_message: str,
        resolved_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return self.client.update_one(
            "conversation_turns",
            filters={"id": f"eq.{turn_id}"},
            patch={
                "assistant_message": assistant_message,
                "resolved_context_json": resolved_context,
            },
        )

    def update_turn_resolved_context(
        self,
        *,
        turn_id: str,
        resolved_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return self.client.update_one(
            "conversation_turns",
            filters={"id": f"eq.{turn_id}"},
            patch={"resolved_context_json": resolved_context},
        )

    def get_latest_turn(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        rows = self.client.select_many(
            "conversation_turns",
            filters={"conversation_id": f"eq.{conversation_id}"},
            order="created_at.desc",
            limit=1,
        )
        return rows[0] if rows else None

    def get_turn(self, turn_id: str) -> Optional[Dict[str, Any]]:
        return self.client.select_one("conversation_turns", filters={"id": f"eq.{turn_id}"})

    def log_model_call(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        service: str,
        call_type: str,
        model: str,
        request_json: Dict[str, Any],
        response_json: Dict[str, Any],
        reasoning_notes: List[str],
        latency_ms: Optional[int] = None,
        status: str = "ok",
        error_message: str = "",
        request_id: Optional[str] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        estimated_cost_usd: Optional[float] = None,
        image_count: Optional[int] = None,
        redact_pii: bool = True,
    ) -> Dict[str, Any]:
        """Persist an LLM/image-gen call with token counts + cost (Item 4, May 1, 2026).

        ``prompt_tokens`` / ``completion_tokens`` / ``total_tokens``: token
        counts pulled from the provider response. Pass via
        ``platform_core.cost_estimator.extract_token_usage(response)``.

        ``estimated_cost_usd``: when omitted but token counts are present,
        the helper computes it via the central pricing table. Pass
        ``image_count`` instead for image-gen models (Gemini try-on).

        ``redact_pii`` (Item 7, May 1, 2026): when True (the default), the
        request and response JSON go through ``pii_redactor.redact_value``
        before insertion so emails / phones / SSNs in user input never
        land on disk in raw form. Pass False explicitly for debug runs
        where the full payload is needed.
        """
        from .cost_estimator import estimate_cost_usd as _estimate
        if redact_pii:
            from .pii_redactor import redact_value as _redact
            request_json = _redact(request_json)
            response_json = _redact(response_json)
            error_message = _redact(error_message) if error_message else error_message

        # Item 11 (May 1, 2026): optional body sampling. With volume,
        # storing every request_json/response_json blob in full balloons
        # the table; an env-driven sample rate keeps a representative
        # slice while replacing the rest with a tiny summary stub.
        # Default rate = 1.0 (everything stored) preserves today's
        # behaviour. Set AURA_LOG_REQUEST_BODY_SAMPLE_RATE=0.1 to keep
        # 10% of full bodies; sampled-out turns get a marker.
        import os as _os
        import random as _random

        def _maybe_sample(body: Dict[str, Any], env_var: str) -> Dict[str, Any]:
            try:
                rate = float(_os.environ.get(env_var, "1.0"))
            except ValueError:
                rate = 1.0
            if rate >= 1.0:
                return body
            if _random.random() < rate:
                return body
            return {
                "sampled_out": True,
                "model": model,
                "approx_size_chars": len(str(body or "")),
            }

        request_json = _maybe_sample(request_json, "AURA_LOG_REQUEST_BODY_SAMPLE_RATE")
        response_json = _maybe_sample(response_json, "AURA_LOG_RESPONSE_BODY_SAMPLE_RATE")
        if estimated_cost_usd is None and (prompt_tokens or completion_tokens or image_count):
            try:
                estimated_cost_usd = _estimate(
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    image_count=image_count,
                )
            except Exception:  # noqa: BLE001 — never block logging on estimator
                estimated_cost_usd = None
        payload: Dict[str, Any] = {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "service": service,
            "call_type": call_type,
            "model": model,
            "request_json": request_json,
            "response_json": response_json,
            "reasoning_notes_json": reasoning_notes,
            "status": status,
            "error_message": error_message,
            "request_id": _maybe_request_id(request_id),
            "created_at": _now_iso(),
        }
        if latency_ms is not None:
            payload["latency_ms"] = latency_ms
        if prompt_tokens is not None:
            payload["prompt_tokens"] = prompt_tokens
        if completion_tokens is not None:
            payload["completion_tokens"] = completion_tokens
        if total_tokens is not None:
            payload["total_tokens"] = total_tokens
        if estimated_cost_usd is not None:
            payload["estimated_cost_usd"] = estimated_cost_usd
        # Item 5 (May 1, 2026): mirror to Prometheus so LLM call rate /
        # latency / cost percentiles are live without re-querying the DB.
        try:
            from .metrics import observe_llm_call
            observe_llm_call(
                service=service or "unknown",
                model=model or "unknown",
                status=status or "ok",
                latency_ms=latency_ms,
                estimated_cost_usd=estimated_cost_usd,
            )
        except Exception:  # noqa: BLE001
            pass
        return self.client.insert_one("model_call_logs", payload)

    def create_feedback_event(
        self,
        *,
        user_id: str,
        conversation_id: str,
        turn_id: Optional[str] = None,
        outfit_rank: Optional[int] = None,
        garment_id: str,
        event_type: str,
        reward_value: int = 0,
        notes: str = "",
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "garment_id": garment_id,
            "event_type": event_type,
            "reward_value": reward_value,
            "notes": notes,
            "created_at": _now_iso(),
        }
        if turn_id:
            payload["turn_id"] = turn_id
        if outfit_rank is not None:
            payload["outfit_rank"] = outfit_rank
        return self.client.insert_one("feedback_events", payload)

    def list_feedback_events_for_user(
        self,
        user_id: str,
        *,
        limit: Optional[int] = 50,
    ) -> List[Dict[str, Any]]:
        """Return raw feedback rows for a user, newest first.

        Used by the profile Recent-Signals timeline; capped to a small
        window so the profile render stays cheap.
        """
        return self.client.select_many(
            "feedback_events",
            filters={"user_id": f"eq.{user_id}"},
            order="created_at.desc",
            limit=limit,
        )

    def list_disliked_product_ids_for_user(
        self,
        user_id: str,
        *,
        conversation_id: Optional[str] = None,
        limit: Optional[int] = 100,
    ) -> List[str]:
        """Return product_ids the user has disliked, newest first.

        Used at turn start to suppress previously disliked items from the
        retrieval/assembly pipeline so the same product does not keep showing
        up after a user has rejected it.
        """
        filters: Dict[str, str] = {
            "user_id": f"eq.{user_id}",
            "event_type": "eq.dislike",
        }
        if conversation_id:
            filters["conversation_id"] = f"eq.{conversation_id}"
        try:
            rows = self.client.select_many(
                "feedback_events",
                filters=filters,
                order="created_at.desc",
                limit=limit,
            )
        except Exception:
            return []
        seen: set[str] = set()
        result: List[str] = []
        for row in rows or []:
            pid = str(row.get("garment_id") or "").strip()
            if pid and pid not in seen:
                seen.add(pid)
                result.append(pid)
        return result

    def list_liked_outfit_keys(self, user_id: str) -> set:
        """Return a set of (turn_id, outfit_rank) tuples that the user has liked."""
        try:
            rows = self.client.select_many(
                "feedback_events",
                filters={
                    "user_id": f"eq.{user_id}",
                    "event_type": "eq.like",
                },
                columns="turn_id,outfit_rank",
                order="created_at.desc",
                limit=500,
            )
        except Exception:
            return set()
        result: set = set()
        for row in rows or []:
            tid = str(row.get("turn_id") or "").strip()
            rank = row.get("outfit_rank")
            if tid and rank is not None:
                result.add((tid, int(rank)))
        return result

    def list_disliked_outfit_keys(self, user_id: str) -> set:
        """Return a set of (turn_id, outfit_rank) tuples that the user has
        disliked. Used by the intent-history endpoint to filter hidden outfits."""
        try:
            rows = self.client.select_many(
                "feedback_events",
                filters={
                    "user_id": f"eq.{user_id}",
                    "event_type": "eq.dislike",
                },
                columns="turn_id,outfit_rank",
                order="created_at.desc",
                limit=500,
            )
        except Exception:
            return set()
        result: set = set()
        for row in rows or []:
            tid = str(row.get("turn_id") or "").strip()
            rank = row.get("outfit_rank")
            if tid and rank is not None:
                result.add((tid, int(rank)))
        return result

    # -- catalog attribute mapping (single source of truth) ------------------

    # Canonical mapping: snake_case prompt key → PascalCase DB column on
    # `catalog_enriched`. Single source of truth for any repo method that
    # reads enrichment attrs. PR #92 was caused by two separate mappings
    # drifting (one had snake_case DB cols, one had PascalCase) — keep
    # everything routed through this dict to prevent that recurrence.
    # When adding new attrs, add them here only.
    _CATALOG_ATTR_MAP: Dict[str, str] = {
        "title":               "title",
        "primary_color":       "PrimaryColor",
        "garment_subtype":     "GarmentSubtype",
        "color_temperature":   "ColorTemperature",
        "pattern_type":        "PatternType",
        "fit_type":            "FitType",
        "silhouette_type":     "SilhouetteType",
        "embellishment_level": "EmbellishmentLevel",
        "formality_level":     "FormalityLevel",
        "occasion_fit":        "OccasionFit",
    }

    # -- archetypal preference aggregation -----------------------------------

    # Subset of _CATALOG_ATTR_MAP used by the archetypal-axis aggregator.
    # These five categorical attrs are the ones the rater used to veto on
    # before PR #89; the other catalog map entries (title, primary_color,
    # garment_subtype, formality_level, occasion_fit) don't aggregate
    # cleanly into discrete axes — they're free-form / continuous.
    _ARCHETYPAL_AXIS_KEYS: tuple = (
        "color_temperature",
        "pattern_type",
        "fit_type",
        "silhouette_type",
        "embellishment_level",
    )
    # Min count for a value to count as a real signal vs noise. Below
    # this floor we suppress the axis entirely so the prompt doesn't
    # learn from a sample-size-of-1.
    _ARCHETYPAL_MIN_COUNT = 2
    _ARCHETYPAL_TOP_N = 3

    def aggregate_archetypal_feedback(
        self,
        user_id: str,
        *,
        lookback_days: int = 90,
        feedback_limit: int = 200,
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """Return a snapshot of which item attributes the user has
        liked / disliked, aggregated across recent feedback events.

        Output shape (R4, May 5 2026):

            {
              "disliked": {
                "color_temperature": [{"value": "warm", "count": 4}, ...],
                "pattern_type":      [{"value": "floral", "count": 3}, ...],
                ...
              },
              "liked": { same shape },
            }

        Each axis lists at most ``_ARCHETYPAL_TOP_N`` values with
        ``count >= _ARCHETYPAL_MIN_COUNT``. Below the floor we drop
        the axis entirely (so the Rater doesn't fire its veto on a
        single-data-point signal). Empty dict on no feedback / DB error.

        Implementation note: PostgREST doesn't compose joins from
        Python ergonomically, so this is two queries — one against
        feedback_events, one batch hydrate against catalog_enriched —
        then aggregate in process. Two queries is fine because the
        feedback table is small per user.
        """
        from collections import Counter
        from datetime import datetime, timedelta, timezone

        cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
        try:
            events = self.client.select_many(
                "feedback_events",
                filters={
                    "user_id": f"eq.{user_id}",
                    "event_type": "in.(like,dislike)",
                    "created_at": f"gte.{cutoff}",
                },
                columns="garment_id,event_type",
                order="created_at.desc",
                limit=feedback_limit,
            )
        except (SupabaseError, httpx.RequestError):
            # Narrow to actual DB / network failures so a logic bug
            # (KeyError, TypeError, etc.) above this `try` fails fast
            # instead of silently degrading to an empty timeline. PR #92
            # was a 400 from Supabase, which comes through SupabaseError;
            # network blips come through httpx.RequestError. Both should
            # gracefully degrade for this call.
            _log.warning(
                "aggregate_archetypal_feedback: feedback_events query failed for user_id=%s — returning empty",
                user_id, exc_info=True,
            )
            return {}
        if not events:
            return {}

        # Bucket garment_ids by event_type. Keep one row per
        # (garment, event) so a hammered like/unlike doesn't dominate.
        liked_ids: List[str] = []
        disliked_ids: List[str] = []
        seen_pairs: set[tuple[str, str]] = set()
        for ev in events:
            gid = str(ev.get("garment_id") or "").strip()
            if not gid:
                continue
            etype = str(ev.get("event_type") or "").strip()
            key = (gid, etype)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            if etype == "like":
                liked_ids.append(gid)
            elif etype == "dislike":
                disliked_ids.append(gid)
        all_ids = sorted(set(liked_ids) | set(disliked_ids))
        if not all_ids:
            return {}

        # Chunk + quote: PostgREST `in.()` filters break on bare commas
        # in product_ids and on URL-line lengths >8KB. With feedback_limit=200
        # and UUID-style ids, an unchunked filter can hit ~7.4KB. Quote
        # each id (defends against future ids with commas / parens) and
        # chunk to 50 ids per query (worst-case ~2KB per request).
        _CHUNK = 50
        column_list = "product_id," + ",".join(
            self._CATALOG_ATTR_MAP[key] for key in self._ARCHETYPAL_AXIS_KEYS
        )
        # Keyed by snake_case prompt key (not DB column) so the inner
        # aggregator and `_CATALOG_ATTR_MAP` agree on the namespace.
        attrs_by_id: Dict[str, Dict[str, str]] = {}
        try:
            for i in range(0, len(all_ids), _CHUNK):
                chunk = all_ids[i : i + _CHUNK]
                in_filter = ",".join(f'"{pid}"' for pid in chunk)
                enriched_rows = self.client.select_many(
                    "catalog_enriched",
                    filters={"product_id": f"in.({in_filter})"},
                    columns=column_list,
                )
                for row in enriched_rows or []:
                    pid = str(row.get("product_id") or "").strip()
                    if pid:
                        attrs_by_id[pid] = {
                            key: str(row.get(self._CATALOG_ATTR_MAP[key]) or "").strip().lower()
                            for key in self._ARCHETYPAL_AXIS_KEYS
                        }
        except (SupabaseError, httpx.RequestError):
            # Narrow to DB/network failures — a KeyError from a
            # _CATALOG_ATTR_MAP miss above should fail fast, not be
            # masked as an I/O error and silently return empty.
            _log.warning(
                "aggregate_archetypal_feedback: catalog_enriched hydration failed for user_id=%s — returning empty",
                user_id, exc_info=True,
            )
            return {}

        def _aggregate(ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
            counters: Dict[str, Counter] = {key: Counter() for key in self._ARCHETYPAL_AXIS_KEYS}
            for pid in ids:
                attrs = attrs_by_id.get(pid)
                if not attrs:
                    continue
                for key in self._ARCHETYPAL_AXIS_KEYS:
                    val = attrs.get(key, "")
                    if val:
                        counters[key][val] += 1
            out: Dict[str, List[Dict[str, Any]]] = {}
            for key in self._ARCHETYPAL_AXIS_KEYS:
                top = [
                    {"value": v, "count": c}
                    for v, c in counters[key].most_common(self._ARCHETYPAL_TOP_N)
                    if c >= self._ARCHETYPAL_MIN_COUNT
                ]
                if top:
                    out[key] = top
            return out

        return {"disliked": _aggregate(disliked_ids), "liked": _aggregate(liked_ids)}

    # -- episodic memory: recent user actions --------------------------------

    # Default lookback for the architect's episodic-memory input. The user
    # signed off on 30 days as the baseline; callers can override.
    RECENT_USER_ACTIONS_LOOKBACK_DAYS_DEFAULT = 30

    # Cap on the number of events surfaced to the architect prompt. The
    # raw timeline can grow large for power users; trim to the most recent
    # N events (across all event_types interleaved) so prompt size stays
    # bounded and recency dominates.
    _RECENT_USER_ACTIONS_MAX = 30

    # The catalog attribute mapping for this method is `_CATALOG_ATTR_MAP`
    # at the top of the class (PR #93, consolidating with the archetypal
    # aggregator). Don't redefine it here.

    def list_recent_user_actions(
        self,
        user_id: str,
        *,
        lookback_days: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return a chronological timeline of the user's recent like/dislike
        events for the architect's episodic-memory input.

        Each row is shaped:

            {
              "event_type": "like" | "dislike",
              "created_at": ISO-8601 string,
              "turn_id": str,
              "user_query": str,        # the message that produced the outfit
              "item": {                 # garment attributes from catalog_enriched
                "title": str, "primary_color": str, ...
              },
            }

        Empty list on cold-start users, missing wiring, or DB error — the
        architect tolerates an empty timeline (interprets as "no signal").
        """
        from datetime import datetime, timedelta, timezone

        days = int(lookback_days if lookback_days is not None else self.RECENT_USER_ACTIONS_LOOKBACK_DAYS_DEFAULT)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        try:
            events = self.client.select_many(
                "feedback_events",
                filters={
                    "user_id": f"eq.{user_id}",
                    "event_type": "in.(like,dislike)",
                    "created_at": f"gte.{cutoff}",
                },
                columns="garment_id,event_type,created_at,turn_id",
                order="created_at.desc",
                limit=self._RECENT_USER_ACTIONS_MAX,
            )
        except (SupabaseError, httpx.RequestError):
            _log.warning(
                "list_recent_user_actions: feedback_events query failed for user_id=%s — returning empty",
                user_id, exc_info=True,
            )
            return []
        if not events:
            return []

        # Hydrate garment attributes (one batched query) and turn user_messages
        # (one batched query) — same pattern as aggregate_archetypal_feedback.
        garment_ids = sorted({str(ev.get("garment_id") or "").strip() for ev in events if ev.get("garment_id")})
        turn_ids = sorted({str(ev.get("turn_id") or "").strip() for ev in events if ev.get("turn_id")})

        items_by_id: Dict[str, Dict[str, str]] = {}
        if garment_ids:
            _CHUNK = 50
            cols = "product_id," + ",".join(self._CATALOG_ATTR_MAP.values())
            try:
                for i in range(0, len(garment_ids), _CHUNK):
                    chunk = garment_ids[i : i + _CHUNK]
                    in_filter = ",".join(f'"{pid}"' for pid in chunk)
                    rows = self.client.select_many(
                        "catalog_enriched",
                        filters={"product_id": f"in.({in_filter})"},
                        columns=cols,
                    )
                    for row in rows or []:
                        pid = str(row.get("product_id") or "").strip()
                        if pid:
                            items_by_id[pid] = {
                                prompt_key: str(row.get(db_col) or "").strip()
                                for prompt_key, db_col in self._CATALOG_ATTR_MAP.items()
                            }
            except (SupabaseError, httpx.RequestError):
                # Narrow: a TypeError or KeyError inside the comprehension
                # is a logic bug we want to surface, not silently degrade
                # to empty items.
                _log.warning(
                    "list_recent_user_actions: catalog_enriched hydration failed for user_id=%s — items will be empty",
                    user_id, exc_info=True,
                )
                items_by_id = {}

        queries_by_turn: Dict[str, str] = {}
        if turn_ids:
            _CHUNK = 50
            try:
                for i in range(0, len(turn_ids), _CHUNK):
                    chunk = turn_ids[i : i + _CHUNK]
                    in_filter = ",".join(f'"{tid}"' for tid in chunk)
                    rows = self.client.select_many(
                        "conversation_turns",
                        filters={"id": f"in.({in_filter})"},
                        columns="id,user_message",
                    )
                    for row in rows or []:
                        tid = str(row.get("id") or "").strip()
                        if tid:
                            queries_by_turn[tid] = str(row.get("user_message") or "").strip()
            except (SupabaseError, httpx.RequestError):
                _log.warning(
                    "list_recent_user_actions: conversation_turns query failed for user_id=%s — events will ship without user_query",
                    user_id, exc_info=True,
                )
                queries_by_turn = {}

        timeline: List[Dict[str, Any]] = []
        for ev in events:
            gid = str(ev.get("garment_id") or "").strip()
            tid = str(ev.get("turn_id") or "").strip()
            item = items_by_id.get(gid) or {}
            if not item:
                # Skip rows we can't hydrate — opaque IDs don't help the LLM
                # find patterns. This will rarely fire if the catalog is
                # in sync with feedback_events.
                continue
            timeline.append({
                "event_type": str(ev.get("event_type") or "").strip(),
                "created_at": str(ev.get("created_at") or "").strip(),
                "turn_id": tid,
                "user_query": queries_by_turn.get(tid, ""),
                "item": item,
            })
        return timeline


    # -- saved_looks ---------------------------------------------------------

    def create_saved_look(
        self,
        *,
        user_id: str,
        conversation_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        outfit_rank: int = 1,
        title: str = "",
        item_ids: Optional[List[str]] = None,
        snapshot_json: Optional[Dict[str, Any]] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "user_id": user_id,
            "outfit_rank": int(outfit_rank or 1),
            "title": title or "",
            "item_ids": list(item_ids or []),
            "snapshot_json": snapshot_json or {},
            "notes": notes or "",
            "is_active": True,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        if turn_id:
            payload["turn_id"] = turn_id
        return self.client.insert_one("saved_looks", payload)

    def list_saved_looks_for_user(
        self,
        user_id: str,
        *,
        limit: Optional[int] = 50,
    ) -> List[Dict[str, Any]]:
        return self.client.select_many(
            "saved_looks",
            filters={
                "user_id": f"eq.{user_id}",
                "is_active": "eq.true",
            },
            order="created_at.desc",
            limit=limit,
        )

    def archive_saved_look(self, saved_look_id: str) -> Optional[Dict[str, Any]]:
        return self.client.update_one(
            "saved_looks",
            filters={"id": f"eq.{saved_look_id}"},
            patch={"is_active": False, "updated_at": _now_iso()},
        )

    # -- catalog_interaction_history ----------------------------------------

    def create_catalog_interaction(
        self,
        *,
        user_id: str,
        product_id: str,
        interaction_type: str,
        conversation_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        source_channel: str = "web",
        source_surface: str = "chat",
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "user_id": user_id,
            "product_id": product_id,
            "interaction_type": interaction_type,
            "source_channel": source_channel,
            "source_surface": source_surface,
            "metadata_json": metadata_json or {},
            "created_at": _now_iso(),
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        if turn_id:
            payload["turn_id"] = turn_id
        return self.client.insert_one("catalog_interaction_history", payload)

    def list_catalog_interactions(
        self,
        user_id: str,
        *,
        interaction_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        filters: Dict[str, str] = {"user_id": f"eq.{user_id}"}
        if interaction_type:
            filters["interaction_type"] = f"eq.{interaction_type}"
        return self.client.select_many(
            "catalog_interaction_history",
            filters=filters,
            order="created_at.desc",
            limit=limit,
        )

    # -- confidence_history --------------------------------------------------

    def create_confidence_history(
        self,
        *,
        user_id: str,
        confidence_type: str,
        score_pct: int,
        factors_json: Optional[List[Dict[str, Any]]] = None,
        conversation_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        source_channel: str = "web",
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "user_id": user_id,
            "confidence_type": confidence_type,
            "score_pct": score_pct,
            "source_channel": source_channel,
            "factors_json": factors_json or [],
            "metadata_json": metadata_json or {},
            "created_at": _now_iso(),
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        if turn_id:
            payload["turn_id"] = turn_id
        return self.client.insert_one("confidence_history", payload)

    def list_confidence_history(
        self,
        user_id: str,
        *,
        confidence_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        filters: Dict[str, str] = {"user_id": f"eq.{user_id}"}
        if confidence_type:
            filters["confidence_type"] = f"eq.{confidence_type}"
        return self.client.select_many(
            "confidence_history",
            filters=filters,
            order="created_at.desc",
            limit=limit,
        )

    # -- policy_event_log ----------------------------------------------------

    def create_policy_event(
        self,
        *,
        policy_event_type: str,
        input_class: str,
        reason_code: str,
        decision: str,
        rule_source: str = "rule",
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        source_channel: str = "web",
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "policy_event_type": policy_event_type,
            "input_class": input_class,
            "reason_code": reason_code,
            "decision": decision,
            "rule_source": rule_source,
            "source_channel": source_channel,
            "metadata_json": metadata_json or {},
            "created_at": _now_iso(),
        }
        if user_id:
            payload["user_id"] = user_id
        if conversation_id:
            payload["conversation_id"] = conversation_id
        if turn_id:
            payload["turn_id"] = turn_id
        return self.client.insert_one("policy_event_log", payload)

    def list_policy_events(
        self,
        *,
        user_id: Optional[str] = None,
        decision: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        filters: Dict[str, str] = {}
        if user_id:
            filters["user_id"] = f"eq.{user_id}"
        if decision:
            filters["decision"] = f"eq.{decision}"
        return self.client.select_many(
            "policy_event_log",
            filters=filters or None,
            order="created_at.desc",
            limit=limit,
        )

    # -- dependency_validation_events --------------------------------------

    def create_dependency_event(
        self,
        *,
        user_id: str,
        event_type: str,
        source_channel: str = "web",
        primary_intent: str = "",
        conversation_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "user_id": user_id,
            "event_type": event_type,
            "source_channel": source_channel,
            "primary_intent": primary_intent,
            "metadata_json": metadata_json or {},
            "created_at": _now_iso(),
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        if turn_id:
            payload["turn_id"] = turn_id
        return self.client.insert_one("dependency_validation_events", payload)

    def list_dependency_events(
        self,
        *,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
        source_channel: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        filters: Dict[str, str] = {}
        if user_id:
            filters["user_id"] = f"eq.{user_id}"
        if event_type:
            filters["event_type"] = f"eq.{event_type}"
        if source_channel:
            filters["source_channel"] = f"eq.{source_channel}"
        return self.client.select_many(
            "dependency_validation_events",
            filters=filters or None,
            order="created_at.asc",
            limit=limit,
        )

    # -- user_comfort_learning ------------------------------------------------

    def insert_comfort_learning_signal(self, **kwargs: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "user_id": kwargs["user_id"],
            "signal_type": kwargs["signal_type"],
            "signal_source": kwargs["signal_source"],
            "detected_seasonal_direction": kwargs["detected_seasonal_direction"],
            "created_at": _now_iso(),
        }
        for optional_key in ("garment_id", "conversation_id", "turn_id", "feedback_event_id"):
            if kwargs.get(optional_key):
                payload[optional_key] = kwargs[optional_key]
        return self.client.insert_one("user_comfort_learning", payload)

    def count_comfort_signals(self, user_id: str, signal_type: str, detected_seasonal_direction: str) -> int:
        rows = self.client.select_many(
            "user_comfort_learning",
            filters={
                "user_id": f"eq.{user_id}",
                "signal_type": f"eq.{signal_type}",
                "detected_seasonal_direction": f"eq.{detected_seasonal_direction}",
            },
        )
        return len(rows)

    def get_comfort_signals(self, user_id: str, signal_type: Optional[str] = None) -> List[Dict[str, Any]]:
        filters: Dict[str, str] = {"user_id": f"eq.{user_id}"}
        if signal_type:
            filters["signal_type"] = f"eq.{signal_type}"
        return self.client.select_many(
            "user_comfort_learning",
            filters=filters,
            order="created_at.desc",
        )

    # -- conversation & turn listing for UI --------------------------------

    def archive_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        return self.client.update_one(
            "conversations",
            filters={"id": f"eq.{conversation_id}"},
            patch={"status": "archived", "updated_at": _now_iso()},
        )

    def rename_conversation(self, conversation_id: str, title: str) -> Optional[Dict[str, Any]]:
        return self.client.update_one(
            "conversations",
            filters={"id": f"eq.{conversation_id}"},
            patch={"title": title, "updated_at": _now_iso()},
        )

    def list_conversations_for_user(
        self,
        user_id: str,
        *,
        status: str = "active",
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        filters: Dict[str, str] = {"user_id": f"eq.{user_id}"}
        if status:
            filters["status"] = f"eq.{status}"
        return self.client.select_many(
            "conversations",
            filters=filters,
            order="updated_at.desc",
            limit=limit,
        )

    def list_turns_for_conversation(
        self,
        conversation_id: str,
    ) -> List[Dict[str, Any]]:
        return self.client.select_many(
            "conversation_turns",
            filters={"conversation_id": f"eq.{conversation_id}"},
            order="created_at.asc",
        )

    def list_recent_results_for_user(
        self,
        user_id: str,
        *,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        conversations = self.client.select_many(
            "conversations",
            filters={"user_id": f"eq.{user_id}"},
            columns="id",
        )
        if not conversations:
            return []
        conv_ids = [c["id"] for c in conversations]
        turns = self.client.select_many(
            "conversation_turns",
            filters={"conversation_id": f"in.({','.join(conv_ids)})"},
            order="created_at.desc",
            limit=limit,
        )
        return [
            t for t in turns
            if t.get("resolved_context_json") and t.get("assistant_message")
        ]

    def log_tool_trace(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        tool_name: str,
        input_json: Dict[str, Any],
        output_json: Dict[str, Any],
        latency_ms: Optional[int] = None,
        status: str = "ok",
        error_message: str = "",
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "tool_name": tool_name,
            "input_json": input_json,
            "output_json": output_json,
            "status": status,
            "error_message": error_message,
            "request_id": _maybe_request_id(request_id),
            "created_at": _now_iso(),
        }
        if latency_ms is not None:
            payload["latency_ms"] = latency_ms
        return self.client.insert_one("tool_traces", payload)

    # -- virtual_tryon_images -------------------------------------------------

    def insert_tryon_image(
        self,
        *,
        user_id: str,
        conversation_id: str = "",
        turn_id: str = "",
        outfit_rank: int = 0,
        garment_ids: List[str],
        garment_source: str = "catalog",
        person_image_path: str,
        encrypted_filename: str,
        file_path: str,
        mime_type: str = "image/png",
        file_size_bytes: int = 0,
        generation_model: str = "gemini-3.1-flash-image-preview",
        quality_score_pct: Optional[int] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "user_id": user_id,
            "garment_ids": sorted(garment_ids),
            "garment_source": garment_source,
            "person_image_path": person_image_path,
            "encrypted_filename": encrypted_filename,
            "file_path": file_path,
            "mime_type": mime_type,
            "file_size_bytes": file_size_bytes,
            "generation_model": generation_model,
            "metadata_json": metadata_json or {},
            "created_at": _now_iso(),
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        if turn_id:
            payload["turn_id"] = turn_id
        if outfit_rank:
            payload["outfit_rank"] = outfit_rank
        if quality_score_pct is not None:
            payload["quality_score_pct"] = quality_score_pct
        return self.client.insert_one("virtual_tryon_images", payload)

    def find_tryon_image_by_garments(
        self,
        user_id: str,
        garment_ids: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Find an existing try-on for the same user + garment set (cache lookup)."""
        sorted_ids = sorted(garment_ids)
        # PostgreSQL array equality: {a,b} = {a,b}
        array_literal = "{" + ",".join(sorted_ids) + "}"
        rows = self.client.select_many(
            "virtual_tryon_images",
            filters={
                "user_id": f"eq.{user_id}",
                "garment_ids": f"eq.{array_literal}",
            },
            order="created_at.desc",
            limit=1,
        )
        return rows[0] if rows else None

    # -- turn_traces -----------------------------------------------------------

    def insert_turn_trace(
        self,
        *,
        turn_id: str,
        conversation_id: str,
        user_id: str,
        user_message: str = "",
        has_image: bool = False,
        image_classification: Optional[Dict[str, Any]] = None,
        primary_intent: str = "",
        intent_confidence: float = 0.0,
        action: str = "",
        reason_codes: Optional[List[str]] = None,
        profile_snapshot: Optional[Dict[str, Any]] = None,
        query_entities: Optional[Dict[str, Any]] = None,
        steps: Optional[List[Dict[str, Any]]] = None,
        evaluation: Optional[Dict[str, Any]] = None,
        total_latency_ms: Optional[int] = None,
        request_id: Optional[str] = None,
        redact_pii: bool = True,
    ) -> Dict[str, Any]:
        """Insert a unified per-turn trace after process_turn completes.

        ``redact_pii`` (Item 7, May 1, 2026): when True (default), redact
        the user_message string and fold height_cm / waist_cm /
        date_of_birth into bands before insertion. Set False explicitly
        when running a one-off debug rehearsal that needs raw values.
        """
        if redact_pii:
            from .pii_redactor import redact_string as _redact_str, redact_profile as _redact_profile
            user_message = _redact_str(user_message)
            if profile_snapshot:
                profile_snapshot = _redact_profile(profile_snapshot)
        payload: Dict[str, Any] = {
            "turn_id": turn_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "user_message": user_message,
            "has_image": has_image,
            "image_classification": image_classification or {},
            "primary_intent": primary_intent,
            "intent_confidence": intent_confidence,
            "action": action,
            "reason_codes": list(reason_codes or []),
            "profile_snapshot": profile_snapshot or {},
            "query_entities": query_entities or {},
            "steps": steps or [],
            "evaluation": evaluation or {},
            "user_response": {},
            "total_latency_ms": total_latency_ms,
            "request_id": _maybe_request_id(request_id),
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        return self.client.insert_one("turn_traces", payload)

    def delete_user_observability_data(self, external_user_id: str) -> Dict[str, int]:
        """Item 7 (May 1, 2026): GDPR data-subject deletion across observability.

        Deletes every observability row attributable to the user across
        the full audit-log set. Returns row counts per table for an
        operations log.

        Tables touched:
            turn_traces, model_call_logs, tool_traces, policy_event_log,
            feedback_events, dependency_validation_events,
            catalog_interaction_history, user_comfort_learning,
            confidence_history, virtual_tryon_images.

        ``external_user_id`` is the public-facing user_id (the one users
        and OTP flows see). The helper resolves it to the internal id
        for tables that join on the internal users.id.
        """
        user_row = self.get_user_by_external_user_id(external_user_id)
        internal_id = user_row.get("id") if user_row else None

        counts: Dict[str, int] = {}
        # Tables keyed by internal user_id.
        for table in (
            "turn_traces",
            "feedback_events",
            "dependency_validation_events",
            "catalog_interaction_history",
            "user_comfort_learning",
            "confidence_history",
            "virtual_tryon_images",
        ):
            if not internal_id:
                counts[table] = 0
                continue
            try:
                rows = self.client.select_many(
                    table, filters={"user_id": f"eq.{internal_id}"}, columns="id",
                )
                for r in rows:
                    self.client.delete_one(table, filters={"id": f"eq.{r['id']}"})
                counts[table] = len(rows)
            except Exception:
                counts[table] = -1  # signal failure

        # Tables that join only by conversation_id — find conversations first.
        try:
            conversations = (
                self.client.select_many(
                    "conversations", filters={"user_id": f"eq.{internal_id}"}, columns="id",
                )
                if internal_id else []
            )
            conversation_ids = [c["id"] for c in conversations]
        except Exception:
            conversation_ids = []

        for table in ("model_call_logs", "tool_traces", "policy_event_log"):
            counts[table] = 0
            for cid in conversation_ids:
                try:
                    rows = self.client.select_many(
                        table, filters={"conversation_id": f"eq.{cid}"}, columns="id",
                    )
                    for r in rows:
                        self.client.delete_one(table, filters={"id": f"eq.{r['id']}"})
                    counts[table] += len(rows)
                except Exception:
                    counts[table] = -1
                    break

        return counts

    def update_turn_trace_user_response(
        self,
        *,
        turn_id: str,
        user_response: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Update the user_response column on a previously-persisted trace.

        Called retroactively when the user's next signal arrives: a
        follow-up message (from the next process_turn), feedback (from
        the feedback endpoint), or a wishlist/purchase click.
        """
        try:
            return self.client.update_one(
                "turn_traces",
                filters={"turn_id": f"eq.{turn_id}"},
                patch={
                    "user_response": user_response,
                    "updated_at": _now_iso(),
                },
            )
        except Exception:
            # Best-effort: a missing trace row (e.g. turn pre-dating the
            # migration) should not break the calling code path.
            return None

    # -- wishlist (catalog_interaction_history) --------------------------------

    def list_wishlist_products(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Return deduplicated wishlisted catalog products for a user.

        Only includes ``source_surface='product_wishlist'`` (the actual
        heart button), NOT ``outfit_feedback`` (like/dislike button
        which also creates ``interaction_type='save'`` rows but includes
        wardrobe UUIDs that aren't catalog products).
        """
        interactions = self.client.select_many(
            "catalog_interaction_history",
            filters={
                "user_id": f"eq.{user_id}",
                "interaction_type": "eq.save",
                "source_surface": "eq.product_wishlist",
            },
            order="created_at.desc",
            limit=limit * 2,
        )
        # Deduplicate by product_id, keeping the most recent
        seen: dict[str, Dict[str, Any]] = {}
        for row in interactions:
            pid = str(row.get("product_id") or "").strip()
            if pid and pid not in seen:
                seen[pid] = row
        if not seen:
            return []
        # Batch hydrate from catalog_enriched — single query
        product_ids = list(seen.keys())[:limit]
        in_filter = ",".join(product_ids)
        enriched_rows = self.client.select_many(
            "catalog_enriched",
            filters={"product_id": f"in.({in_filter})"},
        )
        enriched_map: dict[str, Dict[str, Any]] = {
            str(r.get("product_id") or ""): r for r in enriched_rows
        }
        results: List[Dict[str, Any]] = []
        for pid in product_ids:
            enriched = enriched_map.get(pid)
            if not enriched:
                continue  # skip products not found in catalog
            results.append({
                "product_id": pid,
                "title": str(enriched.get("title") or pid),
                "price": str(enriched.get("price") or ""),
                "image_url": str(
                    enriched.get("images_0_src")
                    or enriched.get("images__0__src")
                    or enriched.get("primary_image_url")
                    or ""
                ),
                "product_url": str(enriched.get("url") or ""),
                "garment_category": str(enriched.get("garment_category") or ""),
                "garment_subtype": str(enriched.get("garment_subtype") or ""),
                "primary_color": str(enriched.get("primary_color") or ""),
                "wishlisted_at": str(seen[pid].get("created_at") or ""),
            })
        return results

    # -- tryon gallery (virtual_tryon_images) ----------------------------------

    def list_tryon_gallery(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent try-on renders for a user's Trial Room gallery."""
        rows = self.client.select_many(
            "virtual_tryon_images",
            filters={"user_id": f"eq.{user_id}"},
            order="created_at.desc",
            limit=limit,
        )
        return [
            {
                "id": str(row.get("id") or ""),
                "file_path": str(row.get("file_path") or ""),
                "garment_ids": list(row.get("garment_ids") or []),
                "garment_source": str(row.get("garment_source") or ""),
                "created_at": str(row.get("created_at") or ""),
            }
            for row in rows
        ]
