"""Composition engine — deterministic YAML reduction for the architect.

Phase 4.7 of the sub-3s latency push (see ``docs/composition_semantics.md``).
The engine replaces the architect's gpt-5.2 LLM call (~19s) with deterministic
intersect/union/avoid reduction over the 8 style-graph YAMLs (~500ms target).

Sub-PR 4.7a (this commit) introduces ``yaml_loader``: typed dataclass shapes
plus a single ``load_style_graph()`` entry point. Subsequent sub-PRs (4.7b
onward) consume these dataclasses to produce the per-direction composition.
"""
