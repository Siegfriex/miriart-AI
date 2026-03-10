# MiriArt-AI 종합 개발 명세서 v1.0

> **문서 성격**: miriart-ai (Python/FastAPI) 마이크로서비스의 식별된 전체 이슈를 범주화하고, 각 범주별 구체적 코드/설정/프롬프트를 포함한 실행 가능한 개발 명세
> **대상 독자**: MiriArt CTO / 로컬 에이전트 (Cursor)
> **기준 문서**: SSOT v1.2, FSD v2.0, API_CONTRACT v1.0, PRD v2.2
> **작성일**: 2026-03-09

---

## 0. 이슈 범주 체계 (Issue Taxonomy)

| 범주 ID | 범주명 | 이슈 수 | 우선순위 | 의존성 |
|---------|--------|---------|---------|--------|
| **A** | 보안 / IAM | 2 | P0 CRITICAL | 없음 (즉시) |
| **B** | LLM 호출 / SDK | 4 | P0 CRITICAL | A 완료 후 |
| **C** | 에러 모델 / API 계약 | 3 | P1 HIGH | B와 병행 |
| **D** | 인프라 / Cloud Run | 5 | P1 HIGH | A 완료 후 |
| **E** | 관측성 / 로깅 | 3 | P2 MEDIUM | B, C 완료 후 |
| **F** | BigQuery RAG (향후) | 2 | P3 LOW | E 완료 후 |
| **G** | C4 AI QA 기능 | 2 | P2 MEDIUM | B, C 완료 후 |
| **H** | GCS / Storage | 2 | P1 HIGH | A 완료 후 |

### 의존성 그래프

```
A (보안) ---+---> B (LLM SDK) ---+---> E (관측성) ---> F (BigQuery RAG)
            |                    |
            +---> D (인프라)     +---> G (C4 AI QA)
            |                    |
            +---> H (GCS)       +---> C (에러 모델)
```

---

## 1. 범주 A: 보안 / IAM

### A1. Cloud Run invoker-iam-disabled 해제

**현황**: `run.googleapis.com/invoker-iam-disabled: true` 설정으로 IAM 체크가 우회되어 사실상 퍼블릭 엔드포인트 상태

**위험도**: CRITICAL -- AI API abuse, 비용 폭주, 정보 노출

**조치**:

```bash
# invoker IAM 체크 재활성화
gcloud run services update miriart-ai \
  --region=asia-northeast3 \
  --invoker-iam-check

# miriart-be-runner SA에게만 Invoker 역할 부여 확인
gcloud run services add-iam-policy-binding miriart-ai \
  --region=asia-northeast3 \
  --member="serviceAccount:miriart-be-runner@miriarts.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

**검증 방법**:
```bash
# 외부에서 직접 호출 시 403이 떨어져야 정상
curl -s -o /dev/null -w "%{http_code}" \
  https://miriart-ai-XXXXX.asia-northeast3.run.app/health
# 기대: 403

# BE에서 SA 토큰으로 호출 시 200
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token --impersonate-service-account=miriart-be-runner@miriarts.iam.gserviceaccount.com)" \
  https://miriart-ai-XXXXX.asia-northeast3.run.app/health
# 기대: 200
```

### A2. GCS Signed URL 전환 (Phase 2 대비)

**현황**: 현재 GCS public URL로 이미지 반환. Bucket 자체가 public이면 보안 이슈.

**Phase 2 전환안** (API_CONTRACT 6.2 Presigned URL):

```python
# app/services/gcs_service.py
import datetime
from google.cloud import storage
from google.auth import impersonated_credentials, default

class GcsService:
    def __init__(self, bucket_name: str, project_id: str):
        self._bucket_name = bucket_name
        self._project_id = project_id
        self._client = storage.Client(project=project_id)
        self._bucket = self._client.bucket(bucket_name)

    def generate_signed_url(
        self, blob_path: str, expiration_minutes: int = 60
    ) -> str:
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

    def download_as_bytes(self, gcs_uri: str) -> bytes:
        if gcs_uri.startswith("gs://"):
            path = gcs_uri.replace(f"gs://{self._bucket_name}/", "")
        else:
            path = gcs_uri
        blob = self._bucket.blob(path)
        return blob.download_as_bytes()
```

**IAM 전제조건**: `miriart-ai-runner` SA에 `iam.serviceAccounts.signBlob` 권한 필요
```bash
gcloud iam service-accounts add-iam-policy-binding \
  miriart-ai-runner@miriarts.iam.gserviceaccount.com \
  --member="serviceAccount:miriart-ai-runner@miriarts.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

