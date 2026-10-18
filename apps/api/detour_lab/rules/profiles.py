"""Demonstration mobility profiles.

These are **demonstration configurations**, not disability standards and not a
description of any individual. MASTER_PROMPT §5.3 forbids assuming that one
wheelchair profile represents all users; the PRD §18 baseline choice is a manual
wheelchair profile plus a limited-mobility walking profile, with low-vision
wayfinding explicitly out of scope and UNKNOWN rather than assumed.

A profile's ``preference_weights`` are additive metre-equivalent route penalties
applied only when the named attribute is known. They can change *which*
confirmed route is shortest. They can never change a hard verdict (INV-05), which
is asserted by ``tests/test_profiles_preferences.py``.
"""

from __future__ import annotations

from detour_lab.domain.contracts import MobilityProfile

__all__ = ["DEMO_PROFILES", "DEMO_PROFILE_LIMITED_MOBILITY_WALKER", "DEMO_PROFILE_MANUAL_WHEELCHAIR", "profile_by_id"]

DEMO_PROFILE_MANUAL_WHEELCHAIR = MobilityProfile(
    id="DEMO_PROFILE_MANUAL_WHEELCHAIR",
    name="Demo profile A - manual wheelchair (DEMONSTRATION ONLY)",
    description=(
        "Synthetic demonstration configuration for a manual wheelchair user. The hard requirements come "
        "from DEMO_RULEPACK_NOT_LEGAL, not from any standard, and the profile does not represent every "
        "wheelchair user or every disability."
    ),
    is_demo_profile=True,
    preference_weights={"surface": 0.25},
    notes=(
        "Preference weights rank routes only. Any real use requires review by a person with lived "
        "experience of the relevant barriers."
    ),
)

DEMO_PROFILE_LIMITED_MOBILITY_WALKER = MobilityProfile(
    id="DEMO_PROFILE_LIMITED_MOBILITY_WALKER",
    name="Demo profile B - limited-mobility walking (DEMONSTRATION ONLY)",
    description=(
        "Synthetic demonstration configuration for a walking user with limited mobility. Differs from "
        "profile A in required width, gradient and surface thresholds so the two produce independent results."
    ),
    is_demo_profile=True,
    preference_weights={},
    notes="Low-vision wayfinding conditions are explicitly out of scope and remain UNKNOWN, not assumed.",
)

DEMO_PROFILES: tuple[MobilityProfile, ...] = (DEMO_PROFILE_MANUAL_WHEELCHAIR, DEMO_PROFILE_LIMITED_MOBILITY_WALKER)


def profile_by_id(profile_id: str) -> MobilityProfile:
    for profile in DEMO_PROFILES:
        if profile.id == profile_id:
            return profile
    raise KeyError(f"unknown demo profile {profile_id!r}")