"""
통합 테스트: 머지 전 TODO 검증.

- 잘못된 imageBase64로 /internal/ai/chat → 400 + VALIDATION_ERROR
- 잘못된 imageBase64로 /internal/ai/draft-from-question → 400 + VALIDATION_ERROR
- 유효하지 않은 gcsUri로 /internal/ai/analyze → 502 + GCS_ERROR
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.core.exceptions import GCSError


@pytest.fixture
def client():
    return TestClient(app)


def test_chat_invalid_image_base64_returns_400_validation_error(client: TestClient):
    """잘못된 imageBase64로 POST /internal/ai/chat → 400, code VALIDATION_ERROR."""
    resp = client.post(
        "/internal/ai/chat",
        json={
            "message": "테스트",
            "modelType": "FAST",
            "imageBase64": "not-valid-base64!!!",
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data.get("code") == "VALIDATION_ERROR"
    assert "message" in data


def test_draft_from_question_invalid_image_base64_returns_400_validation_error(
    client: TestClient,
):
    """잘못된 imageBase64로 POST /internal/ai/draft-from-question → 400, code VALIDATION_ERROR."""
    resp = client.post(
        "/internal/ai/draft-from-question",
        json={
            "title": "제목",
            "content": "내용",
            "imageBase64": "not-valid-base64!!!",
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data.get("code") == "VALIDATION_ERROR"
    assert "message" in data


def test_analyze_invalid_gcs_uri_returns_502_gcs_error(client: TestClient):
    """GCS 다운로드 실패 시 POST /internal/ai/analyze → 502, code GCS_ERROR."""
    with patch("app.services.analyze_service.gcs") as mock_gcs:
        mock_gcs.download_as_bytes.side_effect = GCSError("Failed to download image")
        resp = client.post(
            "/internal/ai/analyze",
            json={
                "gcsUri": "gs://miriart-bucket/nonexistent.png",
                "analysisType": "basic",
            },
        )
    assert resp.status_code == 502
    data = resp.json()
    assert data.get("code") == "GCS_ERROR"
    assert "message" in data