---

## 2. 범주 B: LLM 호출 / SDK 마이그레이션

### B1. vertexai SDK -> google-genai SDK 마이그레이션

**배경**: `vertexai.generative_models`는 2026-06-24 제거 예정. `google-genai` SDK로 전환 필수.

**현재 코드 패턴** (DEPRECATED):
```python
import vertexai
from vertexai.generative_models import GenerativeModel
vertexai.init(project="miriarts", location="asia-northeast3")
model = GenerativeModel("gemini-1.5-flash")
response = model.generate_content(...)
```

**마이그레이션 코드**:

```python
# app/core/gemini_client.py

from google import genai
from google.genai import types
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# ============================
# 1. Client 초기화 (싱글턴)
# ============================
_client: genai.Client | None = None

def get_genai_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_region,
            http_options=types.HttpOptions(
                timeout=28 * 1000,  # 28s (BE 30s - 2s margin)
                retry_options=types.HttpRetryOptions(
                    attempts=3,
                    initial_delay=1.0,
                    max_delay=8.0,
                    exp_base=2.0,
                    jitter=0.5,
                    http_status_codes=[429, 500, 502, 503, 504],
                ),
            ),
        )
        logger.info("GenAI client initialized (project=%s, region=%s)",
                     settings.gcp_project_id, settings.gcp_region)
    return _client


# ============================
# 2. 모델 상수
# ============================
class GeminiModel:
    FLASH = "gemini-2.5-flash"
    PRO = "gemini-2.5-pro"
    FLASH_LITE = "gemini-2.0-flash-lite"


# ============================
# 3. 공통 LLM 호출 래퍼
# ============================
import asyncio
import time
from app.core.exceptions import LLMTimeoutError, LLMServiceError, LLMParsingError

async def call_gemini(
    model: str,
    contents,
    *,
    system_instruction: str | None = None,
    purpose: str = "unknown",
    timeout_override_s: int | None = None,
    temperature: float = 0.7,
    max_output_tokens: int = 4096,
    response_mime_type: str | None = None,
) -> str:
    """
    모든 Gemini 호출의 단일 진입점.
    - asyncio.wait_for로 Python-level timeout 보장
    - 에러를 LLMTimeoutError / LLMServiceError로 분류
    - 구조화 로그 출력
    """
    client = get_genai_client()
    effective_timeout = timeout_override_s or 28

    config = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        system_instruction=system_instruction,
    )
    if response_mime_type:
        config.response_mime_type = response_mime_type

    start = time.monotonic()
    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=contents,
                config=config,
            ),
            timeout=effective_timeout,
        )
        latency = time.monotonic() - start
        text = response.text or ""
        logger.info(
            "gemini_call_success",
            extra={
                "purpose": purpose,
                "model": model,
                "latency_s": round(latency, 2),
                "output_len": len(text),
            },
        )
        return text

    except asyncio.TimeoutError:
        latency = time.monotonic() - start
        logger.warning(
            "gemini_call_timeout",
            extra={"purpose": purpose, "model": model,
                   "timeout_s": effective_timeout,
                   "latency_s": round(latency, 2)},
        )
        raise LLMTimeoutError(
            f"Gemini '{purpose}' timed out after {effective_timeout}s"
        )

    except Exception as e:
        latency = time.monotonic() - start
        logger.error(
            "gemini_call_error",
            extra={"purpose": purpose, "model": model, "error": str(e),
                   "latency_s": round(latency, 2)},
            exc_info=True,
        )
        raise LLMServiceError(
            f"Gemini '{purpose}' failed: {type(e).__name__}: {e}"
        )
```

### B2. requirements.txt 업데이트

```text
# requirements.txt
fastapi==0.115.8
uvicorn[standard]==0.34.0
google-genai>=1.5.0
google-cloud-storage>=2.18.0
google-auth>=2.35.0
pydantic>=2.10.0
python-json-logger>=3.0.0
```

> **삭제**: `google-cloud-aiplatform`, `vertexai` (deprecated SDK)

### B3. 타임아웃 전략 -- 근거 기반 도출

