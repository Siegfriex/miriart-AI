"""
이미지 편집 서비스. Gemini Flash로 이미지+프롬프트 기반 편집 후 GCS 업로드.

- 연계: routers/ai.edit_image → edit_image; GcsService.upload_bytes로 결과 저장.
- Java BE에서 이미지 편집 API 호출 시 /internal/ai/edit-image 사용.
"""
import asyncio
import base64
import uuid
import logging

from google.genai import types as genai_types

from app.core.config import get_settings
from app.core.exceptions import GCSError, ValidationError
from app.core.gemini_client import call_gemini, GeminiModel
from app.schemas.image_edit import InternalImageEditRequest, InternalImageEditResponse
from app.services.gcs_service import GcsService

logger = logging.getLogger(__name__)

_settings = get_settings()
gcs = GcsService(bucket_name=_settings.gcs_bucket_name, project_id=_settings.gcp_project_id)


async def edit_image(request: InternalImageEditRequest) -> InternalImageEditResponse:
    """base64 이미지와 프롬프트로 Gemini Flash 호출 → 편집 결과 이미지 GCS edited/ 경로에 업로드 → 공개 URL 반환."""
    try:
        image_bytes = base64.b64decode(request.image_base64)
    except Exception as e:
        raise ValidationError(f"base64 디코딩 실패: {e}")

    contents = [
        genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
        genai_types.Part.from_text(request.prompt),
    ]

    response = await call_gemini(
        model=GeminiModel.FLASH,
        contents=contents,
        purpose="image_edit",
        temperature=0.4,
        max_output_tokens=2048,
        timeout_override_s=55,
        return_response=True,
    )

    response_text = ""
    edited_image_bytes: bytes | None = None
    edited_mime = "image/jpeg"

    if hasattr(response, "candidates") and response.candidates:
        content = response.candidates[0].content
        parts = getattr(content, "parts", []) if content else []
        for part in parts:
            if hasattr(part, "text") and part.text:
                response_text = part.text
            elif hasattr(part, "inline_data") and part.inline_data:
                edited_image_bytes = part.inline_data.data
                edited_mime = getattr(part.inline_data, "mime_type", None) or "image/jpeg"

    image_url: str | None = None
    if edited_image_bytes:
        blob_path = f"edited/{uuid.uuid4()}.jpg"
        try:
            image_url = await asyncio.to_thread(
                gcs.upload_bytes, blob_path, edited_image_bytes, edited_mime
            )
        except Exception as e:
            raise GCSError(f"GCS 업로드 실패: {e}")

    if not response_text:
        response_text = "이미지 편집이 완료됐습니다."

    return InternalImageEditResponse(
        text=response_text,
        image_url=image_url,
    )
