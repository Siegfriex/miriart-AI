# 2. FastAPI AI 서비스 — I/O Reference + 로깅 + 성능 + 배포 리포트

> **작성일**: 2026-03-10
> **대상 리비전**: `miriart-ai-00004-gfx`
> **근거**: 실 코드 + Cloud Run 설정 + 수동 E2E 테스트 로그

---

## 1. I/O Reference (엔드포인트별 Request/Response/Errors)

### 1.1 POST `/internal/ai/analyze`

**Request** (camelCase):
```json
{
  "gcsUri": "gs://miriart-bucket/uploads/artwork-001.jpg",
  "analysisType": "basic",
  "problemText": "정물화 구도 분석"
}
```

| 필드 | 타입 | 필수 | 코드 위치 |
|------|------|------|-----------|
| `gcsUri` | string | ✅ | `schemas/analyze.py:19` |
| `analysisType` | string | ✅ | `schemas/analyze.py:20` |
| `problemText` | string? | ❌ | `schemas/analyze.py:21` |

**Response** (200):
```json
{
  "grade": "B",
  "totalScore": 78.5,
  "radarData": {
    "density": 82.0,
    "form": 75.0,
    "completion": 80.0,
    "relevance": 73.0,
    "thinking": 77.0
  },
  "fixScope": "DetailTuning",
  "comment": "전체적으로 안정적인 구도이나 형태력 보완이 필요합니다.",
  "universityPredictions": [
    {
      "university": "홍익대학교",
      "major": "회화과",
      "line": "HIGH",
      "probability": 68,
      "similarAcceptedCount": 14
    }
  ]
}
```

**Errors**:
| 상황 | HTTP | Body |
|------|------|------|
| GCS 다운로드 실패 | 502 | `{"code": "GCS_ERROR", "message": "Failed to download image from gs://..."}` |
| Gemini 타임아웃 | 504 | `{"code": "LLM_TIMEOUT", "message": "Gemini 'analyze_artwork' timed out after 28s"}` |
| Gemini 5xx | 502 | `{"code": "LLM_SERVICE_ERROR", "message": "Gemini 'analyze_artwork' failed: ..."}` |
| JSON 파싱 실패 | 502 | `{"code": "LLM_PARSING_ERROR", "message": "Analyze parsing failed: ..."}` |
| 필수 필드 누락 | 400 | `{"code": "VALIDATION_ERROR", "message": "Request validation failed", "errors": [...]}` |

---

### 1.2 POST `/internal/ai/chat`

**Request** (camelCase):
```json
{
  "modelType": "FAST",
  "message": "형태력을 올리려면 어떻게 해야 하나요?",
  "sessionId": "sess-abc-123",
  "stickyContext": {
    "grade": "B",
    "score": 78.5,
    "fixScope": "DetailTuning",
    "radarData": {"density": 82, "form": 75, "completion": 80, "relevance": 73, "thinking": 77}
  },
  "imageBase64": null,
  "imageMimeType": null,
  "history": [
    {"role": "user", "parts": [{"text": "내 그림 분석 결과를 알려줘"}]},
    {"role": "model", "parts": [{"text": "B등급으로 평가되었습니다."}]}
  ]
}
```

| 필드 | 타입 | 필수 | 코드 위치 |
|------|------|------|-----------|
| `modelType` | string (CHAT_PRO/FAST/THINKING/SEARCH/IMAGE_EDIT) | ✅ | `schemas/chat.py:39` |
| `message` | string | ✅ | `schemas/chat.py:40` |
| `sessionId` | string? | ❌ | `schemas/chat.py:41` |
| `stickyContext` | StickyContext? | ❌ | `schemas/chat.py:42` |
| `imageBase64` | string? | ❌ | `schemas/chat.py:43` |
| `imageMimeType` | string? | ❌ | `schemas/chat.py:44` |
| `history` | HistoryItem[]? | ❌ | `schemas/chat.py:45` |

**Response** (200):
```json
{
  "text": "형태력 향상을 위해 매일 크로키 연습을 추천합니다...",
  "groundingUrls": [],
  "quickReplies": [
    "이 부분을 더 자세히 알려주세요",
    "연습 방법을 추천해주세요",
    "비슷한 대학은 어디가 있나요?"
  ]
}
```

**Errors**: LLM_TIMEOUT(504), LLM_SERVICE_ERROR(502), VALIDATION_ERROR(400)

---

### 1.3 POST `/internal/ai/edit-image`

**Request**:
```json
{
  "imageBase64": "/9j/4AAQSkZJRgABAQ...",
  "prompt": "배경을 파란색으로 변경해주세요"
}
```

