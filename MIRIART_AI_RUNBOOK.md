# MiriArt AI 서비스 런북

> **대상**: miriart-ai (FastAPI, Cloud Run)
> **작성일**: 2026-03-10
> **목적**: AI 서비스의 로깅·에러·환경변수·실행·디버깅 플로우를 한곳에 정리

---

## 1. 로깅

### 1.1 로깅 설정

소스: `app/core/logging_config.py`

| 항목 | 값 |
|------|-----|
| 프레임워크 | `python-json-logger` (JSON 구조화 로그) |
| 출력 | `stdout` (Cloud Run이 Cloud Logging으로 자동 수집) |
| 루트 레벨 | `INFO` |
| uvicorn.access | `WARNING` (HTTP 요청 로그 억제, 미들웨어에서 별도 로깅) |
| 필드 | `timestamp`, `severity`, `name`, `message` + 이벤트별 추가 필드 |

### 1.2 로그 이벤트 카탈로그

#### HTTP 요청 로그 (미들웨어)

소스: `app/middleware/request_context.py`

| 이벤트 | 레벨 | 필드 | 설명 |
|--------|------|------|------|
| `http_request` | INFO | `request_id`, `method`, `path`, `status`, `latency_s` | 모든 HTTP 요청 (제외: `/health`, `/internal/ai/health`) |

- 라우트는 `/health`만 정의됨 (main.py). `/internal/ai/health`는 미들웨어 제외 경로로만 등록되어 있으며 해당 경로 라우트는 없음.
- `X-Request-ID`: 요청 헤더에서 추출 또는 12자 UUID 자동 생성, 응답 헤더에 반환

#### Gemini LLM 호출 로그

소스: `app/core/gemini_client.py`

| 이벤트 | 레벨 | 필드 | 설명 |
|--------|------|------|------|
| `gemini_call_start` | INFO | `purpose`, `model` | 호출 시작 |
| `gemini_call_success` | INFO | `purpose`, `model`, `latency_s`, `output_len` | LLM 호출 성공 |
| `gemini_call_timeout` | WARNING | `purpose`, `model`, `timeout_s`, `latency_s` | LLM 타임아웃 |
| `gemini_call_rate_limited` | WARNING | `purpose`, `model`, `latency_s` | Gemini 429 |
| `gemini_call_error` | ERROR | `purpose`, `model`, `error`, `latency_s` | LLM 호출 실패 |

`purpose` 값: `"analyze_artwork"`, `"chat"`, `"image_edit"`, `"summarize_answers"`, `"draft_from_question"`

#### 에러 핸들러 로그

소스: `app/core/error_handler.py`

| 이벤트 | 레벨 | 필드 | 설명 |
|--------|------|------|------|
| `handled_error` | WARNING | `path`, `method`, `error_code`, `status`, `detail` | 커스텀 예외 처리 |
| `request_validation_error` | WARNING | `path`, `errors` (500자 제한) | Pydantic 유효성 실패 |
| `unhandled_exception` | ERROR | `path`, `method`, `error`, `traceback` (2000자 제한) | 미처리 예외 |

#### 앱 라이프사이클 로그

소스: `app/main.py`

| 이벤트 | 레벨 | 설명 |
|--------|------|------|
| `miriart-ai starting up` | INFO | 앱 시작 |
| `GenAI client warmed up` | INFO | Gemini 클라이언트 초기화 완료 |
| `miriart-ai shutting down` | INFO | 앱 종료 |

### 1.3 Cloud Logging에서 조회

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

## 2. 에러 핸들링

### 2.1 예외 클래스 계층

소스: `app/core/exceptions.py`

```
MiriArtAIError (base)
├── LLMTimeoutError      error_code="LLM_TIMEOUT"
├── LLMRateLimitError    error_code="LLM_RATE_LIMITED"
├── LLMServiceError      error_code="LLM_SERVICE_ERROR"
├── LLMParsingError      error_code="LLM_PARSING_ERROR"
├── GCSError             error_code="GCS_ERROR"
└── ValidationError      error_code="VALIDATION_ERROR"
```

