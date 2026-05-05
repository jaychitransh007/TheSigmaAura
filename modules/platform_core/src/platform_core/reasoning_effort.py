"""OpenAI ``reasoning.effort`` vocabulary by model family.

Per OpenAI's Responses API docs, the supported values for the
``reasoning.effort`` parameter are model-gated — different model
families accept different value sets. We centralize the mapping
here so the agent classes don't drift when a new value lands or
a model gets re-tiered.

Sources (verified May 2026):
- gpt-5 / gpt-5-mini accept ``{minimal, low, medium, high}``.
  ``none`` is rejected with: "Unsupported value: 'none' is not
  supported with the 'gpt-5' model."
- gpt-5.4 / gpt-5.5 accept ``{low, medium, high, xhigh}``.
  ``minimal`` is rejected (gpt-5-mini-only).
- gpt-5.1+ accepts ``{none, minimal, low, medium, high, xhigh}``.
  Defaults to ``none``.

When a new model lands, add a constant here rather than inlining
the set in the agent. When OpenAI changes the vocabulary, update
this module and every importing agent picks up the change.
"""

from __future__ import annotations

from typing import FrozenSet

# gpt-5 / gpt-5-mini family. ``minimal`` is the floor (closest to
# "no reasoning") supported here.
GPT5_MINI_EFFORTS: FrozenSet[str] = frozenset({"minimal", "low", "medium", "high"})

# gpt-5.4 / gpt-5.5 family. ``low`` is the floor; no ``minimal``,
# no ``none``. ``xhigh`` is the ceiling.
GPT5_MID_EFFORTS: FrozenSet[str] = frozenset({"low", "medium", "high", "xhigh"})

# gpt-5.1+ — supports the full vocabulary including ``none``
# (which behaves like a non-reasoning model). Not currently used
# by any production agent; included for completeness so future
# adopters have a constant to import.
GPT5_PLUS_EFFORTS: FrozenSet[str] = frozenset({"none", "minimal", "low", "medium", "high", "xhigh"})