| 구간 | 값 | 근거 |
|------|------|------|
| BE WebClient -> AI | 30s | FSD F4: AI_CHAT_TIMEOUT, AiProxyService.java |
| AI call_gemini -> Vertex | 28s | BE 30s - 2s 마진 (네트워크 + 직렬화) |
| SDK HttpOptions.timeout | 28s | call_gemini과 동일 |
| SDK retry attempts | 3 | Vertex 공식 권장: 429/5xx exponential backoff |
| Cloud Run --timeout | 120s | 현행 유지. image-edit 장시간 작업 대비 |
| asyncio.wait_for | 28s (기본), endpoint별 override | analyze: 28s, chat: 28s, image-edit: 55s |

image-edit만 55초인 이유: 이미지 생성/편집은 Gemini Vision + GCS 왕복이 추가.
BE 측도 image-edit 전용 timeout 설정 필요 (현재 일괄 30s).

---

## 3. 범주 C: 에러 모델 / API 계약 정합

### C1. 커스텀 예외 계층

```python
# app/core/exceptions.py

class MiriArtAIError(Exception):
    def __init__(self, message: str, error_code: str = "UNKNOWN"):
        super().__init__(message)
        self.error_code = error_code
        self.message = message

class LLMTimeoutError(MiriArtAIError):
    """Gemini 호출 타임아웃. BE에서 AN002/AI002로 매핑"""
    def __init__(self, message: str):
        super().__init__(message, error_code="LLM_TIMEOUT")

class LLMServiceError(MiriArtAIError):
    """Gemini 호출 5xx/SDK 에러. BE에서 AN001/AI001로 매핑"""
    def __init__(self, message: str):
        super().__init__(message, error_code="LLM_SERVICE_ERROR")

class LLMParsingError(MiriArtAIError):
    """Gemini 응답 파싱 실패"""
    def __init__(self, message: str):
        super().__init__(message, error_code="LLM_PARSING_ERROR")

class GCSError(MiriArtAIError):
    """GCS 접근 실패"""
    def __init__(self, message: str):
        super().__init__(message, error_code="GCS_ERROR")

class ValidationError(MiriArtAIError):
    """입력 검증 실패"""
    def __init__(self, message: str):
        super().__init__(message, error_code="VALIDATION_ERROR")
```

### C2. FastAPI 전역 예외 핸들러

```python
# app/core/error_handler.py

import logging
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.core.exceptions import (
    MiriArtAIError, LLMTimeoutError, LLMServiceError,
    LLMParsingError, GCSError, ValidationError,
)

logger = logging.getLogger(__name__)

# API_CONTRACT 9 에러코드 매핑 테이블
ERROR_MAP = {
    LLMTimeoutError:  (504, "LLM_TIMEOUT"),      # -> BE: AN002 or AI002
    LLMServiceError:  (502, "LLM_SERVICE_ERROR"), # -> BE: AN001 or AI001
    LLMParsingError:  (502, "LLM_PARSING_ERROR"), # -> BE: AN001 or AI001
    GCSError:         (502, "GCS_ERROR"),          # -> BE: F003
    ValidationError:  (400, "VALIDATION_ERROR"),   # -> BE: C001
}

def register_exception_handlers(app: FastAPI):

    @app.exception_handler(MiriArtAIError)
    async def miriart_error_handler(request: Request, exc: MiriArtAIError):
        status, code = ERROR_MAP.get(type(exc), (500, exc.error_code))
        logger.warning(
            "handled_error",
            extra={
                "path": request.url.path,
                "method": request.method,
                "error_code": code,
                "status": status,
                "detail": exc.message,
            },
        )
        return JSONResponse(
            status_code=status,
            content={"code": code, "message": exc.message},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        logger.warning("request_validation_error", extra={
            "path": request.url.path,
            "errors": str(exc.errors())[:500],
        })
        return JSONResponse(
            status_code=400,
            content={
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "errors": [
                    {"field": e.get("loc", [])[-1] if e.get("loc") else "unknown",
                     "message": e.get("msg", "")}
                    for e in exc.errors()
                ],
            },
        )

    @app.exception_handler(Exception)
    async def catch_all_handler(request: Request, exc: Exception):
        logger.error(
            "unhandled_exception",
            extra={
                "path": request.url.path,
                "method": request.method,
                "error": str(exc),
                "traceback": traceback.format_exc()[:2000],
            },
        )
        return JSONResponse(
            status_code=500,
            content={"code": "INTERNAL_ERROR", "message": "Internal server error"},
        )
```

### C3. BE <-> AI 에러코드 매핑 계약

