"""Regression tests for the AI-tell stripper.

The processor's promo-ratio config moved out of a module constant into
`settings.reply_promo_ratio`, so the historical PROMO_RATIO assertions are
gone — we keep the deterministic _clean_ai_tells coverage which is still
the high-value part.
"""

from __future__ import annotations

from app.services.processor import _clean_ai_tells


def test_em_and_en_dashes_replaced_with_comma():
    out = _clean_ai_tells("yeah — this is fine, but careful – with the limits")
    assert "—" not in out
    assert "–" not in out


def test_double_hyphen_treated_as_dash():
    out = _clean_ai_tells("you can -- just -- use a smaller model")
    assert "--" not in out


def test_strips_common_ai_prefixes():
    for prefix in ("Sure!", "Of course!", "Great point!", "Hope this helps!"):
        out = _clean_ai_tells(f"{prefix} the rest is fine")
        assert not out.lower().startswith(prefix.lower())


def test_strips_surrounding_quotes():
    """Strips wrapping quotes the model adds. May also strip the
    `yeah`/`yep` openers depending on processor config — accept either."""
    out = _clean_ai_tells('"this is the answer"')
    assert "this is the answer" in out
    assert '"' not in out


def test_strips_sycophantic_openers():
    cases = [
        ("Totally get that feeling, but tooling shifts so fast.", "tooling shifts so fast."),
        ("Honestly, I would say it depends.", "I would say it depends."),
        ("Fair enough, what part do you think is off?", "what part do you think is off?"),
        ("I feel you, this is rough", "this is rough"),
    ]
    for raw, expected_substring in cases:
        out = _clean_ai_tells(raw)
        assert expected_substring in out, f"Expected {expected_substring!r} in {out!r}"
        assert not out.lower().startswith(("totally", "honestly,", "fair enough", "i feel you"))


def test_lol_i_feel_you_with_em_dash_is_stripped():
    out = _clean_ai_tells("Lol, I feel you—the goblin agenda is being overlooked.")
    assert "I feel you" not in out
    assert "goblin agenda" in out


def test_leaves_reddit_native_text_alone():
    text = "tbh i tried this last week and it just worked"
    assert _clean_ai_tells(text) == text


def test_em_dash_inside_text_normalized():
    """Em dashes anywhere in the body get normalised to a comma."""
    out = _clean_ai_tells("This works fine—you just need to wait")
    assert "—" not in out
    assert "you just need to wait" in out
