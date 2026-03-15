# miriart-ai 인프라·코드 메타 (SSOT)

> **대상**: miriart-ai (FastAPI, Cloud Run)  
> **기준 시점**: 2026-03-15 (app/ 및 cloudbuild.yaml 실제 파일 기준, wc -l 검증 완료)  
> **원칙**: 유일 참조는 코드. 값·라인은 app/ 및 cloudbuild.yaml 실제 파일 기준.

---

## §0. 코드 라인 기준 메타

### 0.1 app/ 폴더별 파일·심볼·라인범위

#### app/main.py (마지막 엔드: 50)

소스: `app/main.py`

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| function | lifespan | 23 | 30 |
| config | app (FastAPI 인스턴스) | 33 | 40 |
| route | (router mount prefix) | 44 | 44 |
| route | health | 47 | 50 |

#### app/core/config.py (마지막 엔드: 33)

소스: `app/core/config.py`

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| class | Settings | 12 | 27 |
| function | get_settings | 30 | 33 |

**환경변수 필드 (코드 기준)**: gcp_project_id (21), gcp_region (22), gemini_location (25), gcs_bucket_name (26), google_application_credentials (27). ※ 23-24행은 gemini_location 주석.

#### app/core/exceptions.py (마지막 엔드: 57)

소스: `app/core/exceptions.py`

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| class | MiriArtAIError | 9 | 15 |
| class | LLMTimeoutError | 18 | 22 |
| class | LLMRateLimitError | 25 | 29 |
| class | LLMServiceError | 32 | 36 |
| class | LLMParsingError | 39 | 43 |
| class | GCSError | 46 | 50 |
| class | ValidationError | 53 | 57 |

#### app/core/error_handler.py (마지막 엔드: 98)

소스: `app/core/error_handler.py`

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| constant | ERROR_MAP | 28 | 35 |
| function | register_exception_handlers | 38 | 98 |

**ERROR_MAP (코드 기준)**: LLMTimeoutError→(504, "LLM_TIMEOUT"), LLMRateLimitError→(429, "LLM_RATE_LIMITED"), LLMServiceError→(502, "LLM_SERVICE_ERROR"), LLMParsingError→(502, "LLM_PARSING_ERROR"), GCSError→(502, "GCS_ERROR"), ValidationError→(400, "VALIDATION_ERROR"). JSON body 필드: **code**, **message** (55-56). RequestValidationError body (69-82). INTERNAL_ERROR (95-98).

#### app/core/gemini_client.py (마지막 엔드: 210)

소스: `app/core/gemini_client.py`

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| constant | GEMINI_TIMEOUT_S, GEMINI_RETRY_ATTEMPTS, GEMINI_IMAGE_EDIT_TIMEOUT_S 등 | 21 | 26 |
| function | get_genai_client | 32 | 59 |
| class | GeminiModel | 62 | 67 |
| function | call_gemini | 70 | 210 |

**핵심 값 (코드 기준)**: GEMINI_TIMEOUT_S=55 (21), GEMINI_TIMEOUT_MS=55000 (22), GEMINI_RETRY_ATTEMPTS=3 (23), GEMINI_RETRY_INITIAL_DELAY=1.0 (24), GEMINI_RETRY_MAX_DELAY=8.0 (25), GEMINI_IMAGE_EDIT_TIMEOUT_S=25 (26). timeout=GEMINI_TIMEOUT_MS (42), attempts=GEMINI_RETRY_ATTEMPTS (44), initial_delay=GEMINI_RETRY_INITIAL_DELAY (45), max_delay=GEMINI_RETRY_MAX_DELAY (46). **effective_timeout = timeout_override_s or GEMINI_TIMEOUT_S (90)**. FLASH="gemini-2.5-flash"/PRO="gemini-2.5-pro"/FLASH_LITE="gemini-2.0-flash-lite" (65-67). automatic_function_calling disable (96). 429→LLMRateLimitError (184-196).

#### app/core/logging_config.py (마지막 엔드: 24)

소스: `app/core/logging_config.py`

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| function | setup_logging | 13 | 24 |

#### app/middleware/request_context.py (마지막 엔드: 45)

소스: `app/middleware/request_context.py`

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| class | RequestContextMiddleware | 18 | 45 |
| constant | EXCLUDE_PATHS | 21 | 21 |

#### app/routers/ai.py (마지막 엔드: 107)

소스: `app/routers/ai.py`

| Method | Path | Handler | 시작행 | 끝행 |
|--------|------|---------|--------|------|
| GET | /internal/ai/status | status | 24 | 46 |
| POST | /internal/ai/analyze | analyze | 49 | 57 |
| POST | /internal/ai/chat | chat | 60 | 68 |
| POST | /internal/ai/edit-image | edit_image | 71 | 79 |
| POST | /internal/ai/summarize-answers | api_summarize_answers | 82 | 91 |
| POST | /internal/ai/draft-from-question | api_draft_from_question | 94 | 107 |

#### app/schemas/analyze.py (마지막 엔드: 58)

소스: `app/schemas/analyze.py`

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| class | InternalAnalyzeRequest | 14 | 21 |
| class | RadarData | 24 | 33 |
| class | UniversityPrediction | 36 | 45 |
| class | InternalAnalyzeResponse | 48 | 58 |

#### app/schemas/chat.py (마지막 엔드: 70)

소스: `app/schemas/chat.py`

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| class | HistoryItem | 14 | 20 |
| class | UniversityPrediction | 23 | 31 |
| class | StickyContext | 33 | 46 |
| class | InternalChatRequest | 49 | 60 |
| class | InternalChatResponse | 63 | 70 |

#### app/schemas/image_edit.py (마지막 엔드: 29)

소스: `app/schemas/image_edit.py`

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| class | InternalImageEditRequest | 14 | 20 |
| class | InternalImageEditResponse | 23 | 29 |

#### app/schemas/qa.py (마지막 엔드: 47)

소스: `app/schemas/qa.py`

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| class | SummarizeAnswersRequest | 14 | 20 |
| class | SummarizeAnswersResponse | 23 | 29 |
| class | DraftFromQuestionRequest | 32 | 39 |
| class | DraftFromQuestionResponse | 42 | 47 |

#### app/services/analyze_service.py (마지막 엔드: 141)

소스: `app/services/analyze_service.py`

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| function | _detect_mime | 38 | 43 |
| constant | ANALYZE_SYSTEM_PROMPT, ANALYZE_USER_TEMPLATE | 45 | 71 |
| function | analyze_artwork | 74 | 141 |

#### app/services/chat_service.py (마지막 엔드: 181)

소스: `app/services/chat_service.py`

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| constant | _MAX_HISTORY_TURNS, _CHAT_MAX_OUTPUT_TOKENS | 19 | 20 |
| constant | MODEL_MAP, CHAT_SYSTEM_PROMPT | 22 | 38 |
| function | _get_effective_history | 41 | 45 |
| constant | _SUMMARY_TEXT_MAX_LEN | 48 | 48 |
| function | _build_system_prompt | 51 | 107 |
| function | _flatten_history | 110 | 125 |
| function | chat | 128 | 181 |

#### app/services/image_edit_service.py (마지막 엔드: 78)

소스: `app/services/image_edit_service.py`

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| function | edit_image | 26 | 78 |

**핵심 값**: timeout_override_s=GEMINI_IMAGE_EDIT_TIMEOUT_S (from gemini_client.py:26). image_edit_service에서 호출 시 44행.

#### app/services/qa_service.py (마지막 엔드: 114)

소스: `app/services/qa_service.py`

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| constant | SUMMARIZE_*, DRAFT_* | 18 | 53 |
| function | summarize_answers | 56 | 76 |
| function | draft_from_question | 79 | 114 |

#### app/services/gcs_service.py (마지막 엔드: 70)

소스: `app/services/gcs_service.py`

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| class | GcsService | 15 | 70 |
| method | download_as_bytes, generate_signed_url, upload_bytes | 30 | 70 |

---

### 0.2 인프라 기준 코드라인

| 파일 | 행 | 설정/의미 |
|------|-----|-----------|
| cloudbuild.yaml | 29 | --port=8080 |
| cloudbuild.yaml | 32 | --timeout=120 |
| cloudbuild.yaml | 40 | --set-env-vars=GCP_PROJECT_ID=miriarts,GCP_REGION=asia-northeast3,GCS_BUCKET_NAME=miriart-bucket,GEMINI_LOCATION=global |
| cloudbuild.yaml | 41 | --project=miriarts |
| app/core/config.py | 21 | gcp_project_id 기본값 "miriart-dev" |
| app/core/config.py | 22 | gcp_region 기본값 "asia-northeast3" |
| app/core/config.py | 25 | gemini_location 기본값 "global" (Gemini API 호출 리전). ※ 23-24행 주석 |
| app/core/config.py | 26 | gcs_bucket_name 기본값 "miriart-bucket" |
| app/core/config.py | 27 | google_application_credentials 기본값 "" |
| Dockerfile | 10 | EXPOSE 8080 |
| Dockerfile | 12 | CMD uvicorn app.main:app --host 0.0.0.0 --port 8080 |

---

## §1. 요청 플로우·리소스

- **BE → AI**: Java BE가 `FASTAPI_INTERNAL_URL`로 miriart-ai Cloud Run을 호출. 경로: `GET /internal/ai/status`, `POST /internal/ai/analyze`, `/chat`, `/edit-image`, `/summarize-answers`, `/draft-from-question`. FE는 AI를 직접 호출하지 않음.
- **헬스체크**: `GET /health` (app/main.py:47-50). prefix `/internal/ai` (app/main.py:44).

**전체 엔드포인트 SSOT**: 본 문서 §0.1 `app/routers/ai.py` 테이블 및 `app/main.py:44, 47-50`.

---

## §2. 배포·환경변수·보안

### 2.1 환경변수 인벤토리

소스: `app/core/config.py:21-27`

| 이름 | 용도 | 기본값 | Prod 값 출처 | 민감도 |
|------|------|--------|-------------|--------|
| GCP_PROJECT_ID | Vertex AI / GCS 프로젝트 ID | miriart-dev | Cloud Run env (cloudbuild.yaml:40): miriarts | 낮음 |
| GCP_REGION | Cloud Run / 설정 리전 | asia-northeast3 | Cloud Run env | 낮음 |
| GEMINI_LOCATION | Gemini API 호출 리전 | global | cloudbuild.yaml:40 또는 config.py:24 기본값 | 낮음 |
| GCS_BUCKET_NAME | GCS 버킷명 | miriart-bucket | Cloud Run env | 낮음 |
| GOOGLE_APPLICATION_CREDENTIALS | 로컬 개발 SA 키 경로 | "" | Cloud Run: 불필요 (SA 자동 토큰) | 높음 (로컬만) |

Prod에서는 Secret Manager 미사용. Cloud Run SA(`miriart-ai-runner`) 자동 인증으로 Vertex AI / GCS 접근.

### 2.2 보안 경계

소스: cloudbuild.yaml (--no-allow-unauthenticated, --invoker-iam-check)

| 경계 | 보호 방식 | 검증 |
|------|-----------|------|
| 외부 → AI | Cloud Run IAM (invoker-iam-check) | curl https://miriart-ai-...run.app/health → 403 |
| BE → AI | BE SA의 roles/run.invoker IAM 바인딩 | BE WebClient에서 SA 토큰 자동 발급 |
| AI → GCS | AI SA의 roles/storage.objectAdmin | Application Default Credentials |
| AI → Vertex AI | AI SA의 roles/aiplatform.user | 동일 |

### 2.3 Cloud Run 배포

소스: `cloudbuild.yaml` (전체). 배포 명령: `gcloud builds submit --config=cloudbuild.yaml --project=miriarts --region=asia-northeast3`. 포트 8080 (cloudbuild.yaml:29), 요청 타임아웃 120s (32), env (40).

---

## §3. 로깅·관측

### 3.1 로그 이벤트 카탈로그

#### HTTP 요청 로그 (미들웨어)

소스: `app/middleware/request_context.py`

| 이벤트 | 레벨 | 필드 | 설명 |
|--------|------|------|------|
| http_request | INFO | request_id, method, path, status, latency_s | 모든 HTTP 요청 (제외: /health, /internal/ai/health). EXCLUDE_PATHS (21). |

라우트는 `/health`만 정의 (app/main.py:47-50). `/internal/ai/health`는 미들웨어 제외 경로(EXCLUDE_PATHS)로만 등록, 해당 라우트 없음.

#### Gemini LLM 호출 로그

소스: `app/core/gemini_client.py`

| 이벤트 | 레벨 | 필드 | 설명 |
|--------|------|------|------|
| gemini_call_start | INFO | purpose, model | 호출 시작 |
| gemini_call_success | INFO | purpose, model, latency_s, output_len | LLM 호출 성공 |
| gemini_call_timeout | WARNING | purpose, model, timeout_s, latency_s | LLM 타임아웃 |
| gemini_call_rate_limited | WARNING | purpose, model, latency_s | Gemini 429 |
| gemini_call_error | ERROR | purpose, model, error, latency_s | LLM 호출 실패 |

purpose 값: "analyze_artwork", "chat", "image_edit", "summarize_answers", "draft_from_question"

#### 에러 핸들러 로그

소스: `app/core/error_handler.py:43-52, 59-82, 84-98`

| 이벤트 | 레벨 | 필드 | 설명 |
|--------|------|------|------|
| handled_error | WARNING | path, method, error_code, status, detail | 커스텀 예외 처리 (55-56 body) |
| request_validation_error | WARNING | path, errors (500자 제한) | Pydantic 유효성 실패 (69-82) |
| unhandled_exception | ERROR | path, method, error, traceback (2000자 제한) | 미처리 예외 (95-98) |

#### 앱 라이프사이클 로그

소스: `app/main.py`

| 이벤트 | 레벨 | 설명 |
|--------|------|------|
| miriart-ai starting up | INFO | 앱 시작 |
| GenAI client warmed up | INFO | Gemini 클라이언트 초기화 완료 |
| miriart-ai shutting down | INFO | 앱 종료 |

### 3.2 Cloud Logging 조회

```bash
# 전체 AI 서비스 로그 (최근 20건)
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-ai"' \
  --project=miriarts --limit=20 \
  --format="table(timestamp,severity,jsonPayload.message)"

# Gemini 호출 에러만
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-ai"
   AND jsonPayload.message="gemini_call_error"' \
  --project=miriarts --limit=10 \
  --format="table(timestamp,jsonPayload.purpose,jsonPayload.model,jsonPayload.error)"

# Gemini 타임아웃만
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-ai"
   AND jsonPayload.message="gemini_call_timeout"' \
  --project=miriarts --limit=10 \
  --format="table(timestamp,jsonPayload.purpose,jsonPayload.model,jsonPayload.timeout_s)"

# 미처리 예외
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-ai"
   AND jsonPayload.message="unhandled_exception"' \
  --project=miriarts --limit=5 \
  --format="table(timestamp,jsonPayload.error,jsonPayload.traceback)"

# 특정 request_id로 요청 추적
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-ai"
   AND jsonPayload.request_id="abc123def456"' \
  --project=miriarts --limit=20
```

---

*문서 끝. 유일 참조는 코드. 갱신 시 app/ 및 cloudbuild.yaml 실제 라인과 교차검증.*
