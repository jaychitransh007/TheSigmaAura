"""F.2.2b — vision attribute enrichment via OpenAI Batch API.

Cost-bearing invariants under test (user-stated, 2026-05-18):

  1. Vision pipeline NEVER re-runs on a row that's already been
     enriched. Submit query filters out row_status='ok' AND any row
     with vision_batch_id set (in-flight in some batch).

  2. Each tenant has at most one in-flight batch. submit_pending_for_tenant
     short-circuits if an open batch exists.

  3. Already-enriched columns are NEVER overwritten when a later
     batch lands — only the vision-derived attribute columns get
     updated.

  4. On batch failure/expiry, rows are freed (vision_batch_id reset
     to NULL) so the next submit retries them.
"""
from __future__ import annotations

import json
import unittest
from io import BytesIO
from unittest.mock import MagicMock

from agentic_application.services.catalog_vision_enrichment_service import (
    CatalogVisionEnrichmentService,
)


def _make_openai_mock(*, batch_id: str = "batch_abc") -> MagicMock:
    """Fake OpenAI client with the minimum surface the service uses."""
    oc = MagicMock()
    oc.files.create.return_value = MagicMock(id="file_in")
    oc.batches.create.return_value = MagicMock(id=batch_id)
    return oc


def _make_client(
    *,
    pending_rows: list[dict] | None = None,
    in_flight_batch: dict | None = None,
) -> MagicMock:
    """Mock SupabaseRestClient. ``pending_rows`` are what
    select_many returns for the candidates query; ``in_flight_batch``
    is what's returned by the in-flight check."""
    pending_rows = list(pending_rows or [])
    client = MagicMock()

    def select_one(table, filters):
        if table == "tenant_enrichment_batches":
            return in_flight_batch
        return None

    def select_many(table, filters=None, columns="*", limit=None, **kwargs):
        if table == "catalog_enriched":
            return pending_rows[: limit or len(pending_rows)]
        if table == "tenant_enrichment_batches":
            return []
        return []

    def insert_one(table, payload):
        if table == "tenant_enrichment_batches":
            return {"id": 7, **payload}
        return payload

    client.select_one.side_effect = select_one
    client.select_many.side_effect = select_many
    client.insert_one.side_effect = insert_one
    client.update_one.return_value = {"ok": True}
    return client


class SubmitIdempotencyTests(unittest.TestCase):
    """Submit-time guardrails — these are the hot invariants."""

    def test_no_pending_rows_returns_no_op(self):
        """Tenant with zero pending rows must NOT create an OpenAI
        batch — that would burn cost on nothing."""
        client = _make_client(pending_rows=[])
        openai_client = _make_openai_mock()
        service = CatalogVisionEnrichmentService(client, openai_client=openai_client)

        result = service.submit_pending_for_tenant("t_test")

        self.assertFalse(result.submitted)
        self.assertEqual(result.row_count, 0)
        openai_client.files.create.assert_not_called()
        openai_client.batches.create.assert_not_called()

    def test_in_flight_batch_blocks_resubmit(self):
        """If a batch is already in-flight for this tenant, the
        second submit must short-circuit. Otherwise we'd create
        parallel batches and have ambiguous row→batch mapping."""
        client = _make_client(
            pending_rows=[
                {"id": 1, "description": "x", "images_0_src": "http://i", "title": "t"}
            ],
            in_flight_batch={
                "id": 99,
                "openai_batch_id": "batch_already",
                "row_count": 5,
            },
        )
        openai_client = _make_openai_mock()
        service = CatalogVisionEnrichmentService(client, openai_client=openai_client)

        result = service.submit_pending_for_tenant("t_test")

        self.assertFalse(result.submitted)
        self.assertEqual(result.openai_batch_id, "batch_already")
        openai_client.batches.create.assert_not_called()

    def test_submit_claims_rows_with_batch_id(self):
        """After submit, every pending row must be marked with the
        batch's db id so a concurrent submit can't double-enrol them."""
        client = _make_client(
            pending_rows=[
                {"id": 11, "description": "kurta", "images_0_src": "http://i", "title": "t"},
                {"id": 12, "description": "saree", "images_0_src": "http://j", "title": "t"},
            ],
        )
        openai_client = _make_openai_mock(batch_id="batch_xyz")
        service = CatalogVisionEnrichmentService(client, openai_client=openai_client)

        result = service.submit_pending_for_tenant("t_test")

        self.assertTrue(result.submitted)
        self.assertEqual(result.row_count, 2)
        self.assertEqual(result.openai_batch_id, "batch_xyz")
        # The update_one call that claims rows must use the batch's
        # db id (7 from our mock insert) and filter by row ids.
        claim_calls = [
            c for c in client.update_one.call_args_list
            if c.kwargs.get("patch", {}).get("vision_batch_id") == 7
        ]
        self.assertGreaterEqual(len(claim_calls), 1)

    def test_filters_exclude_already_enriched(self):
        """select_many candidates query must filter
        row_status='pending_enrichment' AND vision_batch_id IS NULL
        — the SQL-level guard against re-enrichment cost."""
        client = _make_client(pending_rows=[])
        openai_client = _make_openai_mock()
        service = CatalogVisionEnrichmentService(client, openai_client=openai_client)

        service.submit_pending_for_tenant("t_test")

        # Find the select_many call for catalog_enriched candidates.
        cands_call = next(
            c for c in client.select_many.call_args_list
            if c.args and c.args[0] == "catalog_enriched"
        )
        filters = cands_call.kwargs.get("filters") or {}
        self.assertEqual(filters.get("row_status"), "eq.pending_enrichment")
        self.assertEqual(filters.get("vision_batch_id"), "is.null")
        self.assertEqual(filters.get("tenant_id"), "eq.t_test")

    def test_empty_tenant_id_rejected(self):
        client = _make_client()
        service = CatalogVisionEnrichmentService(client)
        with self.assertRaises(ValueError):
            service.submit_pending_for_tenant("")