**Response** (200):
```json
{
  "text": "이미지 편집이 완료됐습니다.",
  "imageUrl": "https://storage.googleapis.com/miriart-bucket/edited/a1b2c3d4-e5f6.jpg"
}
```

**Errors**: VALIDATION_ERROR(400, base64 디코딩 실패), GCS_ERROR(502, 업로드 실패), LLM_TIMEOUT(504), LLM_SERVICE_ERROR(502)

---

### 1.4 POST `/internal/ai/summarize-answers`

**Request**:
```json
{
  "question": "수채화 붓 터치 잘하는 법?",
  "answers": ["물의 양 조절이 중요합니다.", "붓을 45도 각도로 잡으세요.", "연습이 최고입니다."]
}
```

| 필드 | 제약 | 코드 위치 |
|------|------|-----------|
| `question` | min_length=1, max_length=2000 | `schemas/qa.py:19` |
| `answers` | min_length=1, max_length=20 | `schemas/qa.py:20` |

**Response** (200):
```json
{
  "summary": "물 조절과 붓 각도(45도)가 핵심이며, 꾸준한 연습이 중요합니다.",
  "supplement": "다양한 종이 재질에서 연습하면 붓 터치 감각을 더 빠르게 익힐 수 있습니다."
}
```

---

### 1.5 POST `/internal/ai/draft-from-question`

**Request**:
```json
{
  "title": "정물화 음영 표현이 어려워요",
  "content": "명암 대비를 넣으면 자연스럽지 않아요. 어떻게 해야 하나요?",
  "imageBase64": null
}
```

| 필드 | 제약 | 코드 위치 |
|------|------|-----------|
| `title` | min_length=1, max_length=200 | `schemas/qa.py:37` |
| `content` | min_length=1, max_length=5000 | `schemas/qa.py:38` |
| `imageBase64` | optional, alias `imageBase64` | `schemas/qa.py:39` |

**Response** (200):
```json
{
  "draft": "명암 대비를 자연스럽게 표현하려면 중간톤을 먼저 깔고..."
}
```

---

### 1.6 GET `/health`

**Response** (200):
```json
{"status": "ok"}
```

---

### 1.7 에러 응답 형식 종합

모든 에러 응답은 동일 구조:

```json
{"code": "<ERROR_CODE>", "message": "<상세 메시지>"}
```

Pydantic `RequestValidationError`만 추가 필드:
```json
{
  "code": "VALIDATION_ERROR",
  "message": "Request validation failed",
  "errors": [
    {"field": "gcsUri", "message": "Field required"}
  ]
}
```

---

## 2. 로깅/트레이싱

### 2.1 현재 로그 필드 현황

| 로그 이벤트 | 레벨 | 필드 | 코드 위치 |
|-------------|------|------|-----------|
| `http_request` | INFO | request_id, method, path, status, latency_s | `request_context.py:34-43` |
| `gemini_call_success` | INFO | purpose, model, latency_s, output_len | `gemini_client.py:103-111` |
| `gemini_call_timeout` | WARNING | purpose, model, timeout_s, latency_s | `gemini_client.py:134-142` |
| `gemini_call_error` | ERROR | purpose, model, error, latency_s | `gemini_client.py:149-158` |
| `handled_error` | WARNING | path, method, error_code, status, detail | `error_handler.py:43-51` |
| `request_validation_error` | WARNING | path, errors | `error_handler.py:63-67` |
| `unhandled_exception` | ERROR | path, method, error, traceback | `error_handler.py:84-91` |

### 2.2 트레이싱 갭 분석

**현재 문제**: `request_id`는 미들웨어에서만 로깅되고, `gemini_call_*`과 `handled_error`에는 포함되지 않음. 동일 요청의 `http_request` 로그와 `gemini_call_success` 로그를 **연결할 수 없음**.

```
http_request  request_id=a1b2c3  path=/internal/ai/analyze  status=200  latency_s=8.5
gemini_call_success  purpose=analyze_artwork  latency_s=8.2        ← request_id 없음!
```

### 2.3 추가 필드/코드 수정안

**방안**: Python `contextvars`를 사용하여 request_id를 서비스/gemini_client까지 전파.

```python
# app/middleware/request_context.py — 수정안
import contextvars

# 모듈 레벨 ContextVar
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:12]
        request.state.request_id = request_id
        request_id_var.set(request_id)          # ← ContextVar에 저장
        # ... 이하 동일
```

