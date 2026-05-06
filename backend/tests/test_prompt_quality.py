from app.config import settings
from app.services import deepseek_service
from app.services.processor import (
    _clean_ai_tells,
    _comment_allows_promo,
    _enforce_reply_length,
    _reply_is_acceptable,
    generate_reply,
)


def test_deepseek_payload_uses_system_message_and_generation_params(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(settings, "deepseek_model", "deepseek-chat")
    monkeypatch.setattr(settings, "deepseek_temperature", 0.45)
    monkeypatch.setattr(settings, "deepseek_max_tokens", 90)
    monkeypatch.setattr(settings, "deepseek_frequency_penalty", 0.3)
    monkeypatch.setattr(deepseek_service.requests, "post", fake_post)

    assert deepseek_service.deepseek_call("reply please", system_prompt="system rules") == "ok"

    payload = captured["json"]
    assert payload["messages"] == [
        {"role": "system", "content": "system rules"},
        {"role": "user", "content": "reply please"},
    ]
    assert payload["temperature"] == 0.45
    assert payload["max_tokens"] == 90
    assert payload["frequency_penalty"] == 0.3


def test_reply_cleanup_removes_preambles_and_agreeable_openers():
    cleaned = _clean_ai_tells(
        "Here's a natural, helpful Reddit reply: Honestly, totally agree, this is probably just a workflow problem."
    )

    assert cleaned == "this is probably just a workflow problem."


def test_reply_cleanup_normalizes_bad_punctuation():
    cleaned = _clean_ai_tells("I?ve seen that?s usually a tooling issue — not a model issue")

    assert "I've" in cleaned
    assert "that's" in cleaned
    assert "—" not in cleaned


def test_reply_length_is_enforced():
    long_reply = (
        "This is the first useful sentence. "
        "This is the second useful sentence. "
        "This extra sentence should be dropped because it makes the reply too long."
    )

    assert len(_enforce_reply_length(long_reply, 70)) <= 70


def test_promo_mentions_are_gated_by_comment_topic():
    assert _comment_allows_promo("Need a better workflow for evaluating AI agents")
    assert not _comment_allows_promo("This movie ending was weird")


def test_normal_reply_rejects_sentx_mentions():
    assert not _reply_is_acceptable(
        "sentx.ai handles this pretty well",
        include_promo=False,
        comment="Need a better workflow",
    )


def test_promo_reply_rejects_specific_product_claims():
    assert not _reply_is_acceptable(
        "sentx.ai has a similar sandbox mode that makes this easier",
        include_promo=True,
        comment="Need a better workflow for evaluating AI agents",
    )


def test_generate_reply_retries_then_falls_back(monkeypatch):
    calls = iter(
        [
            "Here's a natural reply: Honestly, " + ("too long " * 80),
            "sentx.ai handles it, game changer",
        ]
    )

    monkeypatch.setattr(settings, "reply_max_chars", 120)
    monkeypatch.setattr(
        "app.services.processor.deepseek_call",
        lambda *args, **kwargs: next(calls),
    )

    reply = generate_reply("This movie ending was weird", include_promo=True)

    assert "sentx" not in reply.lower()
    assert len(reply) <= 120


def test_regenerate_endpoint_is_manual_and_limited(client, make_reply, monkeypatch):
    first = make_reply(status="PENDING", reply_text="old one")
    second = make_reply(status="PENDING", reply_text="old two")

    monkeypatch.setattr("app.routes.replies.generate_reply", lambda comment, include_promo: f"new for {comment}")
    monkeypatch.setattr("app.routes.replies.should_insert_promo", lambda: False)

    body = client.post("/replies/regenerate", params={"limit": 1, "reroll_promo": "false"}).json()

    assert body["scanned"] == 1
    assert body["refreshed"] == 1
    replies = client.get("/replies", params={"status": "PENDING", "limit": 10}).json()
    by_id = {item["reply_id"]: item["reply_text"] for item in replies}
    assert by_id[first.id].startswith("new for")
    assert by_id[second.id] == "old two"