| AI HTTP Status | AI error_code | BE ErrorCode | BE HTTP | 설명 |
|---------------|---------------|-------------|---------|------|
| 504 | LLM_TIMEOUT | AN002 (분석) / AI002 (채팅) | 504 | Gemini 타임아웃 |
| 502 | LLM_SERVICE_ERROR | AN001 (분석) / AI001 (채팅) | 502 | Gemini 5xx/SDK |
| 502 | LLM_PARSING_ERROR | AN001 / AI001 | 502 | 응답 파싱 실패 |
| 502 | GCS_ERROR | F003 | 500 | GCS 접근 실패 |
| 400 | VALIDATION_ERROR | C001 | 400 | 입력 검증 실패 |
| 501 | NOT_IMPLEMENTED | - | 501 | C4 스텁 |

**BE 측 AiProxyService 매핑 로직 (참고용)**:
```java
// BE가 AI 응답 status code로 분기하는 예시
.onStatus(status -> status.value() == 504,
    resp -> Mono.error(new BusinessException(ErrorCode.AI_ANALYSIS_TIMEOUT)))
.onStatus(status -> status.is5xxServerError(),
    resp -> Mono.error(new BusinessException(ErrorCode.AI_ANALYSIS_FAILED)))
```

---

## 4. 범주 D: 인프라 / Cloud Run 최적화

### D1. min-instances 설정

**근거 도출**:
- PRD 5.2: "AI 응답 70% 이내" -> cold start 502는 SLO 위반
- PRD 5.3 Year 1 MAU 3,000 -> DAU ~100, peak RPS < 1 -> min-instances=1 충분
- Cloud Run 비용: 1vCPU + 1Gi idle ~ $35/월 (request-based billing)

```bash
gcloud run services update miriart-ai \
  --region=asia-northeast3 \
  --min-instances=1 \
  --cpu-boost
```

### D2. Cloud Run 최종 배포 스펙 (근거 기반)

| 파라미터 | 값 | 근거 |
|---------|------|------|
| --cpu | 1 vCPU | AI 호출은 I/O bound. CPU 증가 효과 미미 |
| --memory | 1 GiB | 이미지 바이트 + SDK overhead. 1Gi 충분 |
| --timeout | 120s | image-edit 최대 55s + 마진 |
| --min-instances | 1 | DAU 100 cold start 방지. Year 2 시 3으로 증가 |
| --max-instances | 20 | 동시 200명 (concurrency 10 x 20) |
| --concurrency | 10 | async I/O bound. 10 적정 |
| --cpu-boost | enabled | cold start 시 CPU 2배 |

### D3. .dockerignore

```
docs/
.cursor/
.cursorules
.git/
.gitignore
*.md
!requirements.txt
__pycache__/
.env
*.pyc
.pytest_cache/
tests/
cloudbuild.yaml
```

### D4. Cloud Build 트리거 + 태깅 전략

```yaml
# cloudbuild.yaml 최종안
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '-t'
      - 'asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:$COMMIT_SHA'
      - '-t'
      - 'asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:latest'
      - '.'

  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', '--all-tags',
           'asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai']

  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: gcloud
    args:
      - 'run'
      - 'deploy'
      - 'miriart-ai'
      - '--image=asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:$COMMIT_SHA'
      - '--region=asia-northeast3'
      - '--platform=managed'
      - '--port=8080'
      - '--cpu=1'
      - '--memory=1Gi'
      - '--timeout=120'
      - '--min-instances=1'
      - '--max-instances=20'
      - '--concurrency=10'
      - '--cpu-boost'
      - '--no-allow-unauthenticated'
      - '--invoker-iam-check'
      - '--service-account=miriart-ai-runner@miriarts.iam.gserviceaccount.com'
      - '--set-env-vars=GCP_PROJECT_ID=miriarts,GCP_REGION=asia-northeast3,GCS_BUCKET_NAME=miriart-bucket'

images:
  - 'asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:$COMMIT_SHA'
  - 'asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:latest'

options:
  logging: CLOUD_LOGGING_ONLY
```

Cloud Build 트리거 생성:
```bash
gcloud builds triggers create github \
  --repo-name=miriart-ai \
  --repo-owner=YOUR_ORG \
  --branch-pattern="^main$" \
  --build-config=cloudbuild.yaml \
  --region=asia-northeast3
```

---

## 5. 범주 E: 관측성 / 구조화 로깅

### E1. JSON 구조화 로깅

```python
# app/core/logging_config.py

import logging
import sys
from pythonjsonlogger import jsonlogger

def setup_logging():
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "severity"},
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = [handler]
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
```

