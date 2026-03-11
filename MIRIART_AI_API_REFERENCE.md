# MiriArt AI API 레퍼런스

> **대상**: miriart-ai (FastAPI) — `/internal/ai/*` 엔드포인트
> **작성일**: 2026-03-10
> **목적**: AI 서비스 전용 엔드포인트·스키마·스토리지 IO 인벤토리
> **Swagger**: prod에서 비활성 (`docs_url=None, redoc_url=None`)

---

## 1. 엔드포인트 인벤토리

| # | Method | Path | Handler | Request Schema | Response Schema | Service | BE 계약명 |
|---|--------|------|---------|----------------|-----------------|---------|-----------|
| 1 | POST | `/internal/ai/analyze` | `analyze` | `InternalAnalyzeRequest` | `InternalAnalyzeResponse` | `analyze_service.analyze_artwork()` | AI 작품 분석 |
| 2 | POST | `/internal/ai/chat` | `chat` | `InternalChatRequest` | `InternalChatResponse` | `chat_service.chat()` | AI 멘토 채팅 |
| 3 | POST | `/internal/ai/edit-image` | `edit_image` | `InternalImageEditRequest` | `InternalImageEditResponse` | `image_edit_service.edit_image()` | AI 이미지 편집 |
| 4 | POST | `/internal/ai/summarize-answers` | `summarize_answers` | `SummarizeAnswersRequest` | `SummarizeAnswersResponse` | `qa_service.summarize_answers()` | QA 답변 요약 |
| 5 | POST | `/internal/ai/draft-from-question` | `draft_from_question` | `DraftFromQuestionRequest` | `DraftFromQuestionResponse` | `qa_service.draft_from_question()` | QA 답변 초안 |
| 6 | GET | `/health` | `health` | — | `{"status": "ok"}` | — | 헬스체크 |

> 모든 `/internal/ai/*` 엔드포인트는 Cloud Run IAM으로 보호. BE SA(`miriart-be-runner`)만 호출 가능.

---

## 2. 스키마 정의

### 2.1 작품 분석 (analyze)

**`InternalAnalyzeRequest`** — `app/schemas/analyze.py`

| 필드 | 타입 | Required | 기본값 | JSON Key | 설명 |
|------|------|----------|--------|----------|------|
| `gcs_uri` | `str` | ✅ | — | `gcsUri` | GCS 이미지 URI |
| `analysis_type` | `str` | ✅ | — | `analysisType` | `"basic"` \| `"major"` |
| `problem_text` | `Optional[str]` | ❌ | `None` | `problemText` | 출제 주제/맥락 |

**`RadarData`** — 5축 레이더 점수

| 필드 | 타입 | 범위 | 설명 |
|------|------|------|------|
| `density` | `float` | 0–100 | 밀도감 |
| `form` | `float` | 0–100 | 형태력 |
| `completion` | `float` | 0–100 | 완성도 |
| `relevance` | `float` | 0–100 | 주제 적합도 |
| `thinking` | `float` | 0–100 | 사고력 |

**`UniversityPrediction`**

| 필드 | 타입 | JSON Key | 설명 |
|------|------|----------|------|
| `university` | `str` | `university` | 대학명 |
| `major` | `str` | `major` | 학과 |
| `line` | `str` | `line` | `"TOP"` \| `"HIGH"` \| `"MID"` \| `"LOW"` |
| `probability` | `int` | `probability` | 0–100 합격 확률 |
| `similar_accepted_count` | `int` | `similarAcceptedCount` | 유사 합격 사례 수 |

**`InternalAnalyzeResponse`**

| 필드 | 타입 | JSON Key | 설명 |
|------|------|----------|------|
| `grade` | `str` | `grade` | `"A"` \| `"B"` \| `"C"` \| `"D"` \| `"F"` |
| `total_score` | `float` | `totalScore` | 종합 점수 |
| `radar_data` | `RadarData` | `radarData` | 5축 레이더 |
| `fix_scope` | `str` | `fixScope` | `"StructureRebuild"` \| `"DetailTuning"` |
| `comment` | `str` | `comment` | AI 평가 코멘트 |
| `university_predictions` | `List[UniversityPrediction]` | `universityPredictions` | 대학 예측 목록 |

