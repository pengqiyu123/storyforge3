from __future__ import annotations

import asyncio
import json
import signal
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from storyforge3.config import StoryForge3Config
from storyforge3.dev_runner import (
    DevProcessError,
    DevRunner,
    StartupDiagnostics,
    _default_health_check,
    _default_web_check,
    _ensure_port_available,
    _install_stop_signal_handlers,
    _resolve_command,
    _spawn_api,
    _spawn_web,
    collect_startup_diagnostics,
)


class FakeStream:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    async def readline(self) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)


class FakeProcess:
    def __init__(self, *, name: str, returncode: int | None = None, stdout: list[bytes] | None = None) -> None:
        self.name = name
        self.pid = 12345
        self.returncode = returncode
        self.stdout = FakeStream(stdout or [])
        self.stderr = FakeStream([])
        self.terminated = False
        self.killed = False
        self.waited = False

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def wait(self) -> int:
        self.waited = True
        return self.returncode or 0


def run(coro):
    return asyncio.run(coro)


def ignore_port(_label: str, _host: str, _port: int) -> None:
    return None


def test_dev_runner_waits_for_health_prints_diagnostics_and_stops(tmp_path: Path) -> None:
    events: list[str] = []
    (tmp_path / "web").mkdir()
    api = FakeProcess(name="api")
    web = FakeProcess(name="web", stdout=[b"VITE ready\n"])
    diagnostics = StartupDiagnostics(
        providers_json=tmp_path / ".storyforge3" / "providers.json",
        providers_exists=True,
        active_provider="Codex Relay (gpt-5.5)",
        ccswitch_db=tmp_path / "cc-switch.db",
        ccswitch_available=False,
        books_dir=tmp_path / "books",
        book_count=2,
    )

    async def spawn_api(_runner: DevRunner) -> FakeProcess:
        events.append("spawn-api")
        return api

    async def spawn_web(_runner: DevRunner) -> FakeProcess:
        events.append("spawn-web")
        return web

    async def health(_url: str) -> bool:
        events.append("health")
        return True

    async def collect_diagnostics(_runner: DevRunner) -> StartupDiagnostics:
        events.append("diagnostics")
        return diagnostics

    runner = DevRunner(
        project_dir=tmp_path,
        config=StoryForge3Config(books_dir=str(tmp_path / "books"), providers_config_dir=str(tmp_path / ".storyforge3")),
        spawn_api=spawn_api,
        spawn_web=spawn_web,
        health_check=health,
        web_check=health,
        diagnostics_collector=collect_diagnostics,
        port_checker=ignore_port,
        sleep=lambda _seconds: None,
        output=events.append,
    )

    run(runner.start())
    run(runner.stop())

    assert events.index("spawn-web") < events.index("spawn-api") < events.index("health")
    assert events.count("health") == 2
    assert any("providers.json =" in event and "exists=True" in event for event in events)
    assert any("active_provider = Codex Relay (gpt-5.5)" in event for event in events)
    assert any("books_dir" in event and "2 books" in event for event in events)
    assert any("ready" in event and "http://localhost:5173" in event for event in events)
    assert api.terminated is True
    assert web.terminated is True


def test_dev_runner_stops_started_process_when_health_gate_fails(tmp_path: Path) -> None:
    (tmp_path / "web").mkdir()
    api = FakeProcess(name="api")
    web = FakeProcess(name="web")

    async def spawn_api(_runner: DevRunner) -> FakeProcess:
        return api

    async def spawn_web(_runner: DevRunner) -> FakeProcess:
        return web

    async def health(_url: str) -> bool:
        return False

    runner = DevRunner(
        project_dir=tmp_path,
        config=StoryForge3Config(books_dir=str(tmp_path / "books"), providers_config_dir=str(tmp_path / ".storyforge3")),
        spawn_api=spawn_api,
        spawn_web=spawn_web,
        health_check=health,
        port_checker=ignore_port,
        health_timeout_seconds=0.01,
        sleep=lambda _seconds: None,
        output=lambda _line: None,
    )

    with pytest.raises(DevProcessError, match="API health check timed out"):
        run(runner.start())

    assert api.terminated is True
    assert web.terminated is True


def test_dev_runner_fails_fast_when_api_process_exits(tmp_path: Path) -> None:
    (tmp_path / "web").mkdir()
    api = FakeProcess(name="api", returncode=1)
    web = FakeProcess(name="web")

    async def spawn_api(_runner: DevRunner) -> FakeProcess:
        return api

    async def spawn_web(_runner: DevRunner) -> FakeProcess:
        return web

    runner = DevRunner(
        project_dir=tmp_path,
        config=StoryForge3Config(books_dir=str(tmp_path / "books"), providers_config_dir=str(tmp_path / ".storyforge3")),
        spawn_api=spawn_api,
        spawn_web=spawn_web,
        health_check=lambda _url: False,
        port_checker=ignore_port,
        sleep=lambda _seconds: None,
        output=lambda _line: None,
    )

    with pytest.raises(DevProcessError, match="API process exited before becoming healthy"):
        run(runner.start())

    assert web.terminated is True


