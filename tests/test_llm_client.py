from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from storyforge3.llm.client import (
    CCSwitchClient,
    LLMProviderError,
    LLMRateLimitError,
    ProviderUnavailableError,
)
from storyforge3.llm.ccswitch_reader import ProviderConfig


def run(coro):
    return asyncio.run(coro)


class StaticReader:
    def __init__(self, provider: ProviderConfig | None = None, *, missing: bool = False) -> None:
        self.provider = None if missing else provider or ProviderConfig("mock", "https://provider.test/v1", "test-key", "mock-model")
        self.last_error = "missing provider" if missing else None

    def read_current_provider(self) -> ProviderConfig | None:
        return self.provider


def make_client(config, responses: list[httpx.Response], reader: StaticReader | None = None) -> CCSwitchClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if not responses:
            raise AssertionError("unexpected request")
        return responses.pop(0)

    return CCSwitchClient(config, transport=httpx.MockTransport(handler), sleep=lambda _: None, config_reader=reader or StaticReader())


def make_sleep_recorder() -> tuple[list[float], Any]:
    delays: list[float] = []

    def sleep(delay: float) -> None:
        delays.append(delay)

    return delays, sleep


def test_provider_config_is_available(config) -> None:
    client = make_client(config, [])
    assert run(client.check_health()) is True


def test_generate_json_builds_responses_request(config, mock_ccswitch_response) -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(200, json=mock_ccswitch_response)

    client = CCSwitchClient(config, transport=httpx.MockTransport(handler), sleep=lambda _: None, config_reader=StaticReader())
    result = run(client.generate_json("smoke", "system", {"x": 1}, {"type": "object"}))
    assert result == {"ok": True}
    assert seen_urls == ["https://provider.test/v1/responses"]
    assert client.last_call is not None
    assert client.last_call.success is True


def test_generate_json_falls_back_to_plain_json_when_schema_mode_5xx(config) -> None:
    seen_payloads: list[dict] = []
    responses = [
        httpx.Response(503), httpx.Response(503), httpx.Response(503),
        httpx.Response(503), httpx.Response(503),
        httpx.Response(200, json={"output": [{"content": [{"text": "{\"ok\": true}"}]}]}),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        seen_payloads.append(json.loads(request.content))
        return responses.pop(0)

    client = CCSwitchClient(config, transport=httpx.MockTransport(handler), sleep=lambda _: None, config_reader=StaticReader())
    result = run(client.generate_json("world_build", "system", {"x": 1}, {"type": "object"}))
    assert result == {"ok": True}
    assert "text" in seen_payloads[0]
    assert "text" not in seen_payloads[-1]
    assert "response_schema" in seen_payloads[-1]["input"][1]["content"][0]["text"]


def test_generate_text_extracts_output(config) -> None:
    payload = {"output": [{"content": [{"text": "正文"}]}]}
    client = make_client(config, [httpx.Response(200, json=payload)])
    assert run(client.generate_text("draft", "system", {"x": 1}, prompt_version="compose-v1:v1")) == "正文"
    assert client.last_call is not None
    assert client.last_call.prompt_version == "compose-v1:v1"


def test_rate_limit_retries_then_fails(config) -> None:
    client = make_client(config, [httpx.Response(429), httpx.Response(429), httpx.Response(429), httpx.Response(429)])
    with pytest.raises(LLMRateLimitError):
        run(client.generate_text("draft", "system", {}))


def test_5xx_becomes_provider_error(config) -> None:
    client = make_client(config, [httpx.Response(502), httpx.Response(502), httpx.Response(502), httpx.Response(502), httpx.Response(502)])
    with pytest.raises(LLMProviderError):
        run(client.generate_text("draft", "system", {}))


def test_transient_5xx_retries_then_succeeds(config) -> None:
    payload = {"output": [{"content": [{"text": "成功"}]}]}
    client = make_client(config, [httpx.Response(503), httpx.Response(503), httpx.Response(200, json=payload)])
    assert run(client.generate_text("draft", "system", {})) == "成功"
    assert client.last_call is not None
    assert client.last_call.success is True


def test_connection_error_is_unavailable(config) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    client = CCSwitchClient(config, transport=httpx.MockTransport(handler), config_reader=StaticReader())
    with pytest.raises(ProviderUnavailableError):
        run(client.generate_text("draft", "system", {}))


def test_missing_provider_config_is_unavailable(config) -> None:
    client = make_client(config, [], reader=StaticReader(missing=True))
    with pytest.raises(ProviderUnavailableError):
        run(client.generate_text("draft", "system", {}))


def test_504_retries_up_to_5_attempts(config) -> None:
    client = make_client(config, [
        httpx.Response(504), httpx.Response(504), httpx.Response(504),
        httpx.Response(504), httpx.Response(504),
    ])
    with pytest.raises(LLMProviderError):
        run(client.generate_text("draft", "system", {}))


def test_504_recover_on_5th_attempt(config) -> None:
    payload = {"output": [{"content": [{"text": "恢复成功"}]}]}
    client = make_client(config, [
        httpx.Response(504), httpx.Response(504), httpx.Response(504),
        httpx.Response(504), httpx.Response(200, json=payload),
    ])
    assert run(client.generate_text("draft", "system", {})) == "恢复成功"


def test_429_still_max_3_retries(config) -> None:
    client = make_client(config, [
        httpx.Response(429), httpx.Response(429), httpx.Response(429), httpx.Response(429),
    ])
    with pytest.raises(LLMRateLimitError):
        run(client.generate_text("draft", "system", {}))


def test_retry_sleep_uses_two_second_exponential_backoff(config) -> None:
    delays, sleep = make_sleep_recorder()
    client = CCSwitchClient(config, sleep=sleep, config_reader=StaticReader())

    run(client._retry_sleep(0))
    run(client._retry_sleep(1))
    run(client._retry_sleep(2))

    assert delays == [2.0, 4.0, 8.0]


def test_504_retry_sleep_adds_jitter(config, monkeypatch) -> None:
    delays, sleep = make_sleep_recorder()
    monkeypatch.setattr("storyforge3.llm.client.random.random", lambda: 1.0)
    client = CCSwitchClient(config, sleep=sleep, config_reader=StaticReader())

    run(client._retry_sleep(0, jitter=0.5))
    run(client._retry_sleep(1, jitter=0.5))

    assert delays == [3.0, 6.0]


def test_task_timeout_draft_uses_longer_timeout(config) -> None:
    assert config.llm_draft_timeout_seconds == 300
    assert config.llm_truth_timeout_seconds == 600
    assert config.llm_short_timeout_seconds == 60
    client = make_client(config, [])
    assert client._timeout_for_task("draft") == 300
    assert client._timeout_for_task("chapter_draft") == 300
    assert client._timeout_for_task("chapter_draft_chunk") == 300
    assert client._timeout_for_task("length_normalize") == 300
    assert client._timeout_for_task("revise") == 300
    assert client._timeout_for_task("plan") == 120
    assert client._timeout_for_task("chapter_plan") == 120
    assert client._timeout_for_task("truth_extract") == 600
    assert client._timeout_for_task("health") == 60
    assert client._timeout_for_task("world_build") == 120
