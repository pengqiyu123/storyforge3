from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from storyforge3.audit.chinese_text import count_chinese_chars
from storyforge3.audit.revision_patch import apply_patches, build_patch_targets, validate_patch_response
from storyforge3.config import StoryForge3Config
from storyforge3.llm.factory import create_llm_service
from storyforge3.models import AuditResult, LLMCallRecord, RuleResult
from storyforge3.workflow import (
    ChapterWorkflow,
    MAX_REVISION_ROUNDS,
    _patch_revision_prompt,
    _patch_revision_schema,
)


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


class DiagnosticWorkflow(ChapterWorkflow):
    def __init__(self, config: StoryForge3Config, *, client: RecordingLLM, out_dir: Path) -> None:
        super().__init__(config, client=client)
        self.out_dir = out_dir
        self.events: list[dict[str, Any]] = []

    async def _step_patch_revise(
        self,
        ctx,
        chapter_no: int,
        text: str,
        audit: AuditResult,
        failed: list[RuleResult],
        mode: str,
        revision_round: int,
    ) -> str:
        patch_targets = build_patch_targets(text, failed)
        event: dict[str, Any] = {
            "stage": "patch_revise",
            "revision_round": revision_round + 1,
            "mode": mode,
            "failed_rules": [result.rule_id for result in failed],
            "blocking_issues": list(audit.blocking_issues),
            "patch_targets": [
                {
                    "rule_id": target.rule_id,
                    "reason": target.reason,
                    "allowed_change": target.allowed_change,
                    "window_chars": len(target.window_text),
                    "window_excerpt": target.window_text[:500],
                }
                for target in patch_targets
            ],
        }
        self.events.append(event)
        if not patch_targets:
            event["error"] = "no patch targets"
            raise RuntimeError("patch_revise_failed: no patch targets")

        payload = {
            "book_id": ctx.book_id,
            "chapter_no": chapter_no,
            "mode": mode,
            "revision_round": revision_round + 1,
            "failed_rules": tuple(result.rule_id for result in failed),
            "blocking_issues": audit.blocking_issues,
            "world": ctx.world,
            "characters": ctx.characters,
            "relevant_truth": self.truth_retriever.retrieve_for_prompt(
                ctx.book_id,
                chapter_no,
                " ".join(result.rule_id for result in failed),
                max_chars=1200,
            ),
            "patch_targets": tuple(target.__dict__ for target in patch_targets),
            "instruction": (
                "只输出 JSON object。生成 find/replace 局部补丁；find 必须逐字来自 patch_targets 的 window_text，"
                "replace 只包含小说正文。不要输出完整章节。"
            ),
        }
        event["payload_summary"] = {
            "relevant_truth_chars": len(str(payload["relevant_truth"])),
            "patch_target_count": len(patch_targets),
        }

        data = await self.client.generate_json(
            "revise",
            _patch_revision_prompt(),
            payload,
            _patch_revision_schema(),
            model=self.config.model_for_task("writer"),
            timeout=self.config.llm_draft_timeout_seconds,
            temperature=0.2,
            max_output_tokens=1200,
            prompt_version="patch-revise-v1",
        )
        event["patch_response"] = data
        patches = validate_patch_response(data)
        result = apply_patches(text, patches)
        event["apply_result"] = {
            "applied_count": result.applied_count,
            "failed_count": result.failed_count,
            "failures": [asdict(failure) for failure in result.failures],
        }
        if result.applied_count < 1:
            failure_rules = ",".join(failure.rule_id or "unknown" for failure in result.failures)
            raise RuntimeError(f"patch_revise_failed: no patches applied; failed_rules={failure_rules}")
        return result.text


def _find_book_id(run_dir: Path) -> str:
    candidates = [path.name for path in run_dir.iterdir() if path.is_dir() and (path / "book.json").exists()]
    if not candidates:
        raise RuntimeError(f"no book directory found in {run_dir}")
    if len(candidates) > 1:
        raise RuntimeError(f"multiple book directories found: {candidates}")
    return candidates[0]


