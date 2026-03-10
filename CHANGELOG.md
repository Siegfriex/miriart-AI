# Changelog

## [Unreleased] - feature/ai-refactor

### 변경 요약

- **vertexai → google-genai 마이그레이션**
  - `google-cloud-aiplatform`(vertexai) 제거, `google-genai>=1.5.0` 사용.
  - `app/core/gemini_client.py`: `genai.Client(vertexai=True)` 싱글턴, `call_gemini()` async 래퍼 (타임아웃 28s, 리트라이, 구조화 로그).
  - `GeminiModel` 상수: FLASH, PRO, FLASH_LITE.

- **예외/에러코드/타임아웃/로깅 구조**
  - `app/core/exceptions.py`: `MiriArtAIError` 베이스, `LLMTimeoutError`, `LLMServiceError`, `LLMParsingError`, `GCSError`, `ValidationError` (BE ErrorCode 매핑: AN002/AI002, AN001/AI001, F003, C001).
  - `app/core/error_handler.py`: 전역 핸들러 등록 (504/502/400/500, JSON `code`/`message`).
  - `app/core/logging_config.py`: JSON 구조화 로깅 (timestamp, severity, name, message), uvicorn.access WARNING 이상.
  - `app/middleware/request_context.py`: X-Request-ID, method/path/status/latency_s 로깅, /health·/internal/ai/health 제외.

- **GCS 서비스 분리**
  - `app/services/gcs_service.py`: `GcsService` — `download_as_bytes`, `generate_signed_url`(Phase 2), `upload_bytes`(image-edit 연동).
  - GCS 관련 코드를 `app/core/gemini_client.py`에서 제거.

- **서비스 레이어 리팩터링**
  - `analyze_service.py`: GcsService + call_gemini, Dev Spec ANALYZE 프롬프트, JSON 파싱 → InternalAnalyzeResponse, GCSError/LLMParsingError.
  - `chat_service.py`: MODEL_MAP(GeminiModel), CHAT_SYSTEM_PROMPT, history flatten, 고정 quick_replies 3개, 이미지 시 Part.from_bytes.
  - `image_edit_service.py`: call_gemini(return_response=True, timeout_override_s=55), GcsService.upload_bytes, ValidationError/GCSError.

- **C4 AI QA 기능 활성화**
  - `app/schemas/qa.py`: SummarizeAnswersRequest/Response, DraftFromQuestionRequest/Response (camelCase).
  - `app/services/qa_service.py`: summarize_answers, draft_from_question (Dev Spec 프롬프트, response_mime_type=application/json).
  - `app/routers/ai.py`: /summarize-answers, /draft-from-question 501 스텁 제거 → 실구현 연결.

- **main.py 통합**
  - lifespan: setup_logging(), get_genai_client() warm up.
  - FastAPI(docs_url=None, redoc_url=None), RequestContextMiddleware, register_exception_handlers(app).

- **기타**
  - `.dockerignore`: docs/, .cursor/, *.md(단 requirements.txt 제외), cloudbuild.yaml 등 반영.
  - 기존 동작과 달라지는 부분은 코드 내 TODO 주석으로 표시 가능.

- **머지 전 TODO 반영**
  - `chat_service.py`: imageBase64 디코딩 실패 시 `ValidationError` → HTTP 400, code `VALIDATION_ERROR`.
  - `qa_service.py`: draft_from_question에서 imageBase64 디코딩 실패 시 `ValidationError` → 400.
  - `analyze_service.py`: GCS URI 버킷 정책 B안 채택(코드 변경 없이 docstring 명시). 동일 버킷 URI만 지원, 그 외는 GCS 실패 시 GCSError(502).
  - 테스트: 잘못된 base64 → 400, 유효하지 않은 gcsUri → 502 시나리오를 tests/ 에 추가.

### 의존성 변경

- 추가: `google-genai>=1.5.0`, `google-auth>=2.35.0`, `python-json-logger>=3.0.0`
- 제거: `google-cloud-aiplatform`
- 유지: `fastapi==0.115.8`, `uvicorn[standard]==0.34.0`, `pydantic==2.10.6`, `google-cloud-storage>=2.18.0`
- `httpx`는 `google-genai`와의 호환을 위해 `>=0.27.0`으로 완화 (기존 `==0.27.2` 제거).