> 직렬화: Pydantic `alias_generator=to_camel`, `populate_by_name=True`

---

### 2.2 AI 채팅 (chat)

**`HistoryItem`**

| 필드 | 타입 | 설명 |
|------|------|------|
| `role` | `str` | `"user"` \| `"model"` |
| `parts` | `List[Dict[str, Any]]` | `[{"text": "..."}]` |

**`StickyContext`**

| 필드 | 타입 | Required | 설명 |
|------|------|----------|------|
| `grade` | `str` | ✅ | 분석 등급 |
| `score` | `float` | ✅ | 분석 점수 |
| `fix_scope` | `str` | ✅ | `"StructureRebuild"` \| `"DetailTuning"` |
| `radar_data` | `Optional[Dict[str, float]]` | ❌ | 5축 레이더 |

**`InternalChatRequest`**

| 필드 | 타입 | Required | 기본값 | JSON Key | 설명 |
|------|------|----------|--------|----------|------|
| `model_type` | `str` | ✅ | — | `modelType` | `"CHAT_PRO"` \| `"FAST"` \| `"THINKING"` \| `"SEARCH"` \| `"IMAGE_EDIT"` |
| `message` | `str` | ✅ | — | `message` | 사용자 메시지 |
| `session_id` | `Optional[str]` | ❌ | `None` | `sessionId` | 세션 ID (AI 미사용, BE Redis 용) |
| `sticky_context` | `Optional[StickyContext]` | ❌ | `None` | `stickyContext` | 분석 결과 컨텍스트 |
| `image_base64` | `Optional[str]` | ❌ | `None` | `imageBase64` | 이미지 base64 |
| `image_mime_type` | `Optional[str]` | ❌ | `None` | `imageMimeType` | 이미지 MIME |
| `history` | `Optional[List[HistoryItem]]` | ❌ | `None` | `history` | 대화 이력 |

**`InternalChatResponse`**

| 필드 | 타입 | 기본값 | JSON Key | 설명 |
|------|------|--------|----------|------|
| `text` | `str` | — | `text` | AI 응답 |
| `grounding_urls` | `List[str]` | `[]` | `groundingUrls` | 참조 URL (현재 빈 배열) |
| `quick_replies` | `List[str]` | 고정 3개 | `quickReplies` | 빠른 응답 버튼 |

---

### 2.3 이미지 편집 (edit-image)

**`InternalImageEditRequest`**

| 필드 | 타입 | Required | JSON Key | 설명 |
|------|------|----------|----------|------|
| `image_base64` | `str` | ✅ | `imageBase64` | 원본 이미지 base64 |
| `prompt` | `str` | ✅ | `prompt` | 편집 지시 |

**`InternalImageEditResponse`**

| 필드 | 타입 | JSON Key | 설명 |
|------|------|----------|------|
| `text` | `str` | `text` | AI 편집 코멘트 |
| `image_url` | `Optional[str]` | `imageUrl` | GCS 공개 URL (편집 이미지 없으면 null) |

---

### 2.4 QA 답변 요약 (summarize-answers)

**`SummarizeAnswersRequest`**

| 필드 | 타입 | Required | 제약 | 설명 |
|------|------|----------|------|------|
| `question` | `str` | ✅ | 1–2000자 | 질문 |
| `answers` | `List[str]` | ✅ | 1–20개 | 답변 목록 |

**`SummarizeAnswersResponse`**

| 필드 | 타입 | 설명 |
|------|------|------|
| `summary` | `str` | 3줄 요약 |
| `supplement` | `str` | 보충 조언 (1–2줄) |

---

### 2.5 QA 답변 초안 (draft-from-question)

**`DraftFromQuestionRequest`**

| 필드 | 타입 | Required | 제약 | 설명 |
|------|------|----------|------|------|
| `title` | `str` | ✅ | 1–200자 | 질문 제목 |
| `content` | `str` | ✅ | 1–5000자 | 질문 본문 |
| `image_base64` | `Optional[str]` | ❌ | — | 이미지 base64 |

**`DraftFromQuestionResponse`**

| 필드 | 타입 | 설명 |
|------|------|------|
| `draft` | `str` | AI 초안 답변 (프롬프트에서 200자 유도, 응답 스키마에는 길이 제한 없음) |

