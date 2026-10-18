"""Closed vocabularies for the verification engine.

Every enum here is part of the persisted/exported contract: values are stable
machine-readable identifiers, not display strings. Human-facing wording is
carried separately by explanation text so that translations never change meaning.
"""

from __future__ import annotations

from enum import StrEnum


class VerdictState(StrEnum):
    """Four-valued result of a single rule applied to a single element.

    NOT_APPLICABLE applies only to one rule proved inapplicable to one element.
    It is never a way of clearing an element with missing evidence
    (MASTER_PROMPT §5.3, PRD FR-008).
    """

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"

    @property
    def is_blocking(self) -> bool:
        """True when the state may never contribute to a model-confirmed route."""
        return self in (VerdictState.FAIL, VerdictState.UNKNOWN)


class NodeType(StrEnum):
    JUNCTION = "junction"
    CURB_INTERFACE = "curb_interface"
    CROSSING_INTERFACE = "crossing_interface"
    ACCESS_NODE = "access_node"
    ORIGIN = "origin"
    DESTINATION = "destination"


class EdgeType(StrEnum):
    SIDEWALK = "sidewalk"
    CROSSING = "crossing"
    TEMPORARY_PATH = "temporary_path"
    SHARED_USE_PATH = "shared_use_path"
    RAMP = "ramp"


class RuleScope(StrEnum):
    EDGE = "edge"
    NODE = "node"


class RuleKind(StrEnum):
    """Hard constraints gate traversal. Preference weights never may (INV-05)."""

    HARD = "hard"
    PREFERENCE = "preference"


class RuleCriticality(StrEnum):
    CRITICAL = "critical"
    ADVISORY = "advisory"


class Operator(StrEnum):
    """Whitelisted comparison operators only.

    Rules are data. There is no ``eval``, no expression language and no imported
    user code path anywhere in the engine (MASTERPROMPT §5.3).
    """

    GTE = "gte"
    LTE = "lte"
    GT = "gt"
    LT = "lt"
    EQ = "eq"
    ONE_OF = "one_of"
    EXISTS = "exists"


class ProvenanceClass(StrEnum):
    """PRD §11.1 — data categories must never be blended without provenance."""

    MEASURED = "measured"
    EXTERNAL_SOURCE = "external_source"
    DERIVED = "derived"
    ASSUMED = "assumed"
    SYNTHETIC = "synthetic"
    SYNTHETIC_FIXTURE = "synthetic_fixture"


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    DISPUTED = "disputed"


class EvidenceQuality(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReasonCode(StrEnum):
    """Stable machine-readable reason codes attached to every finding.

    These strings appear in exports and are contract-frozen once published.
    """

    # rule evaluation
    RULE_PASS = "RULE_PASS"
    RULE_FAIL = "RULE_FAIL"
    RULE_NOT_APPLICABLE = "RULE_NOT_APPLICABLE"
    RULE_UNKNOWN_ATTRIBUTE = "RULE_UNKNOWN_ATTRIBUTE"

    # evidence resolution
    NO_EVIDENCE = "NO_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    UNSUPPORTED_UNIT = "UNSUPPORTED_UNIT"
    INVALID_NUMERIC_VALUE = "INVALID_NUMERIC_VALUE"
    EVIDENCE_EXPIRED = "EVIDENCE_EXPIRED"
    EVIDENCE_NOT_VERIFIED = "EVIDENCE_NOT_VERIFIED"
    EVIDENCE_INVALIDATED = "EVIDENCE_INVALIDATED"
    NO_FRESHNESS_POLICY = "NO_FRESHNESS_POLICY"

    # graph / topology
    EDGE_CLOSED_IN_PHASE = "EDGE_CLOSED_IN_PHASE"
    EDGE_NOT_ACTIVE_IN_PHASE = "EDGE_NOT_ACTIVE_IN_PHASE"
    NODE_BLOCKED = "NODE_BLOCKED"
    NO_APPLICABLE_RULES = "NO_APPLICABLE_RULES"
    DUPLICATE_ID = "DUPLICATE_ID"
    UNKNOWN_NODE_REFERENCE = "UNKNOWN_NODE_REFERENCE"
    SELF_LOOP = "SELF_LOOP"
    CROSSING_WITHOUT_NODE = "CROSSING_WITHOUT_NODE"

    # routing / reachability
    CONFIRMED_ROUTE_FOUND = "CONFIRMED_ROUTE_FOUND"
    POSSIBLE_ROUTE_ONLY = "POSSIBLE_ROUTE_ONLY"
    NO_ROUTE = "NO_ROUTE"
    ORIGIN_NODE_MISSING = "ORIGIN_NODE_MISSING"
    DESTINATION_NODE_MISSING = "DESTINATION_NODE_MISSING"

    # provenance / reporting
    DEMO_RULEPACK_NOT_LEGAL = "DEMO_RULEPACK_NOT_LEGAL"
    SYNTHETIC_DATA_NOTICE = "SYNTHETIC_DATA_NOTICE"
    NOT_CERTIFIED = "NOT_CERTIFIED"


class SolverStatus(StrEnum):
    """Honest optimisation status vocabulary (PRD FR-106, MASTER_PROMPT §7.8)."""

    OPTIMAL_IN_ENUMERATED_DOMAIN = "OPTIMAL_IN_ENUMERATED_DOMAIN"
    FEASIBLE_NOT_PROVEN_OPTIMAL = "FEASIBLE_NOT_PROVEN_OPTIMAL"
    NO_FEASIBLE_IN_ENUMERATED_DOMAIN = "NO_FEASIBLE_IN_ENUMERATED_DOMAIN"
    INVALID_INPUT = "INVALID_INPUT"
    INCOMPLETE_OR_UNKNOWN = "INCOMPLETE_OR_UNKNOWN"


class CostProvenance(StrEnum):
    """Every displayed cost must say where it came from (PRD FR-104)."""

    DEMO_ONLY = "demo_only"
    USER_ENTERED = "user_entered"
    SOURCED = "sourced"
    UNKNOWN = "unknown"