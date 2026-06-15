from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from storyforge3.api.errors import ApiError
from storyforge3.api.response import err
from storyforge3.api.routes.books import router as books_router
from storyforge3.api.routes.chapters import router as chapters_router
from storyforge3.api.routes.characters import router as characters_router
from storyforge3.api.routes.daemon import router as daemon_router
from storyforge3.api.routes.events import router as events_router
from storyforge3.api.routes.export import router as export_router
from storyforge3.api.routes.fanfic import router as fanfic_router
from storyforge3.api.routes.health import router as health_router
from storyforge3.api.routes.providers import router as providers_router
from storyforge3.api.routes.short_story import router as short_story_router
from storyforge3.api.routes.snapshots import router as snapshots_router
from storyforge3.api.routes.truth import router as truth_router
from storyforge3.api.routes.volumes import router as volumes_router
from storyforge3.api.routes.workspace import router as workspace_router
from storyforge3.api.routes.world import router as world_router

app = FastAPI(title="StoryForge3 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApiError)
async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    payload = err(exc).model_dump()
    if payload["error"] is not None:
        payload["error"] = {key: value for key, value in payload["error"].items() if value is not None}
    return JSONResponse(status_code=exc.status, content=payload)


app.include_router(health_router, prefix="/api")
app.include_router(books_router, prefix="/api")
app.include_router(world_router, prefix="/api")
app.include_router(characters_router, prefix="/api")
app.include_router(volumes_router, prefix="/api")
app.include_router(chapters_router, prefix="/api")
app.include_router(truth_router, prefix="/api")
app.include_router(export_router, prefix="/api")
app.include_router(fanfic_router, prefix="/api")
app.include_router(short_story_router, prefix="/api")
app.include_router(snapshots_router, prefix="/api")
app.include_router(providers_router, prefix="/api")
app.include_router(daemon_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(workspace_router, prefix="/api")
