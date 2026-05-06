"""Style-graph YAML loader for the composition engine.

Loads the 8 mapping tables under ``knowledge/style_graph/`` into typed,
frozen dataclasses. After load the result is pure data — no I/O, no clock,
no randomness — so downstream reduction (sub-PR 4.7b onward) can treat the
loader as a deterministic dependency.

The 8 YAMLs:

- ``occasion.yaml`` — ~45 occasions × {archetype, formality, time, seasons,
  flatters, avoid}.
- ``archetype.yaml`` — 8 dimensions (primary_archetype, blend_ratio_primary,
  risk_tolerance, formality_lean, pattern_type, comfort_boundaries, age_band,
  profession), each with their own enumeration of values.
- ``body_frame/female.yaml`` + ``body_frame/male.yaml`` — 16 body-frame
  dimensions per gender × 3-8 values per dimension.
- ``palette.yaml`` — 10 colour-system dimensions (SubSeason, ContrastLevel,
  SkinHairContrast, …).
- ``weather.yaml`` — 10 climate buckets × {description, regions, temp range,
  flatters, avoid}.
- ``query_structure.yaml`` — intent → occasion-or-anchor → outfit structure.
  Three intents: occasion_recommendation (44 occasions), pairing_request
  (4 anchor variants), fallback (1 default).
- ``pairing_rules.yaml`` — 9 relational rule groups (formality_alignment,
  color_story, …). Different shape from the others — preserved as a thin
  wrapper around the raw mapping until sub-PR 4.7d decides what shape it
  needs.

Validation at load time:

- Every attribute name appearing under ``flatters:`` or ``avoid:`` must be a
  known canonical attribute name (``garment_attributes.json``: enum_attributes
  ∪ text_attributes). Unknown names across all 8 files are collected and
  raised in a single ``StyleGraphValidationError``.
- The required top-level keys exist on each YAML (``occasion``, ``weather``,
  ``query_structure``, ``pairing_rules``) and on the body_frame YAMLs we
  expect at least ``BodyShape`` + ``FrameStructure``.
- Missing files raise ``FileNotFoundError`` with the path that failed.

Idempotency: ``load_style_graph()`` is module-cached. Repeated calls return
the same StyleGraph instance (frozen dataclasses + cached tuples make the
underlying data immutable).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml


# Walk up from this file: composition/ → agentic_application/ → src/
# → agentic_application/ → modules/ → repo root.
_REPO_ROOT = Path(__file__).resolve().parents[5]
_STYLE_GRAPH_DIR = _REPO_ROOT / "knowledge" / "style_graph"
_GARMENT_ATTRIBUTES_JSON = (
    _REPO_ROOT
    / "modules"
    / "style_engine"
    / "configs"
    / "config"
    / "garment_attributes.json"
)


class StyleGraphValidationError(ValueError):
    """Raised when style-graph YAMLs reference unknown garment attributes
    or are missing required structural fields."""


# ─────────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AttributeMapping:
    """The base shape shared by every attribute-mapping entry across the
    style graph. ``flatters`` and ``avoid`` map a canonical garment-attribute
    name to a tuple of values; both default to empty dicts (some entries
    carry only ``notes:`` and intentionally have no flatters/avoid)."""

    flatters: Mapping[str, tuple[str, ...]]
    avoid: Mapping[str, tuple[str, ...]]
    notes: str = ""


@dataclass(frozen=True)
class OccasionEntry:
    """One row in ``occasion.yaml`` — the metadata plus the attribute map."""

    name: str
    archetype: str
    formality: str
    time: str
    seasons: tuple[str, ...]
    mapping: AttributeMapping


@dataclass(frozen=True)
class WeatherEntry:
    """One climate bucket from ``weather.yaml``."""

    name: str
    description: str
    indian_regions: tuple[str, ...]
    temp_range_c: str
    mapping: AttributeMapping


@dataclass(frozen=True)
class QueryStructureEntry:
    """One occasion-or-anchor row inside ``query_structure.yaml``.

    ``cultural_variants`` is empty unless the entry carries an Indian /
    Western split (diwali, wedding_ceremony, wedding_reception). ``fills_slots``
    is empty for occasion_recommendation entries; pairing_request entries
    populate it with the slot names the architect must fill around the
    anchor."""

    name: str
    intent: str
    default_structure: str
    alternative_structures: tuple[str, ...]
    cultural_variants: Mapping[str, str]
    fills_slots: tuple[str, ...]
    mapping: AttributeMapping


@dataclass(frozen=True)
class PairingRuleGroup:
    """One of the 9 relational rule groups in ``pairing_rules.yaml``.

    Sub-PR 4.7d will likely refine this into a tighter schema once the
    composer's needs are concrete; for 4.7a we capture ``rule_type`` (the
    only field used uniformly across groups) plus the raw payload."""

    name: str
    rule_type: str
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class StyleGraph:
    """Container for all 8 loaded YAMLs.

    The body_frame / archetype / palette dimensions are nested as
    ``{dimension_name: {value_name: AttributeMapping}}``. Occasion / weather /
    query_structure flatten one level (the YAML's top-level key is implied by
    the field). Pairing_rules stays mostly raw."""

    body_frame_female: Mapping[str, Mapping[str, AttributeMapping]]
    body_frame_male: Mapping[str, Mapping[str, AttributeMapping]]
    archetype: Mapping[str, Mapping[str, AttributeMapping]]
    palette: Mapping[str, Mapping[str, AttributeMapping]]
    occasion: Mapping[str, OccasionEntry]
    weather: Mapping[str, WeatherEntry]
    query_structure: Mapping[str, Mapping[str, QueryStructureEntry]]
    pairing_rules: Mapping[str, PairingRuleGroup]
    known_attributes: frozenset[str] = field(default_factory=frozenset)


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Style graph YAML missing: {path}. Cannot load composition engine."
        )
    with open(path, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    if not isinstance(doc, dict):
        raise StyleGraphValidationError(
            f"{path}: expected top-level mapping, got {type(doc).__name__}"
        )
    return doc


def _freeze_attr_lists(raw: Any) -> Mapping[str, tuple[str, ...]]:
    """Convert a YAML ``flatters:`` / ``avoid:`` dict into an immutable
    ``{attr_name: tuple_of_values}`` mapping. Accepts the YAML's empty-dict
    case (``flatters: {}``) and missing-key case (no flatters at all)."""
    if raw is None:
        return MappingProxyType({})
    if not isinstance(raw, dict):
        raise StyleGraphValidationError(
            f"expected dict of attribute → values, got {type(raw).__name__}"
        )
    out: dict[str, tuple[str, ...]] = {}
    for attr, values in raw.items():
        if values is None:
            out[attr] = ()
            continue
        if not isinstance(values, list):
            raise StyleGraphValidationError(
                f"attribute {attr!r}: expected list of values, "
                f"got {type(values).__name__}"
            )
        # Stringify each value for stable hashing — YAML may parse some
        # numeric-looking values (e.g. age_band keys) as ints.
        out[attr] = tuple(str(v) for v in values)
    return MappingProxyType(out)


def _build_attribute_mapping(entry: Mapping[str, Any]) -> AttributeMapping:
    return AttributeMapping(
        flatters=_freeze_attr_lists(entry.get("flatters")),
        avoid=_freeze_attr_lists(entry.get("avoid")),
        notes=str(entry.get("notes") or "").strip(),
    )


def _load_known_attributes(path: Path = _GARMENT_ATTRIBUTES_JSON) -> frozenset[str]:
    if not path.exists():
        raise FileNotFoundError(
            f"garment_attributes.json missing: {path}. "
            "Cannot validate style graph attribute names."
        )
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    enum_attrs = set((doc.get("enum_attributes") or {}).keys())
    text_attrs = set(doc.get("text_attributes") or [])
    return frozenset(enum_attrs | text_attrs)


def _collect_unknown_attrs(
    label: str,
    flat_or_avoid: Mapping[str, tuple[str, ...]],
    known: frozenset[str],
    sink: list[str],
) -> None:
    for attr in flat_or_avoid:
        if attr not in known:
            sink.append(f"{label}: unknown attribute {attr!r}")


# ─────────────────────────────────────────────────────────────────────────
# Per-YAML loaders
# ─────────────────────────────────────────────────────────────────────────


def _load_attribute_dimensioned(
    doc: Mapping[str, Any],
    yaml_label: str,
    unknown_sink: list[str],
    known: frozenset[str],
) -> Mapping[str, Mapping[str, AttributeMapping]]:
    """Generic loader for the body_frame/archetype/palette shape:
    ``{dimension: {value: {flatters, avoid, notes}}}``."""
    out: dict[str, Mapping[str, AttributeMapping]] = {}
    for dim_name, values in doc.items():
        if not isinstance(values, dict):
            raise StyleGraphValidationError(
                f"{yaml_label}: dimension {dim_name!r} not a mapping"
            )
        dim_out: dict[str, AttributeMapping] = {}
        for value_name, entry in values.items():
            if not isinstance(entry, dict):
                raise StyleGraphValidationError(
                    f"{yaml_label}: {dim_name}.{value_name} not a mapping"
                )
            mapping = _build_attribute_mapping(entry)
            label = f"{yaml_label}.{dim_name}.{value_name}"
            _collect_unknown_attrs(label + ".flatters", mapping.flatters, known, unknown_sink)
            _collect_unknown_attrs(label + ".avoid", mapping.avoid, known, unknown_sink)
            dim_out[str(value_name)] = mapping
        out[str(dim_name)] = MappingProxyType(dim_out)
    return MappingProxyType(out)


def _load_occasion(
    path: Path, unknown_sink: list[str], known: frozenset[str]
) -> Mapping[str, OccasionEntry]:
    doc = _read_yaml(path)
    if "occasion" not in doc or not isinstance(doc["occasion"], dict):
        raise StyleGraphValidationError(
            f"{path}: expected top-level 'occasion:' mapping"
        )
    out: dict[str, OccasionEntry] = {}
    for name, fields in doc["occasion"].items():
        if not isinstance(fields, dict):
            raise StyleGraphValidationError(
                f"{path}: occasion.{name} not a mapping"
            )
        mapping = _build_attribute_mapping(fields)
        label = f"occasion.{name}"
        _collect_unknown_attrs(label + ".flatters", mapping.flatters, known, unknown_sink)
        _collect_unknown_attrs(label + ".avoid", mapping.avoid, known, unknown_sink)
        out[str(name)] = OccasionEntry(
            name=str(name),
            archetype=str(fields.get("archetype", "")),
            formality=str(fields.get("formality", "")),
            time=str(fields.get("time", "")),
            seasons=tuple(str(s) for s in (fields.get("seasons") or ())),
            mapping=mapping,
        )
    return MappingProxyType(out)


def _load_weather(
    path: Path, unknown_sink: list[str], known: frozenset[str]
) -> Mapping[str, WeatherEntry]:
    doc = _read_yaml(path)
    if "weather" not in doc or not isinstance(doc["weather"], dict):
        raise StyleGraphValidationError(
            f"{path}: expected top-level 'weather:' mapping"
        )
    out: dict[str, WeatherEntry] = {}
    for name, fields in doc["weather"].items():
        if not isinstance(fields, dict):
            raise StyleGraphValidationError(f"{path}: weather.{name} not a mapping")
        mapping = _build_attribute_mapping(fields)
        label = f"weather.{name}"
        _collect_unknown_attrs(label + ".flatters", mapping.flatters, known, unknown_sink)
        _collect_unknown_attrs(label + ".avoid", mapping.avoid, known, unknown_sink)
        out[str(name)] = WeatherEntry(
            name=str(name),
            description=str(fields.get("description", "")),
            indian_regions=tuple(str(r) for r in (fields.get("indian_regions") or ())),
            temp_range_c=str(fields.get("temp_range_c", "")),
            mapping=mapping,
        )
    return MappingProxyType(out)


def _load_query_structure(
    path: Path, unknown_sink: list[str], known: frozenset[str]
) -> Mapping[str, Mapping[str, QueryStructureEntry]]:
    doc = _read_yaml(path)
    if "query_structure" not in doc or not isinstance(doc["query_structure"], dict):
        raise StyleGraphValidationError(
            f"{path}: expected top-level 'query_structure:' mapping"
        )
    out: dict[str, Mapping[str, QueryStructureEntry]] = {}
    for intent, entries in doc["query_structure"].items():
        if not isinstance(entries, dict):
            raise StyleGraphValidationError(
                f"{path}: query_structure.{intent} not a mapping"
            )
        intent_out: dict[str, QueryStructureEntry] = {}
        for name, fields in entries.items():
            if not isinstance(fields, dict):
                raise StyleGraphValidationError(
                    f"{path}: query_structure.{intent}.{name} not a mapping"
                )
            mapping = _build_attribute_mapping(fields)
            label = f"query_structure.{intent}.{name}"
            _collect_unknown_attrs(label + ".flatters", mapping.flatters, known, unknown_sink)
            _collect_unknown_attrs(label + ".avoid", mapping.avoid, known, unknown_sink)
            cv = fields.get("cultural_variants") or {}
            if not isinstance(cv, dict):
                raise StyleGraphValidationError(
                    f"{label}: cultural_variants must be a mapping if present"
                )
            intent_out[str(name)] = QueryStructureEntry(
                name=str(name),
                intent=str(intent),
                default_structure=str(fields.get("default_structure", "")),
                alternative_structures=tuple(
                    str(s) for s in (fields.get("alternative_structures") or ())
                ),
                cultural_variants=MappingProxyType(
                    {str(k): str(v) for k, v in cv.items()}
                ),
                fills_slots=tuple(str(s) for s in (fields.get("fills_slots") or ())),
                mapping=mapping,
            )
        out[str(intent)] = MappingProxyType(intent_out)
    return MappingProxyType(out)


def _load_pairing_rules(path: Path) -> Mapping[str, PairingRuleGroup]:
    doc = _read_yaml(path)
    if "pairing_rules" not in doc or not isinstance(doc["pairing_rules"], dict):
        raise StyleGraphValidationError(
            f"{path}: expected top-level 'pairing_rules:' mapping"
        )
    out: dict[str, PairingRuleGroup] = {}
    for name, body in doc["pairing_rules"].items():
        if not isinstance(body, dict):
            raise StyleGraphValidationError(
                f"{path}: pairing_rules.{name} not a mapping"
            )
        out[str(name)] = PairingRuleGroup(
            name=str(name),
            rule_type=str(body.get("rule_type", "")),
            raw=MappingProxyType(body),
        )
    return MappingProxyType(out)


# ─────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────


_CACHE: dict[Path, StyleGraph] = {}


def load_style_graph(
    style_graph_dir: Path | None = None,
    *,
    garment_attributes_path: Path | None = None,
) -> StyleGraph:
    """Load and validate the 8 style-graph YAMLs.

    Pure after first call: subsequent calls with the same paths return the
    cached ``StyleGraph`` instance (the dataclasses are frozen and the inner
    mappings are ``MappingProxyType`` views over frozen dicts, so the
    returned value is safe to share).

    Raises:
        FileNotFoundError: a YAML or ``garment_attributes.json`` is missing.
        StyleGraphValidationError: structural problems or unknown attribute
            names referenced under ``flatters``/``avoid`` blocks. All
            unknown attributes across the 8 files are collected and reported
            together so a single failed load surfaces every problem at once.
    """
    style_graph_dir = (style_graph_dir or _STYLE_GRAPH_DIR).resolve()
    cache_key = style_graph_dir
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    known = _load_known_attributes(garment_attributes_path or _GARMENT_ATTRIBUTES_JSON)
    unknowns: list[str] = []

    body_frame_female_doc = _read_yaml(style_graph_dir / "body_frame" / "female.yaml")
    body_frame_male_doc = _read_yaml(style_graph_dir / "body_frame" / "male.yaml")
    archetype_doc = _read_yaml(style_graph_dir / "archetype.yaml")
    palette_doc = _read_yaml(style_graph_dir / "palette.yaml")

    body_frame_female = _load_attribute_dimensioned(
        body_frame_female_doc, "body_frame_female", unknowns, known
    )
    body_frame_male = _load_attribute_dimensioned(
        body_frame_male_doc, "body_frame_male", unknowns, known
    )
    archetype = _load_attribute_dimensioned(
        archetype_doc, "archetype", unknowns, known
    )
    palette = _load_attribute_dimensioned(palette_doc, "palette", unknowns, known)

    occasion = _load_occasion(style_graph_dir / "occasion.yaml", unknowns, known)
    weather = _load_weather(style_graph_dir / "weather.yaml", unknowns, known)
    query_structure = _load_query_structure(
        style_graph_dir / "query_structure.yaml", unknowns, known
    )
    pairing_rules = _load_pairing_rules(style_graph_dir / "pairing_rules.yaml")

    # Structural sanity checks — fail loudly if a YAML lost its anchor
    # dimensions to a typo.
    for required in ("BodyShape", "FrameStructure"):
        if required not in body_frame_female:
            raise StyleGraphValidationError(
                f"body_frame/female.yaml: missing required dimension {required!r}"
            )
        if required not in body_frame_male:
            raise StyleGraphValidationError(
                f"body_frame/male.yaml: missing required dimension {required!r}"
            )
    for required in ("primary_archetype", "risk_tolerance", "formality_lean"):
        if required not in archetype:
            raise StyleGraphValidationError(
                f"archetype.yaml: missing required dimension {required!r}"
            )
    if "SubSeason" not in palette:
        raise StyleGraphValidationError(
            "palette.yaml: missing required dimension 'SubSeason'"
        )

    if unknowns:
        raise StyleGraphValidationError(
            "Unknown garment attributes referenced in style graph:\n  - "
            + "\n  - ".join(unknowns)
        )

    graph = StyleGraph(
        body_frame_female=body_frame_female,
        body_frame_male=body_frame_male,
        archetype=archetype,
        palette=palette,
        occasion=occasion,
        weather=weather,
        query_structure=query_structure,
        pairing_rules=pairing_rules,
        known_attributes=known,
    )
    _CACHE[cache_key] = graph
    return graph


def clear_cache() -> None:
    """Drop the module-level load cache. Tests use this to force re-reads
    when verifying validation paths."""
    _CACHE.clear()