def _audit_summary(label: str, audit: AuditResult, text: str) -> dict[str, Any]:
    failed = [result for result in audit.rule_results if not result.passed]
    return {
        "stage": label,
        "passed": audit.passed,
        "blocking_issues": list(audit.blocking_issues),
        "warnings": list(audit.warnings),
        "info": list(audit.info),
        "text_chars": count_chinese_chars(text),
        "failed_rules": [_rule_summary(result) for result in failed],
    }


def _rule_summary(result: RuleResult) -> dict[str, Any]:
    return {
        "rule_id": result.rule_id,
        "severity": result.severity.value,
        "category": result.category.value,
        "message": result.message,
        "detail": result.detail,
    }


def _write_text(out_dir: Path, name: str, text: str) -> None:
    (out_dir / name).write_text(text, encoding="utf-8")


async def run_diagnostic(run_dir: Path, chapter_no: int, book_id: str | None, out_dir_arg: Path | None = None) -> int:
    run_dir = run_dir.resolve()
    book_id = book_id or _find_book_id(run_dir)
    out_dir = out_dir_arg or run_dir / "diagnostics" / f"chapter-{chapter_no:04d}-{time.strftime('%Y%m%d-%H%M%S')}"
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    config = StoryForge3Config(books_dir=str(run_dir))
    llm = RecordingLLM(create_llm_service(config))
    workflow = DiagnosticWorkflow(config, client=llm, out_dir=out_dir)
    events: list[dict[str, Any]] = [
        {
            "stage": "start",
            "run_dir": str(run_dir),
            "book_id": book_id,
            "chapter_no": chapter_no,
        }
    ]

    ctx = await workflow.step_import(book_id)
    plan_path = out_dir / "00-plan.txt"
    draft_path = out_dir / "01-draft.md"
    if plan_path.exists():
        plan = plan_path.read_text(encoding="utf-8")
        events.append({"stage": "plan_reused", "chars": len(plan), "excerpt": plan[:500]})
    else:
        plan = await workflow.step_plan(ctx, chapter_no)
        events.append({"stage": "plan", "chars": len(plan), "excerpt": plan[:500]})
        _write_text(out_dir, "00-plan.txt", plan)

    if draft_path.exists():
        text = draft_path.read_text(encoding="utf-8")
        events.append({"stage": "draft_reused", "text_chars": count_chinese_chars(text)})
    else:
        text = await workflow.step_draft(plan, ctx, chapter_no)
        events.append({"stage": "draft", "text_chars": count_chinese_chars(text)})
        _write_text(out_dir, "01-draft.md", text)

    normalized = await workflow.step_normalize_draft(book_id, text)
    text = normalized.text
    events.append(
        {
            "stage": "normalize",
            "action": normalized.action,
            "original_chars": normalized.original_chars,
            "final_chars": normalized.final_chars,
        }
    )
    _write_text(out_dir, "02-normalized.md", text)

    audit = workflow.step_audit(chapter_no, text)
    events.append(_audit_summary("audit_initial", audit, text))

    for revision_round in range(MAX_REVISION_ROUNDS):
        if audit.passed:
            break
        text = await workflow.step_revise(ctx, chapter_no, text, audit, revision_round)
        _write_text(out_dir, f"03-revised-round-{revision_round + 1}.md", text)
        events.extend(workflow.events)
        workflow.events.clear()
        audit = workflow.step_audit(chapter_no, text)
        events.append(_audit_summary(f"audit_after_round_{revision_round + 1}", audit, text))

    events.append(
        {
            "stage": "final",
            "audit_passed": audit.passed,
            "blocking_issues": list(audit.blocking_issues),
            "llm_calls": [asdict(call) for call in llm.calls],
            "out_dir": str(out_dir),
        }
    )
    (out_dir / "diagnostic.json").write_text(json.dumps(events, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(events[-1], ensure_ascii=False, indent=2, default=str))
    return 0 if audit.passed else 2


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--book-id")
    parser.add_argument("--chapter-no", type=int, default=2)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    return await run_diagnostic(args.run_dir, args.chapter_no, args.book_id, args.out_dir)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