def test_dev_runner_fails_fast_when_web_process_exits(tmp_path: Path) -> None:
    (tmp_path / "web").mkdir()
    api = FakeProcess(name="api")
    web = FakeProcess(name="web", returncode=1)

    async def spawn_api(_runner: DevRunner) -> FakeProcess:
        return api

    async def spawn_web(_runner: DevRunner) -> FakeProcess:
        return web

    runner = DevRunner(
        project_dir=tmp_path,
        config=StoryForge3Config(books_dir=str(tmp_path / "books"), providers_config_dir=str(tmp_path / ".storyforge3")),
        spawn_api=spawn_api,
        spawn_web=spawn_web,
        health_check=lambda _url: False,
        port_checker=ignore_port,
        sleep=lambda _seconds: None,
        output=lambda _line: None,
    )

    with pytest.raises(DevProcessError, match="Web process exited before API became healthy"):
        run(runner.start())

    assert api.terminated is True


def test_dev_runner_reports_missing_web_dir_as_human_error(tmp_path: Path) -> None:
    runner = DevRunner(
        project_dir=tmp_path,
        config=StoryForge3Config(books_dir=str(tmp_path / "books"), providers_config_dir=str(tmp_path / ".storyforge3")),
        port_checker=ignore_port,
        output=lambda _line: None,
    )

    with pytest.raises(DevProcessError, match="web directory not found"):
        run(runner.start())


def test_spawn_web_passes_strict_port_and_api_url(tmp_path: Path) -> None:
    (tmp_path / "web").mkdir()
    seen: dict[str, object] = {}
    process = FakeProcess(name="web")
    runner = DevRunner(
        project_dir=tmp_path,
        config=StoryForge3Config(books_dir=str(tmp_path / "books"), providers_config_dir=str(tmp_path / ".storyforge3")),
        api_port=8010,
        web_port=15173,
        output=lambda _line: None,
    )

    async def fake_create(args, *, cwd, env_extra=None):
        seen["args"] = args
        seen["cwd"] = cwd
        seen["env_extra"] = env_extra
        return process

    with patch("storyforge3.dev_runner.shutil.which", return_value="pnpm.cmd"), patch(
        "storyforge3.dev_runner._create_process", side_effect=fake_create
    ):
        assert run(_spawn_web(runner)) is process

    assert seen["args"] == ["pnpm.cmd", "dev", "--host", "127.0.0.1", "--port", "15173", "--strictPort"]
    assert seen["cwd"] == tmp_path / "web"
    assert seen["env_extra"] == {"VITE_API_URL": "http://127.0.0.1:8010"}


def test_spawn_api_reuses_serve_entrypoint_and_reload(tmp_path: Path) -> None:
    seen: dict[str, object] = {}
    process = FakeProcess(name="api")
    runner = DevRunner(
        project_dir=tmp_path,
        config=StoryForge3Config(books_dir=str(tmp_path / "books"), providers_config_dir=str(tmp_path / ".storyforge3")),
        api_port=8010,
        reload=True,
        output=lambda _line: None,
    )

    async def fake_create(args, *, cwd, env_extra=None):
        seen["args"] = args
        seen["cwd"] = cwd
        seen["env_extra"] = env_extra
        return process

    with patch("storyforge3.dev_runner._create_process", side_effect=fake_create):
        assert run(_spawn_api(runner)) is process

    assert seen["args"] == [sys.executable, "-m", "storyforge3", "serve", "--port", "8010", "--reload"]
    assert seen["cwd"] == tmp_path
    assert seen["env_extra"] is None


def test_spawn_web_reports_missing_pnpm(tmp_path: Path) -> None:
    (tmp_path / "web").mkdir()
    runner = DevRunner(
        project_dir=tmp_path,
        config=StoryForge3Config(books_dir=str(tmp_path / "books"), providers_config_dir=str(tmp_path / ".storyforge3")),
        output=lambda _line: None,
    )

    with patch("storyforge3.dev_runner.shutil.which", return_value=None), pytest.raises(DevProcessError, match="command not found: pnpm"):
        run(_spawn_web(runner))


def test_resolve_command_prefers_windows_cmd_shim_for_shell_wrappers() -> None:
    seen: list[str] = []

    def fake_which(command: str) -> str | None:
        seen.append(command)
        if command == "pnpm.cmd":
            return "C:\\Users\\pengq\\AppData\\Roaming\\npm\\pnpm.cmd"
        if command == "pnpm":
            return "C:\\Users\\pengq\\AppData\\Roaming\\npm\\pnpm.ps1"
        return None

    with patch("storyforge3.dev_runner.sys.platform", "win32"), patch("storyforge3.dev_runner.shutil.which", side_effect=fake_which):
        assert _resolve_command("pnpm").endswith("pnpm.cmd")

    assert seen == ["pnpm.cmd"]


