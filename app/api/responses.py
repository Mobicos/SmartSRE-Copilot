"""API response helpers."""

from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def json_response(*, status_code: int, content: Any) -> JSONResponse:
    """Return a JSON response after converting values such as datetime."""
    return JSONResponse(status_code=status_code, content=jsonable_encoder(content))
