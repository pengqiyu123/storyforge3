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
from storyforge3.api.routes.health import router as health_router
from storyforge3.api.routes.providers import router as providers_router
from storyforge3.api.routes.truth import router as truth_router
from storyforge3.api.routes.volumes import router as volumes_router
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
    return JSONResponse(status_code=exc.status, content=err(exc).model_dump())


app.include_router(health_router, prefix="/api")
app.include_router(books_router, prefix="/api")
app.include_router(world_router, prefix="/api")
app.include_router(characters_router, prefix="/api")
app.include_router(volumes_router, prefix="/api")
app.include_router(chapters_router, prefix="/api")
app.include_router(truth_router, prefix="/api")
app.include_router(export_router, prefix="/api")
app.include_router(providers_router, prefix="/api")
app.include_router(daemon_router, prefix="/api")
app.include_router(events_router, prefix="/api")
