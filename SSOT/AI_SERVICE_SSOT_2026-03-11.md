# MiriArt AI 서비스 — 코드 기준 SSOT

> **기준 소스**: FastAPI 코드라인 (2026-03-11)
> **목적**: Gemini 클라이언트 설정 · 타임아웃/리트라이 · 에러 계약 · 엔드포인트/스키마 · 인프라 · 로깅을 코드 SSOT 기준으로 정리

---

## 1. Gemini 클라이언트 설정 + 리전 분리

### 1.1 Settings 필드 (app/core/config.py)

| 필드 | 타입 | 기본값 | env override | 용도 |
|------|------|--------|-------------|------|
| `gcp_project_id` | str | `"miriart-dev"` | `GCP_PROJECT_ID` | GCP 프로젝트. prod: `miriarts` |
| `gcp_region` | str | `"asia-northeast3"` | `GCP_REGION` | Cloud Run 배포 리전 |
| `gemini_location` | str | `"global"` | `GEMINI_LOCATION` | **Gemini API 호출 리전 (신규)**. Cloud Run 리전과 분리. |
| `gcs_bucket_name` | str | `"miriart-bucket"` | `GCS_BUCKET_NAME` | GCS 버킷명 |
| `google_application_credentials` | str | `""` | `GOOGLE_APPLICATION_CREDENTIALS` | 로컬 SA 키 경로. Cloud Run에서는 불필요. |

- `.env` 파일 또는 환경변수로 override (Pydantic BaseSettings, case_sensitive=False).
- `get_settings()` → `@lru_cache` 싱글턴.

### 1.2 GenAI Client 설정 (app/core/gemini_client.py)

| 항목 | 값 | 코드 위치 | 비고 |
|------|-----|-----------|------|
| SDK | `google-genai` (Vertex AI 백엔드) | :12-13 | `vertexai=True` |
| project | `settings.gcp_project_id` | :31 | prod: `miriarts` |
| location | `settings.gemini_location` | :32 | **`"global"` (변경됨)**. 기존: `settings.gcp_region` |
| HTTP timeout | `55,000ms` (55초) | :34 | BE 65s - 10s 마진 |
| retry attempts | `2` (초기 1 + 재시도 1) | :36 | |
| retry initial_delay | `1.0s` | :37 | |
| retry max_delay | `8.0s` | :38 | |
| retry exp_base | `2.0` | :39 | 지수 백오프 |
| retry jitter | `0.5` | :40 | |
| retry http_status_codes | `[429, 500, 502, 503, 504]` | :41 | **404는 재시도 안 함** |
| AFC | `disable=True` | :88 | Automatic Function Calling 비활성 |

### 1.3 모델 상수 (GeminiModel)

| 상수 | 모델 ID | 코드 위치 | 사용처 |
|------|---------|-----------|--------|
| `FLASH` | `gemini-2.5-flash` | :57 | analyze, chat(FAST/SEARCH/IMAGE_EDIT), qa, image_edit |
| `PRO` | `gemini-2.5-pro` | :58 | chat(CHAT_PRO/THINKING) |
| `FLASH_LITE` | `gemini-2.0-flash-lite` | :59 | (예비/폴백용, 현재 미사용) |

### 1.4 리전 분리 변경 diff

```diff
--- a/app/core/config.py
+++ b/app/core/config.py
@@ -21,6 +21,9 @@
     gcp_project_id: str = "miriart-dev"
     gcp_region: str = "asia-northeast3"
+    # Gemini API 호출 리전. Cloud Run 리전(gcp_region)과 분리하여 쿼터·모델 가용성 확보.
+    # prod: GEMINI_LOCATION=global (또는 us-central1). GCP_REGION=asia-northeast3은 Cloud Run 배포용.
+    gemini_location: str = "global"
     gcs_bucket_name: str = "miriart-bucket"
     google_application_credentials: str = ""
```

