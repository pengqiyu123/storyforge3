from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

from diagnostics import describe_prompt
from storyforge3.config import StoryForge3Config
from storyforge3.llm.factory import create_llm_service
from storyforge3.prompts.registry import create_default_registry

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _latest_run(pattern: str) -> Path:
    runs = sorted((PROJECT_ROOT / "books").glob(pattern), key=lambda path: path.stat().st_mtime)
    if not runs:
        raise RuntimeError(f"no run directory found: {pattern}")
    return runs[-1]


def _book_root(run_dir: Path) -> Path:
    matches = [path for path in run_dir.iterdir() if path.is_dir() and (path / "context.md").exists()]
    if not matches:
        raise RuntimeError(f"no book context found in {run_dir}")
    return sorted(matches)[0]


def _single_plan(book_root: Path) -> tuple[str, dict, str | None]:
    registry = create_default_registry()
    prompt = registry.render_system_prompt(registry.get_latest("plan"), chapter_no=1)
    payload = {
        "book_id": book_root.name,
        "chapter_no": 1,
        "context": (book_root / "context.md").read_text(encoding="utf-8"),
    }
    model = StoryForge3Config().model_for_task("planner")
    return prompt, payload, model


def _multi_plan(book_root: Path, chapter_no: int) -> tuple[str, dict, str | None]:
    registry = create_default_registry()
    template = registry.get_latest("plan")
    prompt = registry.render_system_prompt(template, chapter_no=chapter_no)
    chapters_dir = book_root / "chapters"
    chapters = tuple(path.read_text(encoding="utf-8") for path in sorted(chapters_dir.glob("*.md"))) if chapters_dir.exists() else ()
    payload = {
        "book_id": book_root.name,
        "chapter_no": chapter_no,
        "book_context": (book_root / "context.md").read_text(encoding="utf-8"),
        "previous_chapter_tail": chapters[-1][-1200:] if chapters else "",
        "task": "生成章节计划，保持与真实小说上下文连续。",
    }
    return prompt, payload, None


async def _send(label: str, task_name: str, prompt: str, payload: dict, model: str | None) -> None:
    llm = create_llm_service(StoryForge3Config())
    started = time.perf_counter()
    print(f"[DIAG] send {label} task={task_name} model_arg={model!r} start", flush=True)
    try:
        text = await llm.generate_text(task_name, prompt, payload, model=model)
        print(
            f"[DIAG] send {label} ok elapsed={time.perf_counter() - started:.2f}s "
            f"preview={text[:160]}",
            flush=True,
        )
    except Exception as exc:
        print(
            f"[DIAG] send {label} error elapsed={time.perf_counter() - started:.2f}s "
            f"{exc.__class__.__name__}: {exc}",
            flush=True,
        )


async def main_async(args: argparse.Namespace) -> int:
    single_root = _book_root(args.single_run or _latest_run("e2e-*"))
    multi_root = _book_root(args.multi_run or _latest_run("e2e-multi-*"))

    single_prompt, single_payload, single_model = _single_plan(single_root)
    multi_prompt, multi_payload, multi_model = _multi_plan(multi_root, args.chapter_no)

    print(f"[DIAG] single_run={single_root.parent}", flush=True)
    print(f"[DIAG] multi_run={multi_root.parent}", flush=True)
    print(f"[DIAG] single_model_arg={single_model!r}", flush=True)
    print(f"[DIAG] multi_model_arg={multi_model!r}", flush=True)
    describe_prompt("single chapter 1 plan path=ChapterService.plan task=chapter_plan", single_prompt, single_payload)
    describe_prompt(f"multi chapter {args.chapter_no} plan path=ChapterWorkflow.step_plan task=plan", multi_prompt, multi_payload)

    if args.send:
        await _send("single", "chapter_plan", single_prompt, single_payload, single_model)
        await asyncio.sleep(args.interval_seconds)
        await _send("multi", "plan", multi_prompt, multi_payload, multi_model)
    if args.send_variants:
        fixed_prompt = "你是中文网文章节规划师。只输出本章目标。"
        await _send("multi_payload_with_chapter_plan_prompt_task_plan", "plan", fixed_prompt, multi_payload, multi_model)
        await asyncio.sleep(args.interval_seconds)
        await _send("multi_payload_with_chapter_plan_prompt_task_chapter_plan", "chapter_plan", fixed_prompt, multi_payload, multi_model)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--single-run", type=Path)
    parser.add_argument("--multi-run", type=Path)
    parser.add_argument("--chapter-no", type=int, default=1)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--send-variants", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=2.0)
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
