"""Composer cache-key construction.

Cache key shape (see docs/phase_2_cache_design.md):

    hash(
      tenant_id,                       'default' today
      architect_direction_id,          sha1 of architect plan output
      retrieval_fingerprint,           sha1 of sorted SKU IDs returned
                                       by the architect's catalog search
      profile_cluster,                 96 buckets (same as architect)
      composer_prompt_version,         set by outfit_composer.py
    )

The architect_direction_id transitively encodes intent / occasion /
weather / style_goal / time_of_day (those went into the architect
cache key, so the same architect output → same id). We don't repeat
them in the composer key. profile_cluster IS repeated because the
composer applies its own body-harmony reasoning over the architect
direction — different body shapes within the same direction get
different item picks, so the cluster has to discriminate.
"""
from __future__ import annotations

import hashlib
from typing import Iterable, List

from ..schemas import RecommendationPlan, RetrievedSet
from .profile_cluster import ProfileCluster


def architect_direction_id(plan: RecommendationPlan) -> str:
    """SHA1 hex digest of the architect's RecommendationPlan output.

    Collapses the plan to a stable JSON form (Pydantic's model_dump_json
    is sorted-key-stable for our schemas) and hashes. Used both as the
    composer cache key component AND as a pointer the orchestrator can
    log on cache hits.
    """
    payload = plan.model_dump_json()
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def retrieval_fingerprint(retrieved_sets: Iterable[RetrievedSet]) -> str:
    """SHA1 of the sorted SKU id list across all retrieved sets.

    Catalog drift (new product added, old product disabled) → different
    sorted SKU list → different fingerprint → different cache key →
    no stale catalog references in cached outfits.
    """
    sku_ids: List[str] = []
    for rs in retrieved_sets or []:
        for product in (rs.products or []):
            pid = str(product.product_id or "").strip()
            if pid:
                sku_ids.append(pid)
    sku_ids.sort()
    payload = "|".join(sku_ids)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def build_composer_cache_key(
    *,
    tenant_id: str,
    architect_direction_id_value: str,
    retrieval_fingerprint_value: str,
    cluster: ProfileCluster,
    composer_prompt_version: str,
) -> str:
    """Compute the SHA1 hex digest used as the composer cache key.

    Pure function: no I/O, no side effects.
    """
    parts = [
        (tenant_id or "default").strip().lower(),
        architect_direction_id_value,
        retrieval_fingerprint_value,
        str(cluster),
        composer_prompt_version,
    ]
    payload = "|".join(parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def denormalised_key_fields(
    *,
    tenant_id: str,
    architect_direction_id_value: str,
    retrieval_fingerprint_value: str,
    cluster: ProfileCluster,
    composer_prompt_version: str,
    composer_model: str,
) -> dict:
    """Key fields stamped on the cache row for ops queries."""
    return {
        "tenant_id": tenant_id or "default",
        "architect_direction_id": architect_direction_id_value,
        "retrieval_fingerprint": retrieval_fingerprint_value,
        "profile_cluster": str(cluster),
        "composer_prompt_version": composer_prompt_version,
        "composer_model": composer_model,
    }
