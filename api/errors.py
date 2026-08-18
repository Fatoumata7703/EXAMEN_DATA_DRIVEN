from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: Any = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


def error_response(request: Request, status_code: int, code: str, message: str, details: Any = None):
    body: dict[str, Any] = {
        "request_id": getattr(request.state, "request_id", "unknown"),
        "error": {"code": code, "message": message},
    }
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)

