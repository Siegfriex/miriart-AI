"""
AI 멘토 채팅 서비스. Gemini로 대화 생성. 기본 퀵리플라이 3개 반환.

- 연계: routers/ai.chat → chat; Java AiProxyService가 /internal/ai/chat 호출, Redis에 히스토리 저장.
- sticky_context(등급·점수·fix_scope)로 시스템 프롬프트에 반영.
"""
import base64
import logging
from typing import Optional

from google.genai import types as genai_types

from app.core.gemini_client import call_gemini, GeminiModel
from app.core.exceptions import ValidationError
from app.schemas.chat import InternalChatRequest, InternalChatResponse

logger = logging.getLogger(__name__)

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
5. 200자 이내로 간결하게 답변하세요."""


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
    """MODEL_MAP으로 모델 선택 → sticky_context 반영 → 히스토리+메시지(이미지 선택) → call_gemini → 고정 퀵리플라이 반환."""
    model_name = MODEL_MAP.get(req.model_type, GeminiModel.FLASH)

    system = CHAT_SYSTEM_PROMPT
    if req.sticky_context:
        ctx = req.sticky_context
        system += f"\n\n학생 분석 결과: grade={ctx.grade}, score={ctx.score}, fixScope={ctx.fix_scope}"

    history_text = _flatten_history(req.history)
    messages = f"{history_text}\n[user]: {req.message}\n" if history_text else f"[user]: {req.message}\n"

    if req.image_base64:
        try:
            image_bytes = base64.b64decode(req.image_base64)
        except Exception as e:
            raise ValidationError(f"imageBase64 디코딩 실패: {e}")
        mime = req.image_mime_type or "image/jpeg"
        contents = [
            genai_types.Part.from_text(messages),
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
        max_output_tokens=1024,
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
