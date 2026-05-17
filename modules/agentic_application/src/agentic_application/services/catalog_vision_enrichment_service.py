"""Vision attribute enrichment for tenant catalogs (F.2.2b).

Bootstrap (F.2.2) inserts new products with text embeddings only —
the dozens of vision-derived attribute columns (GarmentCategory,
FabricDrape, NecklineType, ...) stay NULL. This service runs the
vision pipeline against those pending rows via the OpenAI Batch API
(``/v1/responses`` endpoint, ``gpt-5-mini`` model — same primitives
as the original 14K-row enrichment at ``modules/catalog/.../enrichment``).

Why Batch API + poller (vs sync per-product):

  - ~50% cheaper per token (~$0.003/product vs ~$0.006 sync)
  - Sync would burn ~5s per product on the request thread, blocking
    Vercel-side merchant-admin requests (60s ceiling); a 100-product
    catalog would exhaust the function budget mid-page.
  - Async write happens whenever the batch lands (typically <2h, up
    to 24h SLA). Customer Vibe runs on text-only similarity during
    that window — degraded but functional.

Cost-bearing invariants (user-stated, 2026-05-18):

  - Vision pipeline NEVER re-runs on an already-enriched row. The
    submit query AND'd ``row_status = 'pending_enrichment'`` with
    ``vision_batch_id IS NULL`` so:
      * already-completed rows (row_status='ok') are excluded
      * rows in an in-flight batch (vision_batch_id != null) are excluded
  - Each tenant has at most one in-flight batch at a time. The submit
    method short-circuits if an open batch exists for the tenant.
  - Failed/expired batches free their rows so the next submit retries.

Lifecycle:

    bootstrap inserts row → row_status='pending_enrichment', vision_batch_id=NULL
                              ↓
    submit_pending_for_tenant   creates a batch, sets vision_batch_id on N rows
                              ↓
    poll_and_ingest_for_batch   OpenAI batch becomes 'completed' → parse output →
                                update catalog_enriched columns → row_status='ok'
                                                                ↓
    (failure path)              batch 'failed' or 'expired' → clear vision_batch_id,
                                row_status stays 'pending_enrichment' so a future
                                submit retries.
"""

from __future__ import annotations

import io
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from catalog.enrichment.batch_builder import build_request_body
from catalog.enrichment.config import PipelineConfig
from catalog.enrichment.response_parser import _extract_row_payload

from platform_core.supabase_rest import SupabaseRestClient

_log = logging.getLogger(__name__)


# The catalog_enriched columns the vision pipeline populates.
# Anything not in this set is treated as not-vision-derived and is
# never overwritten by the ingest step (so an operator-set field
# like price, image_url, or shopify_variant_ids isn't clobbered by
# a batch landing). Sourced from
# modules/style_engine/configs/config/garment_attributes.json's
# ATTRIBUTE_SECTIONS via document_builder.py — kept here as a literal
# allowlist so a typo in the model output can't write to an unexpected
# column.
_VISION_COLUMNS: Tuple[str, ...] = (
    "GarmentCategory",
    "GarmentSubtype",
    "PatternType",
    "PatternScale",
    "PatternDensity",
    "PatternPlacement",
    "ColorTemperature",
    "ColorSaturation",
    "ColorContrast",
    "PrimaryColor",
    "SecondaryColor",
    "FabricDrape",
    "FabricTransparency",
    "FabricSheen",
    "FabricTexture",
    "SilhouetteContour",
    "SilhouetteFit",
    "VolumeProfile",
    "MotionBehavior",
    "Weight",
    "NecklineType",
    "CollarStyle",
    "SleeveStyle",
    "SleeveLength",
    "HemlineLength",
    "HemlineShape",
    "Waistline",
    "Closure",
    "DesignElements",
    "Embellishments",
    "Occasion",
    "FormalityLevel",
    "StyleAesthetic",
    "Season",
)


