"""Evidence resolution policy: B5, B6, B7, INV-01, INV-04, freshness, verification."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from detour_lab.domain.contracts import AttributeSpec, EvidenceRecord, FreshnessPolicy
from detour_lab.domain.enums import ReasonCode
from detour_lab.evidence.resolver import EvidenceRegistry, resolve_attribute
from tests.conftest import AS_OF, evidence

WIDTH = AttributeSpec(quantity="width_mm", accepted_units=["mm", "cm", "m"])
SLOPE = AttributeSpec(quantity="slope_percent", accepted_units=["percent"])
SURFACE = AttributeSpec(quantity="text")
FRESH_WIDTH = AttributeSpec(
    quantity="width_mm",
    accepted_units=["mm"],
    freshness=FreshnessPolicy(max_age_days=365, requires_verified=True),
)


def resolve(records, spec=WIDTH, element_id="E1", as_of=AS_OF):
    return resolve_attribute(element_id=element_id, field="width_mm", records=records, spec=spec, as_of=as_of)


class TestMissingEvidence:
    def test_no_evidence_is_unknown_not_zero_and_not_pass(self):
        resolved = resolve([])
        assert resolved.known is False
        assert resolved.reason_code is ReasonCode.NO_EVIDENCE
        assert resolved.value is None
        assert "never treated as a passing value" in resolved.explanation

    def test_invalidated_records_are_not_eligible(self):
        record = evidence("EV1", "E1", "width_mm", 1500, unit="mm")
        assert resolve([record]).known is True
        invalidated = record.model_copy(update={"invalidated": True})
        resolved = resolve([invalidated])
        assert resolved.known is False
        assert resolved.reason_code is ReasonCode.NO_EVIDENCE

    def test_b05_missing_attribute_evidence_is_reported_as_unknown(self):
        resolved = resolve([])
        assert resolved.known is False
        assert resolved.evidence_ids == []


class TestConflictingEvidence:
    def test_b06_conflicting_measurements_stay_unknown_and_keep_both(self):
        records = [
            evidence("EV-A", "E1", "width_mm", 1500, unit="mm"),
            evidence("EV-B", "E1", "width_mm", 900, unit="mm"),
        ]
        resolved = resolve(records)
        assert resolved.known is False
        assert resolved.reason_code is ReasonCode.CONFLICTING_EVIDENCE
        assert resolved.evidence_ids == ["EV-A", "EV-B"]
        assert sorted(resolved.conflicting_values) == ["1500", "900"]

    def test_records_agreeing_after_unit_conversion_are_not_a_conflict(self):
        records = [
            evidence("EV-A", "E1", "width_mm", 1500, unit="mm"),
            evidence("EV-B", "E1", "width_mm", 150, unit="cm"),
        ]
        resolved = resolve(records)
        assert resolved.known is True
        assert resolved.value == 1500
        assert len(resolved.conversions) == 2
        assert resolved.conversions_explicit is True


class TestUnitHandling:
    def test_b07_unit_conversion_is_recorded_with_original_values(self):
        resolved = resolve([evidence("EV-A", "E1", "width_mm", 1.5, unit="m")])
        assert resolved.known is True
        assert resolved.value == 1500
        conversion = resolved.conversions[0]
        assert conversion["original_value"] == 1.5
        assert conversion["original_unit"] == "m"
        assert conversion["canonical_value"] == 1500

    def test_unusable_unit_makes_the_attribute_unknown(self):
        resolved = resolve([evidence("EV-A", "E1", "width_mm", 5, unit="furlong")])
        assert resolved.known is False
        assert resolved.reason_code is ReasonCode.UNSUPPORTED_UNIT

    def test_one_unusable_record_poisons_the_attribute_even_if_another_is_fine(self):
        records = [
            evidence("EV-A", "E1", "width_mm", 1500, unit="mm"),
            evidence("EV-B", "E1", "width_mm", 5, unit="furlong"),
        ]
        resolved = resolve(records)
        assert resolved.known is False
        assert resolved.reason_code is ReasonCode.UNSUPPORTED_UNIT
        assert set(resolved.evidence_ids) == {"EV-A", "EV-B"}


class TestFreshness:
    def test_no_freshness_policy_means_evidence_never_expires(self):
        old = AS_OF - timedelta(days=3650)
        resolved = resolve([evidence("EV-A", "E1", "width_mm", 1500, unit="mm", observed_at=old)], spec=WIDTH)
        assert resolved.known is True
        assert "does not expire" in resolved.explanation

    def test_expired_evidence_is_unknown_when_a_policy_exists(self):
        old = AS_OF - timedelta(days=400)
        resolved = resolve(
            [evidence("EV-A", "E1", "width_mm", 1500, unit="mm", observed_at=old, verification_status="verified")],
            spec=FRESH_WIDTH,
        )
        assert resolved.known is False
        assert resolved.reason_code is ReasonCode.EVIDENCE_EXPIRED

    def test_fresh_verified_evidence_resolves(self):
        recent = AS_OF - timedelta(days=10)
        resolved = resolve(
            [evidence("EV-A", "E1", "width_mm", 1500, unit="mm", observed_at=recent, verification_status="verified")],
            spec=FRESH_WIDTH,
        )
        assert resolved.known is True
        assert resolved.value == 1500

    def test_missing_observation_date_under_a_freshness_policy_is_unknown(self):
        resolved = resolve(
            [evidence("EV-A", "E1", "width_mm", 1500, unit="mm", observed_at=None, verification_status="verified")],
            spec=FRESH_WIDTH,
        )
        assert resolved.known is False
        assert resolved.reason_code is ReasonCode.EVIDENCE_EXPIRED

    def test_unverified_evidence_fails_a_verification_requiring_policy(self):
        recent = AS_OF - timedelta(days=10)
        resolved = resolve(
            [evidence("EV-A", "E1", "width_mm", 1500, unit="mm", observed_at=recent, verification_status="unverified")],
            spec=FRESH_WIDTH,
        )
        assert resolved.known is False
        assert resolved.reason_code is ReasonCode.EVIDENCE_NOT_VERIFIED


class TestTextAndSlope:
    def test_text_values_are_compared_case_insensitively_but_stored_verbatim(self):
        resolved = resolve_attribute(
            element_id="E1",
            field="surface",
            records=[evidence("EV-A", "E1", "surface", "Asphalt", unit=None)],
            spec=SURFACE,
            as_of=AS_OF,
        )
        assert resolved.known is True
        assert resolved.value == "asphalt"
        assert resolved.canonical_unit == "text"

    def test_slope_sign_is_preserved(self):
        resolved = resolve_attribute(
            element_id="E1",
            field="slope_percent",
            records=[evidence("EV-A", "E1", "slope_percent", -7.5, unit="percent")],
            spec=SLOPE,
            as_of=AS_OF,
        )
        assert resolved.known is True
        assert resolved.value == -7.5


class TestRegistry:
    def test_duplicate_evidence_ids_rejected(self):
        record = evidence("EV-DUP", "E1", "width_mm", 1500, unit="mm")
        with pytest.raises(ValueError):
            EvidenceRegistry([record, record])

    def test_lookup_by_field_and_element(self):
        records = [
            evidence("EV-A", "E1", "width_mm", 1500, unit="mm"),
            evidence("EV-B", "E2", "width_mm", 900, unit="mm"),
        ]
        registry = EvidenceRegistry(records)
        assert [r.id for r in registry.for_field("E1", "width_mm")] == ["EV-A"]
        assert {r.id for r in registry.for_element("E2")} == {"EV-B"}
        assert registry.for_field("E3", "width_mm") == ()
        assert registry.by_id("EV-A") is not None


class TestTimestampValidation:
    def test_naive_timestamp_rejected_at_contract_level(self):
        with pytest.raises(ValueError):
            EvidenceRecord(
                id="EV", element_id="E1", field="width_mm", value=1500, unit="mm",
                method="test", source="test", observed_at="2026-01-05T09:00:00",
                provenance_class="synthetic",
            )

    def test_offsets_are_normalised_to_utc(self):
        record = EvidenceRecord(
            id="EV", element_id="E1", field="width_mm", value=1500, unit="mm",
            method="test", source="test", observed_at="2026-01-05T14:30:00+05:30",
            provenance_class="synthetic",
        )
        assert record.observed_at == datetime(2026, 1, 5, 9, 0, tzinfo=UTC)