### E2. Request ID / 상관관계 미들웨어

```python
# app/middleware/request_context.py

import uuid, time, logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

class RequestContextMiddleware(BaseHTTPMiddleware):
    EXCLUDE_PATHS = {"/health", "/internal/ai/health"}

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:12])
        request.state.request_id = request_id

        if request.url.path in self.EXCLUDE_PATHS:
            return await call_next(request)

        start = time.monotonic()
        response = await call_next(request)
        latency = round(time.monotonic() - start, 3)

        logger.info(
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_s": latency,
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response
```

---

## 6. 범주 G: C4 AI QA 기능 구현

### G1. summarize-answers 서비스

```python
# app/services/qa_service.py

import json, logging
from app.core.gemini_client import call_gemini, GeminiModel

logger = logging.getLogger(__name__)

SUMMARIZE_SYSTEM_PROMPT = """당신은 미술 입시 전문 AI 조교입니다.
커뮤니티 QA 게시판에서 질문에 달린 답변들을 요약합니다.

규칙:
1. 핵심 의견을 3줄 이내로 요약하세요 (summary).
2. 답변들에서 공통적으로 언급하지 않았지만, 질문자에게 도움이 될 추가 조언이 있다면
   1~2줄로 작성하세요 (supplement).
3. 미술 용어는 정확하게 사용하되, 고등학생도 이해할 수 있는 수준으로 설명하세요.
4. 반드시 JSON 형식으로 응답하세요."""

SUMMARIZE_USER_TEMPLATE = """질문: {question}

답변 목록:
{answers_text}

위 답변들을 요약하고, 추가 조언이 있다면 작성해주세요.
응답 형식:
{{"summary": "...", "supplement": "..."}}"""

async def summarize_answers(question: str, answers: list[str]) -> dict:
    answers_text = "\n".join(
        f"[답변 {i+1}] {a}" for i, a in enumerate(answers)
    )
    user_prompt = SUMMARIZE_USER_TEMPLATE.format(
        question=question, answers_text=answers_text,
    )
    raw = await call_gemini(
        model=GeminiModel.FLASH,
        contents=user_prompt,
        system_instruction=SUMMARIZE_SYSTEM_PROMPT,
        purpose="summarize_answers",
        temperature=0.3,
        max_output_tokens=1024,
        response_mime_type="application/json",
    )
    try:
        result = json.loads(raw)
        return {"summary": result.get("summary", ""), "supplement": result.get("supplement", "")}
    except json.JSONDecodeError:
        from app.core.exceptions import LLMParsingError
        raise LLMParsingError(f"Failed to parse summarize response: {raw[:200]}")
```

### G2. draft-from-question 서비스

```python
# app/services/qa_service.py (continued)

DRAFT_SYSTEM_PROMPT = """당신은 미술 입시 전문 AI 조교입니다.
커뮤니티에 올라온 질문을 보고, 도움이 되는 답변 초안을 작성합니다.

규칙:
1. 질문의 맥락(학년, 전공 분야 등)을 고려하세요.
2. 구체적이고 실천 가능한 조언을 포함하세요.
3. 미술 전문 용어를 사용하되 고등학생 수준에 맞게 설명하세요.
4. 200자 이내로 간결하게 작성하세요.
5. 이미지가 첨부된 경우, 이미지 내용도 참고하여 조언하세요.
6. 반드시 JSON 형식으로 응답하세요."""

DRAFT_USER_TEMPLATE = """제목: {title}
내용: {content}

위 질문에 대한 답변 초안을 작성해주세요.
응답 형식:
{{"draft": "..."}}"""

async def draft_from_question(
    title: str, content: str, image_base64: str | None = None,
) -> dict:
    user_prompt = DRAFT_USER_TEMPLATE.format(title=title, content=content)
    contents = [user_prompt]
    if image_base64:
        from google.genai import types as genai_types
        import base64
        contents = [
            genai_types.Part.from_text(user_prompt),
            genai_types.Part.from_bytes(
                data=base64.b64decode(image_base64), mime_type="image/jpeg",
            ),
        ]
    raw = await call_gemini(
        model=GeminiModel.FLASH,
        contents=contents,
        system_instruction=DRAFT_SYSTEM_PROMPT,
        purpose="draft_from_question",
        temperature=0.5,
        max_output_tokens=1024,
        response_mime_type="application/json",
    )
    try:
        result = json.loads(raw)
        return {"draft": result.get("draft", "")}
    except json.JSONDecodeError:
        from app.core.exceptions import LLMParsingError
        raise LLMParsingError(f"Failed to parse draft response: {raw[:200]}")
```

