"""
FastAPI 전역 예외 핸들러 등록. API_CONTRACT 9 / Dev Spec C2.

- MiriArtAIError → 클래스별 HTTP status + code/message JSON
- RequestValidationError → 400, VALIDATION_ERROR, errors
- Exception → 500, INTERNAL_ERROR
- 모든 핸들러에서 구조화 로그 (handled_error, request_validation_error, unhandled_exception)
"""
import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    GCSError,
    LLMParsingError,
    LLMRateLimitError,
    LLMServiceError,
    LLMTimeoutError,
    MiriArtAIError,
    ValidationError,
)

logger = logging.getLogger(__name__)

ERROR_MAP = {
    LLMTimeoutError: (504, "LLM_TIMEOUT"),
    LLMRateLimitError: (429, "LLM_RATE_LIMITED"),
    LLMServiceError: (502, "LLM_SERVICE_ERROR"),
    LLMParsingError: (502, "LLM_PARSING_ERROR"),
    GCSError: (502, "GCS_ERROR"),
    ValidationError: (400, "VALIDATION_ERROR"),
}


def register_exception_handlers(app: FastAPI) -> None:
    """앱에 전역 예외 핸들러 등록."""

    @app.exception_handler(MiriArtAIError)
    async def miriart_error_handler(request: Request, exc: MiriArtAIError):
        status, code = ERROR_MAP.get(type(exc), (500, exc.error_code))
        logger.warning(
            "handled_error",
            extra={
                "path": request.url.path,
                "method": request.method,
                "error_code": code,
                "status": status,
                "detail": exc.message,
            },
        )
        return JSONResponse(
            status_code=status,
            content={"code": code, "message": exc.message},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        logger.warning(
            "request_validation_error",
            extra={
                "path": request.url.path,
                "errors": str(errors)[:500],
            },
        )
        return JSONResponse(
            status_code=400,
            content={
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "errors": [
                    {
                        "field": e.get("loc", [])[-1] if e.get("loc") else "unknown",
                        "message": e.get("msg", ""),
                    }
                    for e in errors
                ],
            },
        )

    @app.exception_handler(Exception)
    async def catch_all_handler(request: Request, exc: Exception):
        logger.error(
            "unhandled_exception",
            extra={
                "path": request.url.path,
                "method": request.method,
                "error": str(exc),
                "traceback": traceback.format_exc()[:2000],
            },
        )
        return JSONResponse(
            status_code=500,
            content={"code": "INTERNAL_ERROR", "message": "Internal server error"},
        )
