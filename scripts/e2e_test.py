from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from storyforge3.audit import thresholds as T
from storyforge3.audit.chinese_text import count_chinese_chars
from storyforge3.audit.runner import AuditRunner
from storyforge3.config import StoryForge3Config
from storyforge3.cost.tracker import CostAccumulator
from storyforge3.export.formatter import PlatformFormatter
from storyforge3.llm.factory import create_llm_service
from storyforge3.models import BookConfig, LLMCallRecord
from storyforge3.services.book_service import BookService
from storyforge3.services.chapter_service import ChapterService
from storyforge3.services.character_service import CharacterService
from storyforge3.services.volume_service import VolumeService
from storyforge3.services.world_service import WorldService
from storyforge3.storage import BookStorage, StoragePaths
from storyforge3.workflow import ChapterWorkflow, MAX_REVISION_ROUNDS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_STEP_RETRIES = 2
RETRY_INTERVAL_SECONDS = 2.0


class E2ERunner:
    def __init__(self) -> None:
        run_id = time.strftime("%Y%m%d-%H%M%S")
        self.config = StoryForge3Config(books_dir=str(PROJECT_ROOT / "books" / f"e2e-{run_id}"))
        self.paths = StoragePaths(Path(self.config.books_dir))
        self.storage = BookStorage(self.paths.books_root)
        self.llm = RecordingLLM(create_llm_service(self.config))
        self.calls: list[LLMCallRecord] = []
        self.costs = CostAccumulator()
        self.book_id = ""

    async def run(self) -> int:
        print("StoryForge3 E2E real LLM test")
        print(f"books_dir={self.config.books_dir}")
        try:
            await self._step("health", self._health)
            await self._step("create_book", self._create_book)
            await self._step("build_world", self._build_world)
            await self._step("create_characters", self._create_characters)
            await self._step("plan_volume", self._plan_volume)
            await self._step("generate_chapter_1", self._generate_chapter)
            self._summary(success=True)
            return 0
        except Exception as exc:
            print(f"\nFAILED step error: {exc.__class__.__name__}: {exc}")
            self._summary(success=False)
            return 2

    async def _step(self, name: str, action) -> None:
        print(f"\n[START] {name}")
        started = time.perf_counter()
        for attempt in range(MAX_STEP_RETRIES + 1):
            try:
                result = await action()
                break
            except Exception as exc:
                if attempt >= MAX_STEP_RETRIES:
                    print(f"[FAIL] {name} after {time.perf_counter() - started:.2f}s")
                    self._print_error_detail(exc)
                    raise
                print(f"[RETRY] {name} attempt={attempt + 1} error={exc.__class__.__name__}: {exc}")
                self._print_error_detail(exc)
                await asyncio.sleep(RETRY_INTERVAL_SECONDS)
        self._collect_last_call()
        print(f"[OK] {name} in {time.perf_counter() - started:.2f}s")
        if result is not None:
            print(self._compact_json(result))

    async def _health(self) -> dict:
        ok = await self.llm.check_health()
        if not ok:
            raise RuntimeError("No active imported provider is available")
        return {"provider_config": "available"}

    async def _create_book(self) -> dict:
        meta = await BookService(self.storage, self.paths).create(
            BookConfig(
                title="测试小说",
                genre="urban",
                platform="tomato",
                target_chapters=10,
                chapter_word_count=2000,
            )
        )
        self.book_id = meta.book_id
        self.storage.write_text(
            self.paths.context(self.book_id),
            "题材：都市玄幻。核心设定：存在感系统会影响他人注意力，异常检测中心负责记录和处理失控能力。",
        )
        return asdict(meta)

    async def _build_world(self) -> dict:
        world = await WorldService(self.llm, self.storage, self.paths, self.config).build(
            self.book_id,
            "urban",
            "都市玄幻设定：存在感系统 + 异常检测中心。规则必须清楚，不能引入工程术语。",
        )
        return asdict(world)

    async def _create_characters(self) -> dict:
        service = CharacterService(self.llm, self.storage, self.paths, self.config)
        characters = []
        for spec in (
            "主角：林默，高三学生，能力是调节自己的存在感，谨慎但不懦弱。",
            "配角：许青，异常检测中心实习记录员，细心，负责引导林默。",
            "配角：周砚，检测中心医生，冷静，知道部分异常真相。",
        ):
            character = await service.create(self.book_id, spec)
            self._collect_last_call()
            characters.append(asdict(character))
        return {"characters": characters}

    async def _plan_volume(self) -> dict:
        volumes = await VolumeService(self.llm, self.storage, self.paths, self.config).plan(self.book_id, 1, 5)
        return {"volumes": [asdict(item) for item in volumes]}

    async def _generate_chapter(self) -> dict:
        service = ChapterService(self.config, llm=self.llm, storage=self.storage, paths=self.paths)
        intent = await service.plan(self.book_id, 1)
        self._collect_last_call()
        text = await service.draft(self.book_id, 1, intent)
        self._collect_last_call()
        word_count = count_chinese_chars(text)
        target_word_count = self._target_word_count()
        hard_range = self._hard_range(target_word_count)
        is_in_hard_range = hard_range[0] <= word_count <= hard_range[1]
        audit = AuditRunner().run_audit(1, text)
        revision_attempts = 0
        workflow = ChapterWorkflow(self.config, client=self.llm)
        workflow_ctx = await workflow.step_import(self.book_id)
        while audit.blocking_issues and revision_attempts < MAX_REVISION_ROUNDS:
            text = await workflow.step_revise(workflow_ctx, 1, text, audit, revision_attempts)
            self._collect_last_call()
            self.storage.write_text(self.paths.chapter_file(self.book_id, 1), text)
            audit = AuditRunner().run_audit(1, text)
            revision_attempts += 1
        if audit.blocking_issues:
            raise RuntimeError(f"revision_exhausted: blocking_issues={audit.blocking_issues}")
        word_count = count_chinese_chars(text)
        is_in_hard_range = hard_range[0] <= word_count <= hard_range[1]
        export_path = await service.export(self.book_id, 1)
        formatted = export_path.read_text(encoding="utf-8")
        format_errors = PlatformFormatter().check_format("第1章", 1, formatted)
        if not is_in_hard_range:
            raise RuntimeError(f"chapter length out of hard range: observed={word_count}, hard_range={hard_range}")
        return {
            "chapter_file": str(self.paths.chapter_file(self.book_id, 1)),
            "export_path": str(export_path),
            "word_count": word_count,
            "target_word_count": target_word_count,
            "hard_range": hard_range,
            "word_count_in_hard_range": is_in_hard_range,
            "audit_passed": audit.passed,
            "blocking_issues": audit.blocking_issues,
            "warning_count": len(audit.warnings),
            "revision_attempts": revision_attempts,
            "revision_exhausted": False,
            "format_errors": format_errors,
        }

    def _collect_last_call(self) -> None:
        while len(self.calls) < len(self.llm.calls):
            call = self.llm.calls[len(self.calls)]
            self.calls.append(call)
            self.costs.from_llm_calls((call,))
            print(
                "  LLM "
                f"task={call.task_name} model={call.model} "
                f"input_tokens={call.input_tokens} output_tokens={call.output_tokens} "
                f"latency_ms={call.latency_ms:.0f} success={call.success}"
            )

    @staticmethod
    def _print_error_detail(exc: Exception) -> None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        text = getattr(response, "text", "")
        if status_code is not None:
            print(f"  HTTP status={status_code}")
        if text:
            print(f"  response={text[:200]}")
        cause = getattr(exc, "__cause__", None)
        if isinstance(cause, Exception):
            E2ERunner._print_error_detail(cause)

    def _summary(self, *, success: bool) -> None:
        summary = self.costs.summary()
        print("\n=== E2E SUMMARY ===")
        print(f"success={success}")
        print(f"llm_calls={len(self.calls)}")
        print(f"total_input_tokens={summary.total_input_tokens}")
        print(f"total_output_tokens={summary.total_output_tokens}")
        print(f"total_tokens={summary.total_tokens}")
        print(f"estimated={summary.estimated}")

    @staticmethod
    def _compact_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)[:2000]

    def _target_word_count(self) -> int:
        data = self.storage.read_json(self.paths.book_meta(self.book_id))
        if not data or not isinstance(data.get("chapter_word_count"), int):
            raise RuntimeError(f"book meta missing chapter_word_count: {self.book_id}")
        return int(data["chapter_word_count"])

    @staticmethod
    def _hard_range(target_word_count: int) -> tuple[int, int]:
        return (int(target_word_count * (1 - T.LENGTH_HARD_RATIO)), int(target_word_count * (1 + T.LENGTH_HARD_RATIO)))


class RecordingLLM:
    def __init__(self, client: Any) -> None:
        self.client = client
        self.calls: list[LLMCallRecord] = []

    @property
    def last_call(self) -> LLMCallRecord | None:
        return self.client.last_call

    async def check_health(self) -> bool:
        return await self.client.check_health()

    async def generate_text(self, *args, **kwargs) -> str:
        text = await self.client.generate_text(*args, **kwargs)
        self._append_last_call()
        return text

    async def generate_json(self, *args, **kwargs) -> dict:
        data = await self.client.generate_json(*args, **kwargs)
        self._append_last_call()
        return data

    def _append_last_call(self) -> None:
        call = self.client.last_call
        if isinstance(call, LLMCallRecord):
            self.calls.append(call)


async def main() -> int:
    return await E2ERunner().run()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
