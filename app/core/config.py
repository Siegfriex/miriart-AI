"""
GCP·Vertex AI·GCS 관련 환경 설정 모듈.

- 연계: gemini_client에서 get_settings()로 프로젝트/리전/버킷 조회.
- .env 파일 또는 환경변수로 오버라이드 가능 (Pydantic BaseSettings).
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """GCP 프로젝트 ID, 리전, GCS 버킷명 등 환경 변수 설정. .env 로드, UTF-8, 대소문자 무시."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    gcp_project_id: str = "miriart-dev"
    gcp_region: str = "asia-northeast3"
    gcs_bucket_name: str = "miriart-bucket"
    google_application_credentials: str = ""


@lru_cache
def get_settings() -> Settings:
    """캐시된 Settings 싱글톤 반환. 앱 전역에서 동일 인스턴스 사용."""
    return Settings()