### 2.2 예외 → HTTP 매핑

소스: `app/core/error_handler.py`

| 예외 클래스 | HTTP Status | body.code | body.message | 로그 이벤트 |
|------------|------------|-----------|--------------|------------|
| `LLMTimeoutError` | 504 | `LLM_TIMEOUT` | 예외 메시지 | `handled_error` (WARNING) |
| `LLMRateLimitError` | 429 | `LLM_RATE_LIMITED` | 예외 메시지 | `handled_error` (WARNING) |
| `LLMServiceError` | 502 | `LLM_SERVICE_ERROR` | 예외 메시지 | `handled_error` (WARNING) |
| `LLMParsingError` | 502 | `LLM_PARSING_ERROR` | 예외 메시지 | `handled_error` (WARNING) |
| `GCSError` | 502 | `GCS_ERROR` | 예외 메시지 | `handled_error` (WARNING) |
| `ValidationError` | 400 | `VALIDATION_ERROR` | 예외 메시지 | `handled_error` (WARNING) |
| `RequestValidationError` | 400 | `VALIDATION_ERROR` | Pydantic 에러 목록 | `request_validation_error` (WARNING) |
| `Exception` (기타) | 500 | `INTERNAL_ERROR` | `"Internal server error"` | `unhandled_exception` (ERROR) |

### 2.3 에러 응답 형식

```json
{
  "code": "LLM_TIMEOUT",
  "message": "Gemini 응답 시간 초과 (55s)"
}
```

### 2.4 BE 에러 코드 매핑 (참조)

BE가 AI 응답의 HTTP status와 `code`를 보고 자체 ErrorCode로 변환:

| AI code | AI HTTP | → BE ErrorCode | BE HTTP | 비고 |
|---------|---------|----------------|---------|------|
| `LLM_TIMEOUT` | 504 | AN002 / AI002 | 504 | 분석/채팅 |
| `LLM_RATE_LIMITED` | 429 | (BE 매핑 정책에 따라) | 429 | 리트라이 유도 |
| `LLM_SERVICE_ERROR` | 502 | AN001 / AI001 | 502 | |
| `LLM_PARSING_ERROR` | 502 | AN001 / AI001 | 502 | |
| `GCS_ERROR` | 502 | F003 | 502 | 파일 IO |
| `VALIDATION_ERROR` | 400 | C001 | 400 | |

---

## 3. 관측성

### 3.1 Cloud Logging 통합

- FastAPI 컨테이너는 `stdout`에 JSON 로그를 출력
- Cloud Run이 자동으로 Cloud Logging `jsonPayload`에 파싱
- 별도 Logging SDK/에이전트 불필요

**JSON 로그 예시** (Cloud Logging에서 보이는 형태):
```json
{
  "timestamp": "2026-03-10T12:00:00.000Z",
  "severity": "INFO",
  "name": "app.core.gemini_client",
  "message": "gemini_call_success",
  "purpose": "analyze_artwork",
  "model": "gemini-2.5-flash",
  "latency_s": 3.45,
  "output_len": 1234
}
```

### 3.2 Log-based Metrics (AI 서비스)

SSOT 참조: `RUNBOOK_AI_INFRA_v1.md` §5.2

| 메트릭 | 필터 | 용도 |
|--------|------|------|
| `miriart-ai-5xx-errors` | AI status>=500 | AI 전체 5xx |
| `miriart-ai-502-gateway` | AI status=502 | LLM/GCS 장애 |
| `miriart-ai-504-timeout` | AI status=504 | Gemini 타임아웃 |

### 3.3 Prometheus/metrics 엔드포인트

