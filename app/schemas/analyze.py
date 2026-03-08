"""
작품 분석 API용 Pydantic 스키마. Java BE ↔ FastAPI /internal/ai/analyze 요청·응답 형식.

- 연계: routers/ai.analyze, services/analyze_service에서 사용. Java InternalAnalyzeRequest/Response DTO와 필드 대응.
"""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

_CAMEL = ConfigDict(populate_by_name=True, alias_generator=to_camel, serialize_by_alias=True)


class InternalAnalyzeRequest(BaseModel):
    """작품 분석 요청. Java AnalysisService에서 GCS URI·분석 타입·문제 문맥 전달."""

    model_config = _CAMEL

    gcs_uri: str
    analysis_type: str  # basic | major
    problem_text: Optional[str] = None


class RadarData(BaseModel):
    """5축 점수(밀도·형태·완성도·정합성·사고력). 레이더 차트용, camelCase 직렬화."""

    model_config = _CAMEL

    density: float
    form: float
    completion: float
    relevance: float
    thinking: float


class UniversityPrediction(BaseModel):
    """대학·전공 합격 예측 (Phase 2 Theory Engine 연동 시 사용)."""

    model_config = _CAMEL

    university: str
    major: str
    line: str  # TOP | HIGH | MID | LOW
    probability: int
    similar_accepted_count: int


class InternalAnalyzeResponse(BaseModel):
    """작품 분석 응답. 등급·총점·레이더·fix_scope·코멘트·대학예측. Java에서 DB 저장 및 FE 전달."""

    model_config = _CAMEL

    grade: str  # A | B | C | D | F
    total_score: float
    radar_data: RadarData
    fix_scope: str  # StructureRebuild | DetailTuning
    comment: str
    university_predictions: List[UniversityPrediction] = []
