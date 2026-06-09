"""GLP-voice reply prompt construction tests.

We don't try to assert what the LLM produces (that's flaky), but we DO assert
the prompt sent to it has the right hooks: GLP-voice rules, no Reddit-isms,
correct system prompt for the platform.
"""

from __future__ import annotations

import pytest

from app.services.processor import (
    _build_reply_prompt,
    _SYSTEM_PROMPT,
    _SYSTEM_PROMPT_GLP,
    _STYLE_RULES_GLP,
    generate_reply,
)


def test_glp_prompt_uses_glp_style_rules():
    prompt = _build_reply_prompt("They say AI is going to take over jobs", include_promo=False, platform="glp")
    assert "GLP poster" in prompt or "godlikeproductions" in prompt.lower() or "BBCode" in prompt
    # Must NOT carry the Reddit-flavored rule.
    assert "Reddit user" not in prompt


def test_reddit_prompt_unchanged_when_platform_omitted():
    prompt = _build_reply_prompt("They say AI is going to take over jobs", include_promo=False)
    assert "Reddit user" in prompt
    assert "GLP" not in prompt


def test_glp_system_prompt_is_distinct_from_reddit():
    assert _SYSTEM_PROMPT_GLP != _SYSTEM_PROMPT
    assert "godlikeproductions" in _SYSTEM_PROMPT_GLP.lower()


def test_glp_style_rules_ban_reddit_isms():
    rules = _STYLE_RULES_GLP
    # Sample of bans listed in the rules — keep test loose to allow rule edits.
    assert "OP" in rules or "TL;DR" in rules or "Reddit-isms" in rules


def test_generate_reply_glp_uses_glp_system_prompt(monkeypatch):
    captured: dict = {}

    def _fake_deepseek(prompt, system_prompt=None):
        captured.setdefault("system_prompts", []).append(system_prompt)
        return "yeah, exactly. not buying it."

    monkeypatch.setattr("app.services.processor.deepseek_call", _fake_deepseek)
    result = generate_reply("interesting take, sure", include_promo=False, platform="glp")
    assert result
    # First (and only successful) call should have received the GLP system prompt.
    assert captured["system_prompts"][0] == _SYSTEM_PROMPT_GLP


def test_generate_reply_reddit_default_uses_reddit_system_prompt(monkeypatch):
    captured: dict = {}

    def _fake_deepseek(prompt, system_prompt=None):
        captured.setdefault("system_prompts", []).append(system_prompt)
        return "yeah, that pattern's been showing up everywhere lately."

    monkeypatch.setattr("app.services.processor.deepseek_call", _fake_deepseek)
    result = generate_reply("interesting take, sure", include_promo=False)
    assert result
    assert captured["system_prompts"][0] == _SYSTEM_PROMPT