---

## 3. GCS 스토리지 IO

### 3.1 GcsService 메서드 인벤토리

소스: `app/services/gcs_service.py`

| 메서드 | 사용처 | blob_path 패턴 | 동작 | 예외 → 에러코드 |
|--------|--------|---------------|------|-----------------|
| `download_as_bytes(gcs_uri)` | `analyze_service` | `gs://miriart-bucket/{path}` 또는 `{path}` | GCS → bytes 다운로드 | → `GCSError` (caller가 감싸서 raise) |
| `upload_bytes(blob_path, data, content_type)` | `image_edit_service` | `edited/{uuid}.jpg` | bytes → GCS 업로드, 공개 URL 반환 | → `GCSError` (caller) |
| `generate_signed_url(blob_path, expiration_minutes)` | **현재 미사용** (Phase 2 준비) | 임의 | V4 Signed URL 생성 (impersonated credentials) | — |

### 3.2 GCS 경로 규칙

| 경로 패턴 | 용도 | 생성 주체 | SSOT 참조 |
|-----------|------|-----------|-----------|
| `artworks/{date}/{uuid}_{filename}` | 원본 업로드 이미지 | BE | `miriarts_infra.md` §3.4 |
| `edited/{uuid}.jpg` | AI 이미지 편집 결과 | AI (`image_edit_service.py:64`) | 동일 |
| `analyses/**` (향후) | 분석 결과 이미지 | AI (미구현) | 동일 |

### 3.3 GCS 초기화

```python
# analyze_service.py, image_edit_service.py 모듈 레벨
_settings = get_settings()
gcs = GcsService(bucket_name=_settings.gcs_bucket_name, project_id=_settings.gcp_project_id)
```

- 버킷: `miriart-bucket` (config.py 기본값, Cloud Run env 오버라이드)
- 프로젝트: `miriarts` (Cloud Run env `GCP_PROJECT_ID`)
- 인증: Application Default Credentials (Cloud Run SA 자동)

---

## 4. 상태 저장 (DB/Redis/메모리)

### AI 서비스는 **stateless**이다.

| 항목 | 상태 |
|------|------|
| DB 연결 | ❌ 없음 (MySQL/PostgreSQL 사용 안 함) |
| Redis 연결 | ❌ 없음 (채팅 세션은 BE가 Redis에서 관리, AI에 `history`로 전달) |
| 인메모리 캐시 | `get_settings()` LRU 캐시 (설정값만), `get_genai_client()` 싱글톤 |
| 세션 관리 | ❌ AI에서 수행하지 않음 (`sessionId`는 pass-through) |
| Rate Limiting | ❌ AI 레벨 없음 (BE에서 처리) |

**결론**: AI 서비스는 요청마다 독립적으로 처리하는 순수 stateless 서비스. 모든 상태 관리(세션, 한도, 인증)는 BE가 담당.

---

## 5. 에러 응답 형식

모든 에러 응답은 동일한 JSON 구조:

```json
{
  "code": "LLM_TIMEOUT",
  "message": "Gemini 응답 시간 초과 (55s)"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `code` | str | 머신 리더블 에러 코드 |
| `message` | str | 사람 리더블 에러 메시지 |

### 에러 코드 전체 목록

| code | HTTP | 예외 클래스 | 발생 서비스 |
|------|------|------------|------------|
| `LLM_TIMEOUT` | 504 | `LLMTimeoutError` | analyze, chat, edit-image, qa |
| `LLM_SERVICE_ERROR` | 502 | `LLMServiceError` | 동일 |
| `LLM_PARSING_ERROR` | 502 | `LLMParsingError` | analyze, qa (JSON 응답) |
| `GCS_ERROR` | 502 | `GCSError` | analyze (다운로드), edit-image (업로드) |
| `VALIDATION_ERROR` | 400 | `ValidationError` / `RequestValidationError` | chat, edit-image, qa (base64/Pydantic) |
| `LLM_RATE_LIMITED` | 429 | `LLMRateLimitError` | analyze, chat, edit-image, qa (Gemini 429 시) |
| `INTERNAL_ERROR` | 500 | `Exception` (미처리) | 전역 |

---

*문서 끝 — 2026-03-10*
