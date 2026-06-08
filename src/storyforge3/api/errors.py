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


def invalid_parameter(message: str) -> ApiError:
    return ApiError(status=400, code="INVALID_PARAMETER", message=message)


def state_conflict(message: str) -> ApiError:
    return ApiError(status=409, code="STATE_CONFLICT", message=message)


def state_error(message: str) -> ApiError:
    return ApiError(status=409, code="STATE_ERROR", message=message)


def internal_error(message: str) -> ApiError:
    return ApiError(status=500, code="INTERNAL_ERROR", message=message)