```python
# app/core/gemini_client.py — 수정안 (gemini_call_success에 request_id 추가)
from app.middleware.request_context import request_id_var

# call_gemini 함수 내부:
logger.info(
    "gemini_call_success",
    extra={
        "request_id": request_id_var.get("-"),   # ← 추가
        "purpose": purpose,
        "model": model,
        "latency_s": round(latency, 2),
        "output_len": len(text),
    },
)
```

```python
# app/core/error_handler.py — 수정안 (handled_error에 request_id 추가)
from app.middleware.request_context import request_id_var

# miriart_error_handler 내부:
logger.warning(
    "handled_error",
    extra={
        "request_id": request_id_var.get("-"),   # ← 추가
        "path": request.url.path,
        # ... 이하 동일
    },
)
```

**추가 로그 필드 제안**:

| 필드 | 출처 | 로그 이벤트 | 구현 방법 |
|------|------|------------|-----------|
| `request_id` | X-Request-ID 헤더 | 모든 이벤트 | contextvars 전파 |
| `session_id` | InternalChatRequest.session_id | chat 관련 로그 | chat_service에서 `logger.info("chat_start", extra={"session_id": req.session_id})` |

### 2.4 Cloud Logging 쿼리 예시

**1. 특정 request_id로 E2E 추적** (수정 후):
```
resource.type="cloud_run_revision"
resource.labels.service_name="miriart-ai"
jsonPayload.request_id="a1b2c3d4e5f6"
```

**2. 최근 Gemini 타임아웃 추적**:
```
resource.type="cloud_run_revision"
resource.labels.service_name="miriart-ai"
jsonPayload.message="gemini_call_timeout"
```

**3. 특정 시간대의 analyze 에러 전체**:
```
resource.type="cloud_run_revision"
resource.labels.service_name="miriart-ai"
jsonPayload.message="handled_error"
jsonPayload.path="/internal/ai/analyze"
timestamp>="2026-03-10T06:00:00Z"
timestamp<="2026-03-10T07:00:00Z"
```

---

## 3. 타임아웃/성능 평가

### 3.1 타임아웃 체인

```
FE (axios ~35s?) → BE WebClient (30s) → AI Python (28s/55s) → Gemini SDK (28s HTTP + 3 retry)
                                                               → Cloud Run (120s request timeout)
```

### 3.2 엔드포인트별 평가

| 엔드포인트 | AI timeout | Gemini SDK timeout | BE timeout | 관계 | 평가 |
|------------|------------|-------------------|------------|------|------|
| analyze | 28s | 28s + 3 retry | 30s | AI < BE ✅ | **주의**: retry 3회 시 worst-case ~84s, BE 30s에서 먼저 cut |
| chat | 28s | 28s + 3 retry | 30s | AI < BE ✅ | 동일 |
| edit-image | **55s** | 28s + 3 retry | 30s | **AI > BE** ⚠️ | BE가 30s에서 먼저 끊음 → AI 55s timeout 무의미 |
| summarize | 28s | 28s + 3 retry | 30s | AI < BE ✅ | 적정 |
| draft | 28s | 28s + 3 retry | 30s | AI < BE ✅ | 적정 |

### 3.3 문제점 및 권장 사항

**문제 1: Gemini retry와 timeout 충돌**

GenAI SDK retry (3회, 1~8s backoff) + HTTP timeout 28s → worst-case 한 호출이 28s x 3 + 17s(backoff) = ~101s. 그러나 `asyncio.wait_for(28s)`가 Python 레벨에서 전체를 감싸므로, **실제로는 28s 이내에 반드시 종료**. SDK 내부 retry가 28s 안에서만 동작.

→ **현재 설정 적정**. `asyncio.wait_for`가 상위 가드 역할.

**문제 2: image_edit 55s vs BE 30s 불일치**

```python
# image_edit_service.py:44
timeout_override_s=55,   # ← BE WebClient 30s보다 김
```

BE가 30s에서 `TimeoutException` → `AI_CHAT_FAILED`로 처리하고, AI 서비스는 55s까지 계속 Gemini 호출 + GCS 업로드를 진행. 리소스 낭비.

→ **권장**: image_edit timeout을 `25s`로 낮추거나, BE의 image_edit 전용 timeout을 `60s`로 올리기.

**문제 3: chat max_tokens 1024 충분한가**

```python
# chat_service.py:87
max_output_tokens=1024,   # ~400-500 한글 글자
```

현재 시스템 프롬프트에 "200자 이내" 제한이 있으므로 1024 토큰은 충분.

### 3.4 권장 설정 요약

| 엔드포인트 | 현재 AI timeout | 권장 AI timeout | 근거 |
|------------|----------------|----------------|------|
| analyze | 28s | **28s** (유지) | BE 30s - 2s margin 적정 |
| chat | 28s | **28s** (유지) | 동일 |
| edit-image | 55s | **25s** 또는 BE를 60s로 | BE 30s와 불일치 해소 |
| summarize | 28s | **28s** (유지) | 적정 |
| draft | 28s | **28s** (유지) | 적정 |

