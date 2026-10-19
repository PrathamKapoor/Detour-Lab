"""Bounded "Fix This Plan" optimisation (MASTER_PROMPT §7).

The package is deliberately split:

* :mod:`library`    - immutable, validated intervention data;
* :mod:`generator`  - eligibility, preconditions, deterministic enumeration;
* :mod:`verify`     - candidate materialisation + real-engine verification;
* :mod:`rank`       - lexicographic ranking, Pareto set, honest status;
* :mod:`service`    - one persisted, replayable search;
* :mod:`promotion`  - explicit, transactional apply-to-branch.

Nothing here computes verdicts: every candidate is verified by
``analysis.run.run_analysis`` and every reported number comes from that output.
"""

from __future__ import annotations

from detour_lab.optimization.library import (
    InterventionLibrary,
    LibraryError,
    load_intervention_library,
)
from detour_lab.optimization.model import SearchConfig, SearchOutcome
from detour_lab.optimization.promotion import PromotionError, promote_proposal
from detour_lab.optimization.service import SearchInputError, run_search

__all__ = [
    "InterventionLibrary",
    "LibraryError",
    "PromotionError",
    "SearchConfig",
    "SearchInputError",
    "SearchOutcome",
    "load_intervention_library",
    "promote_proposal",
    "run_search",
]
