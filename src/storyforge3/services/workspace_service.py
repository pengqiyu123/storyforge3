from __future__ import annotations

import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from storyforge3.config import StoryForge3Config
from storyforge3.models import BackupResult, RestoreResult, WorkspaceValidation


class WorkspaceService:
    """User-facing workspace validation, backup, and restore operations."""

    def __init__(self, config: StoryForge3Config) -> None:
        self._books_dir = Path(config.books_dir)

    def validate(self) -> WorkspaceValidation:
        issues: list[str] = []
        if not self._books_dir.exists():
            issues.append(f"工作区目录不存在: {self._books_dir}")
        elif not self._books_dir.is_dir():
            issues.append(f"工作区路径不是目录: {self._books_dir}")
        else:
            test_file = self._books_dir / ".sf3_write_test"
            try:
                test_file.write_text("ok", encoding="utf-8")
                test_file.unlink(missing_ok=True)
            except OSError as exc:
                issues.append(f"工作区目录不可写: {exc}")

        book_count = len(list(self._books_dir.glob("*/book.json"))) if self._books_dir.is_dir() else 0
        return WorkspaceValidation(
            valid=not issues,
            books_dir=str(self._books_dir),
            book_count=book_count,
            issues=tuple(issues),
        )

    def backup(self) -> BackupResult:
        self._ensure_valid()
        timestamp = self._timestamp()
        zip_path = self._books_dir.parent / f"sf3-backup-{timestamp}.zip"
        tmp_path = zip_path.with_suffix(".zip.tmp")
        book_count = 0
        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for file_path in sorted(self._books_dir.rglob("*")):
                    if not file_path.is_file():
                        continue
                    archive_name = file_path.relative_to(self._books_dir).as_posix()
                    if self._is_hidden_archive_path(archive_name):
                        continue
                    archive.write(file_path, archive_name)
                    if file_path.name == "book.json":
                        book_count += 1
            tmp_path.replace(zip_path)
        except BaseException:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        return BackupResult(
            path=str(zip_path),
            book_count=book_count,
            size_bytes=zip_path.stat().st_size,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def restore(self, zip_path: Path) -> RestoreResult:
        if not zip_path.exists():
            return RestoreResult(False, 0, "", f"无效的备份文件：文件不存在 {zip_path}")
        try:
            entries = self._valid_entries(zip_path)
        except zipfile.BadZipFile:
            return RestoreResult(False, 0, "", "无效的备份文件：无法读取 zip")

        if not any(self._is_book_meta_entry(name) for name, _data in entries):
            return RestoreResult(False, 0, "", "无效的备份文件：未找到 book.json")

        safety_backup = self.backup()
        if self._books_dir.exists():
            shutil.rmtree(self._books_dir)
        self._books_dir.mkdir(parents=True, exist_ok=True)

        root = self._books_dir.resolve()
        for name, data in entries:
            target = self._books_dir / name
            try:
                target.resolve().relative_to(root)
            except ValueError:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = target.with_suffix(target.suffix + ".tmp")
            try:
                tmp_path.write_bytes(data)
                tmp_path.replace(target)
            except BaseException:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise

        book_count = len(list(self._books_dir.glob("*/book.json")))
        return RestoreResult(
            success=True,
            book_count=book_count,
            backup_path=safety_backup.path,
            message=f"恢复成功，共 {book_count} 本书。安全备份: {safety_backup.path}",
        )

    def _ensure_valid(self) -> None:
        validation = self.validate()
        if not validation.valid:
            raise ValueError("；".join(validation.issues))

    @staticmethod
    def _is_hidden_archive_path(archive_name: str) -> bool:
        return any(part.startswith(".") for part in archive_name.split("/"))

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S%f")

    @staticmethod
    def _valid_entries(zip_path: Path) -> list[tuple[str, bytes]]:
        entries: list[tuple[str, bytes]] = []
        with zipfile.ZipFile(zip_path, "r") as archive:
            for name in archive.namelist():
                normalized = name.replace("\\", "/")
                if not normalized or normalized.endswith("/"):
                    continue
                if normalized.startswith("/") or ".." in normalized.split("/"):
                    continue
                entries.append((normalized, archive.read(name)))
        return entries

    @staticmethod
    def _is_book_meta_entry(archive_name: str) -> bool:
        parts = archive_name.split("/")
        return len(parts) == 2 and parts[1] == "book.json" and bool(parts[0])
