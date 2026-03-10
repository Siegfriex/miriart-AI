"""
GCS 다운로드/업로드 및 Signed URL 생성. Phase 2 Presigned URL 대비.

- analyze_service, image_edit_service에서 사용.
- 실패 시 호출부에서 app.core.exceptions.GCSError 사용.
- 모든 I/O 메서드는 sync 전용. async 호출부에서 asyncio.to_thread()로 감싸서 사용할 것.
"""
import datetime
from typing import Optional

from google.auth import default, impersonated_credentials
from google.cloud import storage


class GcsService:
    """GCS 버킷 접근: 다운로드, 업로드, Signed URL 생성(Phase 2). lazy init으로 첫 호출 시 클라이언트 생성."""

    def __init__(self, bucket_name: str, project_id: str):
        self._bucket_name = bucket_name
        self._project_id = project_id
        self._client: Optional[storage.Client] = None
        self._bucket = None

    def _ensure_client(self):
        """첫 GCS 호출 시 클라이언트/버킷 초기화. import 시점에 credentials 불필요."""
        if self._client is None:
            self._client = storage.Client(project=self._project_id)
            self._bucket = self._client.bucket(self._bucket_name)

    def download_as_bytes(self, gcs_uri: str) -> bytes:
        """GCS URI 또는 blob path에서 bytes 다운로드 (sync). 실패 시 호출부에서 GCSError 발생."""
        self._ensure_client()
        if gcs_uri.startswith("gs://"):
            path = gcs_uri.replace(f"gs://{self._bucket_name}/", "", 1)
        else:
            path = gcs_uri
        blob = self._bucket.blob(path)
        return blob.download_as_bytes()

    def generate_signed_url(
        self, blob_path: str, expiration_minutes: int = 60
    ) -> str:
        """Phase 2용. miriart-ai-runner SA로 v4 signed URL 생성."""
        self._ensure_client()
        source_creds, _ = default()
        signing_creds = impersonated_credentials.Credentials(
            source_credentials=source_creds,
            target_principal=f"miriart-ai-runner@{self._project_id}.iam.gserviceaccount.com",
            target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        blob = self._bucket.blob(blob_path)
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=expiration_minutes),
            method="GET",
            credentials=signing_creds,
        )
        return url

    def upload_bytes(
        self,
        blob_path: str,
        data: bytes,
        content_type: str = "image/jpeg",
    ) -> str:
        """bytes를 GCS에 업로드 후 식별용 URL 반환 (sync). image_edit_service에서 사용."""
        self._ensure_client()
        blob = self._bucket.blob(blob_path)
        blob.upload_from_string(data, content_type=content_type)
        return f"https://storage.googleapis.com/{self._bucket_name}/{blob_path}"
