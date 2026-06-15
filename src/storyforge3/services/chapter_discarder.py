from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from storyforge3.services.chapter_reconciler import BookReconciliation, ChapterReconciler
from storyforge3.storage import BookStorage, StoragePaths
from storyforge3.truth.database import TruthEntry
from storyforge3.truth.store import TruthStore


@dataclass(frozen=True)
class DiscardPreview:
    book_id: str
    chapter_no: int
    deleted_files: tuple[str, ...]
    rewritten_files: tuple[str, ...]
    truth_db_rows: int
    pipeline_lines_removed: int
    state_removed: bool
    backed_up_to: str | None


@dataclass(frozen=True)
class DiscardResult:
    book_id: str
    chapter_no: int
    deleted_files: tuple[str, ...]
    rewritten_files: tuple[str, ...]
    truth_db_rows: int
    pipeline_lines_removed: int
    state_removed: bool
    backed_up_to: str | None
    post_reconcile: BookReconciliation


class ChapterDiscarder:
    def __init__(
        self,
        storage: BookStorage,
        paths: StoragePaths,
        truth_store: TruthStore | None = None,
        reconciler: ChapterReconciler | None = None,
    ) -> None:
        self.storage = storage
        self.paths = paths
        self.truth_store = truth_store or TruthStore(str(paths.books_root))
        self.reconciler = reconciler or ChapterReconciler(storage, paths)

    def preview(self, book_id: str, chapter_no: int) -> DiscardPreview:
        plan = self._plan(book_id, chapter_no)
        return DiscardPreview(
            book_id=book_id,
            chapter_no=chapter_no,
            deleted_files=tuple(_relative(path, plan.book_dir) for path in plan.delete_paths),
            rewritten_files=plan.rewritten_files,
            truth_db_rows=len(plan.truth_rows),
            pipeline_lines_removed=plan.pipeline_lines_removed,
            state_removed=plan.state_removed,
            backed_up_to=str(self._next_trash_dir(book_id, chapter_no)) if plan.has_work else None,
        )

    def discard(self, book_id: str, chapter_no: int) -> DiscardResult:
        plan = self._plan(book_id, chapter_no)
        backup_dir = self._next_trash_dir(book_id, chapter_no) if plan.has_work else None
        deleted_files = tuple(_relative(path, plan.book_dir) for path in plan.delete_paths)

        if backup_dir is not None:
            self._backup(plan, backup_dir)
            for path in plan.delete_paths:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
            self._remove_empty_run_dir(book_id, chapter_no)
            self.truth_store.delete_by_chapter(book_id, chapter_no)
            self._rewrite_pipeline(plan)
            self._rewrite_state(plan)

        return DiscardResult(
            book_id=book_id,
            chapter_no=chapter_no,
            deleted_files=deleted_files,
            rewritten_files=plan.rewritten_files,
            truth_db_rows=len(plan.truth_rows),
            pipeline_lines_removed=plan.pipeline_lines_removed,
            state_removed=plan.state_removed,
            backed_up_to=str(backup_dir) if backup_dir is not None else None,
            post_reconcile=self.reconciler.reconcile(book_id),
        )

    def _plan(self, book_id: str, chapter_no: int) -> "_DiscardPlan":
        book_dir = self.paths.book_dir(book_id)
        delete_paths = self._delete_paths(book_id, chapter_no)
        truth_rows = self.truth_store.database.query_by_chapter(book_id, chapter_no)
        pipeline_path = book_dir / "runs" / "pipeline.jsonl"
        pipeline_lines_removed = _count_target_pipeline_lines(pipeline_path, book_id, chapter_no)
        state_path = self.paths.chapter_states(book_id)
        state_removed = _state_key(book_id, chapter_no) in _read_json_object(state_path)
        rewritten_files: list[str] = []
        if pipeline_lines_removed:
            rewritten_files.append("runs/pipeline.jsonl")
        if state_removed:
            rewritten_files.append("state/chapter_states.json")
        return _DiscardPlan(
            book_id=book_id,
            chapter_no=chapter_no,
            book_dir=book_dir,
            delete_paths=tuple(delete_paths),
            truth_rows=tuple(truth_rows),
            pipeline_path=pipeline_path,
            pipeline_lines_removed=pipeline_lines_removed,
            state_path=state_path,
            state_removed=state_removed,
            rewritten_files=tuple(rewritten_files),
        )

    def _delete_paths(self, book_id: str, chapter_no: int) -> list[Path]:
        book_dir = self.paths.book_dir(book_id)
        candidates = [
            self.paths.chapter_file(book_id, chapter_no),
            self.paths.plan_file(book_id, chapter_no),
            self.paths.truth_file(book_id, chapter_no),
        ]
        export_dir = book_dir / "exports"
        if export_dir.exists():
            candidates.extend(
                path
                for path in sorted(export_dir.glob(f"chapter-{chapter_no:04d}*"))
                if path.is_file() and _is_export_artifact(path)
            )
        snapshot_dir = book_dir / "snapshots"
        if snapshot_dir.exists():
            candidates.extend(path for path in sorted(snapshot_dir.glob(f"*ch{chapter_no:04d}*")) if path.is_file())
        run_dir = self.paths.run_dir(book_id, chapter_no)
        if run_dir.exists():
            candidates.extend(path for path in sorted(run_dir.rglob("*")) if path.is_file())
        return [path for path in candidates if _is_scoped(path, book_dir) and path.exists()]

    def _next_trash_dir(self, book_id: str, chapter_no: int) -> Path:
        root = self.paths.book_dir(book_id) / "_trash" / f"ch{chapter_no:04d}"
        index = 1
        while True:
            candidate = root / f"{index:03d}"
            if not candidate.exists():
                return candidate
            index += 1

    def _backup(self, plan: "_DiscardPlan", backup_dir: Path) -> None:
        for path in plan.delete_paths:
            target = backup_dir / _relative(path, plan.book_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        if plan.truth_rows:
            _write_json(backup_dir / "truth_db_rows.json", [_truth_entry_to_dict(row) for row in plan.truth_rows])
        if plan.pipeline_lines_removed and plan.pipeline_path.exists():
            target = backup_dir / "runs" / "pipeline.jsonl"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(plan.pipeline_path, target)
        if plan.state_removed and plan.state_path.exists():
            target = backup_dir / "state" / "chapter_states.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(plan.state_path, target)

    def _rewrite_pipeline(self, plan: "_DiscardPlan") -> None:
        if not plan.pipeline_lines_removed or not plan.pipeline_path.exists():
            return
        kept: list[str] = []
        for line in plan.pipeline_path.read_text(encoding="utf-8").splitlines():
            if _pipeline_line_matches(line, plan.book_id, plan.chapter_no):
                continue
            kept.append(line)
        self.storage.write_text(plan.pipeline_path, "\n".join(kept) + ("\n" if kept else ""))

    def _rewrite_state(self, plan: "_DiscardPlan") -> None:
        if not plan.state_removed:
            return
        data = _read_json_object(plan.state_path)
        data.pop(_state_key(plan.book_id, plan.chapter_no), None)
        self.storage.write_json(plan.state_path, data)

    def _remove_empty_run_dir(self, book_id: str, chapter_no: int) -> None:
        run_dir = self.paths.run_dir(book_id, chapter_no)
        if run_dir.exists() and not any(run_dir.iterdir()):
            run_dir.rmdir()


@dataclass(frozen=True)
class _DiscardPlan:
    book_id: str
    chapter_no: int
    book_dir: Path
    delete_paths: tuple[Path, ...]
    truth_rows: tuple[TruthEntry, ...]
    pipeline_path: Path
    pipeline_lines_removed: int
    state_path: Path
    state_removed: bool
    rewritten_files: tuple[str, ...]

    @property
    def has_work(self) -> bool:
        return bool(self.delete_paths or self.truth_rows or self.pipeline_lines_removed or self.state_removed)


def _is_export_artifact(path: Path) -> bool:
    name = path.name
    return (name.endswith(".txt") or name.endswith(".md") or name.endswith(".epub")) and not name.endswith(".tmp")


def _count_target_pipeline_lines(path: Path, book_id: str, chapter_no: int) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if _pipeline_line_matches(line, book_id, chapter_no))


def _pipeline_line_matches(line: str, book_id: str, chapter_no: int) -> bool:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    try:
        line_chapter_no = int(data.get("chapter_no"))
    except (TypeError, ValueError):
        return False
    return data.get("book_id") == book_id and line_chapter_no == chapter_no


def _read_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _truth_entry_to_dict(entry: TruthEntry) -> dict:
    return {
        "id": entry.id,
        "book_id": entry.book_id,
        "chapter_no": entry.chapter_no,
        "category": entry.category,
        "content": entry.content,
        "importance": entry.importance,
        "related_chapters": list(entry.related_chapters),
        "created_at": entry.created_at,
    }


def _state_key(book_id: str, chapter_no: int) -> str:
    return f"{book_id}:{chapter_no:04d}"


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_scoped(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True
