from __future__ import annotations

import json
from pathlib import Path

import pytest

from storyforge3.storage import BookStorage


def test_write_text_atomic_on_success(tmp_path: Path) -> None:
    storage = BookStorage(tmp_path)
    path = tmp_path / "nested" / "chapter.md"

    storage.write_text(path, "新正文")

    assert path.read_text(encoding="utf-8") == "新正文"
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_write_text_preserves_old_on_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    storage = BookStorage(tmp_path)
    path = tmp_path / "chapter.md"
    path.write_text("旧正文", encoding="utf-8")
    original_write_text = Path.write_text

    def fail_tmp_write(self: Path, data: str, *args, **kwargs) -> int:
        if self.name.endswith(".tmp"):
            raise OSError("simulated tmp write failure")
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_tmp_write)

    with pytest.raises(OSError, match="simulated tmp write failure"):
        storage.write_text(path, "新正文")

    assert path.read_text(encoding="utf-8") == "旧正文"
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_write_json_atomic_on_success(tmp_path: Path) -> None:
    storage = BookStorage(tmp_path)
    path = tmp_path / "nested" / "data.json"

    storage.write_json(path, {"ok": True, "name": "林默"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"ok": True, "name": "林默"}
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_write_json_preserves_old_on_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    storage = BookStorage(tmp_path)
    path = tmp_path / "data.json"
    path.write_text(json.dumps({"old": True}, ensure_ascii=False), encoding="utf-8")
    original_write_text = Path.write_text

    def fail_tmp_write(self: Path, data: str, *args, **kwargs) -> int:
        if self.name.endswith(".tmp"):
            raise OSError("simulated tmp json failure")
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_tmp_write)

    with pytest.raises(OSError, match="simulated tmp json failure"):
        storage.write_json(path, {"old": False})

    assert json.loads(path.read_text(encoding="utf-8")) == {"old": True}
    assert not path.with_suffix(path.suffix + ".tmp").exists()


def test_write_text_creates_parent_dirs(tmp_path: Path) -> None:
    storage = BookStorage(tmp_path)
    path = tmp_path / "a" / "b" / "chapter.md"

    storage.write_text(path, "正文")

    assert path.read_text(encoding="utf-8") == "正文"