```diff
--- a/app/core/gemini_client.py
+++ b/app/core/gemini_client.py
@@ -20,9 +20,6 @@
 logger = logging.getLogger(__name__)

-# [DEBUG] SDK 내부 HTTP 호출 추적 — 배포 후 로그 확인 완료 시 제거
-logging.getLogger("google.genai").setLevel(logging.DEBUG)
-logging.getLogger("httpx").setLevel(logging.DEBUG)
-
 _client: Optional[genai.Client] = None

@@ -32,7 +29,7 @@
         _client = genai.Client(
             vertexai=True,
             project=settings.gcp_project_id,
-            location=settings.gcp_region,
+            location=settings.gemini_location,  # Cloud Run 리전(gcp_region)과 분리
             http_options=types.HttpOptions(
```

```diff
--- a/cloudbuild.yaml
+++ b/cloudbuild.yaml
@@ -40,7 +40,7 @@
-      - '--set-env-vars=GCP_PROJECT_ID=miriarts,GCP_REGION=asia-northeast3,GCS_BUCKET_NAME=miriart-bucket'
+      - '--set-env-vars=GCP_PROJECT_ID=miriarts,GCP_REGION=asia-northeast3,GCS_BUCKET_NAME=miriart-bucket,GEMINI_LOCATION=global'
```

### 1.5 prod 구성 전제

```
Cloud Run 인스턴스: asia-northeast3 (서울)
Gemini API 호출:    global (Google 자동 라우팅)
GCS 버킷:          asia-northeast3 (miriart-bucket)
```

---

## 2. 타임아웃 / 리트라이 / 에러 매핑

### 2.1 서비스별 타임아웃·리트라이

| 서비스 | 함수 | 파일:라인 | model | timeout_override_s | effective_timeout | SDK attempts | response_mime_type |
|--------|------|-----------|-------|-------------------|-------------------|-------------|-------------------|
| **analyze** | `analyze_artwork()` | analyze_service.py:110 | FLASH | 미지정 | **55s** | 2 | `application/json` |
| **chat** | `chat()` | chat_service.py:81 | MODEL_MAP 분기 | 미지정 | **55s** | 2 | 없음 |
| **image_edit** | `edit_image()` | image_edit_service.py:38 | FLASH | **25** | **25s** | 2 | 없음 |
| **qa/summarize** | `summarize_answers()` | qa_service.py:63 | FLASH | 미지정 | **55s** | 2 | `application/json` |
| **qa/draft** | `draft_from_question()` | qa_service.py:101 | FLASH | 미지정 | **55s** | 2 | `application/json` |

> **핵심**: `call_gemini()` 기본값 = 55s, image_edit만 25s override.

### 2.2 타임아웃 체인

```
FE 요청 → Java BE WebClient (65s) → FastAPI call_gemini (55s / 25s) → SDK HTTP (55s) → Vertex AI
                                        ↑ asyncio.wait_for       ↑ HttpOptions.timeout
                                        Python-level 보장         SDK-level (리트라이 포함)
```

- BE 65s > AI 55s → AI가 먼저 응답/실패하여 BE timeout 발동 방지 (10s 마진).
- image_edit은 25s로 더 짧아 BE timeout 문제 없음.

### 2.3 예외 계층 (app/core/exceptions.py)

| 예외 클래스 | error_code | 발생 조건 | HTTP Status | 코드 위치 |
|-------------|------------|-----------|-------------|-----------|
| `MiriArtAIError` (base) | `"UNKNOWN"` | — | — | exceptions.py:9 |
| `LLMTimeoutError` | `LLM_TIMEOUT` | `asyncio.wait_for` timeout 초과 | **504** | gemini_client.py:158-171 |
| `LLMRateLimitError` | `LLM_RATE_LIMITED` | Vertex AI 429 / `RESOURCE_EXHAUSTED` | **429** | gemini_client.py:173-188 |
| `LLMServiceError` | `LLM_SERVICE_ERROR` | Vertex AI 4xx(429제외)/5xx, SDK 에러 | **502** | gemini_client.py:189-202 |
| `LLMParsingError` | `LLM_PARSING_ERROR` | Gemini 응답 JSON 파싱 실패 (`json.loads` / `KeyError`) | **502** | analyze_service.py:140, qa_service.py:76,114 |
| `GCSError` | `GCS_ERROR` | GCS 다운로드/업로드 실패 | **502** | analyze_service.py:83, image_edit_service.py:70 |
| `ValidationError` | `VALIDATION_ERROR` | base64 디코딩 실패, 입력 검증 | **400** | chat_service.py:72, image_edit_service.py:31, qa_service.py:90 |

