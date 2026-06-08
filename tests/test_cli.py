from __future__ import annotations

import sys

import pytest

from storyforge3 import __main__ as cli


def test_main_help_keeps_chinese_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["storyforge3", "--help"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    captured = capsys.readouterr()
    assert exc.value.code == 0
    assert "执行单章管线" in captured.out
    assert "检查 CCSwitch 连通性" in captured.out


def test_configure_console_encoding_is_safe_to_call() -> None:
    cli._configure_console_encoding()