### G3. 라우터 연결 (501 stub -> 실 구현)

```python
# app/routers/ai.py -- C4 엔드포인트

from app.schemas.qa import (
    SummarizeAnswersRequest, SummarizeAnswersResponse,
    DraftFromQuestionRequest, DraftFromQuestionResponse,
)
from app.services.qa_service import summarize_answers, draft_from_question

@router.post("/summarize-answers", response_model=SummarizeAnswersResponse)
async def api_summarize_answers(req: SummarizeAnswersRequest):
    result = await summarize_answers(question=req.question, answers=req.answers)
    return SummarizeAnswersResponse(**result)

@router.post("/draft-from-question", response_model=DraftFromQuestionResponse)
async def api_draft_from_question(req: DraftFromQuestionRequest):
    result = await draft_from_question(
        title=req.title, content=req.content, image_base64=req.imageBase64,
    )
    return DraftFromQuestionResponse(**result)
```

### G4. Pydantic 스키마 (camelCase)

```python
# app/schemas/qa.py

from pydantic import BaseModel, Field

class CamelModel(BaseModel):
    class Config:
        alias_generator = lambda s: ''.join(
            w.capitalize() if i else w for i, w in enumerate(s.split('_'))
        )
        populate_by_name = True

class SummarizeAnswersRequest(CamelModel):
    question: str = Field(..., min_length=1, max_length=2000)
    answers: list[str] = Field(..., min_length=1, max_length=20)

class SummarizeAnswersResponse(CamelModel):
    summary: str
    supplement: str

class DraftFromQuestionRequest(CamelModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=5000)
    image_base64: str | None = Field(None, alias="imageBase64")

class DraftFromQuestionResponse(CamelModel):
    draft: str
```

---

## 7. 기존 서비스 리팩터링

### 7.1 analyze_service.py

```python
# app/services/analyze_service.py -- call_gemini 래퍼 적용

import json, logging
from app.core.gemini_client import call_gemini, GeminiModel
from app.core.exceptions import LLMParsingError, GCSError
from app.services.gcs_service import GcsService
from app.schemas.analyze import InternalAnalyzeRequest, InternalAnalyzeResponse
from app.core.config import settings

logger = logging.getLogger(__name__)

gcs = GcsService(bucket_name=settings.gcs_bucket_name, project_id=settings.gcp_project_id)

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
    # 1. GCS image download
    try:
        image_bytes = gcs.download_as_bytes(req.gcs_uri)
    except Exception as e:
        raise GCSError(f"Failed to download image from {req.gcs_uri}: {e}")

    # 2. Prompt
    problem_line = f"문제/주제: {req.problem_text}" if req.problem_text else ""
    user_text = ANALYZE_USER_TEMPLATE.format(
        analysis_type=req.analysis_type, problem_text_line=problem_line,
    )

    # 3. Gemini Vision (multimodal)
    from google.genai import types as genai_types
    contents = [
        genai_types.Part.from_text(user_text),
        genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
    ]

    raw = await call_gemini(
        model=GeminiModel.FLASH,
        contents=contents,
        system_instruction=ANALYZE_SYSTEM_PROMPT,
        purpose="analyze_artwork",
        temperature=0.3,
        max_output_tokens=2048,
        response_mime_type="application/json",
    )

    # 4. Parse
    try:
        data = json.loads(raw)
        return InternalAnalyzeResponse(
            grade=data["grade"], total_score=data["totalScore"],
            radar_data=data["radarData"], fix_scope=data["fixScope"],
            comment=data["comment"],
            university_predictions=data.get("universityPredictions", []),
        )
    except (json.JSONDecodeError, KeyError) as e:
        raise LLMParsingError(f"Analyze parsing failed: {e}, raw: {raw[:300]}")
```

### 7.2 chat_service.py

