"""
Request ID 및 HTTP 요청 구조화 로깅 미들웨어.

- X-Request-ID: 있으면 사용, 없으면 12자 UUID 생성 → request.state.request_id
- /health, /internal/ai/health 는 로깅 제외
- 그 외: method, path, status, latency_s, request_id JSON 로그 + 응답 헤더에 X-Request-ID
"""
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """요청별 request_id 부여 및 구조화 로깅."""

    EXCLUDE_PATHS = {"/health", "/internal/ai/health"}

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:12]
        request.state.request_id = request_id

        if request.url.path in self.EXCLUDE_PATHS:
            return await call_next(request)

        start = time.monotonic()
        response = await call_next(request)
        latency = round(time.monotonic() - start, 3)

        logger.info(
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_s": latency,
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response
