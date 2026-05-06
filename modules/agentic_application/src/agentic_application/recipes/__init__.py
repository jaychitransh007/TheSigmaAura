"""Recipe library — catalog-independent outfit specifications.

This package holds the precomputation layer for the sub-3s hot path:

- ``profiles``: synthetic profile pool used as architect inputs during
  the bootstrap run. Profiles span (archetype × gender × body × palette)
  with deterministic-seeded randomness for reproducibility.
- ``grid``: bootstrap intent grid enumerating the cells that the
  recipe-bootstrap pipeline (Pre-launch Step 3) will run the slow
  pipeline against.

Downstream additions (separate PRs):

- ``library`` (Step 3): recipe schema + persistence.
- ``feasibility`` (Step 4 — see ``modules/catalog/src/catalog/feasibility/``):
  per-recipe-slot product ranking against ``catalog_enriched``.
"""
