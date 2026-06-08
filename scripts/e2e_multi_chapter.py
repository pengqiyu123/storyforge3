from __future__ import annotations

import asyncio
import argparse
import json
import time
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Any

from storyforge3.audit import thresholds as T
from storyforge3.audit.chinese_text import count_chinese_chars
from storyforge3.config import StoryForge3Config
from storyforge3.cost.tracker import CostAccumulator
from storyforge3.llm.factory import create_llm_service
from storyforge3.models import BookConfig, ChapterResult, ChapterStatus, LLMCallRecord
from storyforge3.services.book_service import BookService
from storyforge3.services.character_service import CharacterService
from storyforge3.services.volume_service import VolumeService
from storyforge3.services.world_service import WorldService
from storyforge3.storage import BookStorage, StoragePaths
from storyforge3.truth.database import TruthDatabase
from storyforge3.truth.retriever import TruthRetriever
from storyforge3.workflow import ChapterWorkflow

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHAPTER_COUNT = 3
MAX_STEP_RETRIES = 2
RETRY_INTERVAL_SECONDS = 2.0
CHAPTER_INTERVAL_SECONDS = 10.0


class MultiChapterE2ERunner:
    def __init__(self, *, resume_latest: bool = False, resume_dir: Path | None = None) -> None:
        run_id = time.strftime("%Y%m%d-%H%M%S")
        books_dir = resume_dir or (self._latest_run_dir() if resume_latest else PROJECT_ROOT / "books" / f"e2e-multi-{run_id}")
        self.config = StoryForge3Config(books_dir=str(books_dir))
        self.paths = StoragePaths(Path(self.config.books_dir))
        self.storage = BookStorage(self.paths.books_root)
        self.llm = RecordingLLM(create_llm_service(self.config))
        self.calls: list[LLMCallRecord] = []
        self.costs = CostAccumulator()
        self.run_id = run_id
        self.book_id = ""
        self.chapter_summaries: list[dict[str, Any]] = []
        self.exported_chapters: list[int] = []
        self.failed_chapters: list[dict[str, Any]] = []
        self.log_path = self.paths.books_root / "e2e_multi_chapter.log"
        self.resume_existing = resume_latest or resume_dir is not None

    async def run(self) -> int:
        self._log("StoryForge3 multi-chapter E2E real LLM test")
        self._log(f"books_dir={self.config.books_dir}")
        self._log(f"log_path={self.log_path}")
        self._log(f"resume_existing={self.resume_existing}")
        try:
            await self._step("health", self._health)
            if self.resume_existing:
                self._load_existing_book()
            else:
                await self._step("create_book", self._create_book)
                await self._step("build_world", self._build_world)
                await self._step("create_characters", self._create_characters)
                await self._step("plan_volume", self._plan_volume)
            for chapter_no in range(1, CHAPTER_COUNT + 1):
                if self._chapter_has_truth(chapter_no):
                    self._log(f"\n[SKIP] generate_chapter_{chapter_no} existing truth found")
                    self._ensure_chapter_file_from_export(chapter_no)
                    self._record_existing_chapter(chapter_no)
                else:
                    try:
                        await self._step(
                            f"generate_chapter_{chapter_no}",
                            lambda chapter_no=chapter_no: self._generate_chapter(chapter_no),
                        )
                    except Exception as exc:
                        self._log(
                            f"[CHAPTER_FAILED] chapter={chapter_no} "
                            f"error={exc.__class__.__name__}: {exc}; continuing"
                        )
                if chapter_no < CHAPTER_COUNT:
                    self._log(f"\n[WAIT] chapter_interval {CHAPTER_INTERVAL_SECONDS:.0f}s")
                    await asyncio.sleep(CHAPTER_INTERVAL_SECONDS)
            await self._step("verify_cross_chapter_truth", self._verify_cross_chapter_truth)
            success = not self.failed_chapters and len(set(self.exported_chapters)) == CHAPTER_COUNT
            self._summary(success=success)
            return 0 if success else 2
        except Exception as exc:
            self._log(f"\nFAILED step error: {exc.__class__.__name__}: {exc}")
            self._summary(success=False)
            return 2

    async def _step(self, name: str, action) -> None:
        self._log(f"\n[START] {name}")
        started = time.perf_counter()
        max_attempts = 1 if name.startswith("generate_chapter_") else MAX_STEP_RETRIES + 1
        for attempt in range(max_attempts):
            try:
                result = await action()
                break
            except Exception as exc:
                self._collect_last_call()
                if attempt >= max_attempts - 1:
                    self._log(f"[FAIL] {name} after {time.perf_counter() - started:.2f}s")
                    self._print_error_detail(exc)
                    raise
                self._log(f"[RETRY] {name} attempt={attempt + 1} error={exc.__class__.__name__}: {exc}")
                self._print_error_detail(exc)
                await asyncio.sleep(RETRY_INTERVAL_SECONDS)
        self._collect_last_call()
        self._log(f"[OK] {name} in {time.perf_counter() - started:.2f}s")
        if result is not None:
            self._log(self._compact_json(result))

    async def _health(self) -> dict:
        ok = await self.llm.check_health()
        if not ok:
            raise RuntimeError("No active imported provider is available")
        return {"provider_config": "available"}

    def _load_existing_book(self) -> None:
        book_ids = self.storage.list_book_ids()
        if not book_ids:
            raise RuntimeError(f"no existing book found in {self.paths.books_root}")
        self.book_id = max(book_ids, key=self._truth_count)
        self._log(f"[RESUME] book_id={self.book_id}")

    def _truth_count(self, book_id: str) -> int:
        database = self.truth_database()
        return sum(len(database.query_by_chapter(book_id, chapter_no)) for chapter_no in range(1, CHAPTER_COUNT + 1))

    async def _create_book(self) -> dict:
        meta = await BookService(self.storage, self.paths).create(
            BookConfig(
                title=f"多章节记忆验证{self.run_id}",
                genre="urban",
                platform="tomato",
                target_chapters=CHAPTER_COUNT,
                chapter_word_count=2500,
            )
        )
        self.book_id = meta.book_id
        self.storage.write_text(
            self.paths.context(self.book_id),
            (
                "题材：都市玄幻。\n"
                "回归验证要求：每章约2500字，分段清晰，直接输出小说正文。\n"
                "核心设定：存在感系统会影响他人注意力，异常检测中心负责记录和处理失控能力。\n"
                "主线：林默、许青、周砚围绕检测中心副楼的残痕机制逐步接近真相。"
            ),
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
            characters.append(character)
        return {"characters": [asdict(character) for character in characters]}

    async def _plan_volume(self) -> dict:
        volumes = await VolumeService(self.llm, self.storage, self.paths, self.config).plan(self.book_id, 1, CHAPTER_COUNT)
        return {"volumes": [asdict(item) for item in volumes]}

    async def _generate_chapter(self, chapter_no: int) -> dict:
        call_start = len(self.llm.calls)
        result: ChapterResult | None = None
        try:
            workflow = ChapterWorkflow(self.config, client=self.llm)
            result = await workflow.run(
                self.book_id,
                chapter_no,
                human_confirm=lambda _: True,
            )
            self._collect_last_call()
            self._assert_chapter_result(chapter_no, result)
            self.storage.write_text(self.paths.chapter_file(self.book_id, chapter_no), result.text)

            text = result.text
            truth_entries = self.truth_database().query_by_chapter(self.book_id, chapter_no)
            if not truth_entries:
                raise RuntimeError(f"truth database has no entries for chapter {chapter_no}")

            llm_calls = self._chapter_llm_calls(call_start, result)
            revision_count = sum(1 for call in llm_calls if call.task_name == "revise")
            summary = {
                "chapter_no": chapter_no,
                "outcome": "exported",
                "status": result.status.value,
                "word_count": count_chinese_chars(text),
                "hard_range": self._hard_range(),
                "audit_passed": bool(result.audit and result.audit.passed),
                "revision_count": revision_count,
                "truth_entry_count": len(truth_entries),
                "input_tokens": sum(call.input_tokens or 0 for call in llm_calls),
                "output_tokens": sum(call.output_tokens or 0 for call in llm_calls),
                "llm_calls": [call.task_name for call in llm_calls],
            }
            self.exported_chapters.append(chapter_no)
            self.chapter_summaries.append(summary)
            return summary
        except Exception as exc:
            self._collect_last_call()
            llm_calls = self._chapter_llm_calls(call_start, result)
            self._write_chapter_diagnostics(chapter_no, result, exc, llm_calls)
            failure = self._chapter_failure_summary(chapter_no, result, exc, llm_calls)
            self.failed_chapters.append(failure)
            self.chapter_summaries.append(failure)
            raise

    async def _verify_cross_chapter_truth(self) -> dict:
        exported_chapters = sorted(set(self.exported_chapters))
        if len(exported_chapters) < 2:
            return {
                "skipped": True,
                "reason": "fewer than 2 exported chapters",
                "exported_chapters": exported_chapters,
                "failed_chapters": [item["chapter_no"] for item in self.failed_chapters],
            }
        retriever = TruthRetriever(self.truth_database())
        prompt_context = "\n".join(
            (
                "林默 许青 周砚 存在感 残痕 检测中心 副楼 真相",
                self.storage.read_text(self.paths.context(self.book_id)) or "",
            )
        )
        text = retriever.retrieve_for_prompt(
            self.book_id,
            4,
            prompt_context,
            max_entries=30,
            max_chars=4000,
        )
        presence = {chapter_no: f"[第{chapter_no}章]" in text for chapter_no in exported_chapters}
        missing = [chapter_no for chapter_no, present in presence.items() if not present]
        if missing:
            raise RuntimeError(
                "cross-chapter truth retrieval failed: "
                f"missing={missing}, presence={presence}, retrieved={text[:500]}"
            )
        return {
            "exported_chapters": exported_chapters,
            "truth_presence": presence,
            "retrieved_lines": text.splitlines()[:12],
        }

    def _assert_chapter_result(self, chapter_no: int, result: ChapterResult) -> None:
        if result.status != ChapterStatus.EXPORTED:
            raise RuntimeError(f"chapter {chapter_no} not exported: status={result.status.value}, error={result.error}")
        if result.audit is None or not result.audit.passed:
            raise RuntimeError(f"chapter {chapter_no} audit not passed after revisions")
        word_count = count_chinese_chars(result.text)
        hard_range = self._hard_range()
        if not hard_range[0] <= word_count <= hard_range[1]:
            raise RuntimeError(f"chapter {chapter_no} length out of hard range: observed={word_count}, hard_range={hard_range}")

    def truth_database(self) -> TruthDatabase:
        return TruthDatabase(self.paths.books_root / "truth.db")

    def _chapter_has_truth(self, chapter_no: int) -> bool:
        if not self.book_id:
            return False
        return bool(self.truth_database().query_by_chapter(self.book_id, chapter_no))

    def _ensure_chapter_file_from_export(self, chapter_no: int) -> None:
        chapter_path = self.paths.chapter_file(self.book_id, chapter_no)
        if chapter_path.exists():
            return
        export_path = self.paths.book_dir(self.book_id) / "exports" / f"chapter-{chapter_no:04d}.txt"
        text = self.storage.read_text(export_path)
        if text is None:
            self._log(f"[WARN] missing chapter and export for skipped chapter {chapter_no}")
            return
        lines = text.splitlines()
        body = "\n".join(lines[1:]).strip() if lines and lines[0].startswith("第") else text.strip()
        self.storage.write_text(chapter_path, body)
        self._log(f"[RESUME] restored chapter file from export: {chapter_path}")

    def _record_existing_chapter(self, chapter_no: int) -> None:
        if chapter_no in self.exported_chapters:
            return
        text = self.storage.read_text(self.paths.chapter_file(self.book_id, chapter_no)) or ""
        truth_entries = self.truth_database().query_by_chapter(self.book_id, chapter_no)
        summary = {
            "chapter_no": chapter_no,
            "outcome": "exported",
            "status": "skipped_existing_truth",
            "word_count": count_chinese_chars(text),
            "hard_range": self._hard_range(),
            "audit_passed": None,
            "revision_count": None,
            "truth_entry_count": len(truth_entries),
            "input_tokens": 0,
            "output_tokens": 0,
            "llm_calls": [],
        }
        self.exported_chapters.append(chapter_no)
        self.chapter_summaries.append(summary)

    def _chapter_llm_calls(self, call_start: int, result: ChapterResult | None) -> list[LLMCallRecord]:
        calls = list(self.llm.calls[call_start:])
        if result is None:
            return calls
        seen = {(call.task_name, call.latency_ms, call.error) for call in calls}
        for call in result.llm_calls:
            key = (call.task_name, call.latency_ms, call.error)
            if key not in seen:
                calls.append(call)
                seen.add(key)
        return calls

    def _chapter_failure_summary(
        self,
        chapter_no: int,
        result: ChapterResult | None,
        exc: Exception,
        llm_calls: list[LLMCallRecord],
    ) -> dict[str, Any]:
        text = result.text if result is not None else ""
        audit = result.audit if result is not None else None
        return {
            "chapter_no": chapter_no,
            "outcome": "failed",
            "status": result.status.value if result is not None else "exception",
            "error": result.error if result is not None and result.error else str(exc),
            "exception": f"{exc.__class__.__name__}: {exc}",
            "word_count": count_chinese_chars(text),
            "hard_range": self._hard_range(),
            "audit_passed": bool(audit and audit.passed),
            "blocking_issues": list(audit.blocking_issues) if audit is not None else [],
            "revision_count": sum(1 for call in llm_calls if call.task_name == "revise"),
            "truth_entry_count": len(self.truth_database().query_by_chapter(self.book_id, chapter_no)),
            "input_tokens": sum(call.input_tokens or 0 for call in llm_calls),
            "output_tokens": sum(call.output_tokens or 0 for call in llm_calls),
            "llm_calls": [call.task_name for call in llm_calls],
            "diagnostics_dir": str(self._diagnostics_dir()),
        }

    def _write_chapter_diagnostics(
        self,
        chapter_no: int,
        result: ChapterResult | None,
        exc: Exception,
        llm_calls: list[LLMCallRecord],
    ) -> None:
        diagnostics_dir = self._diagnostics_dir()
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        prefix = diagnostics_dir / f"chapter_{chapter_no}"
        latest_text = result.text if result is not None else ""
        (prefix.with_name(f"{prefix.name}_last_draft.md")).write_text(latest_text, encoding="utf-8")
        audit_payload = asdict(result.audit) if result is not None and result.audit is not None else None
        self._write_json(prefix.with_name(f"{prefix.name}_audit.json"), audit_payload)
        error_text = "\n".join(
            (
                f"exception={exc.__class__.__name__}: {exc}",
                f"result_error={result.error if result is not None else ''}",
                f"status={result.status.value if result is not None else 'exception'}",
            )
        )
        (prefix.with_name(f"{prefix.name}_error.txt")).write_text(error_text, encoding="utf-8")
        self._write_json(prefix.with_name(f"{prefix.name}_llm_calls.json"), [asdict(call) for call in llm_calls])
        self._log(f"[DIAG] chapter={chapter_no} diagnostics={diagnostics_dir}")

    def _diagnostics_dir(self) -> Path:
        return self.paths.books_root / "diagnostics"

    def _write_json(self, path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=self._json_default), encoding="utf-8")

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        return str(value)

    def _collect_last_call(self) -> None:
        while len(self.calls) < len(self.llm.calls):
            call = self.llm.calls[len(self.calls)]
            self.calls.append(call)
            self.costs.from_llm_calls((call,))
            self._log(
                "  LLM "
                f"task={call.task_name} model={call.model} "
                f"input_tokens={call.input_tokens} output_tokens={call.output_tokens} "
                f"latency_ms={call.latency_ms:.0f} success={call.success}"
            )

    def _print_error_detail(self, exc: Exception) -> None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        text = getattr(response, "text", "")
        if status_code is not None:
            self._log(f"  HTTP status={status_code}")
        if text:
            self._log(f"  response={text[:300]}")
        cause = getattr(exc, "__cause__", None)
        if isinstance(cause, Exception):
            self._print_error_detail(cause)

    def _summary(self, *, success: bool) -> None:
        summary = self.costs.summary()
        self._log("\n=== MULTI-CHAPTER E2E SUMMARY ===")
        self._log(f"success={success}")
        self._log(f"book_id={self.book_id}")
        self._log(f"chapters={len(self.chapter_summaries)}")
        self._log(f"exported_chapters={len(set(self.exported_chapters))}")
        self._log(f"failed_chapters={len(self.failed_chapters)}")
        self._log(f"llm_calls={len(self.calls)}")
        self._log(f"total_input_tokens={summary.total_input_tokens}")
        self._log(f"total_output_tokens={summary.total_output_tokens}")
        self._log(f"total_tokens={summary.total_tokens}")
        self._log(f"estimated={summary.estimated}")
        self._log(self._compact_json({"chapter_summaries": self.chapter_summaries}))

    @staticmethod
    def _compact_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)[:3000]

    def _target_word_count(self) -> int:
        data = self.storage.read_json(self.paths.book_meta(self.book_id))
        if not data or not isinstance(data.get("chapter_word_count"), int):
            raise RuntimeError(f"book meta missing chapter_word_count: {self.book_id}")
        return int(data["chapter_word_count"])

    def _hard_range(self) -> tuple[int, int]:
        target_word_count = self._target_word_count()
        return (
            int(target_word_count * (1 - T.LENGTH_HARD_RATIO)),
            int(target_word_count * (1 + T.LENGTH_HARD_RATIO)),
        )

    def _log(self, message: str) -> None:
        print(message, flush=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")

    @staticmethod
    def _latest_run_dir() -> Path:
        runs = sorted((PROJECT_ROOT / "books").glob("e2e-multi-*"), key=lambda path: path.stat().st_mtime)
        if not runs:
            raise RuntimeError("no e2e-multi run directory found")
        return runs[-1]


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume-latest", action="store_true")
    parser.add_argument("--resume-dir", type=Path)
    args = parser.parse_args()
    return await MultiChapterE2ERunner(resume_latest=args.resume_latest, resume_dir=args.resume_dir).run()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
