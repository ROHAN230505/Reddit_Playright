"""Profile-pool round-robin assignment + structure invariants."""

from __future__ import annotations

from app.services.profile_pool import (
    PROFILE_POOL_SIZE,
    PROFILE_TEMPLATES,
    get_profile,
    pick_next_profile_index,
    summarize_profile,
)


def test_pool_has_exactly_6_unique_profiles():
    assert PROFILE_POOL_SIZE == 6
    assert len(PROFILE_TEMPLATES) == 6
    for p in PROFILE_TEMPLATES:
        for key in ("user_agent", "viewport_width", "viewport_height", "timezone_id", "locale", "device_scale_factor"):
            assert key in p, f"missing {key} in profile"
    sigs = {(p["user_agent"], p["viewport_width"], p["viewport_height"], p["timezone_id"]) for p in PROFILE_TEMPLATES}
    assert len(sigs) == 6, "all 6 profiles must have a distinct (ua, viewport, timezone) signature"


def test_get_profile_wraps_around():
    assert get_profile(0) == PROFILE_TEMPLATES[0]
    assert get_profile(4) == PROFILE_TEMPLATES[4]
    assert get_profile(5) == PROFILE_TEMPLATES[5]
    assert get_profile(6) == PROFILE_TEMPLATES[0]
    assert get_profile(103) == PROFILE_TEMPLATES[1]


def test_round_robin_picks_smallest_unused_slot_first():
    assert pick_next_profile_index([]) == 0
    assert pick_next_profile_index([0]) == 1
    assert pick_next_profile_index([0, 1, 2, 3]) == 4
    assert pick_next_profile_index([0, 1, 2, 3, 4]) == 5
    # All 6 used once -> next picks slot 0 (smallest count + smallest index).
    assert pick_next_profile_index(list(range(6))) == 0
    # If slot 0 used twice and others once, next slot is 1.
    assert pick_next_profile_index([0, 0, 1, 2, 3, 4, 5]) == 1


def test_round_robin_treats_legacy_indices_as_wrapped():
    """profile_index values >=6 left over from the larger pool collapse via
    modulo, so the round-robin still distributes correctly."""
    # Legacy index 8 wraps to slot 2; next free should be 0, 1, 3, then 4.
    assert pick_next_profile_index([8]) == 0
    # Legacy 6..11 all wrap into slots 0..5 -> all slots have count 1.
    assert pick_next_profile_index([6, 7, 8, 9, 10, 11]) == 0


def test_summarize_profile_is_human_readable():
    s = summarize_profile(0)
    assert "slot 0:" in s
    assert "Chrome" in s
    assert "x" in s
    summaries = {summarize_profile(i) for i in range(6)}
    assert len(summaries) == 6