**없음**. 현재 AI 서비스는 별도 metrics 엔드포인트를 노출하지 않음. Cloud Monitoring의 Cloud Run 기본 메트릭(request count, latency, instance count) + Log-based Metrics로 관측.

### 3.4 디버깅 체크리스트

AI 서비스 문제 발생 시 확인 순서:

| 순서 | 확인 | 명령어/위치 |
|------|------|------------|
| 1 | Cloud Run 서비스 상태 | `gcloud run services describe miriart-ai --region=asia-northeast3 --project=miriarts` |
| 2 | 최근 에러 로그 | §1.3 "Gemini 호출 에러만" 쿼리 |
| 3 | 리비전/인스턴스 상태 | `gcloud run revisions list --service=miriart-ai --region=asia-northeast3 --project=miriarts --limit=3` |
| 4 | 환경변수 확인 | `gcloud run services describe ... --format="yaml(spec.template.spec.containers[0].env)"` |
| 5 | GCS 버킷 접근 | `gcloud storage ls gs://miriart-bucket/ --limit=3` |

---

## 4. 환경변수 / API 키 / 보안

### 4.1 환경변수 인벤토리

소스: `app/core/config.py` (Pydantic BaseSettings)

| 이름 | 용도 | 기본값 | Prod 값 출처 | 민감도 |
|------|------|--------|-------------|--------|
| `GCP_PROJECT_ID` | Vertex AI / GCS 프로젝트 ID | `miriart-dev` | Cloud Run env (`cloudbuild.yaml:40`): **miriarts** | 낮음 |
| `GCP_REGION` | Cloud Run / 설정 리전 | `asia-northeast3` | Cloud Run env | 낮음 |
| `GEMINI_LOCATION` | Gemini API 호출 리전 (Cloud Run 리전과 분리) | `global` | cloudbuild 미설정 시 기본값 사용 (config.py:26) | 낮음 |
| `GCS_BUCKET_NAME` | GCS 버킷명 | `miriart-bucket` | Cloud Run env | 낮음 |
| `GOOGLE_APPLICATION_CREDENTIALS` | 로컬 개발 SA 키 경로 | `""` (빈 문자열) | Cloud Run: 불필요 (SA 자동 토큰) | **높음** (로컬만) |

> Prod에서는 Secret Manager를 사용하지 않음. Cloud Run SA(`miriart-ai-runner`)의 자동 인증으로 Vertex AI / GCS에 접근.

### 4.2 보안 경계

```
[인터넷 / FE]
     │
     ╳ ── Cloud Run IAM 차단 (--no-allow-unauthenticated, --invoker-iam-check)
     │    외부 → 403 Forbidden
     │
[BE SA (miriart-be-runner)]
     │
     ✓ ── roles/run.invoker 바인딩
     │
[miriart-ai /internal/ai/*]
     │
     ✓ ── SA 자동 토큰 (miriart-ai-runner)
     │
[GCS / Vertex AI]
```

| 경계 | 보호 방식 | 검증 |
|------|-----------|------|
| 외부 → AI | Cloud Run IAM (invoker-iam-check) | `curl https://miriart-ai-...du.a.run.app/health` → 403 |
| BE → AI | BE SA의 `roles/run.invoker` IAM 바인딩 | BE WebClient에서 SA 토큰 자동 발급 |
| AI → GCS | AI SA의 `roles/storage.objectAdmin` | Application Default Credentials |
| AI → Vertex AI | AI SA의 `roles/aiplatform.user` | 동일 |

### 4.3 테스트/디버그 엔드포인트

| 엔드포인트 | 용도 | Prod 상태 |
|-----------|------|-----------|
| `GET /health` | Cloud Run 헬스체크 / LB | **활성** (IAM 보호 — 외부 403) |
| Swagger UI (`/docs`) | API 문서 | **비활성** (`docs_url=None`) |
| ReDoc (`/redoc`) | API 문서 | **비활성** (`redoc_url=None`) |

