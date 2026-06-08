from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

from storyforge3.api.errors import ApiError


class ErrorDetail(BaseModel):
    code: str
    message: str


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    ok: bool
    data: T | None = None
    error: ErrorDetail | None = None


def ok(data: T) -> ApiResponse[T]:
    return ApiResponse[T](ok=True, data=data, error=None)


def err(error: ApiError) -> ApiResponse[None]:
    return ApiResponse[None](
        ok=False,
        data=None,
        error=ErrorDetail(code=error.code, message=error.message),
    )
