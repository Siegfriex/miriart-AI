"""
C4 AI QA 서비스. summarize-answers, draft-from-question.

- Dev Spec G1/G2 프롬프트 사용.
"""
import base64
import json
import logging
from typing import Optional

from google.genai import types as genai_types

from app.core.exceptions import LLMParsingError, ValidationError
from app.core.gemini_client import call_gemini, GeminiModel

logger = logging.getLogger(__name__)

SUMMARIZE_SYSTEM_PROMPT = """당신은 미술 입시 전문 AI 조교입니다.
커뮤니티 QA 게시판에서 질문에 달린 답변들을 요약합니다.

규칙:
1. 핵심 의견을 3줄 이내로 요약하세요 (summary).
2. 답변들에서 공통적으로 언급하지 않았지만, 질문자에게 도움이 될 추가 조언이 있다면
   1~2줄로 작성하세요 (supplement).
3. 미술 용어는 정확하게 사용하되, 고등학생도 이해할 수 있는 수준으로 설명하세요.
4. 반드시 JSON 형식으로 응답하세요."""

SUMMARIZE_USER_TEMPLATE = """질문: {question}

답변 목록:
{answers_text}

위 답변들을 요약하고, 추가 조언이 있다면 작성해주세요.
응답 형식:
{{"summary": "...", "supplement": "..."}}"""

DRAFT_SYSTEM_PROMPT = """당신은 미술 입시 전문 AI 조교입니다.
커뮤니티에 올라온 질문을 보고, 도움이 되는 답변 초안을 작성합니다.

규칙:
1. 질문의 맥락(학년, 전공 분야 등)을 고려하세요.
2. 구체적이고 실천 가능한 조언을 포함하세요.
3. 미술 전문 용어를 사용하되 고등학생 수준에 맞게 설명하세요.
4. 200자 이내로 간결하게 작성하세요.
5. 이미지가 첨부된 경우, 이미지 내용도 참고하여 조언하세요.
6. 반드시 JSON 형식으로 응답하세요."""

DRAFT_USER_TEMPLATE = """제목: {title}
내용: {content}

위 질문에 대한 답변 초안을 작성해주세요.
응답 형식:
{{"draft": "..."}}"""


async def summarize_answers(question: str, answers: list[str]) -> dict:
    """답변 목록을 요약해 summary, supplement 반환."""
    answers_text = "\n".join(f"[답변 {i+1}] {a}" for i, a in enumerate(answers))
    user_prompt = SUMMARIZE_USER_TEMPLATE.format(
        question=question,
        answers_text=answers_text,
    )
    raw = await call_gemini(
        model=GeminiModel.FLASH,
        contents=user_prompt,
        system_instruction=SUMMARIZE_SYSTEM_PROMPT,
        purpose="summarize_answers",
        temperature=0.3,
        max_output_tokens=1024,
        response_mime_type="application/json",
    )
    try:
        result = json.loads(raw)
        return {"summary": result.get("summary", ""), "supplement": result.get("supplement", "")}
    except json.JSONDecodeError:
        raise LLMParsingError(f"Failed to parse summarize response: {raw[:200]}")


async def draft_from_question(
    title: str,
    content: str,
    image_base64: Optional[str] = None,
) -> dict:
    """질문 제목·내용(및 선택적 이미지)으로 답변 초안 생성."""
    user_prompt = DRAFT_USER_TEMPLATE.format(title=title, content=content)
    if image_base64:
        try:
            decoded = base64.b64decode(image_base64)
        except Exception as e:
            raise ValidationError(f"imageBase64 디코딩 실패: {e}")
        contents = [
            genai_types.Part.from_text(text=user_prompt),
            genai_types.Part.from_bytes(
                data=decoded,
                mime_type="image/jpeg",
            ),
        ]
    else:
        contents = user_prompt

    raw = await call_gemini(
        model=GeminiModel.FLASH,
        contents=contents,
        system_instruction=DRAFT_SYSTEM_PROMPT,
        purpose="draft_from_question",
        temperature=0.5,
        max_output_tokens=1024,
        response_mime_type="application/json",
    )
    try:
        result = json.loads(raw)
        return {"draft": result.get("draft", "")}
    except json.JSONDecodeError:
        raise LLMParsingError(f"Failed to parse draft response: {raw[:200]}")
