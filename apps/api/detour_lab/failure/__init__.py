"""Adversarial Failure Laboratory (Gate 6).

The package is deliberately small and one-directional:

``model``   typed fault, experiment and status contracts
``faults``   validation and the closed kind-to-operation mapping
``engine``   isolated state construction and authoritative re-analysis
``suite``    explicitly defined, deterministic fault suites
``compare``  baseline-versus-fault robustness metrics with stated denominators
``service``  orchestration, persistence and replay

No module here computes a verdict. They prepare inputs and then call
:func:`detour_lab.analysis.run.run_analysis`, which remains the only producer of
accessibility outcomes.
"""

from __future__ import annotations

from detour_lab.failure.compare import RobustnessSummary, summarise_robustness
from detour_lab.failure.engine import execute_experiment
from detour_lab.failure.faults import FaultValidationError, validate_faults
from detour_lab.failure.model import (
    EngineeringObservation,
    ExperimentLimits,
    ExperimentOutcome,
    ExperimentStatus,
    FaultDefinition,
    FaultKind,
)
from detour_lab.failure.suite import SUITES, available_suites, build_suite

__all__ = [
    "SUITES",
    "EngineeringObservation",
    "ExperimentLimits",
    "ExperimentOutcome",
    "ExperimentStatus",
    "FaultDefinition",
    "FaultKind",
    "FaultValidationError",
    "RobustnessSummary",
    "available_suites",
    "build_suite",
    "execute_experiment",
    "summarise_robustness",
    "validate_faults",
]