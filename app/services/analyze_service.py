"""
작품 이미지 분석 서비스. Gemini Vision으로 5축(밀도·형태·완성도·정합성·사고력) 채점.

- 연계: routers/ai.analyze → analyze_artwork; GcsService + call_gemini 사용.
- Java BE AnalysisService가 /internal/ai/analyze 호출 후 결과를 DB에 저장.
- GCS URI: 현재는 settings.gcs_bucket_name과 동일한 버킷의 URI(gs://{bucket}/...)만 지원.
  다른 버킷 URI는 download_as_bytes에서 실패 시 GCSError(502)로 반환됨.
"""
import asyncio
import json
import logging

from google.genai import types as genai_types

from app.core.exceptions import GCSError, LLMParsingError
from app.core.gemini_client import call_gemini, GeminiModel
from app.core.config import get_settings
from app.schemas.analyze import (
    InternalAnalyzeRequest,
    InternalAnalyzeResponse,
    RadarData,
    UniversityPrediction,
)
from app.services.gcs_service import GcsService

logger = logging.getLogger(__name__)

_settings = get_settings()
gcs = GcsService(bucket_name=_settings.gcs_bucket_name, project_id=_settings.gcp_project_id)

_MIME_MAP = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"RIFF": "image/webp",
}


def _detect_mime(data: bytes) -> str:
    """이미지 바이트의 매직 바이트로 MIME 타입 추론. 실패 시 image/jpeg 기본."""
    for magic, mime in _MIME_MAP.items():
        if data[:len(magic)] == magic:
            return mime
    return "image/jpeg"

ANALYZE_SYSTEM_PROMPT = """당신은 미술 입시 전문 AI 평가관입니다.
업로드된 미술 작품 이미지를 분석하여 정확한 평가를 제공합니다.

평가 항목 (각 0~100점):
- density: 밀도감, 화면 구성의 밀도
- form: 형태력, 대상의 형태 정확도
- completion: 완성도, 전체적인 마무리 수준
- relevance: 주제 적합도, 출제 의도와의 부합
- thinking: 사고력, 독창적 해석과 표현

등급: A(90+), B(75+), C(60+), D(45+), F(45-)
fixScope: StructureRebuild(D이하) / DetailTuning(C이상)

대학 예측: 5개 이내
- line: TOP/HIGH/MID/LOW
- probability: 0~100
- similarAcceptedCount: 유사 합격 사례 수

반드시 JSON으로 응답하세요."""

ANALYZE_USER_TEMPLATE = """분석 유형: {analysis_type}
{problem_text_line}

위 미술 작품을 분석해주세요.

응답 JSON:
{{"grade":"A","totalScore":82,"radarData":{{"density":85,"form":80,"completion":78,"relevance":88,"thinking":79}},"fixScope":"DetailTuning","comment":"...","universityPredictions":[{{"university":"...","major":"...","line":"HIGH","probability":68,"similarAcceptedCount":14}}]}}"""


async def analyze_artwork(req: InternalAnalyzeRequest) -> InternalAnalyzeResponse:
    """GCS URI 이미지 다운로드 → Gemini Vision 호출 → JSON 파싱 → InternalAnalyzeResponse 반환.
    현재는 동일 버킷(settings.gcs_bucket_name) URI만 정상 지원; 그 외는 GCS 실패 시 GCSError(502).
    """
    # [DEBUG] GCS 다운로드 단계
    gcs_start = asyncio.get_event_loop().time()
    try:
        image_bytes = await asyncio.to_thread(gcs.download_as_bytes, req.gcs_uri)
    except Exception as e:
        raise GCSError(f"Failed to download image from {req.gcs_uri}: {e}")
    gcs_latency = asyncio.get_event_loop().time() - gcs_start

    mime_type = _detect_mime(image_bytes)
    logger.info(
        "analyze_pre_gemini",
        extra={
            "gcs_uri": req.gcs_uri,
            "gcs_download_s": round(gcs_latency, 2),
            "image_bytes": len(image_bytes),
            "mime_type": mime_type,
            "analysis_type": req.analysis_type,
            "has_problem_text": bool(req.problem_text),
        },
    )

    problem_line = f"문제/주제: {req.problem_text}" if req.problem_text else ""
    user_text = ANALYZE_USER_TEMPLATE.format(
        analysis_type=req.analysis_type,
        problem_text_line=problem_line,
    )

    contents = [
        genai_types.Part.from_text(text=user_text),
        genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
    ]

    raw = await call_gemini(
        model=GeminiModel.FLASH,
        contents=contents,
        system_instruction=ANALYZE_SYSTEM_PROMPT,
        purpose="analyze_artwork",
        temperature=0.3,
        max_output_tokens=8192,
        response_mime_type="application/json",
    )

    try:
        data = json.loads(raw)
        radar = data["radarData"]
        return InternalAnalyzeResponse(
            grade=data["grade"],
            total_score=float(data["totalScore"]),
            radar_data=RadarData(
                density=radar["density"],
                form=radar["form"],
                completion=radar["completion"],
                relevance=radar["relevance"],
                thinking=radar["thinking"],
            ),
            fix_scope=data["fixScope"],
            comment=data["comment"],
            university_predictions=[
                UniversityPrediction(**u)
                for u in data.get("universityPredictions", [])
            ],
        )
    except (json.JSONDecodeError, KeyError) as e:
        raise LLMParsingError(f"Analyze parsing failed: {e}, raw: {raw[:300]}")
