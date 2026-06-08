from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from storyforge3.llm.llm_service import (
    LLMRateLimitError,
    LLMResponseFormatError,
    LLMService,
    ProviderUnavailableError,
    Route,
    _build_route_candidates,
    build_endpoint_url,
    classify_response_error,
)


def run(coro):
    return asyncio.run(coro)


def provider(**overrides) -> dict:
    data = {
        "key": "cc-primary",
        "label": "Primary",
        "base_url": "https://primary.test/v1",
        "api_key": "test-key",
        "model_id": "gpt-5.5",
        "enabled": True,
        "source": "cc-switch",
        "cc_app_type": "codex",
        "cc_api_format": "openai_responses",
        "cc_is_full_url": False,
        "cc_endpoint_auto_select": True,
        "cc_endpoint_candidates": ["https://primary.test/api/coding", "https://secondary.test/v1"],
        "cc_base_url_raw": "https://primary.test/api/coding",
        "cc_usage_base_url": "https://usage.test",
        "cc_last_verified_endpoint": None,
        "cc_last_verified_format": None,
        "cc_last_verified_model": None,
    }
    data.update(overrides)
    return data


def response_text(text: str, *, model: str = "gpt-5.5") -> dict:
    return {"output": [{"content": [{"text": text}]}], "usage": {"input_tokens": 1, "output_tokens": 2}, "model": model}


def test_build_endpoint_url_removes_compat_suffixes_and_adds_protocol_path() -> None:
    assert build_endpoint_url("https://relay.test/api/coding", "openai_chat", "gpt-5.5", False) == (
        "https://relay.test/v1/chat/completions"
    )
    assert build_endpoint_url("https://relay.test/v1", "openai_responses", "gpt-5.5", False) == "https://relay.test/v1/responses"
    assert build_endpoint_url("https://relay.test/anthropic", "anthropic", "claude-sonnet-4", False) == "https://relay.test/v1/messages"
    assert build_endpoint_url("https://relay.test/api", "gemini_native", "gemini-2.5-pro", False) == (
        "https://relay.test/api/v1beta/models/gemini-2.5-pro:generateContent"
    )
    assert build_endpoint_url("https://relay.test/custom", "openai_chat", "gpt-5.5", True) == "https://relay.test/custom"


def test_route_candidates_prioritize_verified_and_dedupe() -> None:
    routes = _build_route_candidates(
        provider(
            cc_last_verified_endpoint="https://verified.test/v1/responses",
            cc_last_verified_format="openai_responses",
            cc_last_verified_model="verified-model",
            cc_endpoint_candidates=["https://primary.test/api/coding", "https://primary.test/api/coding"],
        )
    )

    assert routes[0] == Route("https://verified.test/v1/responses", "openai_responses", "verified-model", True)
    assert len(routes) == len({(route.endpoint, route.api_format, route.model_id) for route in routes})
    assert Route("https://primary.test/v1/responses", "openai_responses", "gpt-5.5", False) in routes
    assert Route("https://primary.test/v1/chat/completions", "openai_chat", "gpt-5.5", False) in routes


def test_route_candidates_respect_auto_select_false() -> None:
    routes = _build_route_candidates(provider(cc_endpoint_auto_select=False, cc_api_format="openai_chat"))

    assert {route.api_format for route in routes} == {"openai_chat"}


def test_openai_provider_auto_select_excludes_anthropic_protocol() -> None:
    routes = _build_route_candidates(provider(cc_api_format="openai_responses"))

    formats = {route.api_format for route in routes}
    assert formats == {"openai_responses", "openai_chat"}


def test_anthropic_provider_keeps_openai_fallback_for_compatibility() -> None:
    routes = _build_route_candidates(provider(cc_app_type="claude", cc_api_format="anthropic"))

    formats = {route.api_format for route in routes}
    assert formats == {"anthropic", "openai_responses", "openai_chat"}


def test_classify_errors_and_html_detection() -> None:
    assert classify_response_error(httpx.Response(401, text='{"error":"bad key"}')) == "auth_failed"
    assert classify_response_error(httpx.Response(429, text='{"error":"slow"}')) == "rate_limited"
    assert classify_response_error(httpx.Response(404, text='{"error":"missing"}')) == "protocol_mismatch"
    assert classify_response_error(httpx.Response(200, text="<!doctype html><html></html>")) == "html_homepage"
    assert classify_response_error(httpx.Response(200, text="not json")) == "protocol_mismatch"


