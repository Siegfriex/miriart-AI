"""
MiriArt AI 서비스 FastAPI 애플리케이션 진입점.

- 연계: Java 백엔드(Spring Boot)가 WebClient로 /internal/ai/* 엔드포인트만 호출. FE 직접 접근 불가.
- lifespan: setup_logging, GenAI client warm up.
- /health: 헬스체크용 (배포/로드밸런서 검사).
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.gemini_client import get_genai_client
from app.core.logging_config import setup_logging
from app.core.error_handler import register_exception_handlers
from app.middleware.request_context import RequestContextMiddleware
from app.routers import ai

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 수명 주기: 로깅 설정, GenAI client warm up."""
    setup_logging()
    logger.info("miriart-ai starting up")
    get_genai_client()
    logger.info("GenAI client warmed up")
    yield
    logger.info("miriart-ai shutting down")


app = FastAPI(
    title="MiriArt AI Service",
    version="1.0.0",
    description="MiriArt 내부 AI 서비스 (Java BE → FastAPI). FE 직접 접근 불가.",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)
app.include_router(ai.router, prefix="/internal/ai", tags=["AI Internal"])


@app.get("/health")
async def health():
    """헬스체크. Cloud Run/로드밸런서에서 서비스 가동 여부 확인용."""
    return {"status": "ok"}
