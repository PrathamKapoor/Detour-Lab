"""Bounded intervention library (MASTER_PROMPT §7.1, PRD FR-102).

The library is an **immutable, versioned data file** bundled with the
repository (``data/demo/interventions.demo.json``). It is loaded read-only:

* every intervention is validated by the :class:`Intervention` contract;
* effects are validated against ``allowed_ops`` and ``target_element_ids``;
* references between interventions are validated (existence, cycles);
* nothing in it is a real engineering finding, legal threshold or sourced
  price - every value is demonstration data authored in this repository.

The loader fails loudly (``LibraryError``) instead of skipping a bad entry: a
half-understood library would silently change every search result.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from detour_lab.domain.contracts import Intervention

__all__ = ["InterventionLibrary", "LibraryError", "load_intervention_library"]

_TOP_LEVEL_KEYS = {"schema_version", "library_id", "version", "notice", "interventions"}

#: Ops whose ``target_id`` must be declared in ``target_element_ids`` when the
#: intervention declares a non-empty target list (defence in depth: the loader
#: never has to guess which parameter carries the element identity).
_TARGETED_OPS = {
    "update_attribute",
    "close_edge",
    "activate_temporary_edge",
    "remove_edge",
    "set_direction",
    "split_edge",
    "link_crossing",
}


class LibraryError(ValueError):
    """The bundled intervention library is invalid. Never silently ignored."""

    def __init__(self, message: str, *, code: str = "INVALID_LIBRARY", detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


@dataclass(frozen=True, slots=True)
class InterventionLibrary:
    id: str
    version: str
    notice: str
    interventions: tuple[Intervention, ...]

    def by_id(self, intervention_id: str) -> Intervention | None:
        return next((i for i in self.interventions if i.id == intervention_id), None)

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(i.id for i in self.interventions)


def _validate_effect_declarations(intervention: Intervention) -> None:
    effect = intervention.effect
    if effect is None:
        return
    allowed = set(intervention.allowed_ops)
    for edit in effect.edits:
        if edit.op not in allowed:
            raise LibraryError(
                f"intervention {intervention.id!r}: effect uses op {edit.op!r} which is not declared "
                f"in allowed_ops {sorted(allowed)}",
                detail={"intervention_id": intervention.id, "op": edit.op},
            )
        if intervention.target_element_ids and edit.op in _TARGETED_OPS and edit.target_id not in intervention.target_element_ids:
            raise LibraryError(
                f"intervention {intervention.id!r}: effect targets {edit.target_id!r}, which is not "
                f"declared in target_element_ids {intervention.target_element_ids}",
                detail={"intervention_id": intervention.id, "target_id": edit.target_id},
            )


def _assert_acyclic(interventions: dict[str, Intervention]) -> None:
    """Requires-cycles make a candidate set undefined; reject the library."""
    color: dict[str, int] = {}  # 0 unseen, 1 on stack, 2 done
    for root in sorted(interventions):
        if color.get(root, 0) != 0:
            continue
        stack: list[tuple[str, int]] = [(root, 0)]
        color[root] = 1
        while stack:
            node_id, index = stack.pop()
            requires = interventions[node_id].requires_intervention_ids
            if index >= len(requires):
                color[node_id] = 2
                continue
            stack.append((node_id, index + 1))
            required = requires[index]
            if required not in interventions:
                continue  # dangling handled separately
            state = color.get(required, 0)
            if state == 1:
                raise LibraryError(
                    f"intervention requirements contain a cycle involving {required!r}; "
                    "a cyclic library cannot produce a well-defined candidate set",
                    code="CYCLIC_LIBRARY",
                    detail={"cycle_at": required},
                )
            if state == 0:
                color[required] = 1
                stack.append((required, 0))


def load_intervention_library(path: str | Path) -> InterventionLibrary:
    """Load and fully validate the bundled intervention library."""
    library_path = Path(path)
    try:
        raw = json.loads(library_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LibraryError(f"cannot read intervention library {str(library_path)!r}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LibraryError(f"intervention library {str(library_path)!r} is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise LibraryError("intervention library must be a JSON object")
    unknown = sorted(set(raw) - _TOP_LEVEL_KEYS)
    if unknown:
        raise LibraryError(
            f"intervention library declares unknown top-level keys {unknown}; the loader refuses "
            "to ignore fields it does not understand"
        )
    for key in ("library_id", "version", "notice", "interventions"):
        if key not in raw:
            raise LibraryError(f"intervention library is missing required key {key!r}")

    entries = raw["interventions"]
    if not isinstance(entries, list):
        raise LibraryError("intervention library 'interventions' must be a list")

    parsed: list[Intervention] = []
    for index, entry in enumerate(entries):
        try:
            parsed.append(Intervention.model_validate(entry))
        except ValidationError as exc:
            identifier = entry.get("id") if isinstance(entry, dict) else None
            raise LibraryError(
                f"intervention at index {index} (id={identifier!r}) failed contract validation: "
                f"{exc.error_count()} error(s); first: {exc.errors()[0]['msg']}",
                detail={"index": index, "intervention_id": identifier},
            ) from exc

    identifiers = [intervention.id for intervention in parsed]
    if len(set(identifiers)) != len(identifiers):
        duplicates = sorted({i for i in identifiers if identifiers.count(i) > 1})
        raise LibraryError(f"duplicate intervention IDs in library: {duplicates}")

    by_id = {intervention.id: intervention for intervention in parsed}
    for intervention in parsed:
        for required in intervention.requires_intervention_ids:
            if required not in by_id:
                raise LibraryError(
                    f"intervention {intervention.id!r} requires unknown intervention {required!r}",
                    detail={"intervention_id": intervention.id, "missing": required},
                )
        for excluded in intervention.excludes_intervention_ids:
            if excluded not in by_id:
                raise LibraryError(
                    f"intervention {intervention.id!r} excludes unknown intervention {excluded!r}",
                    detail={"intervention_id": intervention.id, "missing": excluded},
                )
        _validate_effect_declarations(intervention)
    _assert_acyclic(by_id)

    return InterventionLibrary(
        id=str(raw["library_id"]),
        version=str(raw["version"]),
        notice=str(raw["notice"]),
        interventions=tuple(parsed),
    )