def test_openai_responses_request_and_extract() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=response_text("正文"))

    service = LLMService(provider(), transport=httpx.MockTransport(handler), sleep=lambda _: None)

    assert run(service.generate_text("draft", "system", {"x": 1}, prompt_version="p:v1")) == "正文"
    payload = json.loads(seen[0].content)
    assert str(seen[0].url) == "https://primary.test/v1/responses"
    assert seen[0].headers["Authorization"] == "Bearer test-key"
    assert payload["model"] == "gpt-5.5"
    assert payload["instructions"] == "system"
    assert '"x": 1' in payload["input"]
    assert service.last_call is not None
    assert service.last_call.task_name == "draft"
    assert service.last_call.success is True


def test_task_timeout_defaults_and_explicit_override() -> None:
    seen_extensions: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_extensions.append(dict(request.extensions))
        return httpx.Response(200, json=response_text("正文"))

    service = LLMService(
        provider(
            cc_endpoint_auto_select=False,
            cc_endpoint_candidates=["https://primary.test/v1"],
            cc_base_url_raw="https://primary.test/v1",
            cc_usage_base_url=None,
        ),
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
        default_timeout=120,
        draft_timeout=300,
        short_timeout=60,
    )

    assert run(service.generate_text("chapter_plan", "system", {})) == "正文"
    assert run(service.generate_text("chapter_draft_chunk", "system", {})) == "正文"
    assert run(service.generate_text("world_build", "system", {}, timeout=77)) == "正文"

    assert seen_extensions[0]["timeout"]["connect"] == 60
    assert seen_extensions[1]["timeout"]["connect"] == 300
    assert seen_extensions[2]["timeout"]["connect"] == 77


def test_openai_chat_payload_shape() -> None:
    seen_payloads: list[dict] = []
    chat_provider = provider(cc_api_format="openai_chat", cc_endpoint_auto_select=False)

    def handler(request: httpx.Request) -> httpx.Response:
        seen_payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "chat text"}}]})

    service = LLMService(chat_provider, transport=httpx.MockTransport(handler), sleep=lambda _: None)

    assert run(service.generate_text("draft", "system", {"x": 1})) == "chat text"
    assert seen_payloads[0]["messages"][0] == {"role": "system", "content": "system"}
    assert seen_payloads[0]["messages"][1]["role"] == "user"


def test_anthropic_payload_shape() -> None:
    seen: list[httpx.Request] = []
    anthropic_provider = provider(
        cc_app_type="claude",
        cc_api_format="anthropic",
        cc_endpoint_auto_select=False,
        base_url="https://claude.test",
        cc_endpoint_candidates=["https://claude.test"],
        model_id="claude-sonnet-4",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"content": [{"text": "anthropic text"}]})

    service = LLMService(anthropic_provider, transport=httpx.MockTransport(handler), sleep=lambda _: None)

    assert run(service.generate_text("draft", "system", {"x": 1})) == "anthropic text"
    payload = json.loads(seen[0].content)
    assert str(seen[0].url) == "https://claude.test/v1/messages"
    assert seen[0].headers["x-api-key"] == "test-key"
    assert payload["system"] == "system"
    assert payload["messages"][0]["role"] == "user"


def test_gemini_native_payload_shape_and_key_query() -> None:
    seen: list[httpx.Request] = []
    gemini_provider = provider(
        cc_app_type="gemini",
        cc_api_format="gemini_native",
        cc_endpoint_auto_select=True,
        base_url="https://gemini.test",
        cc_endpoint_candidates=["https://gemini.test"],
        model_id="gemini-2.5-pro",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "gemini text"}]}}]})

    service = LLMService(gemini_provider, transport=httpx.MockTransport(handler), sleep=lambda _: None)

    assert run(service.generate_text("draft", "system", {"x": 1})) == "gemini text"
    assert str(seen[0].url) == "https://gemini.test/v1beta/models/gemini-2.5-pro:generateContent?key=test-key"
    payload = json.loads(seen[0].content)
    assert "system" in payload["contents"][0]["parts"][0]["text"]