def _make_openai_for_poll(
    *,
    status: str,
    output_text: str = "",
    output_file_id: str = "file_out",
) -> MagicMock:
    oc = MagicMock()
    oc.batches.retrieve.return_value = MagicMock(
        status=status,
        output_file_id=output_file_id if status == "completed" else None,
        error_file_id=None,
        errors=None,
    )
    if output_text:
        content = MagicMock()
        content.read.return_value = output_text.encode("utf-8")
        oc.files.content.return_value = content
    return oc


def _make_poll_client(in_flight: list[dict] | None = None) -> MagicMock:
    """Client mock for poll tests — returns the supplied in-flight
    batches from select_many."""
    in_flight = list(in_flight or [])
    client = MagicMock()
    client.select_many.return_value = in_flight
    client.update_one.return_value = {"ok": True}
    return client


class PollIngestTests(unittest.TestCase):

    def test_no_in_flight_batches_returns_empty(self):
        client = _make_poll_client(in_flight=[])
        openai_client = _make_openai_for_poll(status="completed")
        service = CatalogVisionEnrichmentService(client, openai_client=openai_client)

        results = service.poll_and_ingest()

        self.assertEqual(results, [])
        openai_client.batches.retrieve.assert_not_called()

    def test_still_running_batch_left_alone(self):
        """Batch in 'in_progress' must NOT have rows freed — those
        rows are correctly claimed and the next poll picks it up."""
        client = _make_poll_client(in_flight=[
            {"id": 5, "tenant_id": "t_test", "openai_batch_id": "batch_running", "row_count": 3},
        ])
        openai_client = _make_openai_for_poll(status="in_progress")
        service = CatalogVisionEnrichmentService(client, openai_client=openai_client)

        results = service.poll_and_ingest()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].final_status, "submitted")
        # No row freeing, no status update
        for call in client.update_one.call_args_list:
            self.assertNotIn("status", call.kwargs.get("patch", {}))

    def test_completed_batch_ingests_attributes(self):
        """Successful batch → parse output, UPDATE catalog_enriched
        with the vision attribute columns, mark batch completed."""
        # One row's worth of model output. _extract_row_payload sets
        # row_status='ok' automatically.
        output_jsonl = json.dumps({
            "custom_id": "cat_42",
            "response": {
                "body": {
                    "output_text": json.dumps({
                        "GarmentCategory": "Blouse",
                        "GarmentCategory_confidence": 0.95,
                        "FabricDrape": "Fluid",
                        "FabricDrape_confidence": 0.87,
                    })
                }
            }
        })
        client = _make_poll_client(in_flight=[
            {"id": 5, "tenant_id": "t_test", "openai_batch_id": "batch_done", "row_count": 1},
        ])
        openai_client = _make_openai_for_poll(
            status="completed", output_text=output_jsonl,
        )
        service = CatalogVisionEnrichmentService(client, openai_client=openai_client)

        results = service.poll_and_ingest()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].final_status, "completed")
        self.assertEqual(results[0].rows_ingested, 1)
        # The row update must have hit catalog_enriched with the
        # vision columns + row_status='ok'.
        row_updates = [
            c for c in client.update_one.call_args_list
            if c.args and c.args[0] == "catalog_enriched"
            and c.kwargs.get("patch", {}).get("row_status") == "ok"
        ]
        self.assertGreaterEqual(len(row_updates), 1)
        patch = row_updates[0].kwargs["patch"]
        self.assertEqual(patch["GarmentCategory"], "Blouse")
        self.assertEqual(patch["FabricDrape"], "Fluid")

    def test_only_allowlisted_columns_written(self):
        """Model output containing an unexpected key must NOT cause
        that key to be written to catalog_enriched. Protects us from
        a malformed model response writing junk into the table."""
        output_jsonl = json.dumps({
            "custom_id": "cat_42",
            "response": {
                "body": {
                    "output_text": json.dumps({
                        "GarmentCategory": "Blouse",
                        "price": 99999,  # ATTACKER: try to overwrite price
                        "title": "evil",  # ATTACKER: try to rewrite title
                    })
                }
            }
        })
        client = _make_poll_client(in_flight=[
            {"id": 5, "tenant_id": "t_test", "openai_batch_id": "batch_done", "row_count": 1},
        ])
        openai_client = _make_openai_for_poll(
            status="completed", output_text=output_jsonl,
        )
        service = CatalogVisionEnrichmentService(client, openai_client=openai_client)

        service.poll_and_ingest()

        row_updates = [
            c for c in client.update_one.call_args_list
            if c.args and c.args[0] == "catalog_enriched"
            and c.kwargs.get("patch", {}).get("row_status") == "ok"
        ]
        patch = row_updates[0].kwargs["patch"]
        self.assertNotIn("price", patch)
        self.assertNotIn("title", patch)
        self.assertIn("GarmentCategory", patch)

    def test_failed_batch_frees_rows(self):
        """Batch in 'failed' state must clear vision_batch_id on its
        rows so the next submit picks them up. Otherwise a permanent
        OpenAI failure would orphan the rows forever."""
        client = _make_poll_client(in_flight=[
            {"id": 5, "tenant_id": "t_test", "openai_batch_id": "batch_bad", "row_count": 3},
        ])
        openai_client = _make_openai_for_poll(status="failed")
        service = CatalogVisionEnrichmentService(client, openai_client=openai_client)

        results = service.poll_and_ingest()

        self.assertEqual(results[0].final_status, "failed")
        # Look for the update_one that clears vision_batch_id to None.
        freed = [
            c for c in client.update_one.call_args_list
            if c.kwargs.get("patch", {}).get("vision_batch_id") is None
        ]
        self.assertGreaterEqual(len(freed), 1)

    def test_expired_batch_frees_rows(self):
        """Same as failed — expired (>24h SLA) must free rows."""
        client = _make_poll_client(in_flight=[
            {"id": 5, "tenant_id": "t_test", "openai_batch_id": "batch_old", "row_count": 3},
        ])
        openai_client = _make_openai_for_poll(status="expired")
        service = CatalogVisionEnrichmentService(client, openai_client=openai_client)

        results = service.poll_and_ingest()

        self.assertEqual(results[0].final_status, "expired")
        freed = [
            c for c in client.update_one.call_args_list
            if c.kwargs.get("patch", {}).get("vision_batch_id") is None
        ]
        self.assertGreaterEqual(len(freed), 1)

    def test_completed_without_output_file_marked_failed(self):
        """OpenAI claims completed but no output_file_id — surface
        as failure so the rows are freed for retry rather than
        sitting in 'submitted' forever."""
        client = _make_poll_client(in_flight=[
            {"id": 5, "tenant_id": "t_test", "openai_batch_id": "batch_weird", "row_count": 1},
        ])
        openai_client = MagicMock()
        openai_client.batches.retrieve.return_value = MagicMock(
            status="completed",
            output_file_id=None,
            error_file_id=None,
            errors=None,
        )
        service = CatalogVisionEnrichmentService(client, openai_client=openai_client)

        results = service.poll_and_ingest()

        self.assertEqual(results[0].final_status, "failed")
        freed = [
            c for c in client.update_one.call_args_list
            if c.kwargs.get("patch", {}).get("vision_batch_id") is None
        ]
        self.assertGreaterEqual(len(freed), 1)


if __name__ == "__main__":
    unittest.main()
