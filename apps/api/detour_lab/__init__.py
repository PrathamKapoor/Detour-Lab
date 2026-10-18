"""DETOUR LAB backend package.

Authoritative domain engine for pre-construction pedestrian detour verification.

Hard boundaries enforced by this package (see MASTER_PROMPT §0/§2):
  * No generative model participates in any Pass/Fail/Unknown decision.
  * No attribute value exists without an evidence record carrying provenance.
  * Missing or conflicting evidence yields UNKNOWN; it never silently becomes PASS.
  * Verdicts say "Pass in modeled checks" / "Fail" / "Unknown" / "Not applicable".
    They are never a legal, regulatory or safety certification.
"""

from __future__ import annotations

__all__ = ["ENGINE_VERSION", "MANIFEST_SCHEMA_VERSION", "__version__"]

__version__ = "0.1.0"

#: Bumping this string invalidates cross-process result comparisons, so it is part of
#: every run manifest (INV-06).
ENGINE_VERSION = "detour-lab-engine/0.1.0"

#: Canonical JSON manifest schema version reported in exports.
MANIFEST_SCHEMA_VERSION = "1.0.0"