### 2.4 에러 핸들러 매핑 (app/core/error_handler.py)

| 핸들러 | 대상 | HTTP | body.code | body 필드 |
|--------|------|------|-----------|-----------|
| `miriart_error_handler` | `MiriArtAIError` 하위 | ERROR_MAP 참조 | 예외별 상이 | `{"code", "message"}` |
| `validation_error_handler` | `RequestValidationError` | 400 | `VALIDATION_ERROR` | `{"code", "message", "errors"}` |
| `catch_all_handler` | `Exception` | 500 | `INTERNAL_ERROR` | `{"code", "message"}` |

> **에러 응답 body 필드명은 `"message"`** (not `"detail"`). 코드 기준: error_handler.py:56, :73, :97.

### 2.5 retry attempts 변경 제안 (2→3)

변경 시 영향받는 코드:

| 파일 | 라인 | 현재 | 변경 후 |
|------|------|------|---------|
| `gemini_client.py` | :36 | `attempts=2` | `attempts=3` |
| `gemini_client.py` | :37 (주석) | "1회 재시도" | "2회 재시도" |
| `gemini_client.py` | :111 (로그) | `"sdk_attempts": 2` | `"sdk_attempts": 3` |

```diff
# 예시 diff — 별도 승인 후 적용
--- a/app/core/gemini_client.py
+++ b/app/core/gemini_client.py
@@ -36,7 +36,7 @@
             http_options=types.HttpOptions(
                 timeout=55 * 1000,
                 retry_options=types.HttpRetryOptions(
-                    attempts=2,  # 429 등 일시적 에러 시 1회 재시도
+                    attempts=3,  # 429 등 일시적 에러 시 2회 재시도
                     initial_delay=1.0,
@@ -111,7 +111,7 @@
-            "sdk_attempts": 2,
+            "sdk_attempts": 3,
```

> **미적용 상태. 승인 후 적용.**

---

## 3. 엔드포인트 / 스키마 / 내부 계약

### 3.1 전체 라우트 표

| Path | Method | Request Schema | Response Schema | 서비스 함수 | 비고 |
|------|--------|---------------|----------------|-------------|------|
| `/health` | GET | — | `{"status":"ok"}` | inline (main.py:48) | 헬스체크 |
| `/internal/ai/analyze` | POST | `InternalAnalyzeRequest` | `InternalAnalyzeResponse` | `analyze_service.analyze_artwork` | 작품 5축 분석 |
| `/internal/ai/chat` | POST | `InternalChatRequest` | `InternalChatResponse` | `chat_service.chat` | AI 멘토 채팅 |
| `/internal/ai/edit-image` | POST | `InternalImageEditRequest` | `InternalImageEditResponse` | `image_edit_service.edit_image` | 이미지 편집 |
| `/internal/ai/summarize-answers` | POST | `SummarizeAnswersRequest` | `SummarizeAnswersResponse` | `qa_service.summarize_answers` | QA 답변 요약 |
| `/internal/ai/draft-from-question` | POST | `DraftFromQuestionRequest` | `DraftFromQuestionResponse` | `qa_service.draft_from_question` | QA 초안 생성 |

> 모든 `/internal/ai/*` 라우트는 Java BE에서만 호출 (Cloud Run IAM + OIDC 보호). FE 직접 접근 불가.
> 모든 스키마는 **camelCase 직렬화** (`alias_generator=to_camel, serialize_by_alias=True`).

### 3.2 스키마 필드 상세

#### InternalAnalyzeRequest (analyze.py)

| 필드 | JSON alias | 타입 | nullable | 기본값 | BE 사용 |
|------|-----------|------|----------|--------|---------|
| `gcs_uri` | `gcsUri` | str | No | — | ✅ |
| `analysis_type` | `analysisType` | str (`basic`\|`major`) | No | — | ✅ |
| `problem_text` | `problemText` | Optional[str] | Yes | `None` | ✅ |