> Prod에서 디버그 엔드포인트 없음. Swagger/ReDoc 비활성. `/health` 외 모든 경로는 IAM 보호.

---

## 5. 실행 / 테스트 플로우

### 5.1 로컬 실행

**사전 조건**:
1. Python 3.11+
2. GCP SA 키 파일 (로컬 개발용 `miriart-local-dev` SA)
3. `.env` 파일

**.env 예시**:
```env
GCP_PROJECT_ID=miriarts
GCP_REGION=asia-northeast3
GCS_BUCKET_NAME=miriart-bucket
GOOGLE_APPLICATION_CREDENTIALS=/path/to/miriart-local-dev-key.json
```

**실행**:
```bash
# 의존성 설치
pip install -r requirements.txt

# uvicorn으로 실행
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 또는 python -m
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**로컬 테스트 호출** (IAM 없음, 직접 호출 가능):
```bash
# 헬스체크
curl http://localhost:8000/health

# 채팅 테스트
curl -X POST http://localhost:8000/internal/ai/chat \
  -H "Content-Type: application/json" \
  -d '{
    "modelType": "FAST",
    "message": "석고 데생 팁을 알려주세요"
  }'

# 분석 테스트 (GCS에 실제 이미지 필요)
curl -X POST http://localhost:8000/internal/ai/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "gcsUri": "gs://miriart-bucket/artworks/2026-03-03/test.jpeg",
    "analysisType": "basic"
  }'
```

> 로컬에서는 IAM 체크가 없으므로 직접 호출 가능. `GOOGLE_APPLICATION_CREDENTIALS`로 GCS/Vertex AI 인증.

**BE 연동 시 URL**: 로컬 개발은 AI를 uvicorn 8000으로 띄우면 BE의 `FASTAPI_INTERNAL_URL=http://localhost:8000` 사용; prod는 BE가 Cloud Run에 배포된 miriart-ai 서비스 URL을 사용 (SSOT/miriarts_infra.md §3.2 `FASTAPI_INTERNAL_URL` 참조).

### 5.2 Docker 로컬 빌드 / 실행

```bash
# 빌드
docker build -t miriart-ai:local .

# 실행 (SA 키 마운트)
docker run -p 8080:8080 \
  -e GCP_PROJECT_ID=miriarts \
  -e GCP_REGION=asia-northeast3 \
  -e GCS_BUCKET_NAME=miriart-bucket \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/key.json \
  -v /path/to/miriart-local-dev-key.json:/app/key.json:ro \
  miriart-ai:local

# 테스트
curl http://localhost:8080/health
```

### 5.3 Cloud Run Prod 배포 / 롤백

**현재 상태 확인**:
```bash
# 최신 리비전
gcloud run services describe miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --format="value(status.latestReadyRevisionName)"

# 리비전 목록
gcloud run revisions list --service=miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --format="table(REVISION,ACTIVE,LAST_DEPLOYED_AT)" --limit=5

# 환경변수
gcloud run services describe miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --format="yaml(spec.template.spec.containers[0].env)"
```

**배포** (Cloud Build):
```bash
cd /path/to/miriart-ai
gcloud builds submit --config=cloudbuild.yaml \
  --project=miriarts \
  --region=asia-northeast3
```

`cloudbuild.yaml`이 수행하는 작업:
1. Docker 이미지 빌드 (듀얼 태그: `$COMMIT_SHA` + `latest`)
2. Artifact Registry 푸시 (`asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai`)
3. Cloud Run 배포 (min=1, max=20, concurrency=10, cpu-boost, IAM 보호)

**AI만 롤백** (BE 영향 없음):
```bash
# 이전 리비전으로 트래픽 전환
gcloud run services update-traffic miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --to-revisions=<PREVIOUS_REVISION>=100

# 또는 특정 커밋 SHA 이미지로 재배포
gcloud run deploy miriart-ai \
  --image=asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:<COMMIT_SHA> \
  --region=asia-northeast3 --project=miriarts
```

