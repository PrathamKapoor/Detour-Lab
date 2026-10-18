"""Canonical observation resolution.

The resolver is the only place where "what is the current value of this
attribute?" is answered. It implements the conservative policy demanded by the
PRD and MASTER_PROMPT §5.2:

* no eligible record            -> ``UNKNOWN`` / ``NO_EVIDENCE``
* contradictory canonical values-> ``UNKNOWN`` / ``CONFLICTING_EVIDENCE`` (all records kept)
* unusable unit                 -> ``UNKNOWN`` / ``UNSUPPORTED_UNIT``
* stale under an explicit policy-> ``UNKNOWN`` / ``EVIDENCE_EXPIRED``
* policy requires verification and it is absent -> ``UNKNOWN`` / ``EVIDENCE_NOT_VERIFIED``
* no freshness policy exists    -> never invent one; evidence simply does not expire

Nothing here ever returns ``KNOWN`` for a value that was not actually observed.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from detour_lab.domain.contracts import (
    TEXT_FIELDS,
    AttributeSpec,
    EvidenceRecord,
    ResolvedAttribute,
)
from detour_lab.domain.enums import ReasonCode, VerificationStatus
from detour_lab.domain.units import (
    UnitError,
    to_canonical_length_m,
    to_canonical_slope_percent,
    to_canonical_width_mm,
)

__all__ = ["EvidenceRegistry", "resolve_attribute"]

_QUANTITY_CONVERTERS = {
    "length_m": to_canonical_length_m,
    "width_mm": to_canonical_width_mm,
    "slope_percent": to_canonical_slope_percent,
}


class _QuantityConverter(Protocol):  # pragma: no cover - typing only
    def __call__(self, value: object, unit: str, *, field: str):
        ...


def _canonicalise_text(value: object) -> str:
    """Text values compare case-insensitively; the original stays in the record."""
    return str(value).strip().lower()


def _convert(record: EvidenceRecord, spec: AttributeSpec) -> tuple[object, str | None, dict | None, str | None]:
    """Return ``(canonical_value, canonical_unit, conversion, error_reason)``."""
    if spec.quantity == "text" or record.field in TEXT_FIELDS:
        if record.value is None:
            return None, None, None, ReasonCode.NO_EVIDENCE.value
        return _canonicalise_text(record.value), None, None, None

    if record.value is None:
        return None, None, None, ReasonCode.NO_EVIDENCE.value

    unit = record.unit
    if unit is None or unit.strip() == "":
        if spec.quantity == "slope_percent":
            # A grade without a unit is genuinely ambiguous between percent and ratio.
            return None, None, None, ReasonCode.UNSUPPORTED_UNIT.value
        return None, None, None, ReasonCode.UNSUPPORTED_UNIT.value

    converter: _QuantityConverter = _QUANTITY_CONVERTERS[spec.quantity]
    try:
        conversion = converter(record.value, unit, field=record.field)
    except UnitError as exc:
        return None, None, None, exc.code
    return conversion.canonical_value, conversion.canonical_unit, conversion.as_dict(), None


def resolve_attribute(
    *,
    element_id: str,
    field: str,
    records: Iterable[EvidenceRecord],
    spec: AttributeSpec,
    as_of: datetime | None = None,
) -> ResolvedAttribute:
    """Resolve every eligible observation for one ``(element_id, field)`` pair."""
    eligible = sorted(
        (r for r in records if not r.invalidated), key=lambda r: (r.observed_at or datetime.min.replace(tzinfo=UTC), r.id)
    )
    if not eligible:
        return ResolvedAttribute(
            element_id=element_id,
            field=field,
            known=False,
            reason_code=ReasonCode.NO_EVIDENCE,
            explanation=(
                f"No eligible evidence record exists for {field!r} on {element_id}. "
                "Missing evidence is never treated as a passing value."
            ),
        )

    conversions: list[dict] = []
    values: list[object] = []
    evidence_ids = [r.id for r in eligible]
    failures: list[tuple[EvidenceRecord, str]] = []

    for record in eligible:
        value, _unit, conversion, error = _convert(record, spec)
        if error is not None:
            failures.append((record, error))
            continue
        if conversion:
            conversions.append({"evidence_id": record.id, **conversion})
        values.append(value)

    if failures:
        codes = {code for _r, code in failures}
        reason = ReasonCode(codes.pop()) if len(codes) == 1 else ReasonCode.UNSUPPORTED_UNIT
        detail = ", ".join(f"{r.id}: {c}" for r, c in failures)
        return ResolvedAttribute(
            element_id=element_id,
            field=field,
            known=False,
            reason_code=reason,
            explanation=(
                f"{len(failures)} of {len(eligible)} evidence record(s) for {field!r} could not be interpreted "
                f"in the canonical unit ({detail}). The value is unknown, not zero and not passing."
            ),
            evidence_ids=evidence_ids,
            conversions=conversions,
        )

    distinct: list[object] = []
    for value in values:
        if value not in distinct:
            distinct.append(value)

    if len(distinct) > 1:
        return ResolvedAttribute(
            element_id=element_id,
            field=field,
            known=False,
            reason_code=ReasonCode.CONFLICTING_EVIDENCE,
            explanation=(
                f"{len(eligible)} evidence record(s) for {field!r} disagree ({distinct}). Both claims are retained "
                "and the attribute stays UNKNOWN until a reviewer records an explicit decision."
            ),
            evidence_ids=evidence_ids,
            conflicting_values=[str(v) for v in distinct],
            conversions=conversions,
        )

    chosen = eligible[0]
    canonical_value = distinct[0]

    # Freshness: only when the pack declares an explicit policy.
    policy = spec.freshness
    if policy is not None:
        if policy.requires_verified and chosen.verification_status is not VerificationStatus.VERIFIED:
            return ResolvedAttribute(
                element_id=element_id,
                field=field,
                known=False,
                reason_code=ReasonCode.EVIDENCE_NOT_VERIFIED,
                explanation=(
                    f"This rulepack requires verified evidence for {field!r}; record {chosen.id} is "
                    f"{chosen.verification_status.value}."
                ),
                evidence_ids=evidence_ids,
                conversions=conversions,
            )
        if policy.max_age_days is not None:
            if chosen.observed_at is None:
                return ResolvedAttribute(
                    element_id=element_id,
                    field=field,
                    known=False,
                    reason_code=ReasonCode.EVIDENCE_EXPIRED,
                    explanation=(
                        f"A freshness policy of {policy.max_age_days} day(s) applies to {field!r} but record "
                        f"{chosen.id} has no observed timestamp, so its age cannot be established."
                    ),
                    evidence_ids=evidence_ids,
                    conversions=conversions,
                )
            if as_of is None:
                return ResolvedAttribute(
                    element_id=element_id,
                    field=field,
                    known=False,
                    reason_code=ReasonCode.EVIDENCE_EXPIRED,
                    explanation=(
                        f"A freshness policy of {policy.max_age_days} day(s) applies to {field!r} but no "
                        "evaluation time was supplied, so staleness cannot be excluded."
                    ),
                    evidence_ids=evidence_ids,
                    conversions=conversions,
                )
            age = as_of - chosen.observed_at
            if age > timedelta(days=policy.max_age_days):
                return ResolvedAttribute(
                    element_id=element_id,
                    field=field,
                    known=False,
                    reason_code=ReasonCode.EVIDENCE_EXPIRED,
                    explanation=(
                        f"Evidence {chosen.id} for {field!r} is {age.days} day(s) old, beyond the declared "
                        f"{policy.max_age_days} day freshness policy."
                    ),
                    evidence_ids=evidence_ids,
                    conversions=conversions,
                )

    explanation = f"{field} resolved from evidence {chosen.id}"
    if conversions:
        explanation += " after an explicit recorded unit conversion"
    if policy is None:
        explanation += "; no freshness policy is declared for this attribute, so it does not expire"
    return ResolvedAttribute(
        element_id=element_id,
        field=field,
        known=True,
        value=canonical_value,
        canonical_unit=_canonical_unit_for(spec.quantity),
        reason_code=ReasonCode.RULE_PASS,
        explanation=explanation,
        evidence_ids=evidence_ids,
        conversions=conversions,
    )


def _canonical_unit_for(quantity: str) -> str:
    return {"length_m": "m", "width_mm": "mm", "slope_percent": "percent", "text": "text"}[quantity]


class EvidenceRegistry:
    """Immutable index over evidence records, shared by graph and scenario layers."""

    __slots__ = ("_by_element_field", "_by_id")

    def __init__(self, records: Iterable[EvidenceRecord]) -> None:
        by_id: dict[str, EvidenceRecord] = {}
        by_element_field: dict[tuple[str, str], list[EvidenceRecord]] = defaultdict(list)
        for record in records:
            if record.id in by_id:
                raise ValueError(f"duplicate evidence record ID {record.id!r}")
            by_id[record.id] = record
            by_element_field[(record.element_id, record.field)].append(record)
        self._by_id = dict(by_id)
        self._by_element_field = {k: tuple(v) for k, v in by_element_field.items()}

    def for_field(self, element_id: str, field: str) -> tuple[EvidenceRecord, ...]:
        return self._by_element_field.get((element_id, field), ())

    def for_element(self, element_id: str) -> tuple[EvidenceRecord, ...]:
        found: list[EvidenceRecord] = []
        for (element, _field), records in self._by_element_field.items():
            if element == element_id:
                found.extend(records)
        return tuple(sorted(found, key=lambda r: r.id))

    def by_id(self, record_id: str) -> EvidenceRecord | None:
        return self._by_id.get(record_id)

    def all_records(self) -> tuple[EvidenceRecord, ...]:
        return tuple(sorted(self._by_id.values(), key=lambda r: r.id))