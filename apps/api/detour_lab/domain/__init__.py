"""Domain layer: pure contracts, units and canonical hashing.

Nothing in this package may import from ``ingestion``, ``persistence``, ``api`` or
any I/O concern. It is the trusted core that the rest of the system is built on.
"""

from __future__ import annotations

__all__: list[str] = []