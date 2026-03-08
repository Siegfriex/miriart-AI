"""
GCS 파일 다운로드/업로드 및 Vertex AI 클라이언트 래퍼 모듈.

- 연계: analyze_service, image_edit_service에서 import하여 사용.
- get_generative_model() → Vertex AI GenerativeModel 인스턴스 반환.
- download_from_gcs(bucket_name, blob_path) → GCS에서 바이트·MIME 타입 다운로드.
- upload_to_gcs(...) → 처리 결과를 GCS에 저장 후 공개 URL 반환.
"""
import asyncio
from typing import Optional

import vertexai
from google.cloud import storage
from vertexai.generative_models import GenerativeModel

from app.core.config import get_settings

_initialized = False


def init_vertex_ai() -> None:
    """Vertex AI를 초기화한다. 앱 시작 시 main.lifespan에서 1회 호출."""
    global _initialized
    if _initialized:
        return
    settings = get_settings()
    vertexai.init(project=settings.gcp_project_id, location=settings.gcp_region)
    _initialized = True


def get_generative_model(model_name: str, system_instruction: Optional[str] = None) -> GenerativeModel:
    """Vertex AI GenerativeModel 인스턴스 반환. chat_service, analyze_service, image_edit_service에서 사용."""
    init_vertex_ai()
    if system_instruction:
        return GenerativeModel(model_name, system_instruction=system_instruction)
    return GenerativeModel(model_name)


def get_storage_client() -> storage.Client:
    """GCS Storage 클라이언트 반환. config의 gcp_project_id 사용."""
    settings = get_settings()
    return storage.Client(project=settings.gcp_project_id)


def parse_gcs_uri(gcs_uri: str) -> tuple[str, str]:
    """GCS URI를 (bucket_name, blob_path) 튜플로 파싱. download_from_gcs 등에서 사용."""
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"유효하지 않은 GCS URI: {gcs_uri}")
    path = gcs_uri[len("gs://"):]
    bucket_name, _, blob_path = path.partition("/")
    return bucket_name, blob_path


async def download_from_gcs(bucket_name: str, blob_path: str) -> tuple[bytes, str]:
    """GCS에서 이미지 bytes와 MIME 타입을 비동기로 다운로드. analyze_service, image_edit_service에서 사용."""
    def _download() -> tuple[bytes, str]:
        client = get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        data = blob.download_as_bytes()
        # blob.content_type은 download_as_bytes() 후 메타데이터에서 읽힘
        mime = blob.content_type or _infer_mime_from_path(blob_path)
        return data, mime

    return await asyncio.to_thread(_download)


def _infer_mime_from_path(path: str) -> str:
    """경로 확장자에서 MIME 타입을 추론한다. 알 수 없으면 image/jpeg 반환."""
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {"png": "image/png", "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/jpeg")


async def upload_to_gcs(bucket_name: str, blob_path: str, data: bytes, content_type: str = "image/jpeg") -> str:
    """bytes를 GCS에 업로드 후 공개 URL 반환. image_edit_service에서 편집 결과 저장 시 사용."""
    def _upload() -> str:
        client = get_storage_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(data, content_type=content_type)
        return f"https://storage.googleapis.com/{bucket_name}/{blob_path}"

    return await asyncio.to_thread(_upload)
