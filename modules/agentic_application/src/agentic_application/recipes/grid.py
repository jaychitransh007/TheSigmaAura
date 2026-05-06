"""Bootstrap intent grid — the cells the recipe-bootstrap pipeline will run.

A grid cell is a (intent, archetype, occasion, season, gender) tuple.
The bootstrap pipeline (Pre-launch Step 3) iterates the grid; for each
cell it runs the existing slow architect + composer against a synthetic
profile drawn from the profile pool, normalizes the output into a
catalog-independent recipe, and writes it to the recipe library.

Occasions are loaded from ``knowledge/style_graph/occasion.yaml`` —
the canonical list (Phase 4.4 refactor, May 14 2026). Previously the
list was hardcoded here at 31 occasions and drifted from the YAML's
45+; reading the YAML eliminates that drift vector. Tests assert the
two stay in sync.

Coverage filter (``evaluate_coverage``) is a coarse pre-filter against
``catalog_enriched`` — it drops grid buckets where the catalog has too
few SKUs to support recipes for that (gender, formality) combo. Step 4
(per-recipe-slot feasibility index) does the precise per-slot matching.

Cost estimate (``estimate_cost``) uses the May 6 per-turn cost
re-baseline — see OPEN_TASKS.md "Per-turn cost re-baseline (May 6, 2026)"
for the input numbers.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Protocol

import yaml

from .profiles import ARCHETYPES, GENDERS, SyntheticProfile


# ─────────────────────────────────────────────────────────────────────────
# Occasion taxonomy
# ─────────────────────────────────────────────────────────────────────────
# Curated from prompt/outfit_architect.md (Direction Rules + occasion-
# inferred-time table) and the 8 occasion_archetype canonical values in
# user_context_attributes.json. Each occasion carries:
# - occasion_archetype: the bucket in user_context_attributes.json
# - formality:          one of {casual, smart_casual, semi_formal, formal, ceremonial}
# - time:               one of {daytime, evening, flexible}
# - seasons:            the seasons where the occasion makes sense
#                       (e.g. beach_day excludes winter)
#
# When extending this list: keep formality values in the catalog
# vocabulary (per architect prompt — `business_casual` and `ultra_formal`
# don't exist on rows and dilute matching).

ALL_SEASONS: tuple[str, ...] = ("spring", "summer", "autumn", "winter")
WARM_SEASONS: tuple[str, ...] = ("spring", "summer")
NON_WINTER: tuple[str, ...] = ("spring", "summer", "autumn")


@dataclass(frozen=True)
class OccasionSpec:
    occasion: str
    occasion_archetype: str
    formality: str
    time: str
    seasons: tuple[str, ...]


# Repo-relative path to the canonical occasion list. Resolved against
# the package install location, then walked up to the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[5]
_OCCASION_YAML = _REPO_ROOT / "knowledge" / "style_graph" / "occasion.yaml"


def _load_occasions_from_yaml(path: Path = _OCCASION_YAML) -> List[OccasionSpec]:
    """Parse occasion.yaml into a list of OccasionSpec.

    Each top-level entry under the ``occasion:`` root carries the same
    four fields the OccasionSpec dataclass needs (archetype, formality,
    time, seasons). Extra fields (`flatters`, `avoid`, `notes`) are
    skipped — those are inputs to the composition engine (4.7), not
    the bootstrap grid.

    Raises FileNotFoundError if the YAML is missing — bootstrap grid
    generation should fail loudly rather than silently use a stale
    hardcoded list.
    """
    with open(path, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    if not isinstance(doc, dict) or "occasion" not in doc:
        raise ValueError(f"{path}: expected top-level `occasion:` key, got {type(doc).__name__}")
    out: List[OccasionSpec] = []
    for name, fields in (doc["occasion"] or {}).items():
        if not isinstance(fields, dict):
            continue
        out.append(OccasionSpec(
            occasion=str(name),
            occasion_archetype=str(fields.get("archetype", "")),
            formality=str(fields.get("formality", "")),
            time=str(fields.get("time", "")),
            seasons=tuple(fields.get("seasons") or ALL_SEASONS),
        ))
    return out


# Loaded once at module import. Tests use _load_occasions_from_yaml
# directly to assert against the file without relying on import-time
# state.
OCCASIONS: List[OccasionSpec] = _load_occasions_from_yaml()


# ─────────────────────────────────────────────────────────────────────────
# Cost model
# ─────────────────────────────────────────────────────────────────────────
# Per-turn cost re-baseline (May 6 2026) for the recommendation pipeline,
# excluding try-on (bootstrap doesn't render):
#   architect (gpt-5.4)  $0.053
#   composer  (gpt-5.4)  $0.036
#   rater     (gpt-5-mini) $0.001
#   planner   (gpt-5-mini) $0.001
#   ─────────────────────────────
#   total                $0.091
# Synthetic runs see somewhat higher input tokens (no real conversation
# history compresses, but synthetic profile blob inflates) so round to
# $0.10 per cell as a defensible upper bound for budget planning.
COST_PER_CELL_USD: float = 0.10


# ─────────────────────────────────────────────────────────────────────────
# Grid cell
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class GridCell:
    cell_id: str
    intent: str
    archetype: str
    occasion: str
    occasion_archetype: str
    season: str
    gender: str
    formality: str
    time: str
    sample_profile_id: str

    def to_dict(self) -> dict:
        return asdict(self)


def enumerate_grid(
    profiles: List[SyntheticProfile],
    *,
    intents: Iterable[str] = ("occasion_recommendation", "pairing_request"),
) -> List[GridCell]:
    """Enumerate the bootstrap grid.

    Cells = (intent × archetype × occasion × season × gender), filtered
    by the occasion's allowed-seasons list and by profile-pool coverage
    of the (archetype, gender) bucket.
    """
    profile_index: dict[tuple[str, str], List[SyntheticProfile]] = {}
    for p in profiles:
        profile_index.setdefault((p.primary_archetype, p.gender), []).append(p)

    cells: List[GridCell] = []
    cell_idx = 0
    for intent in intents:
        for archetype in ARCHETYPES:
            for occasion_spec in OCCASIONS:
                for season in occasion_spec.seasons:
                    for gender in GENDERS:
                        matching_profiles = profile_index.get((archetype, gender), [])
                        if not matching_profiles:
                            continue
                        # Deterministic profile pick — first match in
                        # insertion order. The pool's first-pass loop
                        # guarantees there's always at least one.
                        profile = matching_profiles[0]
                        cells.append(GridCell(
                            cell_id=f"c_{cell_idx:05d}",
                            intent=intent,
                            archetype=archetype,
                            occasion=occasion_spec.occasion,
                            occasion_archetype=occasion_spec.occasion_archetype,
                            season=season,
                            gender=gender,
                            formality=occasion_spec.formality,
                            time=occasion_spec.time,
                            sample_profile_id=profile.profile_id,
                        ))
                        cell_idx += 1
    return cells


def estimate_cost(cells: List[GridCell]) -> dict:
    """Estimate the bootstrap LLM spend for the given cell set."""
    n = len(cells)
    return {
        "cell_count": n,
        "cost_per_cell_usd": COST_PER_CELL_USD,
        "total_cost_usd": round(n * COST_PER_CELL_USD, 2),
    }


# ─────────────────────────────────────────────────────────────────────────
# Coverage filter
# ─────────────────────────────────────────────────────────────────────────

class CatalogCoverageClient(Protocol):
    """Minimal Protocol for the coverage check; mockable in tests."""

    def count_skus_matching(
        self,
        *,
        gender: str,
        formality: str,
        occasion_archetype: Optional[str] = None,
    ) -> int: ...


@dataclass
class CoverageReport:
    cell_id: str
    bucket_key: str
    sku_count: int
    feasible: bool


def evaluate_coverage(
    cells: List[GridCell],
    catalog: CatalogCoverageClient,
    *,
    min_skus: int = 100,
) -> List[CoverageReport]:
    """Coarse coverage check: for each cell's (gender, formality) bucket,
    count SKUs matching in ``catalog_enriched``. Cells with fewer than
    ``min_skus`` matches are flagged infeasible.

    Cached by bucket — many cells share the same (gender, formality) so
    we hit the catalog once per unique bucket, not once per cell.
    """
    cache: dict[tuple[str, str], int] = {}
    reports: List[CoverageReport] = []
    for cell in cells:
        key = (cell.gender, cell.formality)
        if key not in cache:
            cache[key] = catalog.count_skus_matching(
                gender=cell.gender,
                formality=cell.formality,
            )
        sku_count = cache[key]
        reports.append(CoverageReport(
            cell_id=cell.cell_id,
            bucket_key=f"{cell.gender}/{cell.formality}",
            sku_count=sku_count,
            feasible=sku_count >= min_skus,
        ))
    return reports


# ─────────────────────────────────────────────────────────────────────────
# CSV output
# ─────────────────────────────────────────────────────────────────────────

GRID_CSV_FIELDS: List[str] = [
    "cell_id", "intent", "archetype", "occasion", "occasion_archetype",
    "season", "gender", "formality", "time", "sample_profile_id",
]


def write_grid_csv(cells: List[GridCell], path: Path) -> None:
    """Write the grid to ``path`` as CSV. Output is deterministic for a
    fixed input list, so the file is regeneratable from the script."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=GRID_CSV_FIELDS)
        writer.writeheader()
        for cell in cells:
            writer.writerow(cell.to_dict())
