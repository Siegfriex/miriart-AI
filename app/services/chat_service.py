"""
AI 멘토 채팅 서비스. Gemini로 대화 생성. 기본 퀵리플라이 3개 반환.

- 연계: routers/ai.chat → chat; Java AiProxyService가 /internal/ai/chat 호출, Redis에 히스토리 저장.
- sticky_context(등급·점수·fix_scope·대학예측·코멘트·목표)로 시스템 프롬프트에 반영.
"""
import base64
import logging
from typing import List, Optional

from google.genai import types as genai_types

from app.core.gemini_client import call_gemini, GeminiModel
from app.core.exceptions import ValidationError
from app.schemas.chat import HistoryItem, InternalChatRequest, InternalChatResponse

logger = logging.getLogger(__name__)

_MAX_HISTORY_TURNS = 8
_CHAT_MAX_OUTPUT_TOKENS = 4096

MODEL_MAP = {
    "CHAT_PRO": GeminiModel.PRO,
    "FAST": GeminiModel.FLASH,
    "THINKING": GeminiModel.PRO,
    "SEARCH": GeminiModel.FLASH,
    "IMAGE_EDIT": GeminiModel.FLASH,
}

CHAT_SYSTEM_PROMPT = """당신은 MiriArt의 미술 입시 AI 멘토입니다.
학생의 미술 작품 분석 결과와 맥락을 바탕으로 친절하고 전문적인 상담을 제공합니다.

규칙:
1. 미술 전문 용어를 사용하되, 고등학생이 이해할 수 있게 설명하세요.
2. 구체적이고 실천 가능한 조언을 제공하세요.
3. 학생의 현재 수준(grade, fixScope)을 고려한 맞춤 조언을 하세요.
4. 격려와 동기부여를 포함하되, 현실적인 피드백도 함께 제공하세요.
5. 충분한 깊이로 답변하되, 핵심을 놓치지 마세요."""


def _get_effective_history(history: Optional[List[HistoryItem]]) -> List[HistoryItem]:
    """최근 N턴만 사용하여 컨텍스트 윈도우 절약."""
    if not history:
        return []
    return history[-_MAX_HISTORY_TURNS:]


def _build_system_prompt(req: InternalChatRequest) -> str:
    """sticky_context 기반으로 시스템 프롬프트를 구성."""
    system = CHAT_SYSTEM_PROMPT
    ctx = req.sticky_context
    if not ctx:
        return system

    system += f"\n\n학생 분석 요약: 등급={ctx.grade}, 점수={ctx.score}, fixScope={ctx.fix_scope}."
    if ctx.radar_data:
        system += f" 레이더 지표={ctx.radar_data}."
    if ctx.university_predictions:
        ups = ", ".join(
            f"{u.name}({u.type},{u.probability:.0%})"
            for u in ctx.university_predictions
        )
        system += f" 추천 대학군={ups}."
    if ctx.analysis_comment:
        system += f" 분석 코멘트: {ctx.analysis_comment}"
    if ctx.target_major:
        system += f" 목표 전공={ctx.target_major}."
    if ctx.target_university:
        system += f" 목표 대학={ctx.target_university}."
    return system


def _flatten_history(history: Optional[list]) -> str:
    """히스토리를 [role]: text 형식의 단일 텍스트로 변환."""
    if not history:
        return ""
    lines = []
    for h in history:
        role = getattr(h, "role", None) or (h.get("role", "user") if isinstance(h, dict) else "user")
        parts = getattr(h, "parts", None) or (h.get("parts", []) if isinstance(h, dict) else [])
        text = ""
        if parts and isinstance(parts, list) and len(parts) > 0:
            first = parts[0]
            text = first.get("text", "") if isinstance(first, dict) else getattr(first, "text", "")
        elif isinstance(h, dict):
            text = h.get("text", "")
        lines.append(f"[{role}]: {text}")
    return "\n".join(lines)


async def chat(req: InternalChatRequest) -> InternalChatResponse:
    """MODEL_MAP으로 모델 선택 → sticky_context 반영 → 히스토리 슬라이싱 → call_gemini → 퀵리플라이 반환."""
    model_name = MODEL_MAP.get(req.model_type, GeminiModel.FLASH)
    system = _build_system_prompt(req)

    effective_history = _get_effective_history(req.history)
    raw_history_len = len(req.history) if req.history else 0

    logger.info(
        "chat_request",
        extra={
            "session_id": req.session_id,
            "model_type": req.model_type,
            "history_len": len(effective_history),
            "history_len_raw": raw_history_len,
            "sticky_context_present": req.sticky_context is not None,
            "has_image": req.image_base64 is not None,
        },
    )

    history_text = _flatten_history(effective_history)
    messages = f"{history_text}\n[user]: {req.message}\n" if history_text else f"[user]: {req.message}\n"

    if req.image_base64:
        try:
            image_bytes = base64.b64decode(req.image_base64)
        except Exception as e:
            raise ValidationError(f"imageBase64 디코딩 실패: {e}")
        mime = req.image_mime_type or "image/jpeg"
        contents = [
            genai_types.Part.from_text(text=messages),
            genai_types.Part.from_bytes(data=image_bytes, mime_type=mime),
        ]
    else:
        contents = messages

    raw = await call_gemini(
        model=model_name,
        contents=contents,
        system_instruction=system,
        purpose="chat",
        temperature=0.7,
        max_output_tokens=_CHAT_MAX_OUTPUT_TOKENS,
    )

    return InternalChatResponse(
        text=raw.strip(),
        grounding_urls=[],
        quick_replies=[
            "이 부분을 더 자세히 알려주세요",
            "연습 방법을 추천해주세요",
            "비슷한 대학은 어디가 있나요?",
        ],
    )
