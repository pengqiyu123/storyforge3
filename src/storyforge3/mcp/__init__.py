"""StoryForge3 MCP server package."""


def create_server():
    from storyforge3.mcp.server import create_server as _create_server

    return _create_server()


__all__ = ["create_server"]
