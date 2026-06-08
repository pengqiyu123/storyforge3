from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import Callable
from typing import Any

import httpx

from storyforge3.config import StoryForge3Config
from storyforge3.llm.ccswitch_reader import CCSwitchConfigReader, ProviderConfig
from storyforge3.models import LLMCallRecord


class ProviderUnavailableError(RuntimeError):
    pass


class LLMRateLimitError(RuntimeError):
    pass


class LLMProviderError(RuntimeError):
    pass


class LLMTimeoutError(RuntimeError):
    pass


class LLMResponseFormatError(RuntimeError):
    pass


class CCSwitchClient:
    """Deprecated OpenAI Responses-compatible client.

    New code should use storyforge3.llm.llm_service.LLMService through
    storyforge3.llm.factory.create_llm_service().
    """

    def __init__(
        self,
        config: StoryForge3Config,
        *,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Any] | None = None,
        config_reader: CCSwitchConfigReader | None = None,
    ) -> None:
        self.config = config
        self.last_call: LLMCallRecord | None = None
        self._transport = transport
        self._sleep = sleep or asyncio.sleep
        self._config_reader = config_reader or CCSwitchConfigReader(config)

    async def check_health(self) -> bool:
        return self._config_reader.read_current_provider() is not None

    async def generate_json(
        self,
        task_name: str,
        system_prompt: str,
        user_payload: dict,
        response_schema: dict,
        *,
        model: str | None = None,
        prompt_version: str | None = None,
        timeout: int | None = None,
    ) -> dict:
        provider = self._require_provider()
        payload = self._build_payload(system_prompt, user_payload, model=model or provider.default_model, response_schema=response_schema)
        effective_timeout = timeout or self._timeout_for_task(task_name)
        try:
            text = await self._post_and_extract(task_name, provider, payload, prompt_version=prompt_version, timeout=effective_timeout)
        except LLMProviderError:
            fallback_payload = self._build_plain_json_payload(
                system_prompt,
                user_payload,
                response_schema=response_schema,
                model=model or provider.default_model,
            )
            text = await self._post_and_extract(task_name, provider, fallback_payload, prompt_version=prompt_version, timeout=effective_timeout)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMResponseFormatError(f"{task_name}: invalid JSON response") from exc
        if not isinstance(parsed, dict):
            raise LLMResponseFormatError(f"{task_name}: JSON response is not an object")
        return parsed

    async def generate_text(
        self,
        task_name: str,
        system_prompt: str,
        user_payload: dict,
        *,
        model: str | None = None,
        timeout: int | None = None,
        **kwargs: object,
    ) -> str:
        provider = self._require_provider()
        payload = self._build_payload(system_prompt, user_payload, model=model or provider.default_model, **kwargs)
        effective_timeout = timeout or self._timeout_for_task(task_name)
        return await self._post_and_extract(task_name, provider, payload, prompt_version=kwargs.get("prompt_version"), timeout=effective_timeout)

    def _client(self, timeout: int | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=timeout or self.config.llm_timeout_seconds,
            transport=self._transport,
        )

    def _build_payload(self, system_prompt: str, user_payload: dict, *, model: str | None = None, **kwargs: object) -> dict:
        payload = {
            "model": model or self.config.default_model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": json.dumps(user_payload, ensure_ascii=False)}]},
            ],
        }
        if kwargs.get("response_schema") is not None:
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "storyforge3_response",
                    "schema": kwargs["response_schema"],
                }
            }
        for key in ("temperature", "max_output_tokens"):
            if kwargs.get(key) is not None:
                payload[key] = kwargs[key]
        return payload

    def _build_plain_json_payload(
        self,
        system_prompt: str,
        user_payload: dict,
        *,
        response_schema: dict,
        model: str | None = None,
    ) -> dict:
        fallback_payload = {
            **user_payload,
            "response_schema": response_schema,
            "format_instruction": "请只输出一个合法 JSON object，不要 Markdown，不要解释。",
        }
        return self._build_payload(system_prompt, fallback_payload, model=model)

    def _require_provider(self) -> ProviderConfig:
        provider = self._config_reader.read_current_provider()
        if provider is None:
            error = self._config_reader.last_error or "CCSwitch provider config unavailable"
            raise ProviderUnavailableError(error)
        return provider

    async def _post_and_extract(self, task_name: str, provider: ProviderConfig, payload: dict, *, prompt_version: str | None = None, timeout: int | None = None) -> str:
        started = time.perf_counter()
        try:
            raw = await self._post_with_retries(provider, payload, timeout=timeout)
            text = self._extract_text(raw)
            self._record_call(task_name, raw, started, success=True, prompt_version=prompt_version)
            return text
        except httpx.TimeoutException as exc:
            self._record_call(task_name, {}, started, success=False, error=str(exc), prompt_version=prompt_version)
            raise LLMTimeoutError(f"{task_name}: CCSwitch request timed out") from exc
        except httpx.ConnectError as exc:
            self._record_call(task_name, {}, started, success=False, error=str(exc), prompt_version=prompt_version)
            raise ProviderUnavailableError("Provider 不可达，请检查 CCSwitch 当前配置") from exc

    async def _post_with_retries(self, provider: ProviderConfig, payload: dict, *, timeout: int | None = None) -> dict:
        url = f"{provider.base_url}/responses"
        max_attempts = 5
        for attempt in range(max_attempts):
            async with self._client(timeout=timeout) as client:
                response = await client.post(url, json=payload, headers={"Authorization": f"Bearer {provider.api_key}"})
            if response.status_code == 429 and attempt < 3:
                await self._retry_sleep(attempt, base=2.0)
                continue
            if response.status_code in {502, 503, 504} and attempt < max_attempts - 1:
                await self._retry_sleep(attempt, base=2.0, jitter=0.5)
                continue
            if response.status_code == 429:
                raise LLMRateLimitError("CCSwitch rate limit after 3 retries")
            if response.status_code >= 500:
                raise LLMProviderError(f"CCSwitch provider error after retries: HTTP {response.status_code}")
            response.raise_for_status()
            return response.json()
        raise LLMProviderError("CCSwitch provider error: max retries exceeded")

    @staticmethod
    def _should_retry(status_code: int) -> bool:
        return status_code == 429 or status_code in {502, 503, 504}

    async def _retry_sleep(self, attempt: int, *, base: float = 2.0, jitter: float = 0.0) -> None:
        delay = base * (2**attempt)
        if jitter > 0:
            delay *= 1.0 + random.random() * jitter  # noqa: S311
        result = self._sleep(delay)
        if hasattr(result, "__await__"):
            await result

    def _timeout_for_task(self, task_name: str) -> int:
        normalized = task_name.lower()
        if "draft" in normalized or "revise" in normalized or "normalize" in normalized:
            return self.config.llm_draft_timeout_seconds
        short_tasks = {"health", "chapter_plan", "plan"}
        if normalized in short_tasks:
            return self.config.llm_short_timeout_seconds
        return self.config.llm_timeout_seconds

    @staticmethod
    def _extract_text(raw: dict) -> str:
        for item in raw.get("output", []):
            for content in item.get("content", []):
                text = content.get("text") or content.get("output_text")
                if isinstance(text, str):
                    return text
        raise LLMResponseFormatError("missing output text")

    def _record_call(
        self,
        task_name: str,
        raw: dict,
        started: float,
        *,
        success: bool,
        error: str | None = None,
        prompt_version: str | None = None,
    ) -> None:
        usage = raw.get("usage", {}) if isinstance(raw, dict) else {}
        self.last_call = LLMCallRecord(
            task_name=task_name,
            model=str(raw.get("model") or self.config.default_model),
            prompt_version=prompt_version or "unknown",
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            latency_ms=(time.perf_counter() - started) * 1000,
            success=success,
            error=error,
        )
