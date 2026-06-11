from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ApiError(Exception):
    """API-layer error converted to the shared response envelope."""

    status: int
    code: str
    message: str


def book_not_found(book_id: str) -> ApiError:
    return ApiError(status=404, code="BOOK_NOT_FOUND", message=f"Book not found: {book_id}")


def chapter_not_found(book_id: str, chapter_no: int) -> ApiError:
    return ApiError(
        status=404,
        code="CHAPTER_NOT_FOUND",
        message=f"Chapter not found: {book_id}#{chapter_no}",
    )


def chapter_empty(message: str = "空章节请先使用 draft 管线生成正文") -> ApiError:
    return ApiError(status=409, code="CHAPTER_EMPTY", message=message)


def content_conflict(message: str = "章节内容已被修改，请刷新后重试") -> ApiError:
    return ApiError(status=409, code="CONTENT_CONFLICT", message=message)


def invalid_parameter(message: str) -> ApiError:
    return ApiError(status=400, code="INVALID_PARAMETER", message=message)


def state_conflict(message: str) -> ApiError:
    return ApiError(status=409, code="STATE_CONFLICT", message=message)


def state_error(message: str) -> ApiError:
    return ApiError(status=409, code="STATE_ERROR", message=message)


def internal_error(message: str) -> ApiError:
    return ApiError(status=500, code="INTERNAL_ERROR", message=message)


def not_found(message: str) -> ApiError:
    return ApiError(status=404, code="NOT_FOUND", message=message)