### 5.4 배포 검증

```bash
# 외부 접근 차단 확인 (403이어야 정상)
curl -s -o /dev/null -w "%{http_code}" \
  https://miriart-ai-gzjczkus6q-du.a.run.app/health
# → 403

# 서비스 Ready 상태
gcloud run services describe miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --format="value(status.conditions[0].status)"
# → True

# 에러 로그 확인 (배포 직후)
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-ai"
   AND severity>=ERROR' \
  --project=miriarts --limit=10 \
  --format="table(timestamp,severity,jsonPayload.message)"
```

---

## 6. Gemini 클라이언트 상세

소스: `app/core/gemini_client.py`

### 6.1 클라이언트 초기화

| 항목 | 값 |
|------|-----|
| SDK | `google-genai` (Vertex AI 모드) |
| 초기화 | `genai.Client(vertexai=True, project=..., location=...)` |
| 싱글톤 | `get_genai_client()` — 모듈 레벨 `_client` 캐시 |
| 웜업 | `main.py` lifespan에서 앱 시작 시 호출 |

### 6.2 모델 상수

| 상수 | 모델 ID | 용도 |
|------|---------|------|
| `GeminiModel.FLASH` | `gemini-2.5-flash` | 분석, 이미지편집, QA, 채팅(FAST/SEARCH/IMAGE_EDIT) |
| `GeminiModel.PRO` | `gemini-2.5-pro` | 채팅(CHAT_PRO/THINKING) |
| `GeminiModel.FLASH_LITE` | `gemini-2.0-flash-lite` | (현재 미사용) |

### 6.3 타임아웃 / 리트라이

| 항목 | 값 |
|------|-----|
| 기본 타임아웃 | 55s |
| `timeout_override_s` | 이미지 편집: 25s |
| 리트라이 횟수 | 2 |
| 초기 딜레이 | 1.0s |
| 최대 딜레이 | 8.0s |
| 지수 베이스 | 2.0 |
| 지터 | ±0.5 |
| 리트라이 대상 HTTP | [429, 500, 502, 503, 504] |

### 6.4 호출 흐름

```
call_gemini()
  │
  ├─ asyncio.wait_for(timeout=effective_timeout)
  │   └─ asyncio.to_thread(sync generate_content)
  │       └─ client.models.generate_content(model, contents, config)
  │
  ├─ 성공: 텍스트 추출 (response.text 또는 candidates[0]...parts[0].text)
  │         return_response=True 시 raw response 반환
  │
  ├─ TimeoutError → LLMTimeoutError
  ├─ 429 (Gemini) → LLMRateLimitError → HTTP 429
  └─ Exception → LLMServiceError
```

---

## 7. 주의사항 / 알려진 제한

| # | 항목 | 상태 | 비고 |
|---|------|------|------|
| 1 | `generate_signed_url()` in gcs_service | **미사용** | Phase 2 준비용. BE에서 Signed URL 생성 (miriart-be-runner SA). |
| 2 | `upload_bytes()` 반환값 | 공개 URL 형태 | `https://storage.googleapis.com/...` — 버킷 비공개이므로 직접 접근 불가. BE가 DB에 저장 후 Signed URL로 변환. |
| 3 | Chat `sessionId` | AI에서 미사용 | BE Redis에서 세션/히스토리 관리, AI에 `history`로 전달. |
| 4 | `quick_replies` 고정값 | 3개 하드코딩 | 동적 생성 미구현. |
| 5 | Swagger/ReDoc | prod 비활성 | `docs_url=None, redoc_url=None`. 로컬에서도 비활성 (코드 기준). |
| 6 | `stub.py` | 미사용 | Phase C4 스텁. 현재 라우터에서 참조 없음. |

---

*문서 끝 — 2026-03-10*