```python
# app/services/chat_service.py

import logging
from app.core.gemini_client import call_gemini, GeminiModel
from app.schemas.chat import InternalChatRequest, InternalChatResponse

logger = logging.getLogger(__name__)

MODEL_MAP = {
    "CHAT_PRO": GeminiModel.PRO,
    "FAST": GeminiModel.FLASH,
    "THINKING": GeminiModel.PRO,
    "SEARCH": GeminiModel.FLASH,
    "IMAGE_EDIT": GeminiModel.FLASH,
}

CHAT_SYSTEM_PROMPT = """당신은 MiriArt의 미술 입시 AI 멘토입니다.
학생의 미술 작품 분석 결과와 맥락을 바탕으로 친절하고 전문적인 상담을 제공합니다.

규칙:
1. 미술 전문 용어를 사용하되, 고등학생이 이해할 수 있게 설명하세요.
2. 구체적이고 실천 가능한 조언을 제공하세요.
3. 학생의 현재 수준(grade, fixScope)을 고려한 맞춤 조언을 하세요.
4. 격려와 동기부여를 포함하되, 현실적인 피드백도 함께 제공하세요.
5. 200자 이내로 간결하게 답변하세요."""

async def chat(req: InternalChatRequest) -> InternalChatResponse:
    model_name = MODEL_MAP.get(req.model_type, GeminiModel.FLASH)

    system = CHAT_SYSTEM_PROMPT
    if req.sticky_context:
        ctx = req.sticky_context
        system += f"\n\n학생 분석 결과: grade={ctx.get('grade','N/A')}, score={ctx.get('score','N/A')}, fixScope={ctx.get('fixScope','N/A')}"

    messages = ""
    if req.history:
        for h in req.history:
            role = h.get("role", "user")
            text = h.get("parts", [{}])[0].get("text", "") if isinstance(h.get("parts"), list) else h.get("text", "")
            messages += f"[{role}]: {text}\n"
    messages += f"[user]: {req.message}\n"

    raw = await call_gemini(
        model=model_name, contents=messages,
        system_instruction=system, purpose="chat",
        temperature=0.7, max_output_tokens=1024,
    )

    return InternalChatResponse(
        text=raw.strip(), grounding_urls=[],
        quick_replies=["이 부분을 더 자세히 알려주세요",
                        "연습 방법을 추천해주세요",
                        "비슷한 대학은 어디가 있나요?"],
    )
```

---

## 8. 범주 F: BigQuery RAG (P2 아키텍처)

### F1. 아키텍처

```
miriart-be --> miriart-ai --> BigQuery (vector_store)
                    |
              Vertex AI (Gemini + text-embedding-005)
```

### F2. BigQuery 스키마 (설계안)

```sql
CREATE TABLE IF NOT EXISTS `miriarts.rag_data.document_chunks` (
  chunk_id STRING NOT NULL,
  source_type STRING NOT NULL,   -- 'analysis_comment', 'qa_answer', 'guide'
  source_id STRING,
  content STRING NOT NULL,
  embedding ARRAY<FLOAT64>,      -- 768-dim (text-embedding-005)
  metadata JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

CREATE VECTOR INDEX IF NOT EXISTS doc_embedding_idx
ON `miriarts.rag_data.document_chunks`(embedding)
OPTIONS(index_type='IVF', distance_type='COSINE',
        ivf_options='{"num_lists": 50}');
```

### F3. Python 인터페이스 (P2 준비)

```python
# app/services/rag_service.py

from abc import ABC, abstractmethod

class RAGService(ABC):
    @abstractmethod
    async def index_document(self, source_type: str, source_id: str,
                             content: str, metadata: dict) -> str: ...

    @abstractmethod
    async def search(self, query: str, top_k: int = 5,
                     filters: dict | None = None) -> list[dict]: ...

    @abstractmethod
    async def generate_with_context(self, query: str,
                                    context_docs: list[dict]) -> str: ...

class BigQueryRAGService(RAGService):
    def __init__(self, project_id: str, dataset: str = "rag_data"):
        self._project_id = project_id
        self._dataset = dataset

    async def index_document(self, source_type, source_id, content, metadata):
        raise NotImplementedError("P2")

    async def search(self, query, top_k=5, filters=None):
        raise NotImplementedError("P2")

    async def generate_with_context(self, query, context_docs):
        raise NotImplementedError("P2")
```

---

## 9. main.py 통합

```python
# app/main.py

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.logging_config import setup_logging
from app.core.error_handler import register_exception_handlers
from app.core.gemini_client import get_genai_client
from app.middleware.request_context import RequestContextMiddleware
from app.routers import ai

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("miriart-ai starting up")
    get_genai_client()  # warm up
    logger.info("GenAI client warmed up")
    yield
    logger.info("miriart-ai shutting down")

app = FastAPI(
    title="MiriArt AI Service",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
register_exception_handlers(app)
app.include_router(ai.router, prefix="/internal/ai")

@app.get("/health")
async def health():
    return {"status": "ok"}
```

