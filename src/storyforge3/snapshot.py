from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path


class SnapshotManager:
    """导出前自动快照管理。"""

    def __init__(self, books_dir: str | Path, *, max_count: int = 5) -> None:
        self._books_dir = Path(books_dir)
        self._max_count = max(1, max_count)

    def create_snapshot(self, book_id: str, chapter_no: int) -> Path | None:
        """为指定书籍创建快照 zip；没有可打包内容时返回 None。"""
        book_dir = self._books_dir / book_id
        if not book_dir.exists():
            return None
        files_to_pack = self._collect_files(book_dir)
        if not files_to_pack:
            return None

        timestamp = self._timestamp()
        snap_dir = book_dir / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        zip_path = snap_dir / f"{timestamp}_ch{chapter_no:04d}.zip"
        tmp_path = zip_path.with_suffix(".zip.tmp")
        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for source, archive_name in files_to_pack:
                    archive.write(source, archive_name)
            tmp_path.replace(zip_path)
        except BaseException:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        self._write_meta(zip_path, book_id, chapter_no, timestamp, len(files_to_pack))
        self._cleanup(book_id)
        return zip_path

    def list_snapshots(self, book_id: str) -> list[dict]:
        """列出书籍快照元数据，按时间倒序。"""
        snap_dir = self._books_dir / book_id / "snapshots"
        if not snap_dir.exists():
            return []
        items: list[dict] = []
        for meta_path in sorted(snap_dir.glob("*.meta.json"), reverse=True):
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(data, dict):
                items.append(data)
        return items

    def restore_snapshot(self, book_id: str, snapshot_path: str) -> dict:
        snap_dir = self._books_dir / book_id / "snapshots"
        zip_path = snap_dir / snapshot_path
        if not zip_path.exists():
            raise FileNotFoundError(f"snapshot not found: {snapshot_path}")

        book_dir = self._books_dir / book_id
        restored: list[str] = []
        book_root = book_dir.resolve()

        with zipfile.ZipFile(zip_path, "r") as archive:
            for name in archive.namelist():
                normalized = name.replace("\\", "/")
                if ".." in normalized or normalized.startswith("/"):
                    continue
                if not (normalized.startswith("chapters/") or normalized.startswith("state/")):
                    continue
                target = book_dir / normalized
                try:
                    target.resolve().relative_to(book_root)
                except ValueError:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_suffix(target.suffix + ".tmp")
                data = archive.read(name)
                try:
                    tmp.write_bytes(data)
                    tmp.replace(target)
                except BaseException:
                    try:
                        tmp.unlink(missing_ok=True)
                    except OSError:
                        pass
                    raise
                restored.append(normalized)

        return {"restored_files": restored, "count": len(restored)}

    def _cleanup(self, book_id: str) -> None:
        snap_dir = self._books_dir / book_id / "snapshots"
        if not snap_dir.exists():
            return
        snapshots = sorted(snap_dir.glob("*.zip"))
        while len(snapshots) > self._max_count:
            oldest = snapshots.pop(0)
            oldest.unlink(missing_ok=True)
            oldest.with_suffix(".meta.json").unlink(missing_ok=True)

    def _collect_files(self, book_dir: Path) -> list[tuple[Path, str]]:
        files: list[tuple[Path, str]] = []
        for name in ("book.json", "world.json", "characters.json", "volumes.json", "context.md"):
            path = book_dir / name
            if path.is_file():
                files.append((path, name))
        for subdir in ("chapters", "truth", "state"):
            root = book_dir / subdir
            if not root.exists():
                continue
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    files.append((path, f"{subdir}/{path.relative_to(root).as_posix()}"))

        book_truth_db = book_dir / "truth.db"
        if book_truth_db.is_file():
            files.append((book_truth_db, "truth.db"))
        global_truth_db = self._books_dir / "truth.db"
        if global_truth_db.is_file() and global_truth_db != book_truth_db:
            files.append((global_truth_db, "truth.db"))
        global_state = self._books_dir / "state.json"
        if global_state.is_file():
            files.append((global_state, "state/state.json"))
        return files

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")

    @staticmethod
    def _write_meta(zip_path: Path, book_id: str, chapter_no: int, timestamp: str, file_count: int) -> None:
        meta_path = zip_path.with_suffix(".meta.json")
        tmp_path = meta_path.with_suffix(".meta.json.tmp")
        meta = {
            "book_id": book_id,
            "chapter_no": chapter_no,
            "timestamp": timestamp,
            "file_count": file_count,
            "path": zip_path.name,
        }
        try:
            tmp_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(meta_path)
        except BaseException:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
