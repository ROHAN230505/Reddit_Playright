"""Pool of 6 unique-but-similar browser profiles assigned to Reddit accounts.

Each profile mixes a different UA / viewport / timezone / locale / device pixel
ratio. All entries are realistic US-English desktop Chrome variations, so they
sit naturally in the "active US redditor" persona we're impersonating, while
ensuring no two accounts share the exact same browser fingerprint.

Slots are 0-indexed. Accounts are auto-assigned via round-robin in
`pick_next_profile_index()` — slot 0, 1, 2, 3, 4, 5, then 0 again at #7.
"""

from __future__ import annotations

from typing import TypedDict


class ProfileTemplate(TypedDict):
    user_agent: str
    viewport_width: int
    viewport_height: int
    timezone_id: str
    locale: str
    device_scale_factor: float


PROFILE_TEMPLATES: list[ProfileTemplate] = [
    {  # 0 — Windows Chrome 120 desktop, NYC
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "viewport_width": 1920,
        "viewport_height": 1080,
        "timezone_id": "America/New_York",
        "locale": "en-US",
        "device_scale_factor": 1.0,
    },
    {  # 1 — Windows Chrome 119 laptop, Chicago
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "viewport_width": 1366,
        "viewport_height": 768,
        "timezone_id": "America/Chicago",
        "locale": "en-US",
        "device_scale_factor": 1.0,
    },
    {  # 2 — Windows Chrome 121 hi-DPI laptop, Denver
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "viewport_width": 1536,
        "viewport_height": 864,
        "timezone_id": "America/Denver",
        "locale": "en-US",
        "device_scale_factor": 1.25,
    },
    {  # 3 — macOS Chrome 120 retina, Los Angeles
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "viewport_width": 1440,
        "viewport_height": 900,
        "timezone_id": "America/Los_Angeles",
        "locale": "en-US",
        "device_scale_factor": 2.0,
    },
    {  # 4 — macOS Chrome 121 retina, Phoenix
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "viewport_width": 1680,
        "viewport_height": 1050,
        "timezone_id": "America/Phoenix",
        "locale": "en-US",
        "device_scale_factor": 2.0,
    },
    {  # 5 — Windows Chrome 120 desktop, London (EU-coherent: pair with Decodo EU proxy)
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "viewport_width": 1920,
        "viewport_height": 1080,
        "timezone_id": "Europe/London",
        "locale": "en-GB",
        "device_scale_factor": 1.0,
    },
]

PROFILE_POOL_SIZE = len(PROFILE_TEMPLATES)


def get_profile(index: int) -> ProfileTemplate:
    """Return the profile at slot `index`, wrapping around if out of range."""
    return PROFILE_TEMPLATES[index % PROFILE_POOL_SIZE]


def pick_next_profile_index(used_indices: list[int]) -> int:
    """Round-robin: return the next slot the next account should occupy.

    `used_indices` is the current list of profile_index values already in use
    by enabled accounts. Returns the smallest slot not in the list; if
    every slot is taken, returns the slot in use by the FEWEST accounts —
    i.e. spreads collisions evenly.
    """
    counts = {i: 0 for i in range(PROFILE_POOL_SIZE)}
    for idx in used_indices:
        # Treat out-of-range (legacy) values as if they live in their wrapped slot.
        if idx is not None and idx >= 0:
            counts[idx % PROFILE_POOL_SIZE] += 1
    return min(counts.keys(), key=lambda i: (counts[i], i))


def summarize_profile(index: int) -> str:
    """One-line human description for UIs and logs."""
    p = get_profile(index)
    os_name = "Windows"
    if "Macintosh" in p["user_agent"]:
        os_name = "macOS"
    elif "Linux" in p["user_agent"]:
        os_name = "Linux"
    chrome_ver = p["user_agent"].split("Chrome/")[1].split(".")[0] if "Chrome/" in p["user_agent"] else "?"
    return (
        f"slot {index}: {os_name} Chrome {chrome_ver}, "
        f"{p['viewport_width']}x{p['viewport_height']} @{p['device_scale_factor']}x, "
        f"{p['timezone_id']}"
    )