def test_failover_skips_bad_route_and_returns_first_success() -> None:
    seen_urls: list[str] = []
    responses = [
        httpx.Response(200, text="<html>homepage</html>"),
        httpx.Response(200, json={"choices": [{"message": {"content": "success"}}]}),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return responses.pop(0)

    service = LLMService(provider(), transport=httpx.MockTransport(handler), sleep=lambda _: None)

    assert run(service.generate_text("draft", "system", {"x": 1})) == "success"
    assert seen_urls[:2] == [
        "https://primary.test/v1/responses",
        "https://primary.test/v1/chat/completions",
    ]


def test_provider_level_fallback_after_primary_routes_fail() -> None:
    fallback = provider(
        key="cc-fallback",
        label="Fallback",
        base_url="https://fallback.test/v1",
        cc_endpoint_candidates=["https://fallback.test/v1"],
    )
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        if "fallback" in str(request.url):
            return httpx.Response(200, json=response_text("fallback success"))
        return httpx.Response(401, json={"error": "bad key"})

    service = LLMService(
        provider(
            cc_endpoint_auto_select=False,
            cc_endpoint_candidates=["https://primary.test/v1"],
            cc_base_url_raw="https://primary.test/v1",
            cc_usage_base_url=None,
        ),
        fallback_provider=fallback,
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
    )

    assert run(service.generate_text("draft", "system", {"x": 1})) == "fallback success"
    assert seen_urls == ["https://primary.test/v1/responses", "https://fallback.test/v1/responses"]


def test_generate_json_uses_schema_then_plain_json_fallback() -> None:
    seen_payloads: list[dict] = []
    responses = [
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(200, json=response_text('{"ok": true}')),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        seen_payloads.append(json.loads(request.content))
        return responses.pop(0)

    service = LLMService(
        provider(
            cc_endpoint_auto_select=False,
            cc_endpoint_candidates=["https://primary.test/v1"],
            cc_base_url_raw="https://primary.test/v1",
            cc_usage_base_url=None,
        ),
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
    )

    assert run(service.generate_json("world", "system", {"x": 1}, {"type": "object"})) == {"ok": True}
    assert "text" in seen_payloads[0]
    assert "response_schema" in seen_payloads[-1]["input"]
    assert "text" not in seen_payloads[-1]


def test_generate_json_rejects_missing_required_schema_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_text('{"role": "protagonist"}'))

    service = LLMService(
        provider(
            cc_endpoint_auto_select=False,
            cc_endpoint_candidates=["https://primary.test/v1"],
            cc_base_url_raw="https://primary.test/v1",
            cc_usage_base_url=None,
        ),
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
    )

    with pytest.raises(LLMResponseFormatError, match="missing required fields: name"):
        run(
            service.generate_json(
                "character_create",
                "system",
                {"spec": "主角：林默"},
                {"type": "object", "required": ["name", "role"]},
            )
        )


def test_rate_limit_and_504_retry_budgets() -> None:
    attempts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(str(request.url))
        return httpx.Response(429, json={"error": "limited"})

    service = LLMService(
        provider(
            cc_endpoint_auto_select=False,
            cc_endpoint_candidates=["https://primary.test/v1"],
            cc_base_url_raw="https://primary.test/v1",
            cc_usage_base_url=None,
        ),
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
    )

    with pytest.raises(LLMRateLimitError):
        run(service.generate_text("draft", "system", {}))
    assert len(attempts) == 4


def test_504_retries_five_attempts_with_jittered_backoff(monkeypatch) -> None:
    attempts: list[str] = []
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(str(request.url))
        return httpx.Response(504, json={"error": "gateway timeout"})

    def sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("storyforge3.llm.llm_service.random.random", lambda: 1.0)
    service = LLMService(
        provider(
            cc_endpoint_auto_select=False,
            cc_endpoint_candidates=["https://primary.test/v1"],
            cc_base_url_raw="https://primary.test/v1",
            cc_usage_base_url=None,
        ),
        transport=httpx.MockTransport(handler),
        sleep=sleep,
    )

    with pytest.raises(ProviderUnavailableError):
        run(service.generate_text("draft", "system", {}))

    assert len(attempts) == 5
    assert delays == [3.0, 6.0, 12.0, 24.0]


def test_model_id_defaults_when_missing() -> None:
    routes = _build_route_candidates(provider(model_id=""))

    assert routes[0].model_id == "default"