@dataclass
class BatchSubmitResult:
    submitted: bool
    openai_batch_id: str
    row_count: int
    reason: str = ""


@dataclass
class BatchPollResult:
    openai_batch_id: str
    final_status: str  # 'submitted' | 'completed' | 'failed' | 'expired'
    rows_ingested: int = 0
    rows_failed: int = 0


class CatalogVisionEnrichmentService:
    """Per-tenant vision enrichment via the OpenAI Batch API."""

    def __init__(
        self,
        client: SupabaseRestClient,
        *,
        openai_client: Optional[OpenAI] = None,
        config: Optional[PipelineConfig] = None,
        # Per-batch row cap. Below the OpenAI per-file limit (50K) and
        # also keeps a single batch's failure blast-radius bounded.
        # Most install-time catalogs are well under this; for re-syncs
        # of larger merchants the submit caller would loop.
        max_rows_per_batch: int = 1000,
    ) -> None:
        self._client = client
        self._openai = openai_client
        self._config = config or PipelineConfig()
        self._max_rows = max_rows_per_batch

    # ─── Public surface ────────────────────────────────────────────────

    def submit_pending_for_tenant(self, tenant_id: str) -> BatchSubmitResult:
        """Submit pending-enrichment rows for a tenant to OpenAI Batch.

        Idempotent in two senses:
          1. If a batch is already in-flight for this tenant (status
             'submitted'), returns submitted=False without creating
             a duplicate.
          2. Already-enriched rows are excluded by the SQL predicate
             (row_status='pending_enrichment' AND vision_batch_id IS NULL).
        """
        if not tenant_id or not tenant_id.strip():
            raise ValueError("submit_pending_for_tenant: tenant_id is required")

        # Guard: never submit a second batch while one is in-flight.
        # Open batches monopolise the per-tenant lane so the row→batch
        # mapping stays unambiguous.
        in_flight = self._client.select_one(
            "tenant_enrichment_batches",
            filters={
                "tenant_id": f"eq.{tenant_id}",
                "status": "eq.submitted",
            },
        )
        if in_flight:
            return BatchSubmitResult(
                submitted=False,
                openai_batch_id=str(in_flight.get("openai_batch_id") or ""),
                row_count=int(in_flight.get("row_count") or 0),
                reason="batch already in-flight",
            )

        # Find pending rows. Excludes already-enriched rows AND rows
        # already claimed by some other batch. Limit prevents one huge
        # tenant from monopolising the org's batch tokens-per-minute.
        #
        # Pull a small overshoot so we can drop image-less rows below
        # without dropping the batch under the row cap.
        candidates_raw = self._client.select_many(
            "catalog_enriched",
            filters={
                "tenant_id": f"eq.{tenant_id}",
                "row_status": "eq.pending_enrichment",
                "vision_batch_id": "is.null",
            },
            columns="id,shopify_product_id,description,images_0_src,title",
            limit=self._max_rows,
        )
        # Vision needs at least one image — without it the model
        # returns a row-level error. Submitting an imageless row would
        # cost a slot, fail, and (because the failure-recovery sweep
        # frees vision_batch_id) get resubmitted next cycle in an
        # infinite loop. Filter at submit time so doomed rows never
        # enter a batch. Operators can clean them up by setting
        # row_status='error' + a populated error_reason via admin
        # tooling once we have one.
        candidates: List[Dict[str, Any]] = []
        skipped_no_image = 0
        for row in candidates_raw:
            img = str(row.get("images_0_src") or "").strip()
            if not img:
                skipped_no_image += 1
                continue
            candidates.append(row)
        if skipped_no_image:
            _log.warning(
                "CatalogVisionEnrichment: skipped %d rows with empty images_0_src for tenant=%s",
                skipped_no_image,
                tenant_id,
            )
        if not candidates:
            return BatchSubmitResult(
                submitted=False,
                openai_batch_id="",
                row_count=0,
                reason=(
                    f"no pending rows ({skipped_no_image} skipped: no image)"
                    if skipped_no_image
                    else "no pending rows"
                ),
            )

        # Build the JSONL input file in memory. ``build_request_body``
        # expects keys ``description`` + ``images__0__src`` / ``images__1__src``
        # (the original ops-pipeline shape). Translate from the
        # catalog_enriched column names — we only have one image URL
        # at bootstrap (images_0_src) so images__1__src stays empty.
        jsonl_lines: List[str] = []
        catalog_ids: List[int] = []
        for idx, row in enumerate(candidates):
            normalised = {
                "description": str(row.get("description") or ""),
                "images__0__src": str(row.get("images_0_src") or ""),
                "images__1__src": "",
            }
            req = {
                # custom_id is how we'll join the output back to the
                # catalog_enriched row. Pre-prefixing with the catalog
                # row id makes the join O(1) on ingestion.
                "custom_id": f"cat_{row['id']}",
                "method": "POST",
                "url": self._config.endpoint,
                "body": build_request_body(normalised, self._config),
            }
            jsonl_lines.append(json.dumps(req, ensure_ascii=True))
            catalog_ids.append(int(row["id"]))

        jsonl_bytes = ("\n".join(jsonl_lines) + "\n").encode("utf-8")

        # Upload + create the batch. The upload + create pair are
        # roughly equivalent to BatchRunner.upload_batch_file +
        # BatchRunner.create_batch in modules/catalog/.../batch_runner.py
        # — we don't reuse that class because it expects a file path
        # on disk; here the input is built in memory.
        openai_client = self._get_openai_client()
        try:
            file_obj = openai_client.files.create(
                file=("vibe_enrich.jsonl", io.BytesIO(jsonl_bytes)),
                purpose="batch",
            )
            batch = openai_client.batches.create(
                input_file_id=file_obj.id,
                endpoint=self._config.endpoint,
                completion_window=self._config.completion_window,
                metadata={"tenant_id": tenant_id, "vibe_phase": "F.2.2b"},
            )
        except Exception as exc:  # noqa: BLE001
            _log.exception(
                "CatalogVisionEnrichmentService.submit failed for tenant=%s rows=%d",
                tenant_id,
                len(catalog_ids),
            )
            raise RuntimeError(
                f"OpenAI batch submit failed: {type(exc).__name__}: {exc}"
            ) from exc

        # Persist the batch record before claiming any rows so an
        # interrupted submit can be reconciled later by looking at
        # OpenAI batch metadata.tenant_id rather than orphaned rows.
        batch_row = self._client.insert_one(
            "tenant_enrichment_batches",
            {
                "tenant_id": tenant_id,
                "openai_batch_id": batch.id,
                "status": "submitted",
                "row_count": len(catalog_ids),
                "input_file_id": file_obj.id,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        batch_db_id = int(batch_row["id"])

        # Claim the rows for this batch so a parallel submit (race) or
        # a daily-cron retry doesn't double-enrol them. The single
        # update_many call covers every row at once — there's no
        # partial-failure path here because Supabase REST returns
        # the whole patched set atomically.
        self._client.update_one(
            "catalog_enriched",
            filters={"id": f"in.({','.join(str(i) for i in catalog_ids)})"},
            patch={"vision_batch_id": batch_db_id},
        )

        _log.info(
            "CatalogVisionEnrichment: submitted batch tenant=%s openai_batch=%s rows=%d",
            tenant_id,
            batch.id,
            len(catalog_ids),
        )
        return BatchSubmitResult(
            submitted=True,
            openai_batch_id=batch.id,
            row_count=len(catalog_ids),
        )

    def poll_and_ingest(
        self,
        *,
        tenant_id: Optional[str] = None,
    ) -> List[BatchPollResult]:
        """Poll every in-flight batch (optionally filtered by tenant).

        For each ``submitted`` batch:
          - Fetch its OpenAI status.
          - If ``completed``: download the output file, parse, apply
            each row's attributes to catalog_enriched, flip the batch
            to ``completed`` and rows to ``row_status='ok'``.
          - If ``failed`` / ``expired`` / ``cancelled``: clear the rows'
            ``vision_batch_id`` so a future submit retries them; mark
            the batch row accordingly.
          - Otherwise: leave it alone (next poll picks it up).
        """
        filters: Dict[str, Any] = {"status": "eq.submitted"}
        if tenant_id:
            filters["tenant_id"] = f"eq.{tenant_id}"
        in_flight = self._client.select_many(
            "tenant_enrichment_batches",
            filters=filters,
            columns="id,tenant_id,openai_batch_id,row_count",
        )
        if not in_flight:
            return []

        results: List[BatchPollResult] = []
        openai_client = self._get_openai_client()
        for batch_row in in_flight:
            batch_db_id = int(batch_row["id"])
            openai_batch_id = str(batch_row["openai_batch_id"])
            try:
                batch = openai_client.batches.retrieve(openai_batch_id)
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    "CatalogVisionEnrichment: retrieve failed batch=%s err=%s",
                    openai_batch_id,
                    exc,
                )
                # Don't break the poll loop — try the next one.
                results.append(BatchPollResult(
                    openai_batch_id=openai_batch_id,
                    final_status="submitted",
                ))
                continue

            status = getattr(batch, "status", "")
            if status == "completed":
                results.append(
                    self._ingest_completed_batch(
                        batch_db_id=batch_db_id,
                        openai_batch_id=openai_batch_id,
                        batch=batch,
                        openai_client=openai_client,
                    )
                )
            elif status in {"failed", "expired", "cancelled"}:
                results.append(
                    self._handle_terminal_failure(
                        batch_db_id=batch_db_id,
                        openai_batch_id=openai_batch_id,
                        batch=batch,
                        status=status,
                    )
                )
            else:
                # Still in_progress / finalizing / validating —
                # nothing to do. Leave row_status + vision_batch_id
                # untouched so the next poll picks it up.
                results.append(BatchPollResult(
                    openai_batch_id=openai_batch_id,
                    final_status="submitted",
                ))
        return results

    # ─── Private helpers ───────────────────────────────────────────────

    def _get_openai_client(self) -> OpenAI:
        if self._openai is not None:
            return self._openai
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "CatalogVisionEnrichmentService: OPENAI_API_KEY not set"
            )
        self._openai = OpenAI(api_key=api_key)
        return self._openai

    def _ingest_completed_batch(
        self,
        *,
        batch_db_id: int,
        openai_batch_id: str,
        batch: Any,
        openai_client: OpenAI,
    ) -> BatchPollResult:
        output_file_id = getattr(batch, "output_file_id", None)
        if not output_file_id:
            # OpenAI claims completed but no output — treat as failure
            # so the rows are freed for retry.
            return self._handle_terminal_failure(
                batch_db_id=batch_db_id,
                openai_batch_id=openai_batch_id,
                batch=batch,
                status="failed",
                error="completed but no output_file_id",
            )

        try:
            output = openai_client.files.content(output_file_id)
            raw = output.read().decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            _log.exception(
                "CatalogVisionEnrichment: output download failed batch=%s",
                openai_batch_id,
            )
            return self._handle_terminal_failure(
                batch_db_id=batch_db_id,
                openai_batch_id=openai_batch_id,
                batch=batch,
                status="failed",
                error=f"output download failed: {type(exc).__name__}: {exc}",
            )

        rows_ingested = 0
        rows_failed = 0
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                rows_failed += 1
                continue
            custom_id = str(item.get("custom_id") or "")
            if not custom_id.startswith("cat_"):
                rows_failed += 1
                continue
            try:
                catalog_row_id = int(custom_id[len("cat_"):])
            except ValueError:
                rows_failed += 1
                continue
            payload = _extract_row_payload(item)
            if payload.get("row_status") != "ok":
                # Parse error or model error. Leave row in
                # pending_enrichment state (will be retried).
                rows_failed += 1
                continue
            # Apply only vision columns + row_status. Never write
            # other columns — they're either bootstrap-managed
            # (title/price) or webhook-managed (available_for_sale).
            patch: Dict[str, Any] = {
                "row_status": "ok",
                "error_reason": "",
            }
            for col in _VISION_COLUMNS:
                if col in payload:
                    patch[col] = payload[col]
                conf_key = f"{col}_confidence"
                if conf_key in payload:
                    patch[conf_key] = payload[conf_key]
            try:
                self._client.update_one(
                    "catalog_enriched",
                    filters={"id": f"eq.{catalog_row_id}"},
                    patch=patch,
                )
                rows_ingested += 1
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    "CatalogVisionEnrichment: row update failed id=%d err=%s",
                    catalog_row_id,
                    exc,
                )
                rows_failed += 1

        # Mark the batch completed regardless of partial-row failures —
        # the failed rows will surface in row_status checks and the
        # daily cron's resubmit will retry them (once vision_batch_id
        # is cleared). We don't clear vision_batch_id on success
        # because the row no longer matches the "pending" predicate
        # anyway (row_status='ok').
        self._client.update_one(
            "tenant_enrichment_batches",
            filters={"id": f"eq.{batch_db_id}"},
            patch={
                "status": "completed",
                "output_file_id": output_file_id,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        # Free the rows that DIDN'T ingest cleanly so they can be
        # picked up by a future submit. We do this by setting
        # vision_batch_id back to null for any row still in
        # pending_enrichment status with this batch_db_id.
        self._client.update_one(
            "catalog_enriched",
            filters={
                "vision_batch_id": f"eq.{batch_db_id}",
                "row_status": "eq.pending_enrichment",
            },
            patch={"vision_batch_id": None},
        )
        _log.info(
            "CatalogVisionEnrichment: ingested batch=%s ingested=%d failed=%d",
            openai_batch_id,
            rows_ingested,
            rows_failed,
        )
        return BatchPollResult(
            openai_batch_id=openai_batch_id,
            final_status="completed",
            rows_ingested=rows_ingested,
            rows_failed=rows_failed,
        )

    def _handle_terminal_failure(
        self,
        *,
        batch_db_id: int,
        openai_batch_id: str,
        batch: Any,
        status: str,
        error: Optional[str] = None,
    ) -> BatchPollResult:
        # Free the claimed rows so they're picked up by the next
        # submit. The batch row stays for audit (we keep all batches
        # forever — they're small).
        self._client.update_one(
            "catalog_enriched",
            filters={"vision_batch_id": f"eq.{batch_db_id}"},
            patch={"vision_batch_id": None},
        )
        error_file_id = getattr(batch, "error_file_id", None)
        error_text = error or self._summarise_batch_errors(batch)
        self._client.update_one(
            "tenant_enrichment_batches",
            filters={"id": f"eq.{batch_db_id}"},
            patch={
                "status": status if status != "cancelled" else "failed",
                "error_file_id": error_file_id,
                "error": error_text[:1000] if error_text else None,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        _log.warning(
            "CatalogVisionEnrichment: batch %s ended status=%s error=%s",
            openai_batch_id,
            status,
            error_text,
        )
        return BatchPollResult(
            openai_batch_id=openai_batch_id,
            final_status=status if status != "cancelled" else "failed",
        )

    @staticmethod
    def _summarise_batch_errors(batch: Any) -> str:
        errors = getattr(batch, "errors", None)
        if not errors:
            return ""
        data = getattr(errors, "data", None)
        if not data:
            return ""
        parts: List[str] = []
        for e in data[:3]:
            code = getattr(e, "code", "") or ""
            msg = getattr(e, "message", "") or ""
            parts.append(f"{code}: {msg}".strip(": "))
        return "; ".join(p for p in parts if p)
