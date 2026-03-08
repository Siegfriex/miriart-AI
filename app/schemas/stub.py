"""
Phase C4 미구현 스텁 API용 스키마. summarize-answers, draft-from-question 엔드포인트 요청·응답 형식.

- 연계: routers/ai에서 501 스텁으로 사용. Java BE 호출 시 Phase C4 구현 후 연동 예정.
"""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

_CAMEL = ConfigDict(populate_by_name=True, alias_generator=to_camel, serialize_by_alias=True)


class SummarizeRequest(BaseModel):
    """Q&A 답변 요약 요청. 질문과 답변 목록."""

    model_config = _CAMEL

    question: str
    answers: List[str]


class SummarizeResponse(BaseModel):
    """Q&A 답변 요약 응답. 3줄 요약과 보충 설명."""

    model_config = _CAMEL

    summary: str    # 3줄 요약
    supplement: str  # 추가 보충 설명


class DraftRequest(BaseModel):
    """질문 초안 생성 요청. 제목·내용·이미지(선택)."""

    model_config = _CAMEL

    title: str
    content: str
    image_base64: Optional[str] = None


class DraftResponse(BaseModel):
    """질문 초안 생성 응답. AI가 생성한 초안 답변 텍스트."""

    model_config = _CAMEL

    draft: str  # AI 초안 답변
