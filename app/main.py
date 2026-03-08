"""
MiriArt AI 서비스 FastAPI 애플리케이션 진입점.

- 연계: Java 백엔드(Spring Boot)가 WebClient로 /internal/ai/* 엔드포인트만 호출. FE 직접 접근 불가.
- lifespan에서 Vertex AI 초기화 후 ai 라우터를 /internal/ai 접두사로 마운트.
- /health: 헬스체크용 (배포/로드밸런서 검사).
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.gemini_client import init_vertex_ai
from app.routers import ai


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 수명 주기: 시작 시 Vertex AI 초기화, 실패 시 경고만 남기고 로컬 개발 모드로 계속 실행."""
    try:
        init_vertex_ai()
    except Exception as e:
        logging.warning(f"Vertex AI 초기화 실패 (로컬 개발 모드로 실행): {e}")
    yield


app = FastAPI(
    title="MiriArt AI Service",
    version="1.0.0",
    description="MiriArt 내부 AI 서비스 (Java BE → FastAPI). FE 직접 접근 불가.",
    lifespan=lifespan,
)

app.include_router(ai.router, prefix="/internal/ai", tags=["AI Internal"])


@app.get("/health")
def health():
    """헬스체크. Cloud Run/로드밸런서에서 서비스 가동 여부 확인용."""
    return {"status": "ok"}
