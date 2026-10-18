"""Exact, reproducible unit handling (INV-04).

Canonical representations
-------------------------
* **length / distance**  -> metres (``m``), float, compared at 1 mm resolution
* **width**              -> integer millimetres (``mm``) so that comparisons are exact
* **slope / grade**      -> signed percent of the **traversal direction**
  (``+5.0`` = 5 % rise while walking u→v; ``-2.0`` = 2 % descent), 4 decimal places
* **timestamp**          -> timezone-aware ISO 8601 UTC

Design rules
------------
* Unknown unit strings are rejected, never guessed.
* ``NaN`` / ``Infinity`` are rejected at the boundary.
* Every conversion is exact at the documented comparison precision and is covered
  by tests, including unit-incompatible rejections.
* Conversions never silently mutate the stored observation: an
  :class:`UnitConversion` records the original value/unit and the canonical one.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

__all__ = [
    "CANONICAL_UNIT",
    "LENGTH_UNITS",
    "UnitConversion",
    "UnitError",
    "canonicalise_numeric",
    "parse_timestamp",
    "to_canonical_length_m",
    "to_canonical_slope_percent",
    "to_canonical_width_mm",
]

#: Canonical unit per canonical quantity.
CANONICAL_UNIT: Final[dict[str, str]] = {
    "length_m": "m",
    "width_mm": "mm",
    "slope_percent": "percent",
}

#: Recognised unit -> factor relative to metres. Imperial factors are exact
#: definitions (0.3044 m and 0.0254 m), not survey observations.
LENGTH_UNITS: Final[dict[str, float]] = {
    "m": 1.0,
    "metre": 1.0,
    "meter": 1.0,
    "cm": 0.01,
    "centimetre": 0.01,
    "centimeter": 0.01,
    "mm": 0.001,
    "millimetre": 0.001,
    "millimeter": 0.001,
    "ft": 0.3044,
    "foot": 0.3044,
    "feet": 0.3044,
    "in": 0.0254,
    "inch": 0.0254,
    "inches": 0.0254,
}

_WIDTH_UNITS: Final[dict[str, str]] = {
    "m": "width_mm",
    "metre": "width_mm",
    "meter": "width_mm",
    "cm": "width_mm",
    "centimetre": "width_mm",
    "centimeter": "width_mm",
    "mm": "width_mm",
    "millimetre": "width_mm",
    "millimeter": "width_mm",
    "ft": "width_mm",
    "foot": "width_mm",
    "feet": "width_mm",
    "in": "width_mm",
    "inch": "width_mm",
    "inches": "width_mm",
}

_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


class UnitError(ValueError):
    """Raised for unknown units, incompatible units and non-finite numbers.

    Inherits ``ValueError`` so Pydantic validators and the API error contract can
    translate it into a 422 with field-level detail.
    """

    def __init__(self, message: str, *, code: str = "UNSUPPORTED_UNIT", detail: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


@dataclass(frozen=True, slots=True)
class UnitConversion:
    """Result of converting an observation into its canonical representation."""

    original_value: float
    original_unit: str
    canonical_value: float | int
    canonical_unit: str
    factor_applied: float

    def as_dict(self) -> dict:
        return {
            "original_value": self.original_value,
            "original_unit": self.original_unit,
            "canonical_value": self.canonical_value,
            "canonical_unit": self.canonical_unit,
            "factor_applied": self.factor_applied,
        }


def canonicalise_numeric(value: object, *, field: str) -> float:
    """Reject bools, NaN and Infinity, then return a plain float."""
    if isinstance(value, bool):
        raise UnitError(f"{field} must be a number, not a boolean", code="INVALID_NUMERIC_VALUE")
    if isinstance(value, int | float):
        numeric = float(value)
    else:
        raise UnitError(
            f"{field} must be numeric, got {type(value).__name__}", code="INVALID_NUMERIC_VALUE"
        )
    if math.isnan(numeric) or math.isinf(numeric):
        raise UnitError(f"{field} must be finite (NaN/Infinity rejected)", code="INVALID_NUMERIC_VALUE")
    return numeric


def _normalise_unit(unit: str, *, field: str) -> str:
    cleaned = unit.strip()
    if not cleaned:
        raise UnitError(f"{field}: unit must not be empty", code="UNSUPPORTED_UNIT")
    return cleaned


def to_canonical_length_m(value: object, unit: str, *, field: str = "length") -> UnitConversion:
    """Convert a length observation to metres."""
    numeric = canonicalise_numeric(value, field=field)
    key = _normalise_unit(unit, field=field).lower()
    factor = LENGTH_UNITS.get(key)
    if factor is None:
        raise UnitError(
            f"{field}: unsupported length unit {unit!r}",
            code="UNSUPPORTED_UNIT",
            detail={"supported_units": sorted(set(LENGTH_UNITS))},
        )
    metres = numeric * factor
    if metres < 0:
        raise UnitError(f"{field}: length must not be negative", code="INVALID_NUMERIC_VALUE")
    return UnitConversion(numeric, unit, round(metres, 6), "m", factor)


def to_canonical_width_mm(value: object, unit: str, *, field: str = "width") -> UnitConversion:
    """Convert a width observation to **integer millimetres**.

    Integer millimetres make threshold comparisons exact and deterministic, which
    is what INV-04 requires: a conversion is either recorded explicitly or the
    value is rejected.
    """
    numeric = canonicalise_numeric(value, field=field)
    key = _normalise_unit(unit, field=field).lower()
    if key not in _WIDTH_UNITS:
        raise UnitError(
            f"{field}: unsupported width unit {unit!r}",
            code="UNSUPPORTED_UNIT",
            detail={"supported_units": sorted(set(_WIDTH_UNITS))},
        )
    metres = numeric * LENGTH_UNITS[key]
    millimetres = metres * 1000.0
    # Round half away from zero to 1 mm so float representation cannot change a verdict.
    rounded = math.floor(millimetres + 0.5) if millimetres >= 0 else -math.floor(-millimetres + 0.5)
    if rounded < 0:
        raise UnitError(f"{field}: width must not be negative", code="INVALID_NUMERIC_VALUE")
    return UnitConversion(numeric, unit, rounded, "mm", LENGTH_UNITS[key] * 1000.0)


def to_canonical_slope_percent(value: object, unit: str, *, field: str = "slope") -> UnitConversion:
    """Convert a grade observation to signed percent along the traversal direction.

    Supported inputs: ``percent``/``%`` already in percent; ``ratio`` expressed as
    rise/run (dimensionless) and ``degree``/``deg`` of inclination. An absolute
    slope (no direction) is *not* silently accepted as a directed value: pass the
    documented ``abs_percent`` unit only when the source genuinely cannot state
    direction, and the rule set decides whether that is usable.
    """
    numeric = canonicalise_numeric(value, field=field)
    key = _normalise_unit(unit, field=field).lower()
    if key in {"percent", "%", "pct"}:
        percent, factor = numeric, 1.0
    elif key in {"ratio", "rise_over_run", ":1"}:
        percent, factor = numeric * 100.0, 100.0
    elif key in {"degree", "deg", "degrees", "°"}:
        # tan(theta) = rise/run; percent grade = 100 * tan(theta).
        percent, factor = math.tan(math.radians(numeric)) * 100.0, math.tan(math.radians(numeric)) * 100.0 / numeric if numeric else 1.0
    elif key in {"abs_percent", "absolute_percent"}:
        percent, factor = abs(numeric), 1.0
    else:
        raise UnitError(
            f"{field}: unsupported slope unit {unit!r}",
            code="UNSUPPORTED_UNIT",
            detail={"supported_units": ["percent", "%", "ratio", "degree", "abs_percent"]},
        )
    return UnitConversion(numeric, unit, round(percent, 4), "percent", factor)


def parse_timestamp(value: str, *, field: str = "observed_at") -> datetime:
    """Parse a strict, timezone-aware ISO 8601 timestamp into UTC.

    A timezone-naive timestamp is rejected rather than assumed to be UTC: silently
    assuming a timezone would fabricate a survey time.
    """
    if not isinstance(value, str) or not _TIMESTAMP_RE.match(value.strip()):
        raise UnitError(
            f"{field}: expected timezone-aware ISO 8601 timestamp such as '2026-01-05T09:30:00Z'",
            code="INVALID_NUMERIC_VALUE",
        )
    text = value.strip().replace("z", "Z")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise UnitError(f"{field}: timestamp must carry a timezone offset", code="INVALID_NUMERIC_VALUE")
    return parsed.astimezone(UTC)