#### InternalAnalyzeResponse (analyze.py)

| 필드 | JSON alias | 타입 | nullable | 기본값 | BE 사용 |
|------|-----------|------|----------|--------|---------|
| `grade` | `grade` | str (`A`\|`B`\|`C`\|`D`\|`F`) | No | — | ✅ |
| `total_score` | `totalScore` | float | No | — | ✅ |
| `radar_data` | `radarData` | RadarData | No | — | ✅ |
| `fix_scope` | `fixScope` | str (`StructureRebuild`\|`DetailTuning`) | No | — | ✅ |
| `comment` | `comment` | str | No | — | ✅ |
| `university_predictions` | `universityPredictions` | List[UniversityPrediction] | No | `[]` | ✅ |

#### RadarData (analyze.py)

| 필드 | 타입 | BE 사용 |
|------|------|---------|
| `density` | float | ✅ |
| `form` | float | ✅ |
| `completion` | float | ✅ |
| `relevance` | float | ✅ |
| `thinking` | float | ✅ |

#### UniversityPrediction (analyze.py)

| 필드 | JSON alias | 타입 | BE 사용 |
|------|-----------|------|---------|
| `university` | `university` | str | ✅ |
| `major` | `major` | str | ✅ |
| `line` | `line` | str (`TOP`\|`HIGH`\|`MID`\|`LOW`) | ✅ |
| `probability` | `probability` | int | ✅ |
| `similar_accepted_count` | `similarAcceptedCount` | int | ✅ |

#### InternalChatRequest (chat.py)

| 필드 | JSON alias | 타입 | nullable | 기본값 | BE 사용 |
|------|-----------|------|----------|--------|---------|
| `model_type` | `modelType` | str (`CHAT_PRO`\|`FAST`\|`THINKING`\|`SEARCH`\|`IMAGE_EDIT`) | No | — | ✅ |
| `message` | `message` | str | No | — | ✅ |
| `session_id` | `sessionId` | Optional[str] | Yes | `None` | ✅ |
| `sticky_context` | `stickyContext` | Optional[StickyContext] | Yes | `None` | ✅ |
| `image_base64` | `imageBase64` | Optional[str] | Yes | `None` | ✅ |
| `image_mime_type` | `imageMimeType` | Optional[str] | Yes | `None` | ✅ |
| `history` | `history` | Optional[List[HistoryItem]] | Yes | `[]` | ✅ |

#### StickyContext (chat.py)

| 필드 | JSON alias | 타입 | nullable | BE 사용 |
|------|-----------|------|----------|---------|
| `grade` | `grade` | str | No | ✅ |
| `score` | `score` | float | No | ✅ |
| `fix_scope` | `fixScope` | str | No | ✅ |
| `radar_data` | `radarData` | Optional[Dict[str, float]] | Yes | △ |

#### InternalChatResponse (chat.py)

| 필드 | JSON alias | 타입 | 기본값 | BE 사용 |
|------|-----------|------|--------|---------|
| `text` | `text` | str | — | ✅ |
| `grounding_urls` | `groundingUrls` | List[str] | `[]` | ✅ |
| `quick_replies` | `quickReplies` | List[str] | `[]` | ✅ |

#### InternalImageEditRequest (image_edit.py)

| 필드 | JSON alias | 타입 | BE 사용 |
|------|-----------|------|---------|
| `image_base64` | `imageBase64` | str | ✅ |
| `prompt` | `prompt` | str | ✅ |

#### InternalImageEditResponse (image_edit.py)

| 필드 | JSON alias | 타입 | nullable | BE 사용 |
|------|-----------|------|----------|---------|
| `text` | `text` | str | No | ✅ |
| `image_url` | `imageUrl` | Optional[str] | Yes | ✅ |

#### SummarizeAnswersRequest (qa.py)

| 필드 | JSON alias | 타입 | 제약 | BE 사용 |
|------|-----------|------|------|---------|
| `question` | `question` | str | min=1, max=2000 | ✅ |
| `answers` | `answers` | List[str] | min=1, max=20 | ✅ |

#### SummarizeAnswersResponse (qa.py)

