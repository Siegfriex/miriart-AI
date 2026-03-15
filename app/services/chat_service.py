"""
AI 멘토 채팅 서비스. Gemini로 대화 생성. 기본 퀵리플라이 3개 반환.

- 연계: routers/ai.chat → chat; Java AiProxyService가 /internal/ai/chat 호출, Redis에 히스토리 저장.
- sticky_context(등급·점수·fix_scope·대학예측·코멘트·목표)로 시스템 프롬프트에 반영.
"""
import base64
import json as _json
import logging
import re
from typing import List, Optional

from google.genai import types as genai_types
from pydantic import BaseModel, ValidationError as PydanticValidationError

from app.core.gemini_client import call_gemini, GeminiModel
from app.core.exceptions import ValidationError
from app.schemas.chat import ChatSection, HistoryItem, InternalChatRequest, InternalChatResponse

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

_DEFAULT_QUICK_REPLIES = ["구도 분석 요청", "색감 피드백", "합격 확률 보기"]
_FALLBACK_TEXT = "(응답을 구조화하지 못했습니다. 내용을 다시 확인해 주세요.)"


# ── response_schema용 내부 Pydantic 모델 (SDK가 JSON Schema로 변환) ──
class _SectionSchema(BaseModel):
    type: str
    title: str
    text: str


class _ChatResponseSchema(BaseModel):
    summary: str
    sections: List[_SectionSchema]


CHAT_SYSTEM_PROMPT = """당신은 MiriArt의 미술 입시 AI 멘토입니다.
학생의 미술 작품 분석 결과와 맥락을 바탕으로 실질적인 피드백을 제공합니다.

[응답 형식 — 반드시 아래 JSON만 출력하세요. 코드블록 없이 순수 JSON만.]
{
  "summary": "이번 피드백의 핵심 한 줄 (50자 이내)",
  "sections": [
    { "type": "strength",    "title": "잘하고 있는 것",        "text": "구체적 근거와 함께 격려. 3~5문장." },
    { "type": "improvement", "title": "지금 당장 바꿔야 할 것", "text": "포장 없이 직설적으로. 문제→이유→영향 순서. 3~5문장." },
    { "type": "action",      "title": "다음 2주 실천 전략",     "text": "번호 매긴 구체 행동 2~3개. 동사로 시작. 3~5문장." }
  ]
}

[톤 규칙]
- strength: 격려하되 근거를 반드시 포함. '잘했어요'로만 끝내지 말 것.
- improvement: 단호하게. '~인 것 같아요' 표현 금지. 문제를 직접 명시.
- action: 오늘 당장 실행 가능한 수준으로. 추상적 조언 금지.
- 전체: 고등학생이 이해할 수 있는 미술 전문 용어. 총 1,200자 이내.
- JSON 외 다른 텍스트(코드블록 포함) 절대 출력 금지."""


def _get_effective_history(history: Optional[List[HistoryItem]]) -> List[HistoryItem]:
    """최근 N턴만 사용하여 컨텍스트 윈도우 절약."""
    if not history:
        return []
    return history[-_MAX_HISTORY_TURNS:]


_SUMMARY_TEXT_MAX_LEN = 500


def _build_system_prompt(req: InternalChatRequest) -> str:
    """sticky_context 기반으로 시스템 프롬프트를 구성.

    - summary_text가 있으면 학생 분석 카드 전체를 한 덩어리로 사용 (개별 필드 중복 최소화).
    - summary_text가 없으면 기존 grade/score/fixScope/대학예측/코멘트/목표를 개별 조합.

    예시 (a) summary_text 있음:
        ...시스템 프롬프트 기본...

        학생 분석 요약:
        B등급(72.5점) · 구조 재구성 필요 · 구도 3.2 / 색채 4.1 / ...
        추천 대학: 홍익대(상향,68%) · 국민대(적정,82%) ...
        목표: 시각디자인 / 홍익대

    예시 (b) summary_text 없음 (기존 방식):
        ...시스템 프롬프트 기본...

        학생 분석 요약: 등급=B, 점수=72.5, fixScope=StructureRebuild.
        레이더 지표={...}. 추천 대학군=홍익대(TOP,68%), ...
        분석 코멘트: ... 목표 전공=시각디자인. 목표 대학=홍익대.
    """
    system = CHAT_SYSTEM_PROMPT
    ctx = req.sticky_context
    if not ctx:
        return system

    # (a) summary_text가 존재하면 한 덩어리 텍스트 사용
    if ctx.summary_text:
        summary = ctx.summary_text.strip()
        if len(summary) > _SUMMARY_TEXT_MAX_LEN:
            summary = summary[:_SUMMARY_TEXT_MAX_LEN] + "…(이하 생략)"
            logger.warning("summary_text truncated: original length=%d", len(ctx.summary_text))
        system += f"\n\n학생 분석 요약:\n{summary}"
        # summary_text에 포함되지 않았을 수 있는 목표 정보만 보충
        if ctx.target_major and ctx.target_major not in summary:
            system += f"\n목표 전공={ctx.target_major}."
        if ctx.target_university and ctx.target_university not in summary:
            system += f"\n목표 대학={ctx.target_university}."
        return system

    # (b) summary_text 없음 → 개별 필드 조합 (기존 로직)
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
        response_mime_type="application/json",
        response_schema=_ChatResponseSchema,
    )

    # ── JSON 전처리: 간헐적 마크다운 래핑 방어 ──
    cleaned = re.sub(r"^\s*```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```\s*$", "", cleaned).strip()

    # ── 구조화 파싱 시도 ──
    try:
        parsed = _json.loads(cleaned)
        raw_sections = parsed.get("sections") or []

        if not raw_sections:
            raise ValueError("empty_sections")

        sections = [
            ChatSection(type=s["type"], title=s.get("title", ""), text=s.get("text", ""))
            for s in raw_sections
        ]
        summary = parsed.get("summary", "")

        # 하위 호환 text: [제목]\n본문 join (Redis 저장·히스토리 재로드 호환)
        fallback_text = "\n\n".join(f"[{s.title}]\n{s.text}" for s in sections)

        logger.info(
            "chat_response_format",
            extra={
                "response_format": "structured",
                "sections_count": len(sections),
                "session_id": req.session_id,
            },
        )
        return InternalChatResponse(
            text=fallback_text,
            summary=summary,
            sections=sections,
            grounding_urls=[],
            quick_replies=_DEFAULT_QUICK_REPLIES,
        )

    except (_json.JSONDecodeError, KeyError, PydanticValidationError, ValueError) as e:
        reason = (
            "empty_sections" if isinstance(e, ValueError)
            else "validation_error" if isinstance(e, PydanticValidationError)
            else "json_parse_error"
        )
        logger.warning(
            "chat_response_format",
            extra={
                "response_format": "fallback",
                "reason": reason,
                "session_id": req.session_id,
            },
        )
        text_out = raw.strip() or _FALLBACK_TEXT
        return InternalChatResponse(
            text=text_out,
            summary=None,
            sections=None,
            grounding_urls=[],
            quick_replies=_DEFAULT_QUICK_REPLIES,
        )
