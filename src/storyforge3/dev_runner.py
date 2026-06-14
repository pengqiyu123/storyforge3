from __future__ import annotations

import asyncio
import json
import os
import signal
import shutil
import socket
import subprocess
import sys
import webbrowser
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.request import Request, urlopen

from storyforge3.config import StoryForge3Config
from storyforge3.services.book_service import BookService
from storyforge3.storage import BookStorage, StoragePaths


class DevProcessError(RuntimeError):
    pass


class ManagedProcess(Protocol):
    returncode: int | None
    stdout: object | None
    stderr: object | None

    def terminate(self) -> None: ...
    def kill(self) -> None: ...
    async def wait(self) -> int: ...


@dataclass(frozen=True)
class StartupDiagnostics:
    providers_json: Path
    providers_exists: bool
    active_provider: str
    ccswitch_db: Path
    ccswitch_available: bool
    books_dir: Path
    book_count: int


SleepFunc = Callable[[float], Awaitable[object] | object]
OutputFunc = Callable[[str], None]
HealthCheck = Callable[[str], Awaitable[bool]]
Spawner = Callable[["DevRunner"], Awaitable[ManagedProcess]]
DiagnosticsCollector = Callable[["DevRunner"], Awaitable[StartupDiagnostics]]
PortChecker = Callable[[str, str, int], None]


