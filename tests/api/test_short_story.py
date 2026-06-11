from __future__ import annotations

from pathlib import Path

from storyforge3.api.app import app
from storyforge3.api.deps import get_short_story_service
from storyforge3.models import AuditResult, ShortStoryMeta, ShortStoryPlan, ShortStoryResult, ShortStoryStatus


class ApiFakeShortStoryService:
    def __init__(self) -> None:
        self.last_created = None
        self.last_export_format = ""
        self.meta = ShortStoryMeta(
            book_id="story-test",
            title="凌晨三点十七",
            genre="horror",
            status=ShortStoryStatus.EMPTY,
            target_chars=6000,
            premise="便利店夜班怪谈",
            style="悬疑克制",
        )

    async def create(self, config) -> ShortStoryMeta:
        self.last_created = config
        self.meta = ShortStoryMeta(
            book_id="story-test",
            title=config.title,
            genre=config.genre,
            status=ShortStoryStatus.EMPTY,
            target_chars=config.target_chars,
            premise=config.premise,
            style=config.style,
        )
        return self.meta

    def list_stories(self) -> list[ShortStoryMeta]:
        return [self.meta]

    def get_status(self, book_id: str) -> ShortStoryResult | None:
        if book_id == "missing":
            return None
        return ShortStoryResult(book_id=book_id, status=self.meta.status, text="短篇正文")

    async def plan(self, book_id: str) -> ShortStoryPlan:
        return ShortStoryPlan(
            book_id=book_id,
            premise="便利店夜班怪谈",
            opening="收银机自动弹开",
            climax="纸币背面浮现地址",
            ending="工牌出现在抽屉里",
            characters="林默：夜班店员",
            key_scenes=("收银机弹开", "监控黑屏", "纸币浮字"),
        )

    async def draft(self, _book_id: str) -> str:
        return "林默站在收银台后。\n\n抽屉突然弹开。"

    async def audit(self, _book_id: str) -> AuditResult:
        return AuditResult(1, True, (), (), (), ())

    async def revise(self, book_id: str) -> ShortStoryResult:
        return ShortStoryResult(book_id, ShortStoryStatus.REVISED, "修订正文")

    async def export(self, _book_id: str, fmt: str = "tomato_txt") -> Path:
        self.last_export_format = fmt
        return Path("exports") / f"short.{fmt}"

    async def run_full_pipeline(self, book_id: str) -> ShortStoryResult:
        return ShortStoryResult(book_id, ShortStoryStatus.EXPORTED, "完整短篇正文", audit=await self.audit(book_id))


def _install_fake_service(fake: ApiFakeShortStoryService) -> None:
    app.dependency_overrides[get_short_story_service] = lambda: fake


def test_create_short_story(client):
    fake = ApiFakeShortStoryService()
    _install_fake_service(fake)

    resp = client.post(
        "/api/short-stories",
        json={
            "title": "凌晨三点十七",
            "genre": "horror",
            "target_chars": 6000,
            "premise": "便利店夜班怪谈",
            "style": "悬疑克制",
        },
    )

    assert resp.status_code == 201
    assert resp.json()["ok"] is True
    assert resp.json()["data"]["book_id"] == "story-test"
    assert resp.json()["data"]["status"] == "empty"
    assert fake.last_created.title == "凌晨三点十七"


def test_list_short_stories_200(client):
    fake = ApiFakeShortStoryService()
    _install_fake_service(fake)

    resp = client.get("/api/short-stories")

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["data"] == [
        {
            "book_id": "story-test",
            "title": "凌晨三点十七",
            "genre": "horror",
            "status": "empty",
            "target_chars": 6000,
            "premise": "便利店夜班怪谈",
            "style": "悬疑克制",
            "actual_chars": 0,
            "created_at": "",
            "updated_at": "",
        }
    ]


def test_plan_short_story(client):
    fake = ApiFakeShortStoryService()
    _install_fake_service(fake)

    resp = client.post("/api/short-stories/story-test/plan")

    assert resp.status_code == 200
    assert resp.json()["data"]["opening"] == "收银机自动弹开"
    assert resp.json()["data"]["key_scenes"] == ["收银机弹开", "监控黑屏", "纸币浮字"]


def test_run_full_pipeline(client):
    fake = ApiFakeShortStoryService()
    _install_fake_service(fake)

    resp = client.post("/api/short-stories/story-test/run")

    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "exported"
    assert resp.json()["data"]["text"] == "完整短篇正文"


def test_export_short_story(client):
    fake = ApiFakeShortStoryService()
    _install_fake_service(fake)

    resp = client.post("/api/short-stories/story-test/export", json={"fmt": "md"})

    assert resp.status_code == 200
    assert resp.json()["data"]["path"].endswith("short.md")
    assert fake.last_export_format == "md"


def test_get_short_story_404(client):
    fake = ApiFakeShortStoryService()
    _install_fake_service(fake)

    resp = client.get("/api/short-stories/missing")

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "BOOK_NOT_FOUND"