def test_collect_startup_diagnostics_reads_provider_config_without_creating_it(tmp_path: Path) -> None:
    (tmp_path / "books").mkdir()
    runner = DevRunner(
        project_dir=tmp_path,
        config=StoryForge3Config(
            books_dir=str(tmp_path / "books"),
            providers_config_dir=str(tmp_path / ".storyforge3"),
            ccswitch_db_path=str(tmp_path / "missing-cc-switch.db"),
        ),
        output=lambda _line: None,
    )

    diagnostics = run(collect_startup_diagnostics(runner))

    assert diagnostics.providers_exists is False
    assert diagnostics.active_provider == "none"
    assert diagnostics.ccswitch_available is False
    assert not (tmp_path / ".storyforge3").exists()


def test_collect_startup_diagnostics_reports_active_provider_from_existing_json(tmp_path: Path) -> None:
    providers_dir = tmp_path / ".storyforge3"
    providers_dir.mkdir()
    (providers_dir / "providers.json").write_text(
        json.dumps(
            {
                "active_provider_key": "cc-volcano",
                "providers": [{"provider_key": "cc-volcano", "label": "Volcano", "model_id": "ark-code-latest"}],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "books" / "book-a").mkdir(parents=True)
    (tmp_path / "books" / "book-a" / "book.json").write_text(
        json.dumps(
            {
                "book_id": "book-a",
                "title": "Book A",
                "genre": "x",
                "platform": "tomato",
                "status": "incubating",
                "target_chapters": 3,
                "chapter_word_count": 2000,
                "language": "zh",
                "fanfic_mode": False,
                "created_at": "2026-06-14T00:00:00+00:00",
                "updated_at": "2026-06-14T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    db_path = tmp_path / "cc-switch.db"
    db_path.write_text("", encoding="utf-8")
    runner = DevRunner(
        project_dir=tmp_path,
        config=StoryForge3Config(
            books_dir=str(tmp_path / "books"),
            providers_config_dir=str(providers_dir),
            ccswitch_db_path=str(db_path),
        ),
        output=lambda _line: None,
    )

    diagnostics = run(collect_startup_diagnostics(runner))

    assert diagnostics.providers_exists is True
    assert diagnostics.active_provider == "Volcano (ark-code-latest)"
    assert diagnostics.ccswitch_available is True
    assert diagnostics.book_count == 1


def test_port_checker_reports_busy_port_as_human_error() -> None:
    with patch("storyforge3.dev_runner.socket.socket") as socket_factory:
        sock = socket_factory.return_value.__enter__.return_value
        sock.connect_ex.return_value = 0

        with pytest.raises(DevProcessError, match="API port 8000 is already in use on 127.0.0.1"):
            _ensure_port_available("API", "127.0.0.1", 8000)


def test_signal_handler_fallback_installs_sigbreak_and_restores(monkeypatch) -> None:
    class FakeLoop:
        def add_signal_handler(self, _sig, _callback) -> None:
            raise NotImplementedError

        def call_soon_threadsafe(self, callback) -> None:
            callback()

    installed: dict[int, object] = {}

    def fake_signal(sig, handler):
        previous = f"old-{sig}"
        installed[sig] = handler
        return previous

    monkeypatch.setattr("storyforge3.dev_runner.asyncio.get_running_loop", lambda: FakeLoop())
    monkeypatch.setattr("storyforge3.dev_runner.signal.getsignal", lambda sig: f"old-{sig}")
    monkeypatch.setattr("storyforge3.dev_runner.signal.signal", fake_signal)
    sigbreak = getattr(signal, "SIGBREAK", 21)
    monkeypatch.setattr("storyforge3.dev_runner.signal.SIGBREAK", sigbreak, raising=False)
    stop_event = asyncio.Event()

    restore = _install_stop_signal_handlers(stop_event)
    installed[sigbreak](sigbreak, None)

    assert stop_event.is_set()

    restore()

    assert installed[signal.SIGINT] == f"old-{signal.SIGINT}"
    assert installed[sigbreak] == f"old-{sigbreak}"


def test_default_health_check_requires_ok_envelope_status(monkeypatch) -> None:
    class FakeResponse:
        status = 200

        def __init__(self, payload: bytes) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return self.payload

    def fake_urlopen(_request, timeout):
        assert timeout == 2
        return FakeResponse(b'{"ok": true, "data": {"status": "ok"}, "error": null}')

    monkeypatch.setattr("storyforge3.dev_runner.urlopen", fake_urlopen)

    assert run(_default_health_check("http://127.0.0.1:8000/api/health")) is True


def test_default_health_check_rejects_non_ok_envelope(monkeypatch) -> None:
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return b'{"ok": true, "data": {"status": "starting"}, "error": null}'

    monkeypatch.setattr("storyforge3.dev_runner.urlopen", lambda *_args, **_kwargs: FakeResponse())

    assert run(_default_health_check("http://127.0.0.1:8000/api/health")) is False


def test_default_web_check_accepts_http_2xx(monkeypatch) -> None:
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr("storyforge3.dev_runner.urlopen", lambda *_args, **_kwargs: FakeResponse())

    assert run(_default_web_check("http://localhost:5173")) is True