class DevRunner:
    def __init__(
        self,
        *,
        project_dir: Path,
        config: StoryForge3Config,
        api_port: int = 8000,
        web_port: int = 5173,
        reload: bool = False,
        open_browser: bool = False,
        health_timeout_seconds: float = 30.0,
        spawn_api: Spawner | None = None,
        spawn_web: Spawner | None = None,
        health_check: HealthCheck | None = None,
        web_check: HealthCheck | None = None,
        diagnostics_collector: DiagnosticsCollector | None = None,
        port_checker: PortChecker | None = None,
        sleep: SleepFunc | None = None,
        output: OutputFunc | None = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.config = config
        self.api_port = api_port
        self.web_port = web_port
        self.reload = reload
        self.open_browser = open_browser
        self.health_timeout_seconds = health_timeout_seconds
        self.spawn_api = spawn_api or _spawn_api
        self.spawn_web = spawn_web or _spawn_web
        self.health_check = health_check or _default_health_check
        self.web_check = web_check or _default_web_check
        self.diagnostics_collector = diagnostics_collector or collect_startup_diagnostics
        self.port_checker = port_checker or _ensure_port_available
        self.sleep = sleep or asyncio.sleep
        self.output = output or _print_line
        self.api_process: ManagedProcess | None = None
        self.web_process: ManagedProcess | None = None
        self._pump_tasks: list[asyncio.Task] = []

    @property
    def api_url(self) -> str:
        return f"http://127.0.0.1:{self.api_port}"

    @property
    def web_url(self) -> str:
        return f"http://localhost:{self.web_port}"

    async def start(self) -> None:
        try:
            self._validate_project()
            self.output(f"[sf3] starting web :{self.web_port} + api :{self.api_port}")
            self.web_process = await self.spawn_web(self)
            self._pump_tasks.extend(_prefix_process_output(self.web_process, "[web]", self.output))
            self.api_process = await self.spawn_api(self)
            self._pump_tasks.extend(_prefix_process_output(self.api_process, "[api]", self.output))
            await self._wait_for_api_health()
            await self._wait_for_web_health()
            diagnostics = await self.diagnostics_collector(self)
            self._print_diagnostics(diagnostics)
            self.output(f"[sf3] ✓ ready → {self.web_url}")
            if self.open_browser:
                webbrowser.open(self.web_url)
        except Exception:
            await self.stop()
            raise

    async def wait_until_exit(self) -> int:
        processes = [process for process in (self.api_process, self.web_process) if process is not None]
        if not processes:
            return 1
        wait_tasks = [asyncio.create_task(process.wait()) for process in processes]
        done, pending = await asyncio.wait(wait_tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        exit_code = next(iter(done)).result()
        await self.stop()
        return exit_code

    async def stop(self) -> None:
        for task in self._pump_tasks:
            task.cancel()
        self._pump_tasks.clear()
        for process in (self.web_process, self.api_process):
            if process is not None:
                await _terminate_process(process)
        self.web_process = None
        self.api_process = None

    async def _wait_for_api_health(self) -> None:
        self.output(f"[sf3] waiting for API health {self.api_url}/api/health")
        deadline = asyncio.get_running_loop().time() + self.health_timeout_seconds
        next_status_at = 0.0
        while True:
            self._fail_if_process_exited()
            if await self.health_check(f"{self.api_url}/api/health"):
                return
            now = asyncio.get_running_loop().time()
            if now >= deadline:
                raise DevProcessError(f"API health check timed out after {self.health_timeout_seconds:g}s")
            if now >= next_status_at:
                self.output("[sf3] waiting: API is still starting")
                next_status_at = now + 2.0
            await _maybe_await(self.sleep(0.5))

    async def _wait_for_web_health(self) -> None:
        self.output(f"[sf3] waiting for Web health {self.web_url}")
        deadline = asyncio.get_running_loop().time() + self.health_timeout_seconds
        next_status_at = 0.0
        while True:
            self._fail_if_process_exited()
            if await self.web_check(self.web_url):
                return
            now = asyncio.get_running_loop().time()
            if now >= deadline:
                raise DevProcessError(f"Web health check timed out after {self.health_timeout_seconds:g}s")
            if now >= next_status_at:
                self.output("[sf3] waiting: Web is still starting")
                next_status_at = now + 2.0
            await _maybe_await(self.sleep(0.5))

    def _fail_if_process_exited(self) -> None:
        if self.api_process is not None and self.api_process.returncode is not None:
            raise DevProcessError(f"API process exited before becoming healthy (exit={self.api_process.returncode})")
        if self.web_process is not None and self.web_process.returncode is not None:
            raise DevProcessError(f"Web process exited before API became healthy (exit={self.web_process.returncode})")

    def _validate_project(self) -> None:
        if not self.project_dir.exists():
            raise DevProcessError(f"project directory not found: {self.project_dir}")
        web_dir = self.project_dir / "web"
        if not web_dir.is_dir():
            raise DevProcessError(f"web directory not found: {web_dir}")
        self.port_checker("API", "127.0.0.1", self.api_port)
        self.port_checker("Web", "127.0.0.1", self.web_port)

    def _print_diagnostics(self, diagnostics: StartupDiagnostics) -> None:
        self.output(f"[sf3] providers.json = {diagnostics.providers_json}  (exists={diagnostics.providers_exists})")
        self.output(f"[sf3] active_provider = {diagnostics.active_provider}")
        self.output(f"[sf3] ccswitch_db   = {diagnostics.ccswitch_db}  (available={diagnostics.ccswitch_available})")
        self.output(f"[sf3] books_dir     = {diagnostics.books_dir}  ({diagnostics.book_count} books)")


async def run_dev_async(
    *,
    api_port: int = 8000,
    web_port: int = 5173,
    reload: bool = False,
    open_browser: bool = False,
    project_dir: Path | None = None,
    config: StoryForge3Config | None = None,
) -> int:
    runner = DevRunner(
        project_dir=project_dir or _project_root(),
        config=config or StoryForge3Config(),
        api_port=api_port,
        web_port=web_port,
        reload=reload,
        open_browser=open_browser,
    )
    stop_event = asyncio.Event()
    restore_signal_handlers = _install_stop_signal_handlers(stop_event)
    try:
        await runner.start()
        wait_task = asyncio.create_task(runner.wait_until_exit())
        stop_task = asyncio.create_task(stop_event.wait())
        done, pending = await asyncio.wait({wait_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        if stop_task in done:
            await runner.stop()
            return 0
        return wait_task.result()
    except KeyboardInterrupt:
        await runner.stop()
        return 0
    except DevProcessError as exc:
        print(f"[sf3] error: {exc}", file=sys.stderr)
        return 2
    finally:
        restore_signal_handlers()


def run_dev(**kwargs: object) -> int:
    return asyncio.run(run_dev_async(**kwargs))


def _print_line(line: str) -> None:
    print(line, flush=True)


def _install_stop_signal_handlers(stop_event: asyncio.Event) -> Callable[[], None]:
    loop = asyncio.get_running_loop()
    signals = [signal.SIGINT, signal.SIGTERM]
    sigbreak = getattr(signal, "SIGBREAK", None)
    if sigbreak is not None:
        signals.append(sigbreak)
    installed: list[tuple[str, int, object]] = []

    def request_stop(_signum: int, _frame: object) -> None:
        loop.call_soon_threadsafe(stop_event.set)

    for sig in signals:
        try:
            loop.add_signal_handler(sig, stop_event.set)
            installed.append(("loop", sig, None))
            continue
        except (NotImplementedError, RuntimeError):
            pass
        try:
            previous = signal.getsignal(sig)
            signal.signal(sig, request_stop)
            installed.append(("signal", sig, previous))
        except (OSError, RuntimeError, ValueError):
            pass

    def restore() -> None:
        for kind, sig, previous in reversed(installed):
            if kind == "loop":
                try:
                    loop.remove_signal_handler(sig)
                except (NotImplementedError, RuntimeError, ValueError):
                    pass
            else:
                try:
                    signal.signal(sig, previous)
                except (OSError, RuntimeError, ValueError):
                    pass

    return restore


async def collect_startup_diagnostics(runner: DevRunner) -> StartupDiagnostics:
    provider_dir = runner.config.resolved_providers_config_dir()
    providers_json = provider_dir / "providers.json"
    active = _read_active_provider(providers_json)
    active_provider = _active_provider_label(active)
    paths = StoragePaths(Path(runner.config.books_dir))
    books = await BookService(BookStorage(paths.books_root), paths).list_books()
    return StartupDiagnostics(
        providers_json=providers_json.resolve(),
        providers_exists=providers_json.exists(),
        active_provider=active_provider,
        ccswitch_db=runner.config.resolved_ccswitch_db_path(),
        ccswitch_available=runner.config.resolved_ccswitch_db_path().exists(),
        books_dir=paths.books_root.resolve(),
        book_count=len(books),
    )


async def _spawn_api(runner: DevRunner) -> ManagedProcess:
    args = [
        sys.executable,
        "-m",
        "storyforge3",
        "serve",
        "--port",
        str(runner.api_port),
    ]
    if runner.reload:
        args.append("--reload")
    return await _create_process(args, cwd=runner.project_dir)


async def _spawn_web(runner: DevRunner) -> ManagedProcess:
    args = [
        _resolve_command("pnpm"),
        "dev",
        "--host",
        "127.0.0.1",
        "--port",
        str(runner.web_port),
        "--strictPort",
    ]
    return await _create_process(args, cwd=runner.project_dir / "web", env_extra={"VITE_API_URL": runner.api_url})


async def _create_process(args: list[str], *, cwd: Path, env_extra: dict[str, str] | None = None) -> ManagedProcess:
    env = {**os.environ, "PYTHONUNBUFFERED": "1", **(env_extra or {})}
    try:
        return await asyncio.create_subprocess_exec(
            *args,
            cwd=str(cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        command = args[0]
        raise DevProcessError(f"command not found: {command}") from exc
    except OSError as exc:
        raise DevProcessError(f"failed to start {args[0]}: {exc}") from exc


def _resolve_command(command: str) -> str:
    candidates = [command]
    if sys.platform == "win32" and Path(command).suffix == "":
        # PowerShell often resolves pnpm to pnpm.ps1 first, but CreateProcess
        # needs the cmd shim when subprocess_exec bypasses a shell.
        candidates = [f"{command}.cmd", f"{command}.exe", command]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved is not None:
            return resolved
    raise DevProcessError(f"command not found: {command}")


async def _default_health_check(url: str) -> bool:
    def _request() -> bool:
        request = Request(url, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=2) as response:
                if not 200 <= response.status < 300:
                    return False
                payload = json.loads(response.read().decode("utf-8"))
                data = payload.get("data") if isinstance(payload, dict) else None
                return bool(payload.get("ok")) and isinstance(data, dict) and data.get("status") == "ok"
        except (OSError, json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            return False

    return await asyncio.to_thread(_request)


async def _default_web_check(url: str) -> bool:
    def _request() -> bool:
        try:
            with urlopen(url, timeout=2) as response:
                return 200 <= response.status < 300
        except OSError:
            return False

    return await asyncio.to_thread(_request)


def _ensure_port_available(label: str, host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        if sock.connect_ex((host, port)) == 0:
            raise DevProcessError(f"{label} port {port} is already in use on {host}")


def _prefix_process_output(process: ManagedProcess, prefix: str, output: OutputFunc) -> list[asyncio.Task]:
    tasks: list[asyncio.Task] = []
    for stream in (process.stdout, process.stderr):
        if stream is not None and hasattr(stream, "readline"):
            tasks.append(asyncio.create_task(_pump_stream(stream, prefix, output)))
    return tasks


async def _pump_stream(stream: object, prefix: str, output: OutputFunc) -> None:
    readline = getattr(stream, "readline")
    while True:
        line = await readline()
        if not line:
            return
        text = line.decode("utf-8", errors="replace").rstrip()
        if text:
            output(f"{prefix} {text}")


async def _terminate_process(process: ManagedProcess) -> None:
    if process.returncode is not None:
        await _wait_safely(process)
        return
    _terminate_process_tree(process)
    try:
        process.terminate()
    except (OSError, ProcessLookupError):
        pass
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except TimeoutError:
        try:
            process.kill()
        except (OSError, ProcessLookupError):
            return
        await _wait_safely(process)


async def _wait_safely(process: ManagedProcess) -> None:
    try:
        await process.wait()
    except ProcessLookupError:
        return


def _terminate_process_tree(process: ManagedProcess) -> None:
    pid = getattr(process, "pid", None)
    if sys.platform != "win32" or not isinstance(pid, int):
        return
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


async def _maybe_await(value: object) -> None:
    if hasattr(value, "__await__"):
        await value  # type: ignore[misc]


def _active_provider_label(active: dict | None) -> str:
    if not active:
        return "none"
    label = str(active.get("label") or active.get("provider_key") or "unknown")
    model_id = str(active.get("model_id") or "default")
    return f"{label} ({model_id})"


def _read_active_provider(providers_json: Path) -> dict | None:
    if not providers_json.exists():
        return None
    try:
        data = json.loads(providers_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    active_key = data.get("active_provider_key")
    providers = data.get("providers")
    if not active_key or not isinstance(providers, list):
        return None
    for provider in providers:
        if isinstance(provider, dict) and provider.get("provider_key") == active_key:
            return dict(provider)
    return None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]
