from __future__ import annotations

import asyncio

from storyforge3.llm.llm_service import LLMProviderError, LLMTimeoutError
from storyforge3.llm.chunked_generator import ChunkedGenerator


def run(coro):
    return asyncio.run(coro)


class RecordingLLM:
    def __init__(self, *, plan_error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self.chunks = ["甲" * 500, "乙" * 500]
        self.plan_error = plan_error

    async def generate_text(self, task_name, system_prompt, user_payload, **kwargs):
        self.calls.append(
            {
                "task_name": task_name,
                "system_prompt": system_prompt,
                "payload": user_payload,
                "kwargs": kwargs,
            }
        )
        if task_name == "draft_chunk_plan":
            if self.plan_error is not None:
                raise self.plan_error
            return "1. 林默进入检测中心\n2. 许青追问异常残痕"
        if task_name == "draft_chunk":
            return self.chunks.pop(0)
        raise AssertionError(f"unexpected task: {task_name}")


def test_chunked_generator_plans_chunks_and_passes_previous_tail() -> None:
    llm = RecordingLLM()
    generator = ChunkedGenerator(llm, chunk_target_chars=500, max_chunks=3)

    text = run(
        generator.generate(
            "draft",
            "你是中文网文作者。",
            "林默进入检测中心。",
            {
                "target_chars": 1000,
                "world": {"setting": "存在感系统"},
                "characters": [{"name": "林默"}],
                "model": "writer-model",
                "prompt_version": "compose:v1",
            },
        )
    )

    assert text == f"{'甲' * 500}\n\n{'乙' * 500}"
    assert [call["task_name"] for call in llm.calls] == ["draft_chunk_plan", "draft_chunk", "draft_chunk"]
    plan_payload = llm.calls[0]["payload"]
    assert plan_payload["chunk_count"] == 2
    assert plan_payload["chunk_target_chars"] == 500
    assert plan_payload["outline"] == "林默进入检测中心。"
    first_chunk_payload = llm.calls[1]["payload"]
    second_chunk_payload = llm.calls[2]["payload"]
    assert first_chunk_payload["chunk_outline"] == "林默进入检测中心"
    assert first_chunk_payload["previous_chunk_tail"] == ""
    assert first_chunk_payload["world"] == {"setting": "存在感系统"}
    assert first_chunk_payload["characters"] == [{"name": "林默"}]
    assert second_chunk_payload["previous_chunk_tail"] == "甲" * 200
    assert llm.calls[1]["kwargs"]["model"] == "writer-model"
    assert llm.calls[1]["kwargs"]["prompt_version"] == "compose:v1"
    assert llm.calls[0]["kwargs"]["timeout"] == 60


def test_chunked_generator_calls_progress_after_each_chunk() -> None:
    llm = RecordingLLM()
    progress: list[tuple[int, int]] = []

    async def on_progress(completed: int, total: int) -> None:
        progress.append((completed, total))

    text = run(
        ChunkedGenerator(llm, chunk_target_chars=500, max_chunks=3, on_progress=on_progress).generate(
            "draft",
            "你是中文网文作者。",
            "林默进入检测中心。",
            {"target_chars": 1000},
        )
    )

    assert text == f"{'甲' * 500}\n\n{'乙' * 500}"
    assert progress == [(1, 2), (2, 2)]


def test_chunked_generator_without_progress_callback_keeps_old_behavior() -> None:
    llm = RecordingLLM()

    text = run(
        ChunkedGenerator(llm, chunk_target_chars=500, max_chunks=3).generate(
            "draft",
            "你是中文网文作者。",
            "林默进入检测中心。",
            {"target_chars": 1000},
        )
    )

    assert text == f"{'甲' * 500}\n\n{'乙' * 500}"


def test_chunked_generator_falls_back_to_outline_on_plan_timeout() -> None:
    llm = RecordingLLM(plan_error=LLMTimeoutError("slow plan"))

    text = run(
        ChunkedGenerator(llm, chunk_target_chars=500, max_chunks=3).generate(
            "draft",
            "你是中文网文作者。",
            "林默进入检测中心；许青追问异常残痕",
            {"target_chars": 1000},
        )
    )

    assert text == f"{'甲' * 500}\n\n{'乙' * 500}"
    assert [call["task_name"] for call in llm.calls] == ["draft_chunk_plan", "draft_chunk", "draft_chunk"]
    assert llm.calls[1]["payload"]["chunk_outline"] == "林默进入检测中心"
    assert llm.calls[2]["payload"]["chunk_outline"] == "许青追问异常残痕"


def test_chunked_generator_falls_back_to_outline_on_provider_error() -> None:
    llm = RecordingLLM(plan_error=LLMProviderError("bad route"))

    text = run(
        ChunkedGenerator(llm, chunk_target_chars=500, max_chunks=3).generate(
            "draft",
            "你是中文网文作者。",
            "林默进入检测中心；许青追问异常残痕",
            {"target_chars": 1000},
        )
    )

    assert text == f"{'甲' * 500}\n\n{'乙' * 500}"
