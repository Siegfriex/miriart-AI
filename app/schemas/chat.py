"""
AI 채팅 API용 Pydantic 스키마. Java BE ↔ FastAPI /internal/ai/chat 요청·응답 형식.

- 연계: routers/ai.chat, services/chat_service에서 사용. Java AiProxyService가 Redis 히스토리와 함께 전달.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

_CAMEL = ConfigDict(populate_by_name=True, alias_generator=to_camel, serialize_by_alias=True)


class HistoryItem(BaseModel):
    """대화 히스토리 한 건. Vertex AI Content와 대응, role + parts(텍스트)."""

    model_config = _CAMEL

    role: str  # "user" | "model"
    parts: List[Dict[str, Any]]  # [{"text": "..."}]


class StickyContext(BaseModel):
    """채팅 세션에 고정되는 맥락(작품 등급·점수·fix_scope). 시스템 프롬프트 분기용."""

    model_config = _CAMEL

    grade: str
    score: float
    fix_scope: str  # StructureRebuild | DetailTuning
    radar_data: Optional[Dict[str, float]] = None


class InternalChatRequest(BaseModel):
    """채팅 요청. Java AiChatController에서 세션 ID·히스토리·스티키 컨텍스트·메시지(이미지可选) 전달."""

    model_config = _CAMEL

    model_type: str  # CHAT_PRO | FAST | THINKING | SEARCH | IMAGE_EDIT
    message: str
    session_id: Optional[str] = None
    sticky_context: Optional[StickyContext] = None
    image_base64: Optional[str] = None
    image_mime_type: Optional[str] = None
    history: Optional[List[HistoryItem]] = []


class InternalChatResponse(BaseModel):
    """채팅 응답. AI 멘토 텍스트·grounding URL·퀵리플라이. Java에서 FE로 그대로 전달."""

    model_config = _CAMEL

    text: str
    grounding_urls: List[str] = []
    quick_replies: List[str] = []
