from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

from storyforge3.audit.runner import AuditRunner
from storyforge3.config import StoryForge3Config
from storyforge3.dev_runner import run_dev
from storyforge3.llm.factory import create_llm_service
from storyforge3.llm.llm_service import ProviderUnavailableError
from storyforge3.models import BookConfig
from storyforge3.services.book_service import BookService
from storyforge3.services.chapter_service import ChapterService
from storyforge3.services.character_service import CharacterService
from storyforge3.services.volume_service import VolumeService
from storyforge3.services.world_service import WorldService
from storyforge3.state.machine import ChapterStateMachine
from storyforge3.storage import BookStorage, StoragePaths


def _configure_console_encoding() -> None:
    """Prefer UTF-8 for Chinese CLI text on Windows terminals."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _configure_console_encoding()
    parser = argparse.ArgumentParser(prog="storyforge3")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="执行单章管线")
    run_parser.add_argument("book_id")
    run_parser.add_argument("chapter_no", type=int)
    run_parser.add_argument("--confirm", action="store_true", help="人工确认通过后导出")

    audit_parser = subparsers.add_parser("audit", help="单独审计章节文件")
    audit_parser.add_argument("file_path")
    audit_parser.add_argument("--chapter-no", type=int, default=1)

    subparsers.add_parser("health", help="检查 CCSwitch 连通性")

    status_parser = subparsers.add_parser("status", help="查看章节状态")
    status_parser.add_argument("book_id")
    status_parser.add_argument("chapter_no", type=int)

    book_parser = subparsers.add_parser("book", help="书籍管理")
    book_sub = book_parser.add_subparsers(dest="book_command", required=True)
    book_create = book_sub.add_parser("create", help="创建书籍")
    book_create.add_argument("--title", required=True)
    book_create.add_argument("--genre", required=True)
    book_create.add_argument("--platform", required=True)
    book_create.add_argument("--chapters", type=int, required=True)
    book_create.add_argument("--words", type=int, required=True)
    book_sub.add_parser("list", help="列出书籍")

    world_parser = subparsers.add_parser("world", help="世界设定")
    world_sub = world_parser.add_subparsers(dest="world_command", required=True)
    world_build = world_sub.add_parser("build", help="构建世界观")
    world_build.add_argument("book_id")
    world_build.add_argument("--genre", default="")
    world_build.add_argument("--seed", required=True)

    character_parser = subparsers.add_parser("character", help="角色管理")
    character_sub = character_parser.add_subparsers(dest="character_command", required=True)
    character_create = character_sub.add_parser("create", help="创建角色")
    character_create.add_argument("book_id")
    character_create.add_argument("--spec", required=True)

    volume_parser = subparsers.add_parser("volume", help="卷纲管理")
    volume_sub = volume_parser.add_subparsers(dest="volume_command", required=True)
    volume_plan = volume_sub.add_parser("plan", help="规划卷纲")
    volume_plan.add_argument("book_id")
    volume_plan.add_argument("--volumes", type=int, required=True)
    volume_plan.add_argument("--chapters", type=int, default=10)

    chapter_parser = subparsers.add_parser("chapter", help="章节管理")
    chapter_sub = chapter_parser.add_subparsers(dest="chapter_command", required=True)
    for name in ("plan", "draft", "run"):
        chapter_action = chapter_sub.add_parser(name)
        chapter_action.add_argument("book_id")
        chapter_action.add_argument("chapter_no", type=int)
    chapter_status = chapter_sub.add_parser("status")
    chapter_status.add_argument("book_id")
    chapter_status.add_argument("chapter_no", type=int)

    serve_parser = subparsers.add_parser("serve", help="启动 API 服务器")
    serve_parser.add_argument("--port", type=int, default=8000, help="API 服务器监听端口")
    serve_parser.add_argument("--reload", action="store_true", help="启用 uvicorn reload")
    dev_parser = subparsers.add_parser("dev", help="一键启动后端和前端开发服务")
    dev_parser.add_argument("--port", type=int, default=8000, help="API 服务器监听端口")
    dev_parser.add_argument("--web-port", type=int, default=5173, help="前端 Vite 监听端口")
    dev_parser.add_argument("--reload", action="store_true", help="启用后端 uvicorn reload")
    dev_parser.add_argument("--open", action="store_true", help="ready 后打开浏览器")
    subparsers.add_parser("mcp", help="启动 MCP Server（STDIO 模式）")

    args = parser.parse_args()
    config = StoryForge3Config()
    paths = StoragePaths(Path(config.books_dir))
    storage = BookStorage(paths.books_root)

    def llm():
        return create_llm_service(config)

    if args.command == "serve":
        import uvicorn

        uvicorn.run("storyforge3.api.app:app", host="127.0.0.1", port=args.port, reload=args.reload)
        return 0
    if args.command == "dev":
        return run_dev(api_port=args.port, web_port=args.web_port, reload=args.reload, open_browser=args.open)
    if args.command == "mcp":
        from storyforge3.mcp.server import create_server

        create_server().run(transport="stdio")
        return 0
    if args.command == "health":
        try:
            ok = asyncio.run(llm().check_health())
        except ProviderUnavailableError as exc:
            print(json.dumps({"ccswitch": "unavailable", "error": str(exc) or exc.__class__.__name__}, ensure_ascii=False))
            return 1
        except Exception as exc:
            print(json.dumps({"ccswitch": "unavailable", "error": str(exc) or exc.__class__.__name__}, ensure_ascii=False))
            return 1
        if not ok:
            print(json.dumps({"ccswitch": "unavailable"}, ensure_ascii=False))
            return 1
        print(json.dumps({"ccswitch": "ok"}, ensure_ascii=False))
        return 0
    if args.command == "audit":
        text = Path(args.file_path).read_text(encoding="utf-8")
        result = AuditRunner().run_audit(args.chapter_no, text)
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))
        return 0 if result.passed else 2
    if args.command == "status":
        machine = ChapterStateMachine(Path(config.books_dir) / "state.json")
        status = machine.current_status(args.book_id, args.chapter_no)
        print(json.dumps({"book_id": args.book_id, "chapter_no": args.chapter_no, "status": status.value}, ensure_ascii=False))
        return 0
    if args.command == "run":
        confirm = (lambda _: True) if args.confirm else None
        result = asyncio.run(ChapterService(config).run_full_pipeline(args.book_id, args.chapter_no, human_confirm=confirm))
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))
        return 0 if result.error is None else 2
    if args.command == "book":
        service = BookService(storage, paths)
        if args.book_command == "create":
            result = asyncio.run(service.create(BookConfig(args.title, args.genre, args.platform, args.chapters, args.words)))
        else:
            result = asyncio.run(service.list_books())
        print(json.dumps(asdict(result) if not isinstance(result, list) else [asdict(item) for item in result], ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "world":
        result = asyncio.run(WorldService(llm(), storage, paths, config).build(args.book_id, args.genre, args.seed))
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "character":
        result = asyncio.run(CharacterService(llm(), storage, paths, config).create(args.book_id, args.spec))
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "volume":
        result = asyncio.run(VolumeService(llm(), storage, paths, config).plan(args.book_id, args.volumes, args.chapters))
        print(json.dumps([asdict(item) for item in result], ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "chapter":
        service = ChapterService(config)
        if args.chapter_command == "plan":
            result = asyncio.run(service.plan(args.book_id, args.chapter_no))
        elif args.chapter_command == "draft":
            result = asyncio.run(service.draft(args.book_id, args.chapter_no))
        elif args.chapter_command == "status":
            result = asyncio.run(service.get_status(args.book_id, args.chapter_no))
        else:
            result = asyncio.run(service.run_full_pipeline(args.book_id, args.chapter_no))
        print(json.dumps(asdict(result) if hasattr(result, "__dataclass_fields__") else result, ensure_ascii=False, indent=2, default=str))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
