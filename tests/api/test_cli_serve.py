from __future__ import annotations

from unittest.mock import patch

from storyforge3.__main__ import main


def test_serve_command_starts_uvicorn():
    with patch("sys.argv", ["storyforge3", "serve"]), patch("uvicorn.run") as run:
        run.return_value = None
        assert main() == 0
    run.assert_called_once_with("storyforge3.api.app:app", host="0.0.0.0", port=8000, reload=True)
