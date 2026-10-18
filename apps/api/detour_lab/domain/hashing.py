"""Canonical serialisation and semantic hashing.

MASTER_PROMPT §5.5 requires two replay runs with equal immutable semantic inputs
to produce the same canonical *semantic* hash, while inherently volatile run
metadata (run id, timestamps, durations) is excluded from that fingerprint.

The rules below make hashes stable across processes, machines and dictionary
insertion order:

* keys sorted, fixed separators, UTF-8, no insignificant whitespace;
* floats normalised to a fixed number of decimals so that ``0.1 + 0.2`` and
  ``0.3`` cannot produce different hashes for the same physical quantity;
* ``NaN``/``Infinity`` rejected (they are not valid JSON and not reproducible);
* sets and sets-like containers serialised in sorted order;
* Pydantic models and dataclasses reduced through their canonical field values.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping, Sequence, Set
from datetime import date, datetime
from enum import Enum
from typing import Any, Final

__all__ = [
    "FLOAT_DECIMALS",
    "SemanticPayloadError",
    "canonical_json",
    "canonicalise",
    "semantic_hash",
    "sha256_hex",
]

#: Decimal places kept when normalising floats. 1 mm / 1e-6 m resolution is far
#: below any threshold the rulepack uses, so this cannot mask a real difference.
FLOAT_DECIMALS: Final[int] = 6


class SemanticPayloadError(ValueError):
    """Raised when a payload cannot be hashed reproducibly."""


def _normalise_float(value: float) -> float:
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
        raise SemanticPayloadError("non-finite numbers cannot be hashed")
    rounded = round(float(value), FLOAT_DECIMALS)
    # Normalise -0.0 to 0.0 so sign of zero cannot change a hash.
    return 0.0 if rounded == 0 else rounded


def canonicalise(value: Any) -> Any:
    """Recursively convert ``value`` into a JSON-compatible canonical structure."""
    if value is None or isinstance(value, bool | str | int):
        return value
    if isinstance(value, float):
        return _normalise_float(value)
    if isinstance(value, Enum):
        return canonicalise(value.value)
    if isinstance(value, datetime | date):
        # Timestamps participate in hashes only when the caller deliberately
        # includes them; UTC 'Z' form keeps the textual form canonical.
        return value.isoformat()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return canonicalise(dataclasses.asdict(value))
    if hasattr(value, "model_dump") and callable(value.model_dump):  # pydantic v2
        return canonicalise(value.model_dump(mode="json", exclude_none=True))
    if isinstance(value, Mapping):
        return {str(key): canonicalise(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, Set):
        return [canonicalise(item) for item in sorted(value, key=str)]
    if isinstance(value, Sequence):
        return [canonicalise(item) for item in value]
    if hasattr(value, "to_canonical"):  # explicit opt-in for domain objects
        return canonicalise(value.to_canonical())
    raise SemanticPayloadError(f"cannot canonicalise value of type {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialise ``value`` to the canonical JSON form used for hashing and export."""
    return json.dumps(
        canonicalise(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def semantic_hash(value: Any) -> str:
    """Return ``sha256:<hex>`` over the canonical JSON of ``value``."""
    return f"sha256:{sha256_hex(canonical_json(value))}"