"""
Java 백엔드 전용 내부 AI API 라우터. prefix /internal/ai 로 마운트됨.

- 연계: Java BE의 WebClient가 /internal/ai/analyze, /chat, /edit-image, /summarize-answers, /draft-from-question 호출.
"""
import logging

from fastapi import APIRouter

from app.schemas.analyze import InternalAnalyzeRequest, InternalAnalyzeResponse
from app.schemas.chat import InternalChatRequest, InternalChatResponse
from app.schemas.image_edit import InternalImageEditRequest, InternalImageEditResponse
from app.schemas.qa import (
    DraftFromQuestionRequest,
    DraftFromQuestionResponse,
    SummarizeAnswersRequest,
    SummarizeAnswersResponse,
)
from app.services import analyze_service, chat_service, image_edit_service, qa_service

router = APIRouter()


@router.get("/status", summary="AI 서비스 상태")
async def status():
    """GenAI client 초기화 여부 + 설정값 리포트. 배포 직후 정합성 확인용."""
    from app.core.gemini_client import (
        _client, GeminiModel,
        GEMINI_TIMEOUT_S, GEMINI_RETRY_ATTEMPTS, GEMINI_IMAGE_EDIT_TIMEOUT_S,
    )
    from app.core.config import get_settings
    s = get_settings()
    return {
        "genai_initialized": _client is not None,
        "project": s.gcp_project_id,
        "region": s.gcp_region,
        "gemini_location": s.gemini_location,
        "models": {
            "flash": GeminiModel.FLASH,
            "pro": GeminiModel.PRO,
            "flash_lite": GeminiModel.FLASH_LITE,
        },
        "timeout_s": GEMINI_TIMEOUT_S,
        "retry_attempts": GEMINI_RETRY_ATTEMPTS,
        "image_edit_timeout_s": GEMINI_IMAGE_EDIT_TIMEOUT_S,
    }


@router.post(
    "/analyze",
    response_model=InternalAnalyzeResponse,
    summary="작품 분석",
    description="GCS URI의 이미지를 Gemini Vision으로 분석하여 5축 채점 결과를 반환한다.",
)
async def analyze(request: InternalAnalyzeRequest) -> InternalAnalyzeResponse:
    """GCS URI 이미지를 Gemini Vision으로 5축 분석."""
    return await analyze_service.analyze_artwork(request)


@router.post(
    "/chat",
    response_model=InternalChatResponse,
    summary="AI 채팅",
    description="모델 타입과 채팅 히스토리를 기반으로 AI 멘토 응답을 생성한다.",
)
async def chat(request: InternalChatRequest) -> InternalChatResponse:
    """채팅 히스토리 기반 AI 멘토 응답 생성."""
    return await chat_service.chat(request)


@router.post(
    "/edit-image",
    response_model=InternalImageEditResponse,
    summary="이미지 편집",
    description="base64 이미지와 프롬프트로 Gemini 이미지 편집을 수행하고 GCS URL을 반환한다.",
)
async def edit_image(request: InternalImageEditRequest) -> InternalImageEditResponse:
    """base64 이미지+프롬프트로 Gemini 이미지 편집 후 GCS URL 반환."""
    return await image_edit_service.edit_image(request)


@router.post(
    "/summarize-answers",
    response_model=SummarizeAnswersResponse,
    summary="Q&A 답변 요약",
    description="Q&A 답변들을 요약하여 summary와 supplement를 반환한다.",
)
async def api_summarize_answers(request: SummarizeAnswersRequest) -> SummarizeAnswersResponse:
    """Q&A 답변 요약 (C4 AI QA)."""
    result = await qa_service.summarize_answers(question=request.question, answers=request.answers)
    return SummarizeAnswersResponse(**result)


@router.post(
    "/draft-from-question",
    response_model=DraftFromQuestionResponse,
    summary="질문 초안 생성",
    description="질문 제목·내용(및 이미지)을 기반으로 AI 답변 초안을 생성한다.",
)
async def api_draft_from_question(request: DraftFromQuestionRequest) -> DraftFromQuestionResponse:
    """질문 기반 AI 초안 생성 (C4 AI QA)."""
    result = await qa_service.draft_from_question(
        title=request.title,
        content=request.content,
        image_base64=request.image_base64,
    )
    return DraftFromQuestionResponse(**result)