| 필드 | 타입 | BE 사용 |
|------|------|---------|
| `summary` | str | ✅ |
| `supplement` | str | ✅ |

#### DraftFromQuestionRequest (qa.py)

| 필드 | JSON alias | 타입 | nullable | 제약 | BE 사용 |
|------|-----------|------|----------|------|---------|
| `title` | `title` | str | No | min=1, max=200 | ✅ |
| `content` | `content` | str | No | min=1, max=5000 | ✅ |
| `image_base64` | `imageBase64` | Optional[str] | Yes | — | ✅ |

#### DraftFromQuestionResponse (qa.py)

| 필드 | 타입 | BE 사용 |
|------|------|---------|
| `draft` | str | ✅ |

### 3.3 BE(Java)용 최소 API Contract 필드 세트

> 모든 필드가 BE에서 사용됨. 현재 불필요한 필드 없음. API_CONTRACT에 전체 노출 권장.

---

## 4. 인프라 / 배포 설정

### 4.1 Cloud Run 배포 설정 (cloudbuild.yaml)

| 항목 | 값 | 비고 |
|------|-----|------|
| Region | `asia-northeast3` | Cloud Run 인스턴스 위치 |
| Image | `asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:$COMMIT_SHA` | Artifact Registry |
| Port | `8080` | |
| CPU | `1` (boost enabled) | 콜드스타트 시 CPU 부스트 |
| Memory | `1Gi` | |
| Timeout | `120s` | Cloud Run 요청 최대 시간 |
| Min instances | `1` | 콜드스타트 방지 |
| Max instances | `20` | |
| Concurrency | `10` | 인스턴스당 동시 요청 |
| Auth | `--no-allow-unauthenticated` + `--invoker-iam-check` | IAM 보호 |
| Service Account | `miriart-ai-runner@miriarts.iam.gserviceaccount.com` | |

| 환경변수 | 값 | 용도 |
|---------|-----|------|
| `GCP_PROJECT_ID` | `miriarts` | GCP 프로젝트 |
| `GCP_REGION` | `asia-northeast3` | Cloud Run 리전 / GCS 리전 |
| `GCS_BUCKET_NAME` | `miriart-bucket` | GCS 버킷 |
| `GEMINI_LOCATION` | `global` | **Gemini API 호출 리전 (신규)** |

### 4.2 Dockerfile

| 항목 | 값 |
|------|-----|
| Base image | `python:3.11-slim` |
| EXPOSE | `8080` |
| CMD | `uvicorn app.main:app --host 0.0.0.0 --port 8080` |
| Workers | 1 (uvicorn 기본) |
| Log level | uvicorn 기본 (info) |

### 4.3 네트워크 경로 (리전 분리 구성)

```
사용자(한국) → Vercel(Edge) → Java BE Cloud Run (asia-northeast3, 서울)
                                  ↓ OIDC
                              FastAPI AI Cloud Run (asia-northeast3, 서울)
                                  ├─ GCS download (asia-northeast3 → asia-northeast3) ← 동일 리전, ~1-5ms
                                  ├─ Gemini API (global endpoint)
                                  │   └─ Google 내부 네트워크로 최적 리전 자동 라우팅
                                  │   └─ 예상 추가 레이턴시: ~50-200ms (vs 동일 리전)
                                  │   └─ 쿼터: global은 리전별 제한 없이 전체 프로젝트 쿼터 적용
                                  └─ GCS upload (asia-northeast3 → asia-northeast3) ← 동일 리전
```

> **"global" location 선택 이유**: `us-central1`보다 레이턴시 예측 가능하고 (Google이 최적 리전 자동 선택),
> 리전별 쿼터 제한에 걸리지 않음. 최신 모델도 global에서 우선 지원됨.

---

## 5. 로깅 / 관측성

### 5.1 로깅 설정 (app/core/logging_config.py)

| 항목 | 값 | 코드 위치 |
|------|-----|-----------|
| Handler | `StreamHandler(sys.stdout)` | :15 |
| Formatter | `JsonFormatter` (python-json-logger) | :16-18 |
| 출력 필드 | `timestamp`, `severity`, `name`, `message` + extra | :17 |
| Root level | `INFO` | :22 |
| uvicorn.access | `WARNING` (노이즈 감소) | :24 |

