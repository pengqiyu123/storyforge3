from __future__ import annotations

import json
from unittest.mock import patch

import httpx

from storyforge3.__main__ import main


def test_serve_command_starts_uvicorn():
    with patch("sys.argv", ["storyforge3", "serve"]), patch("uvicorn.run") as run:
        run.return_value = None
        assert main() == 0
    run.assert_called_once_with("storyforge3.api.app:app", host="127.0.0.1", port=8000, reload=False)


def test_serve_command_accepts_port_override():
    with patch("sys.argv", ["storyforge3", "serve", "--port", "18731"]), patch("uvicorn.run") as run:
        run.return_value = None
        assert main() == 0
    run.assert_called_once_with("storyforge3.api.app:app", host="127.0.0.1", port=18731, reload=False)


def test_serve_command_accepts_reload():
    with patch("sys.argv", ["storyforge3", "serve", "--reload"]), patch("uvicorn.run") as run:
        run.return_value = None
        assert main() == 0
    run.assert_called_once_with("storyforge3.api.app:app", host="127.0.0.1", port=8000, reload=True)


def test_dev_command_runs_unified_dev_runner():
    with patch("sys.argv", ["storyforge3", "dev", "--port", "18731", "--web-port", "15173", "--reload"]), patch(
        "storyforge3.__main__.run_dev"
    ) as run_dev:
        run_dev.return_value = 0
        assert main() == 0
    kwargs = run_dev.call_args.kwargs
    assert kwargs["api_port"] == 18731
    assert kwargs["web_port"] == 15173
    assert kwargs["reload"] is True
    assert kwargs["open_browser"] is False


def test_mcp_command_starts_stdio_server():
    with patch("sys.argv", ["storyforge3", "mcp"]), patch("storyforge3.mcp.server.create_server") as create_server:
        server = create_server.return_value
        assert main() == 0
    server.run.assert_called_once_with(transport="stdio")


def test_health_command_reports_unavailable_without_traceback(capsys):
    class TimeoutLLM:
        async def check_health(self) -> bool:
            raise httpx.ReadTimeout("slow provider")

    with patch("sys.argv", ["storyforge3", "health"]), patch("storyforge3.__main__.create_llm_service", return_value=TimeoutLLM()):
        assert main() == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["ccswitch"] == "unavailable"
    assert "slow provider" in payload["error"]