---

## 4. 배포 및 E2E 검증

### 4.1 배포 명령어

**방법 A: Cloud Build (권장)**
```bash
cd /home/sieg/projects-wsl/miriart-ai
COMMIT_SHA=$(git rev-parse --short HEAD)
gcloud builds submit . \
  --project=miriarts \
  --config=cloudbuild.yaml \
  --substitutions=COMMIT_SHA=$COMMIT_SHA
```

**방법 B: 수동 (Cloud Build 실패 시)**
```bash
# 1. Docker 빌드
cd /home/sieg/projects-wsl/miriart-ai
COMMIT_SHA=$(git rev-parse --short HEAD)
docker build -t asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:$COMMIT_SHA .
docker push asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:$COMMIT_SHA

# 2. Cloud Run 배포
gcloud run deploy miriart-ai \
  --image=asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:$COMMIT_SHA \
  --project=miriarts \
  --region=asia-northeast3 \
  --cpu=1 --memory=1Gi \
  --timeout=120 \
  --min-instances=1 --max-instances=20 \
  --concurrency=10 \
  --cpu-boost \
  --no-allow-unauthenticated --invoker-iam-check \
  --service-account=miriart-ai-runner@miriarts.iam.gserviceaccount.com \
  --set-env-vars=GCP_PROJECT_ID=miriarts,GCP_REGION=asia-northeast3,GCS_BUCKET_NAME=miriart-bucket \
  --set-cloudsql-instances= \
  --set-logging=CLOUD_LOGGING_ONLY
```

### 4.2 E2E 검증 절차 (BE ID 토큰 적용 후)

#### 시나리오 1: 정상 분석 (실제 GCS URI)

**호출** (BE 경유 또는 수동):
```bash
TOKEN=$(gcloud auth print-identity-token)
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"gcsUri":"gs://miriart-bucket/artworks/실제파일.jpg","analysisType":"basic"}' \
  https://miriart-ai-946560105497.asia-northeast3.run.app/internal/ai/analyze
```

**기대 응답**: HTTP 200 + JSON (grade, totalScore, radarData, ...)

**기대 Cloud Logging**:
```
[INFO]    gemini_call_success  purpose=analyze_artwork  model=gemini-2.5-flash  latency_s=6~12  output_len=300~600
[INFO]    http_request         path=/internal/ai/analyze  status=200  latency_s=7~13
```

#### 시나리오 2: GCS 실패 (존재하지 않는 URI)

**호출**:
```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"gcsUri":"gs://miriart-bucket/nonexistent.jpg","analysisType":"basic"}' \
  https://miriart-ai-946560105497.asia-northeast3.run.app/internal/ai/analyze
```

**기대 응답**: HTTP 502 + `{"code": "GCS_ERROR", "message": "Failed to download..."}`

**기대 Cloud Logging**:
```
[WARNING] handled_error        error_code=GCS_ERROR  status=502  path=/internal/ai/analyze
[INFO]    http_request         status=502  latency_s=0.2~0.5
```
(gemini_call 로그 **없음** — GCS 단계에서 실패)

#### 시나리오 3: 정상 채팅

**호출**:
```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"modelType":"FAST","message":"테스트 메시지입니다"}' \
  https://miriart-ai-946560105497.asia-northeast3.run.app/internal/ai/chat
```

**기대 응답**: HTTP 200 + `{"text": "...", "groundingUrls": [], "quickReplies": [...]}`

**기대 Cloud Logging**:
```
[INFO]    gemini_call_success  purpose=chat  model=gemini-2.5-flash  latency_s=5~15  output_len=50~200
[INFO]    http_request         path=/internal/ai/chat  status=200  latency_s=5~15
```

---

## 5. 종합

| 영역 | 상태 | 비고 |
|------|------|------|
| I/O Reference | ✅ 정리 완료 | 6개 엔드포인트 Request/Response/Error JSON 예시 |
| 로깅/트레이싱 | ⚠️ 갭 있음 | `request_id`가 gemini_call/error_handler에 미전파 → contextvars 수정안 제시 |
| 타임아웃 | ⚠️ 1건 불일치 | image_edit 55s vs BE 30s → timeout 조정 필요 |
| 배포 | ✅ 정상 | Cloud Build + 수동 fallback 명령어 정리 |
| E2E 검증 | ✅ 절차 정리 | 3개 시나리오별 기대 로그/응답 |