### 5.2 DEBUG 로깅 제거 (변경 완료)

```diff
--- a/app/core/gemini_client.py
+++ b/app/core/gemini_client.py
-# [DEBUG] SDK 내부 HTTP 호출 추적 — 배포 후 로그 확인 완료 시 제거
-logging.getLogger("google.genai").setLevel(logging.DEBUG)
-logging.getLogger("httpx").setLevel(logging.DEBUG)
```

> `google.genai`와 `httpx` 로거의 DEBUG 레벨 설정이 prod에서 대량 로그 노이즈 + 성능 영향을 유발.
> root logger가 INFO이므로 제거 후 이 두 로거도 INFO 이상만 출력.

### 5.3 prod 운영 로그 식별 가이드

#### 에러/슬로우 콜 로그 키워드

| 이벤트 | logger | level | 메시지 키워드 | 의미 | Cloud Logging 필터 예시 |
|--------|--------|-------|---------------|------|------------------------|
| Gemini 타임아웃 | `app.core.gemini_client` | WARNING | `gemini_call_timeout` | asyncio.wait_for 초과 (55s/25s) | `jsonPayload.message="gemini_call_timeout"` |
| Gemini 429 | `app.core.gemini_client` | WARNING | `gemini_call_rate_limited` | Vertex AI 429, SDK 재시도 후에도 실패 | `jsonPayload.message="gemini_call_rate_limited"` |
| Gemini 일반 에러 | `app.core.gemini_client` | ERROR | `gemini_call_error` | 404/5xx 등 비-429 에러 | `jsonPayload.message="gemini_call_error"` |
| Gemini 성공 | `app.core.gemini_client` | INFO | `gemini_call_success` | 정상 완료. `latency_s` 필드로 슬로우 콜 탐지 | `jsonPayload.message="gemini_call_success" AND jsonPayload.latency_s>10` |
| 비즈니스 에러 | `app.core.error_handler` | WARNING | `handled_error` | MiriArtAIError 계열 예외 처리 | `jsonPayload.message="handled_error"` |
| 미처리 예외 | `app.core.error_handler` | ERROR | `unhandled_exception` | 예상치 못한 Exception | `jsonPayload.message="unhandled_exception"` |
| HTTP 요청 | `app.middleware.request_context` | INFO | `http_request` | 모든 요청의 status/latency 기록 | `jsonPayload.message="http_request" AND jsonPayload.status>=500` |
| 밸리데이션 에러 | `app.core.error_handler` | WARNING | `request_validation_error` | Pydantic 밸리데이션 실패 | `jsonPayload.message="request_validation_error"` |

#### 슬로우 콜 탐지 기준 (권장)

- `gemini_call_success`의 `latency_s` > **10초**: 주의
- `gemini_call_success`의 `latency_s` > **30초**: 경고
- `http_request`의 `latency_s` > **20초**: 전체 요청 기준 주의

#### Gemini 호출 로그 extra 필드

```json
{
  "message": "gemini_call_start",
  "purpose": "analyze_artwork",
  "model": "gemini-2.5-flash",
  "effective_timeout_s": 55,
  "content_parts": ["Part(image/jpeg)", "Part"],
  "has_image": true,
  "response_mime_type": "application/json",
  "afc_disabled": true,
  "sdk_attempts": 2,
  "sdk_timeout_ms": 55000
}
```

---

## 부록: 에러 응답 형식 (전체)

### 정상 에러 (MiriArtAIError 계열)

```json
{
  "code": "LLM_SERVICE_ERROR",
  "message": "Gemini 'analyze_artwork' failed: ClientError: ..."
}
```

### 밸리데이션 에러

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Request validation failed",
  "errors": [
    {"field": "gcs_uri", "message": "field required"}
  ]
}
```

### 미처리 예외

```json
{
  "code": "INTERNAL_ERROR",
  "message": "Internal server error"
}
```

> **모든 에러 응답의 텍스트 필드명은 `"message"`**. `"detail"`이 아님.

---

*문서 끝 — 코드 기준 2026-03-11*
