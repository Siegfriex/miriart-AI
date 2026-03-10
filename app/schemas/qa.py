"""
C4 AI QA API용 Pydantic 스키마. summarize-answers, draft-from-question 요청·응답.

- camelCase 직렬화 (Java BE 연동).
"""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

_CAMEL = ConfigDict(populate_by_name=True, alias_generator=to_camel, serialize_by_alias=True)


class SummarizeAnswersRequest(BaseModel):
    """Q&A 답변 요약 요청."""

    model_config = _CAMEL

    question: str = Field(..., min_length=1, max_length=2000)
    answers: List[str] = Field(..., min_length=1, max_length=20)


class SummarizeAnswersResponse(BaseModel):
    """Q&A 답변 요약 응답."""

    model_config = _CAMEL

    summary: str
    supplement: str


class DraftFromQuestionRequest(BaseModel):
    """질문 초안 생성 요청."""

    model_config = _CAMEL

    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=5000)
    image_base64: Optional[str] = Field(None, alias="imageBase64")


class DraftFromQuestionResponse(BaseModel):
    """질문 초안 생성 응답."""

    model_config = _CAMEL

    draft: str