---

## 10. 디렉토리 구조

```
miriart-ai/
+-- app/
|   +-- __init__.py
|   +-- main.py
|   +-- core/
|   |   +-- config.py
|   |   +-- gemini_client.py
|   |   +-- exceptions.py
|   |   +-- error_handler.py
|   |   +-- logging_config.py
|   +-- middleware/
|   |   +-- request_context.py
|   +-- routers/
|   |   +-- ai.py
|   +-- schemas/
|   |   +-- analyze.py
|   |   +-- chat.py
|   |   +-- image_edit.py
|   |   +-- qa.py
|   +-- services/
|       +-- analyze_service.py
|       +-- chat_service.py
|       +-- image_edit_service.py
|       +-- qa_service.py
|       +-- gcs_service.py
|       +-- rag_service.py
+-- tests/
+-- Dockerfile
+-- requirements.txt
+-- cloudbuild.yaml
+-- .dockerignore
+-- .env.example
```

---

## 11. 실행 순서 체크리스트

### Phase 0 (즉시, 1~2일)
- [ ] A1: `gcloud run services update miriart-ai --invoker-iam-check`
- [ ] A1: BE SA Invoker binding 확인
- [ ] D3: `.dockerignore` 추가
- [ ] D4: Cloud Build 트리거 생성

### Phase 1 (1주)
- [ ] B1: `requirements.txt` 업데이트 (google-genai 추가, vertexai 제거)
- [ ] B1: `gemini_client.py` google-genai SDK 리팩터링
- [ ] B2-B3: `call_gemini` 래퍼 (타임아웃/리트라이/로깅)
- [ ] C1: `exceptions.py` 커스텀 예외 계층
- [ ] C2: `error_handler.py` 전역 핸들러
- [ ] D1: `--min-instances=1 --cpu-boost`
- [ ] D4: `cloudbuild.yaml` 최종안 + $COMMIT_SHA 태깅

### Phase 2 (2주차)
- [ ] 7.1: analyze_service.py 리팩터링
- [ ] 7.2: chat_service.py 리팩터링
- [ ] E1-E2: 구조화 로깅 + Request ID 미들웨어
- [ ] H1: gcs_service.py (signed URL)

### Phase 3 (3주차)
- [ ] G1-G4: C4 AI QA 구현
- [ ] C3: BE AiProxyService 에러 매핑 연동 검증

### Phase 4 (P2 이후)
- [ ] F1-F3: BigQuery RAG
- [ ] A2: GCS Presigned URL 전환

---

## 12. 로컬 에이전트 통합 프롬프트

```
miriart-ai 레포에서 feature/ai-refactor 브랜치를 만들고 다음 작업을 순서대로 수행해줘:

1. requirements.txt 업데이트:
   - google-cloud-aiplatform, vertexai 관련 의존성 제거
   - google-genai>=1.5.0, google-cloud-storage>=2.18.0, python-json-logger>=3.0.0 추가

2. app/core/exceptions.py 생성:
   - MiriArtAIError(base), LLMTimeoutError, LLMServiceError, LLMParsingError, GCSError, ValidationError
   - 각 예외에 error_code 속성

3. app/core/gemini_client.py 전면 리팩터링:
   - google-genai SDK genai.Client(vertexai=True) 패턴
   - HttpOptions timeout=28000, HttpRetryOptions(attempts=3, initial_delay=1.0)
   - call_gemini() async 래퍼: asyncio.wait_for + 예외 분류

4. app/core/error_handler.py 생성:
   - LLMTimeoutError->504, LLMServiceError->502, GCSError->502, ValidationError->400
   - catch-all 500

5. app/core/logging_config.py + app/middleware/request_context.py 생성

6. analyze_service.py, chat_service.py -> call_gemini 래퍼 사용 리팩터링

7. app/schemas/qa.py + app/services/qa_service.py 생성 (C4)

8. app/routers/ai.py: 501 스텁을 실 구현으로 교체

9. app/services/gcs_service.py 생성

10. app/main.py 통합 (lifespan warm-up, middleware, error_handler)

11. .dockerignore 생성

변경점 요약을 CHANGELOG.md에, 기존과 달라지는 부분은 TODO 주석으로 표시해줘.
```

---

*이 문서는 miriart-ai의 전체 이슈 범주화 + 코드 수준 개발 명세를 포함하며,
로컬 에이전트(Cursor)에서 직접 실행 가능한 형태로 작성됨.*
