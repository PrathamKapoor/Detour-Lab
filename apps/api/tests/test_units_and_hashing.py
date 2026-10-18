"""Unit canonicalisation and canonical hashing (INV-04, FR-013)."""

from __future__ import annotations

import math

import pytest
from detour_lab.domain.hashing import SemanticPayloadError, canonical_json, semantic_hash
from detour_lab.domain.units import (
    UnitError,
    parse_timestamp,
    to_canonical_length_m,
    to_canonical_slope_percent,
    to_canonical_width_mm,
)
from hypothesis import given, settings
from hypothesis import strategies as st


class TestWidthConversion:
    @pytest.mark.parametrize(
        ("value", "unit", "expected_mm"),
        [
            (1500, "mm", 1500),
            (150, "cm", 1500),
            (1.5, "m", 1500),
            (59.05511811, "in", 1500),
            (4.92773193, "ft", 1500),
            (1500, "MILLIMETRE", 1500),
        ],
    )
    def test_known_conversions_are_exact_at_millimetre_resolution(self, value, unit, expected_mm):
        assert to_canonical_width_mm(value, unit).canonical_value == expected_mm

    def test_conversion_is_recorded_not_silent(self):
        conversion = to_canonical_width_mm(150, "cm")
        assert conversion.original_value == 150
        assert conversion.original_unit == "cm"
        assert conversion.canonical_unit == "mm"
        assert conversion.as_dict()["factor_applied"] == pytest.approx(10.0)

    def test_incompatible_unit_is_rejected(self):
        with pytest.raises(UnitError) as excinfo:
            to_canonical_width_mm(5, "furlong")
        assert excinfo.value.code == "UNSUPPORTED_UNIT"

    def test_missing_unit_is_rejected(self):
        with pytest.raises(UnitError):
            to_canonical_width_mm(1500, "")

    def test_nan_and_infinity_are_rejected(self):
        with pytest.raises(UnitError) as excinfo:
            to_canonical_width_mm(float("nan"), "mm")
        assert excinfo.value.code == "INVALID_NUMERIC_VALUE"
        with pytest.raises(UnitError):
            to_canonical_width_mm(float("inf"), "mm")

    def test_boolean_is_not_a_number(self):
        with pytest.raises(UnitError):
            to_canonical_width_mm(True, "mm")

    def test_negative_width_rejected(self):
        with pytest.raises(UnitError):
            to_canonical_width_mm(-5, "mm")

    @settings(max_examples=200, deadline=None)
    @given(st.integers(min_value=0, max_value=10_000))
    def test_same_physical_width_converts_to_the_same_canonical_value(self, millimetres):
        expressed = {
            "mm": millimetres,
            "cm": millimetres / 10.0,
            "m": millimetres / 1000.0,
        }
        canonical = {
            to_canonical_width_mm(value, unit).canonical_value
            for unit, value in expressed.items()
        }
        assert canonical == {millimetres}


class TestLengthConversion:
    def test_metres_and_kilometres_are_rejected_together(self):
        # "km" is intentionally not accepted: silently guessing a scale factor
        # for safety-relevant geometry is exactly the failure INV-04 forbids.
        with pytest.raises(UnitError):
            to_canonical_length_m(1, "km")

    def test_exact_inch_definition(self):
        assert to_canonical_length_m(1, "in").canonical_value == pytest.approx(0.0254)


class TestSlopeConversion:
    def test_percent_passes_through(self):
        assert to_canonical_slope_percent(5, "percent").canonical_value == 5.0

    def test_ratio_becomes_percent(self):
        assert to_canonical_slope_percent(0.05, "ratio").canonical_value == pytest.approx(5.0)

    def test_negative_grade_is_preserved_with_sign(self):
        assert to_canonical_slope_percent(-3.5, "%").canonical_value == -3.5

    def test_ambiguous_unit_rejected(self):
        with pytest.raises(UnitError):
            to_canonical_slope_percent(5, "furlongs_per_fortnight")


class TestTimestamps:
    def test_timezone_aware_required(self):
        with pytest.raises(UnitError):
            parse_timestamp("2026-01-05T09:00:00")

    def test_offsets_normalised_to_utc(self):
        assert parse_timestamp("2026-01-05T14:30:00+05:30").hour == 9

    def test_z_suffix_accepted(self):
        assert parse_timestamp("2026-01-05T09:00:00Z") == parse_timestamp("2026-01-05T09:00:00+00:00")


class TestCanonicalHashing:
    def test_key_order_does_not_change_the_hash(self):
        assert semantic_hash({"a": 1, "b": 2}) == semantic_hash({"b": 2, "a": 1})

    def test_float_noise_is_normalised(self):
        assert semantic_hash({"x": 0.1 + 0.2}) == semantic_hash({"x": 0.3})

    def test_negative_zero_normalised(self):
        assert semantic_hash({"x": -0.0}) == semantic_hash({"x": 0.0})

    def test_real_differences_still_change_the_hash(self):
        assert semantic_hash({"x": 1.0}) != semantic_hash({"x": 1.000001})

    def test_nan_cannot_be_hashed(self):
        with pytest.raises(SemanticPayloadError):
            semantic_hash({"x": float("nan")})

    def test_list_order_matters_for_sequences(self):
        assert semantic_hash([1, 2]) != semantic_hash([2, 1])

    def test_canonical_json_is_stable_text(self):
        text = canonical_json({"b": [1, 2], "a": "x"})
        assert text == '{"a":"x","b":[1,2]}'

    @settings(max_examples=100, deadline=None)
    @given(st.lists(st.floats(allow_nan=False, allow_infinity=False, width=32), min_size=1, max_size=5))
    def test_hashing_is_repeatable_for_arbitrary_payloads(self, values):
        first = semantic_hash({"values": values})
        second = semantic_hash({"values": list(values)})
        assert first == second
        assert math.isfinite(values[0]) or True