"""
이미지 편집 서비스. Gemini 2.0 Flash로 이미지+프롬프트 기반 편집 후 GCS 업로드.

- 연계: routers/ai.edit_image → 이 모듈 edit_image; gemini_client.upload_to_gcs로 결과 저장.
- Java BE에서 이미지 편집 API 호출 시 /internal/ai/edit-image 사용.
"""
import asyncio
import base64
import uuid

from fastapi import HTTPException

from app.core.config import get_settings
from app.core.gemini_client import get_generative_model, upload_to_gcs
from app.schemas.image_edit import InternalImageEditRequest, InternalImageEditResponse


async def edit_image(request: InternalImageEditRequest) -> InternalImageEditResponse:
    """base64 이미지와 프롬프트로 Gemini 2.0 Flash 호출 → 편집 결과 이미지 GCS edited/ 경로에 업로드 → 공개 URL 반환."""
    try:
        image_bytes = base64.b64decode(request.image_base64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"base64 디코딩 실패: {e}")

    try:
        from vertexai.generative_models import Part

        model = get_generative_model("gemini-2.0-flash-exp")

        def _call_gemini():
            response = model.generate_content([
                Part.from_bytes(image_bytes, mime_type="image/jpeg"),
                request.prompt,
            ])
            return response

        response = await asyncio.to_thread(_call_gemini)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"이미지 편집 실패: {e}")

    response_text = ""
    edited_image_bytes: bytes | None = None
    edited_mime = "image/jpeg"

    for part in response.candidates[0].content.parts:
        if hasattr(part, "text") and part.text:
            response_text = part.text
        elif hasattr(part, "inline_data") and part.inline_data:
            edited_image_bytes = part.inline_data.data
            edited_mime = part.inline_data.mime_type or "image/jpeg"

    image_url: str | None = None
    if edited_image_bytes:
        settings = get_settings()
        blob_path = f"edited/{uuid.uuid4()}.jpg"
        try:
            image_url = await upload_to_gcs(
                bucket_name=settings.gcs_bucket_name,
                blob_path=blob_path,
                data=edited_image_bytes,
                content_type=edited_mime,
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"GCS 업로드 실패: {e}")

    if not response_text:
        response_text = "이미지 편집이 완료됐습니다."

    return InternalImageEditResponse(
        text=response_text,
        image_url=image_url,
    )
