from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from storyforge3.models import LLMCallRecord

API_FORMATS = ("openai_responses", "openai_chat", "anthropic", "gemini_native")
OPENAI_FORMATS = ("openai_responses", "openai_chat")
NON_GEMINI_FORMATS = ("openai_responses", "openai_chat", "anthropic")
COMPAT_SUFFIXES = (
    "/api/claudecode",
    "/api/anthropic",
    "/apps/anthropic",
    # NOTE: "/api/coding" and "/coding" intentionally NOT stripped — Volcano Engine
    # (火山引擎) Coding Plan uses /api/coding as a real path prefix
    # (endpoint = .../api/coding/v1/messages). Stripping it corrupts the route.
    "/claudecode",
    "/anthropic",
    "/step_plan",
    "/claude",
)
TERMINAL_PATHS = (
    "/v1/chat/completions",
    "/chat/completions",
    "/v1/responses",
    "/responses",
    "/v1/messages",
    "/messages",
)


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


class LLMRouteError(RuntimeError):
    def __init__(self, probe_status: str, message: str, *, route: Route | None = None) -> None:
        self.probe_status = probe_status
        self.route = route
        super().__init__(message)


@dataclass(frozen=True)
class Route:
    endpoint: str
    api_format: str
    model_id: str
    verified: bool = False


