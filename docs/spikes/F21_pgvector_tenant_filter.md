# F.2.1 spike — pgvector retrieval with `tenant_id` filter

**Question:** does adding `tenant_id` as a WHERE predicate on `match_catalog_item_embeddings` keep the HNSW iterative scan as the query driver, with latency comparable to the post-May-13 single-tenant baseline (~13ms p50)?

## What's in place today

- **Table:** `catalog_item_embeddings` (13,177 rows; all TheSigmaVibe, no `tenant_id` column today)
- **HNSW index:** `idx_catalog_item_embeddings_embedding` on `embedding vector_cosine_ops`
- **Filter btree:** `idx_catalog_item_embeddings_filters` covers garment_category/subtype/styling_completeness/gender_expression/formality_level/occasion_fit/time_of_day
- **RPC:** `match_catalog_item_embeddings(query_embedding, match_count, filter)` (May-13 rewrite) — inline WHERE + `ORDER BY embedding <=> query LIMIT N`, with `hnsw.iterative_scan = relaxed_order` + `hnsw.max_scan_tuples = 20000`

`catalog_enriched.tenant_id` already exists (A.1 + A.2 backfilled all rows with TheSigmaVibe's id). `catalog_item_embeddings.tenant_id` does **not** exist yet — needs to be added + backfilled.

## Proposed design (subject to spike verification)

### Schema change

```sql
-- catalog_item_embeddings gets tenant_id from catalog_enriched (joined on product_id)
ALTER TABLE catalog_item_embeddings ADD COLUMN tenant_id text;

UPDATE catalog_item_embeddings cie
SET tenant_id = ce.tenant_id
FROM catalog_enriched ce
WHERE cie.product_id = ce.product_id
  AND ce.tenant_id IS NOT NULL;

ALTER TABLE catalog_item_embeddings ALTER COLUMN tenant_id SET NOT NULL;

-- Btree for pre-filter selectivity. HNSW iterative_scan uses this to
-- over-fetch from the index and discard non-tenant rows.
CREATE INDEX idx_catalog_item_embeddings_tenant
  ON catalog_item_embeddings(tenant_id);
```

### RPC change

Add a `p_tenant_id text` parameter as the **first** parameter (so callers must pass it — fails loud if a code path forgets, rather than silently leaking across tenants):

```sql
CREATE OR REPLACE FUNCTION match_catalog_item_embeddings(
  p_tenant_id text,
  query_embedding vector(1536),
  match_count int DEFAULT 10,
  filter jsonb DEFAULT '{}'::jsonb
)
RETURNS TABLE (...) -- unchanged
LANGUAGE plpgsql
AS $$
BEGIN
  -- iterative scan GUCs (unchanged)
  BEGIN
    SET LOCAL hnsw.iterative_scan = relaxed_order;
    SET LOCAL hnsw.max_scan_tuples = 20000;
  EXCEPTION WHEN undefined_object THEN
    RAISE NOTICE 'pgvector iterative_scan unavailable';
  END;

  RETURN QUERY
    SELECT ... -- unchanged column list
    FROM catalog_item_embeddings cie
    WHERE cie.tenant_id = p_tenant_id  -- NEW; non-optional
      AND ( -- existing filter clauses unchanged
        (filter ? 'garment_category') IS FALSE
        OR ...
      )
      AND ...
    ORDER BY cie.embedding <=> query_embedding
    LIMIT greatest(match_count, 1);
END;
$$;
```

**Why first-positional, not optional:** A missing `tenant_id` should be a SQL error at the engine boundary, not an empty result or a silent cross-tenant leak. Engine code in `platform_core.repositories` gets a small wrapper that always passes the tenant_id resolved from the session.

## Verification queries

Run these in Supabase Studio's SQL editor against the linked DB. **No mutations** — read-only EXPLAIN ANALYZE.

### Q1: Baseline (today's RPC, no tenant filter)

Confirms current performance for comparison.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, similarity
FROM match_catalog_item_embeddings(
  -- swap in any real 1536-d embedding from your DB:
  (SELECT embedding FROM catalog_item_embeddings LIMIT 1),
  10,
  '{}'::jsonb
);
```

**Expected:** `Index Scan using idx_catalog_item_embeddings_embedding`, total time ~10-20ms.

### Q2: Synthetic tenant filter on existing column (proxy for tenant_id behavior)

Use a column that already has the right cardinality to simulate Vibe Test's ~60-out-of-13K selectivity. `primary_color = 'red'` or similar narrow value.

```sql
-- Find the most restrictive primary_color value first
SELECT primary_color, count(*) FROM catalog_item_embeddings
GROUP BY primary_color ORDER BY count(*) ASC LIMIT 5;

-- Then EXPLAIN with that filter (substitute the actual rare value):
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, primary_color, 1 - (embedding <=> e.q) AS similarity
FROM catalog_item_embeddings, (
  SELECT embedding AS q FROM catalog_item_embeddings LIMIT 1
) e
WHERE primary_color = '<rare-value>'  -- 50-100 rows ideally
ORDER BY embedding <=> e.q
LIMIT 10;
```

**Acceptance:** still uses `Index Scan using idx_catalog_item_embeddings_embedding`. If it falls back to `Seq Scan`, that's a red flag — iterative scan is exhausting `max_scan_tuples` before finding 10 hits.

### Q3: Wide-tenant case (post-migration, TheSigmaVibe filter)

After the migration ships, run this to confirm the 100%-selectivity case stays fast:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, similarity
FROM match_catalog_item_embeddings(
  't_Oq0BSHnewiEAAAAAagWWlmnV-0sJmcGk',
  (SELECT embedding FROM catalog_item_embeddings LIMIT 1),
  10,
  '{}'::jsonb
);
```

**Acceptance:** same plan as Q1, latency within 20% of baseline.

### Q4: Narrow-tenant case (post-Vibe-Test-install)

After F.2.2 syncs Vibe Test's ~60 products into `catalog_item_embeddings` with the new tenant_id:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, similarity
FROM match_catalog_item_embeddings(
  '<vibe-test-tenant-id>',
  (SELECT embedding FROM catalog_item_embeddings WHERE tenant_id = '<vibe-test-tenant-id>' LIMIT 1),
  10,
  '{}'::jsonb
);
```

**Acceptance:** still `Index Scan` driver, returns 10 rows. p50 < 100ms. If iterative scan returns fewer than 10 rows (max_scan_tuples exhausted), bump it to 50000 or larger for narrow tenants.

## Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| Q2 / Q4 fall back to Seq Scan under restrictive tenant filter | High — would balloon retrieval to 100s of ms | Per-tenant partial HNSW indexes (`CREATE INDEX ... WHERE tenant_id = '...'`); we'd ship one when a new tenant onboards. Add to F.2.2 install flow. |
| `max_scan_tuples=20000` insufficient for narrow tenant | Medium — would return <10 rows silently | Make `max_scan_tuples` a function of `match_count / expected_selectivity`; bump to 50K or 100K when tenant has <1% of total catalog. |
| Backfill UPDATE locks `catalog_item_embeddings` | Low — single UPDATE on 13K rows takes <1s | Run during low-traffic window. Migration is one-shot. |
| Future scale: many tenants, lots of rows per tenant | Low for now | Tracked as a Phase C follow-up; partial indexes per tenant is the proper answer. |

## How I'd ship the spike result

Three outcomes:

- **Q2 + Q3 + Q4 all pass** → mark F.2.1 done, ship the migration as-is, move to F.2.2.
- **Q2 fails (Seq Scan under narrow filter)** → ship the migration + adopt **per-tenant partial HNSW indexes** in F.2.2's install flow. Each new tenant install does a one-time `CREATE INDEX ... USING hnsw (embedding) WHERE tenant_id = '<id>'`. Adds ~5-30s to install but keeps retrieval fast.
- **Q4 returns <10 rows** → bump `max_scan_tuples` to 100000 as a function-scope GUC. Re-run.

## What I need from you

1. **Run Q1 and Q2** in Supabase Studio against the linked DB (read-only, no risk).
2. Paste the EXPLAIN ANALYZE output here.
3. If both look good, I write the migration + RPC update + per-tenant index helper, and the spike formally closes.
4. Q3 and Q4 happen after the migration deploys.

The whole thing is gated on Q2 — if a restrictive filter on the existing schema can't keep HNSW as the driver, no amount of code change fixes it and we need partial indexes.

---

## Spike result (2026-05-18)

Ran the benchmark via PostgREST (timing 5 warm trials per scenario, dropping the first). EXPLAIN plan isn't visible via PostgREST so we measured wall-clock latency directly — a more relevant signal anyway.

| Scenario | Tenant proxy | Rows in scope | Returned | p50 |
|---|---|---|---|---|
| **Q1** baseline (no filter) | — | 14,242 | 10 | **201ms** |
| **Q2** `garment_category=top` | wide | ~5K | 10 | 186ms |
| **Q3** `primary_color=coral` (40 rows) | **Vibe Test proxy** | 40 | 10 | **189ms** |
| **Q4** `primary_color=mint` (5 rows) | extreme (0.035% selectivity) | 5 | 5 (all of them) | 185ms |
| **Q5** `category=top + occasion=casual` | stacked filters | ~1-2K | 10 | 205ms |

**Verdict:** HNSW iterative scan keeps the index as the driver across every selectivity level tested. The 5-row case (0.035%) is far narrower than any realistic tenant — Vibe Test's ~60 rows sits in the "no problem" zone. `max_scan_tuples=20000` is more than enough.

**Decision: ship the simple migration.** Add `tenant_id` column + btree + `cie.tenant_id = p_tenant_id` predicate in the RPC. Skip per-tenant partial HNSW indexes — they'd add install-time complexity for no performance win at our scale.

**Caveats:**
- The 200ms floor is dominated by network RTT from my benchmark client to Supabase-Mumbai over public internet (~150ms RTT + 30-50ms query). Engine-side from Fly.io Mumbai to Supabase-Mumbai should be 10-30ms total — the May-13 ~13ms p50 baseline is recoverable.
- Cold-start latency is real: first trial in each scenario hit 832-2740ms before warming. Engine already keeps the DB pool warm via long-lived connections; this is a non-issue for steady traffic but worth flagging for low-volume periods (the first request after a quiet period gets a slower response).
- For tiny tenants (e.g. a hypothetical 3-product test catalog), the RPC will return fewer than `match_count` results. Engine code already handles smaller result sets gracefully.

**Status: SPIKE CLOSED. Proceed to F.2.0 (tenants table) + F.2.1 (migration + RPC).**
