"""StoryForge3 MCP Server entrypoint.

Usage:
    python -m storyforge3.mcp
"""

from __future__ import annotations

from storyforge3.mcp.server import create_server


def main() -> None:
    server = create_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