def _extract_json_object(text: str) -> str:
    """Tolerantly extract a JSON object from an LLM response.

    Models (especially Claude via relays) often wrap JSON in ```json fences or
    add prose around it, which breaks strict ``json.loads``. This strips a single
    code fence and, failing that, brace-matches the outermost ``{...}`` (string-
    aware) to recover the object. Raises ``json.JSONDecodeError`` if nothing parses,
    so callers can wrap it in LLMResponseFormatError with task context.
    """
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", stripped, re.DOTALL | re.IGNORECASE)
    if fence:
        stripped = fence.group(1).strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    if start == -1:
        return stripped  # let json.loads raise with the original text
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(stripped)):
        char = stripped[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return stripped[start : index + 1]
    return stripped


class LLMService:
    """Direct provider caller with CC-Switch-derived route failover."""

    def __init__(
        self,
        provider: dict,
        *,
        fallback_provider: dict | None = None,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Any] | None = None,
        default_timeout: int = 120,
        draft_timeout: int = 300,
        truth_timeout: int = 600,
        short_timeout: int = 60,
    ) -> None:
        self.provider = dict(provider)
        self.fallback_provider = dict(fallback_provider) if fallback_provider else None
        self.last_call: LLMCallRecord | None = None
        self._transport = transport
        self._sleep = sleep or asyncio.sleep
        self.default_timeout = default_timeout
        self.draft_timeout = draft_timeout
        self.truth_timeout = truth_timeout
        self.short_timeout = short_timeout

    async def check_health(self) -> bool:
        try:
            result = await self._try_provider_routes(
                self.provider,
                self._payload("health", "Return a short health response.", {}, None, model=None),
                task_name="health",
                timeout=30,
            )
        except (LLMRouteError, httpx.HTTPError):
            return False
        self._write_verified_to_provider(self.provider, result)
        return True

    async def generate_text(
        self,
        task_name,
        system_prompt,
        user_payload,
        *,
        model=None,
        timeout=None,
        **kwargs,
    ) -> str:
        started = time.perf_counter()
        payload = self._payload(task_name, system_prompt, user_payload, kwargs, model=model)
        effective_timeout = timeout or self._timeout_for_task(str(task_name))
        self._diag(
            "generate_text start "
            f"task={task_name} timeout={effective_timeout}s "
            f"prompt_chars={len(str(system_prompt))} user_text_chars={len(payload['user_text'])}"
        )
        try:
            result = await self._try_with_provider_fallback(payload, task_name=task_name, timeout=effective_timeout)
            self._diag(f"generate_text ok task={task_name} elapsed={time.perf_counter() - started:.2f}s")
            self._record_call(task_name, result["raw"], started, True, prompt_version=kwargs.get("prompt_version"))
            return str(result["text"])
        except httpx.TimeoutException as exc:
            self._diag(f"generate_text timeout task={task_name} elapsed={time.perf_counter() - started:.2f}s timeout={effective_timeout}s")
            self._record_call(task_name, {}, started, False, error=str(exc), prompt_version=kwargs.get("prompt_version"))
            raise LLMTimeoutError(f"{task_name}: provider request timed out") from exc
        except httpx.ConnectError as exc:
            self._record_call(task_name, {}, started, False, error=str(exc), prompt_version=kwargs.get("prompt_version"))
            raise ProviderUnavailableError(f"{task_name}: provider unavailable") from exc
        except LLMRouteError as exc:
            self._record_call(task_name, {}, started, False, error=str(exc), prompt_version=kwargs.get("prompt_version"))
            if exc.probe_status == "rate_limited":
                raise LLMRateLimitError(str(exc)) from exc
            if exc.probe_status == "connection_failed":
                raise ProviderUnavailableError(str(exc)) from exc
            raise LLMProviderError(str(exc)) from exc

    async def generate_text_stream(
        self,
        task_name: str,
        system_prompt: str,
        user_payload: dict,
        *,
        model: str | None = None,
        timeout: int | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Stream text chunks when the active route supports OpenAI-compatible SSE."""
        started = time.perf_counter()
        payload = self._payload(task_name, system_prompt, user_payload, kwargs, model=model)
        effective_timeout = timeout or self._timeout_for_task(str(task_name))
        route_pair = self._streaming_provider_route(payload)
        if route_pair is None:
            async for text in self._generate_text_as_stream(task_name, system_prompt, user_payload, model=model, timeout=timeout, **kwargs):
                yield text
            return

        provider, route = route_pair
        yielded = False
        try:
            async for chunk in self._stream_response(provider, route, payload, timeout=effective_timeout):
                yielded = True
                yield chunk
            self._record_call(
                task_name,
                {"model": route.model_id, "usage": {}},
                started,
                True,
                prompt_version=kwargs.get("prompt_version"),
            )
        except httpx.TimeoutException as exc:
            self._record_call(task_name, {}, started, False, error=str(exc), prompt_version=kwargs.get("prompt_version"))
            raise LLMTimeoutError(f"{task_name}: provider request timed out") from exc
        except httpx.ConnectError as exc:
            self._record_call(task_name, {}, started, False, error=str(exc), prompt_version=kwargs.get("prompt_version"))
            raise ProviderUnavailableError(f"{task_name}: provider unavailable") from exc
        except LLMRouteError:
            if yielded:
                self._record_call(
                    task_name,
                    {"model": route.model_id, "usage": {}},
                    started,
                    False,
                    error="stream interrupted",
                    prompt_version=kwargs.get("prompt_version"),
                )
                raise
            async for text in self._generate_text_as_stream(task_name, system_prompt, user_payload, model=model, timeout=timeout, **kwargs):
                yield text

    async def _generate_text_as_stream(
        self,
        task_name: str,
        system_prompt: str,
        user_payload: dict,
        *,
        model: str | None = None,
        timeout: int | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        text = await self.generate_text(task_name, system_prompt, user_payload, model=model, timeout=timeout, **kwargs)
        if text:
            yield text

    async def generate_json(
        self,
        task_name,
        system_prompt,
        user_payload,
        response_schema,
        *,
        model=None,
        timeout=None,
        max_json_retries=1,
        **kwargs,
    ) -> dict:
        last_error_text = ""
        for attempt in range(max_json_retries + 1):
            try:
                payload = user_payload
                call_kwargs = dict(kwargs)
                if attempt == 0:
                    call_kwargs["response_schema"] = response_schema
                else:
                    payload = {
                        **dict(user_payload),
                        "response_schema": response_schema,
                        "format_instruction": "请只输出一个合法 JSON object，不要 Markdown，不要解释。",
                        "previous_invalid_response": last_error_text,
                        "correction_instruction": "上一轮响应无法解析为 JSON，请修正并只输出合法 JSON object。",
                    }
                text = await self.generate_text(task_name, system_prompt, payload, model=model, timeout=timeout, **call_kwargs)
            except (LLMProviderError, ProviderUnavailableError):
                if attempt >= max_json_retries:
                    raise
                fallback_payload = {
                    **dict(user_payload),
                    "response_schema": response_schema,
                    "format_instruction": "请只输出一个合法 JSON object，不要 Markdown，不要解释。",
                }
                text = await self.generate_text(task_name, system_prompt, fallback_payload, model=model, timeout=timeout, **kwargs)
            try:
                data = json.loads(_extract_json_object(text))
            except json.JSONDecodeError as exc:
                last_error_text = text[:500]
                if attempt >= max_json_retries:
                    raise LLMResponseFormatError(f"{task_name}: invalid JSON response after {attempt + 1} attempts") from exc
                continue
            if not isinstance(data, dict):
                raise LLMResponseFormatError(f"{task_name}: JSON response is not an object")
            _validate_response_schema(data, response_schema, task_name)
            return data
        raise LLMResponseFormatError(f"{task_name}: exhausted JSON retries")

    async def _try_with_provider_fallback(self, payload: dict, *, task_name: str, timeout: int | None) -> dict:
        primary_provider = self._provider_for_payload(self.provider, payload)
        try:
            result = await self._try_provider_routes(primary_provider, payload, task_name=task_name, timeout=timeout)
            self._write_verified_to_provider(self.provider, result)
            return result
        except LLMRouteError:
            if self.fallback_provider is None:
                raise
            fallback_provider = self._provider_for_payload(self.fallback_provider, payload)
            result = await self._try_provider_routes(fallback_provider, payload, task_name=task_name, timeout=timeout)
            self._write_verified_to_provider(self.fallback_provider, result)
            return result

    async def _try_provider_routes(self, provider: dict, payload: dict, *, task_name: str, timeout: int | None = None) -> dict:
        last_error: LLMRouteError | None = None
        routes = _build_route_candidates(provider)
        if not routes:
            raise LLMRouteError("request_failed", "未找到可用的请求端点")
        for route in routes:
            try:
                return await self._invoke_route(provider, route, payload, task_name=task_name, timeout=timeout)
            except LLMRouteError as exc:
                last_error = exc
                if exc.probe_status == "model_missing" and route.api_format in OPENAI_FORMATS and not route.model_id:
                    fallback_result = await self._try_model_fallbacks(provider, route, payload, task_name=task_name, timeout=timeout)
                    if fallback_result is not None:
                        return fallback_result
                continue
            except LLMResponseFormatError as exc:
                last_error = LLMRouteError("protocol_mismatch", str(exc), route=route)
                continue
        raise last_error or LLMRouteError("request_failed", "未找到可用的请求端点")

    async def _invoke_route(self, provider: dict, route: Route, payload: dict, *, task_name: str, timeout: int | None) -> dict:
        request_route = _request_route_for_default_model(route)
        response = await self._post_with_retries(provider, request_route, payload, timeout=timeout)
        raw = self._safe_response_json(response, request_route)
        return {
            "text": self._extract_text(request_route.api_format, raw),
            "raw": raw,
            "route": request_route,
            "resolved_endpoint": request_route.endpoint,
            "resolved_format": request_route.api_format,
            "resolved_model": str(raw.get("model") or request_route.model_id),
        }

    async def _try_model_fallbacks(
        self,
        provider: dict,
        route: Route,
        payload: dict,
        *,
        task_name: str,
        timeout: int | None,
    ) -> dict | None:
        for model_id in await self._fetch_model_ids(provider, route, timeout=timeout):
            fallback_route = Route(_route_endpoint_for_model(route, model_id), route.api_format, model_id, route.verified)
            try:
                return await self._invoke_route(provider, fallback_route, payload, task_name=task_name, timeout=timeout)
            except LLMRouteError:
                continue
        return None

    async def _fetch_model_ids(self, provider: dict, route: Route, *, timeout: int | None) -> list[str]:
        endpoint = _models_endpoint_for(route.endpoint)
        try:
            async with self._client(timeout=timeout) as client:
                response = await client.get(endpoint, headers=self._headers(provider, route))
        except httpx.HTTPError:
            return []
        if classify_response_error(response) != "verified":
            return []
        try:
            raw = response.json()
        except json.JSONDecodeError:
            return []
        return _rank_model_ids(_extract_model_ids(raw))

    def _streaming_provider_route(self, payload: dict) -> tuple[dict, Route] | None:
        providers = [self._provider_for_payload(self.provider, payload)]
        if self.fallback_provider is not None:
            providers.append(self._provider_for_payload(self.fallback_provider, payload))
        for provider in providers:
            for route in _build_route_candidates(provider):
                request_route = _request_route_for_default_model(route)
                if request_route.api_format in OPENAI_FORMATS:
                    return provider, request_route
        return None

    async def _stream_response(
        self,
        provider: dict,
        route: Route,
        payload: dict,
        *,
        timeout: int | None,
    ) -> AsyncIterator[str]:
        body = self._streaming_body_for_route(route, payload)
        async with self._client(timeout=timeout) as client:
            async with client.stream(
                "POST",
                self._request_url(provider, route),
                headers=self._headers(provider, route),
                json=body,
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise LLMRouteError(
                        classify_response_error(response),
                        f"{route.api_format} {route.endpoint}: HTTP {response.status_code}",
                        route=route,
                    )
                buffer = ""
                async for raw_chunk in response.aiter_text():
                    buffer += raw_chunk
                    while "\n\n" in buffer:
                        event_text, buffer = buffer.split("\n\n", 1)
                        text = self._extract_stream_delta(route.api_format, event_text)
                        if text is not None:
                            yield text
                if buffer:
                    text = self._extract_stream_delta(route.api_format, buffer)
                    if text is not None:
                        yield text

    async def _post_with_retries(self, provider: dict, route: Route, payload: dict, *, timeout: int | None) -> httpx.Response:
        attempts = 4 if route.api_format == "gemini_native" else 5
        for attempt in range(attempts):
            request_started = time.perf_counter()
            self._diag(
                "request start "
                f"attempt={attempt + 1}/{attempts} format={route.api_format} "
                f"endpoint={route.endpoint} timeout={timeout or self.default_timeout}s"
            )
            try:
                async with self._client(timeout=timeout) as client:
                    response = await client.post(
                        self._request_url(provider, route),
                        headers=self._headers(provider, route),
                        json=self._body_for_route(route, payload),
                    )
            except httpx.TimeoutException:
                self._diag(
                    "request timeout "
                    f"attempt={attempt + 1}/{attempts} format={route.api_format} "
                    f"elapsed={time.perf_counter() - request_started:.2f}s "
                    f"timeout={timeout or self.default_timeout}s"
                )
                raise
            except httpx.ConnectError as exc:
                self._diag(
                    "request connect_error "
                    f"attempt={attempt + 1}/{attempts} format={route.api_format} "
                    f"elapsed={time.perf_counter() - request_started:.2f}s"
                )
                raise LLMRouteError("connection_failed", f"connection failed: {exc}", route=route) from exc
            except httpx.RemoteProtocolError as exc:
                self._diag(
                    "request protocol_error "
                    f"attempt={attempt + 1}/{attempts} format={route.api_format} "
                    f"elapsed={time.perf_counter() - request_started:.2f}s"
                )
                if attempt < attempts - 1:
                    await self._retry_sleep(attempt, jitter=0.5)
                    continue
                raise LLMRouteError("server_disconnected", f"server disconnected: {exc}", route=route) from exc
            self._diag(
                "request response "
                f"attempt={attempt + 1}/{attempts} format={route.api_format} "
                f"status={response.status_code} elapsed={time.perf_counter() - request_started:.2f}s"
            )
            if response.status_code == 429 and attempt < 3:
                await self._retry_sleep(attempt)
                continue
            if response.status_code in {502, 503, 504} and attempt < 4:
                await self._retry_sleep(attempt, jitter=0.5)
                continue
            status = classify_response_error(response)
            if status == "verified":
                return response
            raise LLMRouteError(status, f"{route.api_format} {route.endpoint}: HTTP {response.status_code}", route=route)
        raise LLMRouteError("request_failed", f"{route.api_format} {route.endpoint}: max retries exceeded", route=route)

    def _client(self, timeout: int | None) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout or self.default_timeout, transport=self._transport)

    @staticmethod
    def _request_url(provider: dict, route: Route) -> str:
        if route.api_format != "gemini_native":
            return route.endpoint
        separator = "&" if "?" in route.endpoint else "?"
        return f"{route.endpoint}{separator}{urlencode({'key': str(provider.get('api_key') or '')})}"

    @staticmethod
    def _headers(provider: dict, route: Route) -> dict[str, str]:
        api_key = str(provider.get("api_key") or "")
        if route.api_format == "anthropic":
            return {
                "x-api-key": api_key,
                "Authorization": f"Bearer {api_key}",
                "anthropic-version": "2023-06-01",
            }
        if route.api_format == "gemini_native":
            return {}
        return {"Authorization": f"Bearer {api_key}"}

    @staticmethod
    def _body_for_route(route: Route, payload: dict) -> dict:
        if route.api_format == "openai_chat":
            body = {
                "model": route.model_id,
                "messages": [
                    {"role": "system", "content": payload["system_prompt"]},
                    {"role": "user", "content": payload["user_text"]},
                ],
            }
            _copy_generation_options(payload, body, max_token_key="max_tokens")
            return body
        if route.api_format == "openai_responses":
            body = {
                "model": route.model_id,
                "instructions": payload["system_prompt"],
                "input": payload["user_text"],
            }
            if payload.get("response_schema") is not None:
                body["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": "storyforge3_response",
                        "schema": payload["response_schema"],
                    }
                }
            _copy_generation_options(payload, body, max_token_key="max_output_tokens")
            return body
        if route.api_format == "anthropic":
            body = {
                "model": route.model_id,
                "max_tokens": int(payload.get("max_tokens") or payload.get("max_output_tokens") or 4096),
                "system": payload["system_prompt"],
                "messages": [{"role": "user", "content": payload["user_text"]}],
            }
            _copy_generation_options(payload, body, max_token_key="max_tokens")
            return body
        body = {
            "contents": [{"parts": [{"text": f"{payload['system_prompt']}\n\n{payload['user_text']}"}]}],
            "generationConfig": {},
        }
        if payload.get("temperature") is not None:
            body["generationConfig"]["temperature"] = payload["temperature"]
        max_tokens = payload.get("max_output_tokens") or payload.get("max_tokens")
        if max_tokens is not None:
            body["generationConfig"]["maxOutputTokens"] = max_tokens
        if not body["generationConfig"]:
            body.pop("generationConfig")
        return body

    @staticmethod
    def _streaming_body_for_route(route: Route, payload: dict) -> dict:
        body = LLMService._body_for_route(route, payload)
        if route.api_format == "openai_chat":
            body["stream"] = True
            body["stream_options"] = {"include_usage": True}
        elif route.api_format == "openai_responses":
            body["stream"] = True
        return body

    @staticmethod
    def _payload(task_name: str, system_prompt: str, user_payload: dict, options: dict | None, *, model: str | None) -> dict:
        options = options or {}
        body = {
            "task_name": task_name,
            "system_prompt": system_prompt,
            "user_payload": user_payload,
            "user_text": _payload_text(user_payload),
            "model": model,
        }
        for key in ("temperature", "max_output_tokens", "max_tokens", "response_schema"):
            if options.get(key) is not None:
                body[key] = options[key]
        return body

    @staticmethod
    def _safe_response_json(response: httpx.Response, route: Route) -> dict:
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise LLMRouteError(classify_response_error(response), f"non-JSON response from {route.endpoint}", route=route) from exc
        if not isinstance(data, dict):
            raise LLMRouteError("protocol_mismatch", f"non-object JSON response from {route.endpoint}", route=route)
        return data

    @staticmethod
    def _extract_text(api_format: str, raw: dict) -> str:
        if api_format == "openai_chat":
            choices = raw.get("choices")
            if isinstance(choices, list) and choices:
                message = choices[0].get("message") if isinstance(choices[0], dict) else None
                content = message.get("content") if isinstance(message, dict) else None
                if isinstance(content, str):
                    return content
        if api_format == "openai_responses":
            output_text = raw.get("output_text")
            if isinstance(output_text, str):
                return output_text
            for item in raw.get("output", []):
                if not isinstance(item, dict):
                    continue
                for content in item.get("content", []):
                    if isinstance(content, dict):
                        text = content.get("text") or content.get("output_text")
                        if isinstance(text, str):
                            return text
        if api_format == "anthropic":
            for content in raw.get("content", []):
                if isinstance(content, dict) and isinstance(content.get("text"), str):
                    return content["text"]
        if api_format == "gemini_native":
            candidates = raw.get("candidates")
            if isinstance(candidates, list) and candidates:
                content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
                parts = content.get("parts") if isinstance(content, dict) else None
                if isinstance(parts, list) and parts and isinstance(parts[0], dict) and isinstance(parts[0].get("text"), str):
                    return parts[0]["text"]
        raise LLMResponseFormatError("missing output text")

    @staticmethod
    def _extract_stream_delta(api_format: str, event_text: str) -> str | None:
        """Extract a text delta from one Server-Sent Event block."""
        for line in event_text.splitlines():
            if not line.startswith("data: "):
                continue
            data_str = line[6:].strip()
            if data_str == "[DONE]":
                return None
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            if api_format == "openai_chat":
                choices = data.get("choices")
                if isinstance(choices, list) and choices:
                    first = choices[0]
                    delta = first.get("delta") if isinstance(first, dict) else None
                    content = delta.get("content") if isinstance(delta, dict) else None
                    if isinstance(content, str):
                        return content
            if api_format == "openai_responses" and data.get("type") == "response.output_text.delta":
                delta = data.get("delta")
                if isinstance(delta, str):
                    return delta
        return None

    async def _retry_sleep(self, attempt: int, *, jitter: float = 0.0) -> None:
        delay = 2.0 * (2**attempt)
        if jitter > 0:
            delay *= 1.0 + random.random() * jitter  # noqa: S311
        result = self._sleep(delay)
        if hasattr(result, "__await__"):
            await result

    def _timeout_for_task(self, task_name: str) -> int:
        normalized = task_name.lower()
        if "draft" in normalized or "revise" in normalized or "normalize" in normalized:
            return self.draft_timeout
        if normalized == "truth_extract":
            return self.truth_timeout
        if normalized == "health":
            return self.short_timeout
        return self.default_timeout

    @staticmethod
    def _diag(message: str) -> None:
        if os.environ.get("STORYFORGE3_LLM_DIAG") == "1":
            print(f"[LLM-DIAG] {time.strftime('%Y-%m-%d %H:%M:%S')} {message}", flush=True)

    @staticmethod
    def _write_verified_to_provider(provider: dict, result: dict) -> None:
        provider["cc_last_verified_endpoint"] = result["resolved_endpoint"]
        provider["cc_last_verified_format"] = result["resolved_format"]
        provider["cc_last_verified_model"] = result["resolved_model"]

    @staticmethod
    def _provider_for_payload(provider: dict, payload: dict) -> dict:
        routed = dict(provider)
        if payload.get("model"):
            routed["model_id"] = str(payload["model"])
        return routed

    def _record_call(
        self,
        task_name: str,
        raw: dict,
        started: float,
        success: bool,
        *,
        error: str | None = None,
        prompt_version: object = None,
    ) -> None:
        usage = raw.get("usage", {}) if isinstance(raw, dict) else {}
        self.last_call = LLMCallRecord(
            task_name=str(task_name),
            model=str(raw.get("model") or self.provider.get("model_id") or "default"),
            prompt_version=str(prompt_version or "unknown"),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            latency_ms=(time.perf_counter() - started) * 1000,
            success=success,
            error=error,
        )


def _build_route_candidates(provider: dict, prefer_verified: bool = True) -> list[Route]:
    declared_format = _declared_format(provider)
    model_id = str(provider.get("model_id") or "").strip()
    verified_model = str(provider.get("cc_last_verified_model") or "").strip()
    route_model_id = model_id or verified_model
    formats = _formats_for_provider(provider, declared_format)
    is_full_url = bool(provider.get("cc_is_full_url"))
    routes: list[Route] = []
    if prefer_verified and provider.get("cc_last_verified_endpoint"):
        routes.append(
            Route(
                str(provider["cc_last_verified_endpoint"]),
                str(provider.get("cc_last_verified_format") or declared_format),
                verified_model or model_id,
                True,
            )
        )
    for raw_endpoint in _raw_endpoint_candidates(provider):
        for api_format in formats:
            endpoint = build_endpoint_url(raw_endpoint, api_format, route_model_id, is_full_url)
            if not endpoint:
                continue
            routes.append(
                Route(
                    endpoint,
                    api_format,
                    route_model_id,
                    False,
                )
            )
    return _dedupe_routes(routes)


def build_endpoint_url(raw_url: str, api_format: str, model_id: str, is_full_url: bool | None = False) -> str:
    base = raw_url.rstrip("/")
    if is_full_url:
        return base
    base = _strip_terminal_path(_strip_compat_suffix(base))
    if api_format == "gemini_native":
        if not model_id:
            return ""
        return f"{base}/v1beta/models/{model_id}:generateContent"
    if base.endswith("/v1"):
        suffix = {
            "openai_chat": "/chat/completions",
            "openai_responses": "/responses",
            "anthropic": "/messages",
        }[api_format]
    else:
        suffix = {
            "openai_chat": "/v1/chat/completions",
            "openai_responses": "/v1/responses",
            "anthropic": "/v1/messages",
        }[api_format]
    return f"{base}{suffix}"


def classify_response_error(response: httpx.Response) -> str:
    preview = response.text[:200].lstrip().lower()
    if preview.startswith("<!doctype html") or preview.startswith("<html"):
        return "html_homepage"
    if response.status_code in {400, 404} and _looks_like_model_missing(response.text):
        return "model_missing"
    if 200 <= response.status_code < 300:
        try:
            response.json()
        except json.JSONDecodeError:
            return "protocol_mismatch"
        return "verified"
    if response.status_code in {401, 403}:
        return "auth_failed"
    if response.status_code == 429:
        return "rate_limited"
    if response.status_code in {404, 405}:
        return "protocol_mismatch"
    if response.status_code in {502, 503, 504}:
        return "connection_failed"
    return "request_failed"


def _looks_like_model_missing(text: str) -> bool:
    lowered = text.lower()
    return "model" in lowered and any(marker in lowered for marker in ("not found", "does not exist", "missing", "不存在"))


def _declared_format(provider: dict) -> str:
    value = str(provider.get("cc_api_format") or "")
    if value in API_FORMATS:
        return value
    app_type = str(provider.get("cc_app_type") or "")
    if app_type == "claude":
        return "anthropic"
    if app_type == "gemini":
        return "gemini_native"
    return "openai_responses"


def _formats_for_provider(provider: dict, declared_format: str) -> list[str]:
    if declared_format == "gemini_native" or provider.get("cc_endpoint_auto_select") is False:
        return [declared_format]
    if declared_format in OPENAI_FORMATS:
        ordered = [declared_format, *OPENAI_FORMATS]
    else:
        ordered = [declared_format, *NON_GEMINI_FORMATS]
    return _dedupe_strings(ordered)


def _raw_endpoint_candidates(provider: dict) -> list[str]:
    values = []
    values.extend(provider.get("cc_endpoint_candidates") or [])
    values.extend([provider.get("cc_base_url_raw"), provider.get("cc_usage_base_url"), provider.get("base_url")])
    return _dedupe_strings(str(value).strip() for value in values if value)


def _strip_compat_suffix(url: str) -> str:
    lowered = url.lower()
    for suffix in COMPAT_SUFFIXES:
        if lowered.endswith(suffix):
            return url[: -len(suffix)].rstrip("/")
    return url


def _strip_terminal_path(url: str) -> str:
    lowered = url.lower()
    for suffix in TERMINAL_PATHS:
        if lowered.endswith(suffix):
            return url[: -len(suffix)].rstrip("/")
    return url


def _models_endpoint_for(endpoint: str) -> str:
    base = _strip_terminal_path(endpoint.rstrip("/"))
    if base.endswith("/v1"):
        return f"{base}/models"
    return f"{base}/v1/models"


def _route_endpoint_for_model(route: Route, model_id: str) -> str:
    if route.api_format != "gemini_native" or "/models/" not in route.endpoint:
        return route.endpoint
    prefix, _, remainder = route.endpoint.partition("/models/")
    _, separator, suffix = remainder.partition(":generateContent")
    if not separator:
        return route.endpoint
    return f"{prefix}/models/{model_id}:generateContent{suffix}"


def _request_route_for_default_model(route: Route) -> Route:
    if route.model_id or route.api_format not in OPENAI_FORMATS:
        return route
    return Route(route.endpoint, route.api_format, "default", route.verified)


def _extract_model_ids(raw: dict) -> list[str]:
    values = raw.get("data") or raw.get("models") or []
    if not isinstance(values, list):
        return []
    model_ids: list[str] = []
    for item in values:
        if isinstance(item, dict):
            value = item.get("id") or item.get("name")
        else:
            value = item
        if isinstance(value, str) and value.strip():
            model_ids.append(value.removeprefix("models/").strip())
    return model_ids


def _rank_model_ids(model_ids: list[str]) -> list[str]:
    indexed = list(enumerate(model_ids))
    indexed.sort(key=lambda item: (-_model_score(item[1]), item[0]))
    return [model_id for _, model_id in indexed]


def _model_score(model_id: str) -> int:
    lowered = model_id.lower()
    if "claude" in lowered and ("4" in lowered or "opus" in lowered or "sonnet" in lowered):
        return 100
    if "gpt-5" in lowered:
        return 90
    if "gemini" in lowered and "2.5" in lowered:
        return 80
    if "glm-5" in lowered:
        return 70
    if "deepseek" in lowered:
        return 60
    return 10


def _copy_generation_options(source: dict, target: dict, *, max_token_key: str) -> None:
    if source.get("temperature") is not None:
        target["temperature"] = source["temperature"]
    max_tokens = source.get(max_token_key) or source.get("max_output_tokens") or source.get("max_tokens")
    if max_tokens is not None:
        target[max_token_key] = max_tokens


def _validate_response_schema(data: dict, response_schema: object, task_name: str) -> None:
    if not isinstance(response_schema, dict):
        return
    required = response_schema.get("required")
    if not isinstance(required, list):
        return
    missing = [field for field in required if isinstance(field, str) and field not in data]
    if missing:
        raise LLMResponseFormatError(f"{task_name}: missing required fields: {', '.join(missing)}")


def _payload_text(user_payload: object) -> str:
    return json.dumps(user_payload, ensure_ascii=False)


def _dedupe_routes(routes: list[Route]) -> list[Route]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[Route] = []
    for route in routes:
        key = (route.endpoint, route.api_format, route.model_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(route)
    return deduped


def _dedupe_strings(values: object) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped
