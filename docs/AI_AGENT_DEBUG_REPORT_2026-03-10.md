# miriart-ai FastAPI 디버깅 리포트 (2026-03-10)

> 에이전트용 코드 탐색·체크포인트·Cloud Run·헬스체크 검증 결과.
> **과거 스냅샷.** 현재 코드: 55s (gemini_client.py), image_edit 25s (GEMINI_IMAGE_EDIT_TIMEOUT_S).

---

## 1. AI 라우팅 상태

| 항목 | 내용 |
|------|------|
| **Router prefix** | `/internal/ai` |
| **등록 위치** | `app/main.py:43` — `app.include_router(ai.router, prefix="/internal/ai", tags=["AI Internal"])` |

### 등록된 엔드포인트

| Method | Path | 핸들러 | 용도 |
|--------|------|--------|------|
| POST | `/internal/ai/analyze` | `analyze()` | GCS URI 이미지 → Gemini Vision 5축 분석 |
| POST | `/internal/ai/chat` | `chat()` | 히스토리·메시지(이미지可选) → AI 멘토 응답 |
| POST | `/internal/ai/edit-image` | `edit_image()` | base64 이미지+프롬프트 → Gemini 편집 → GCS URL |
| POST | `/internal/ai/summarize-answers` | `api_summarize_answers()` | Q&A 답변 요약 (summary, supplement) |
| POST | `/internal/ai/draft-from-question` | `api_draft_from_question()` | 질문 제목·내용(이미지可选) → 답변 초안 |

- **헬스**: `GET /health` (prefix 없음) — `app/main.py:46-49`

---

## 2. 스키마 (Pydantic · camelCase)

- **공통 설정**: `ConfigDict(populate_by_name=True, alias_generator=to_camel, serialize_by_alias=True)`  
  → 요청/응답 필드가 **camelCase**로 직렬화·역직렬화 (Java BE와 계약 일치).

### InternalAnalyzeRequest 예시

| Python 필드 | JSON alias (요청/응답) |
|-------------|-------------------------|
| `gcs_uri` | `gcsUri` |
| `analysis_type` | `analysisType` |
| `problem_text` | `problemText` |

- **InternalAnalyzeResponse**: `grade`, `totalScore`, `radarData`, `fixScope`, `comment`, `universityPredictions` 등 동일 규칙.
- **InternalChatRequest**: `modelType`, `sessionId`, `stickyContext`, `imageBase64`, `imageMimeType`, `history`.
- **InternalImageEditRequest**: `imageBase64`, `prompt`.

---

## 3. 내부 연동 상태

### Gemini 호출

| 항목 | 값 |
|------|-----|
| **진입점** | `app/core/gemini_client.py` — `call_gemini()` |
| **모델** | `GeminiModel.FLASH` (= `gemini-2.5-flash`), `GeminiModel.PRO` (= `gemini-2.5-pro`) |
| **기본 timeout** | 28s (당시). **현재 코드: 55s** (gemini_client.py:21, 89-90). |
| **image_edit** | 당시 55. **현재: 25s** (GEMINI_IMAGE_EDIT_TIMEOUT_S, gemini_client.py:26). |
| **temperature** | analyze 0.3, chat 0.7, image_edit 0.4, summarize/draft 0.3 |
| **재시도** | SDK `HttpRetryOptions`: 429, 500, 502, 503, 504, attempts=3 |

- **환경변수**: `get_settings()` → `gcp_project_id`, `gcp_region` (Vertex AI용).  
  기본값: `miriart-dev`, `asia-northeast3` — Cloud Run에서는 `GCP_PROJECT_ID`, `GCP_REGION`으로 오버라이드.

### GCS 호출

| 항목 | 값 |
|------|-----|
| **설정** | `app/core/config.py` — `Settings.gcs_bucket_name`, `Settings.gcp_project_id` |
| **기본값** | `gcs_bucket_name="miriart-bucket"`, `gcp_project_id="miriart-dev"` |
| **Cloud Run** | env `GCS_BUCKET_NAME=miriart-bucket`, `GCP_PROJECT_ID=miriarts` |
| **사용처** | `analyze_service`: `GcsService(bucket_name=..., project_id=...).download_as_bytes(gcs_uri)` |
| **사용처** | `image_edit_service`: `GcsService(...).upload_bytes(blob_path, data)` (경로 `edited/{uuid}.jpg`) |

- 인증: Cloud Run에서는 서비스 계정(`miriart-ai-runner`) ADC 자동 사용.

---

## 4. 에러 핸들러 매핑

`app/core/error_handler.py` — `ERROR_MAP`:

| 예외 | HTTP status | code (JSON) |
|------|-------------|-------------|
| `LLMTimeoutError` | **504** | `LLM_TIMEOUT` |
| `LLMServiceError` | **502** | `LLM_SERVICE_ERROR` |
| `LLMParsingError` | **502** | `LLM_PARSING_ERROR` |
| `GCSError` | **502** | `GCS_ERROR` |
| `ValidationError` | **400** | `VALIDATION_ERROR` |

- `RequestValidationError` (FastAPI): 400, `VALIDATION_ERROR`, `errors` 배열.
- 미등록 예외: 500, `INTERNAL_ERROR`.

---

## 5. Cloud Run 배포 상태 (2026-03-10 기준)

| 항목 | 값 |
|------|-----|
| **서비스** | `miriart-ai` |
| **리전** | `asia-northeast3` |
| **프로젝트** | `miriarts` |
| **최신 리비전** | `miriart-ai-00004-gfx` |
| **이미지** | `asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:21f0023` |
| **URL** | `https://miriart-ai-gzjczkus6q-du.a.run.app` (및 `...-946560105497...`) |

**환경변수 (컨테이너)**  
- `GCP_PROJECT_ID=miriarts`  
- `GCP_REGION=asia-northeast3`  
- `GCS_BUCKET_NAME=miriart-bucket`

---

## 6. 로그 분석 (최근 1~7일)

- **최근 요청 수**: 최근 1일 내 Cloud Run 요청 로그 다수 — 대부분 **403 Unauthorized** (인증 없이 호출).
- **요청 예**: `POST /internal/ai/analyze` (ReactorNetty/1.2.2), `GET /health` (curl) → 403.
- **의도**: `--no-allow-unauthenticated` + IAM invoker 정책으로 **BE SA(`miriart-be-runner`)만 호출 가능**. 외부/비인증 호출 403은 정상.
- **에러 패턴**:
  - **5xx**: 최근 7일 내 502 한 건 (2026-03-03) — 상세 메시지는 로그 상세에서 확인 필요.
  - **LLM_TIMEOUT / gemini_call_timeout**: 최근 로그에서 별도 집계 없음 (추가 조회 시 `jsonPayload.message=~"gemini_call_timeout"` 또는 `handled_error` + `error_code=LLM_TIMEOUT` 사용).

---

## 7. 헬스 체크

- **엔드포인트**: `GET /health` → `{"status": "ok"}` (prefix 없음, 루트).
- **Lifespan** (`app/main.py`):
  1. `setup_logging()`
  2. `get_genai_client()` → GenAI 클라이언트 warm-up (Vertex AI 설정만 로드, 실제 모델 호출 없음)
  3. `yield` 후 shutdown 로그

→ 서비스 기동 시 GenAI client 초기화 성공 시점에 "GenAI client warmed up" 로그 출력.  
→ `/health`는 인증 필요 시 IAM 통과 시 200, 비인증 시 403 (Cloud Run 정책에 따름).

---

## 8. 발견된 문제

| # | 문제 | 코드 위치 | 비고 |
|---|------|-----------|------|
| 1 | **없음** | — | 라우트 prefix/path, 스키마 alias, 환경변수, 에러 매핑 모두 코드·문서와 일치. |
| 2 | BE → AI 403 가능성 | — | 최근 로그에 BE(ReactorNetty)에서 `/internal/ai/analyze` 403 다수. BE가 **Bearer ID 토큰**을 붙여 호출하는지, 그리고 **호출 URL**이 현재 배포된 서비스 URL과 일치하는지 확인 필요. (Cloud Run 서비스 URL이 `...-946560105497...` / `...-gzjczkus6q-du...` 등으로 다를 수 있음.) |
| 3 | (선택) 502 상세 | 2026-03-03 502 1건 | 원인 파악 시 Cloud Logging에서 해당 시간대 `jsonPayload`(handled_error, gemini_call_error 등) 조회 권장. |

---

## 9. 참고 파일 목록

- `app/main.py` — 앱 구성, lifespan, router 등록, `/health`
- `app/routers/ai.py` — `/internal/ai/*` 엔드포인트 5개
- `app/services/analyze_service.py`, `chat_service.py`, `image_edit_service.py`, `qa_service.py` — 비즈니스 로직
- `app/core/gemini_client.py` — GenAI 클라이언트, `call_gemini()`
- `app/core/config.py` — `Settings`, `get_settings()`
- `app/core/error_handler.py` — `ERROR_MAP`, 전역 핸들러
- `app/services/gcs_service.py` — GCS 다운로드/업로드/Signed URL
- `app/schemas/analyze.py`, `chat.py`, `image_edit.py`, `qa.py` — camelCase 스키마
