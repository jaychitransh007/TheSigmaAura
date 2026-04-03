-- Drop unused catalog_items table.
-- Replaced by catalog_enriched which stores enriched product data with garment attributes.
-- Verified: only 10 test rows, no code references the table.

DROP TABLE IF EXISTS catalog_items;
