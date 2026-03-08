"""
이미지 편집 API용 Pydantic 스키마. Java BE ↔ FastAPI /internal/ai/edit-image 요청·응답 형식.

- 연계: routers/ai.edit_image, services/image_edit_service에서 사용.
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

_CAMEL = ConfigDict(populate_by_name=True, alias_generator=to_camel, serialize_by_alias=True)


class InternalImageEditRequest(BaseModel):
    """이미지 편집 요청. base64 이미지와 편집 지시 프롬프트."""

    model_config = _CAMEL

    image_base64: str
    prompt: str


class InternalImageEditResponse(BaseModel):
    """이미지 편집 응답. AI 코멘트 텍스트와 GCS에 저장된 결과 이미지 URL."""

    model_config = _CAMEL

    text: str
    image_url: Optional[str] = None
