-- Drop the 5-arg overload of match_catalog_item_embeddings.
--
-- Background: the May 13 iterative-HNSW rewrite
-- (20260513000000_match_embeddings_iterative_hnsw.sql) created a NEW
-- 3-arg signature `(query_embedding, match_count, filter)` rather than
-- replacing the May 7 5-arg signature
-- `(query_embedding, match_count, filter, hard_attrs, hard_penalty)`.
-- PostgreSQL's `CREATE OR REPLACE FUNCTION` only replaces a function
-- with the EXACT same signature, so both ended up coexisting.
--
-- The application calls the RPC without `hard_attrs` whenever the
-- planner/architect emits an empty hard_attrs (LLM-architect path on
-- pairing turns is the common case). PostgREST then sees two valid
-- candidates and returns PGRST203 ("Could not choose the best candidate
-- function") — the search agent catches the exception and returns 0
-- products, surfacing as the "I couldn't find a strong match" fallback
-- even when the catalog has plenty of inventory.
--
-- Fix: drop the 5-arg version. The Python re-rank
-- (`agents/catalog_search_agent._apply_hard_attr_penalty`) already
-- enforces hard_attrs against the rich `catalog_enriched` data after
-- retrieval, so the SQL-level penalty was redundant anyway — most
-- hard_attr keys aren't present on `catalog_item_embeddings.metadata_json`
-- and the SQL penalty counted 0 violations for them.

drop function if exists match_catalog_item_embeddings(
  vector(1536),  -- query_embedding
  int,           -- match_count
  jsonb,         -- filter
  jsonb,         -- hard_attrs
  double precision  -- hard_penalty
);
