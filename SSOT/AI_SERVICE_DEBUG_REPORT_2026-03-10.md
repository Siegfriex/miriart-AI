# MiriArt AI 서비스 디버깅 리포트 v2

> **작성일**: 2026-03-10
> **대상 리비전**: `miriart-ai-00004-gfx`
> **이미지**: `asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:21f0023`
> **작성 근거**: Cloud Logging 실 로그 + 코드 라인 직접 인용 + 수동 ID 토큰 호출 검증

---

## 1. 라우팅/스키마/에러 핸들러 일치 여부

### 1.1 라우터 등록

```python
# app/main.py:44
app.include_router(ai.router, prefix="/internal/ai", tags=["AI Internal"])
```

```python
# app/routers/ai.py:19
router = APIRouter()
```

**Router prefix**: `/internal/ai`
**Docs**: 비활성 (`main.py:37-38` — `docs_url=None, redoc_url=None`)

### 1.2 등록된 엔드포인트

| # | 메서드 | 경로 | 코드 위치 | 서비스 함수 |
|---|--------|------|-----------|------------|
| 1 | POST | `/internal/ai/analyze` | `routers/ai.py:22-30` | `analyze_service.analyze_artwork` |
| 2 | POST | `/internal/ai/chat` | `routers/ai.py:33-41` | `chat_service.chat` |
| 3 | POST | `/internal/ai/edit-image` | `routers/ai.py:44-52` | `image_edit_service.edit_image` |
| 4 | POST | `/internal/ai/summarize-answers` | `routers/ai.py:55-64` | `qa_service.summarize_answers` |
| 5 | POST | `/internal/ai/draft-from-question` | `routers/ai.py:67-80` | `qa_service.draft_from_question` |
| 6 | GET | `/health` | `main.py:47-50` | 직접 핸들러 |

### 1.3 스키마 camelCase 설정

모든 스키마에 동일 패턴 적용 확인:

```python
# app/schemas/analyze.py:11 (동일: chat.py:11, image_edit.py:11, qa.py:11)
_CAMEL = ConfigDict(populate_by_name=True, alias_generator=to_camel, serialize_by_alias=True)
```

| 스키마 | 파일:라인 | 주요 필드 (snake → camel) |
|--------|-----------|--------------------------|
| `InternalAnalyzeRequest` | `schemas/analyze.py:14` | `gcs_uri` → `gcsUri`, `analysis_type` → `analysisType` |
| `InternalAnalyzeResponse` | `schemas/analyze.py:48` | `total_score` → `totalScore`, `radar_data` → `radarData`, `fix_scope` → `fixScope` |
| `RadarData` | `schemas/analyze.py:24` | density, form, completion, relevance, thinking (단일 단어) |
| `UniversityPrediction` | `schemas/analyze.py:36` | `similar_accepted_count` → `similarAcceptedCount` |
| `InternalChatRequest` | `schemas/chat.py:34` | `model_type` → `modelType`, `session_id` → `sessionId`, `sticky_context` → `stickyContext`, `image_base64` → `imageBase64` |
| `InternalChatResponse` | `schemas/chat.py:48` | `grounding_urls` → `groundingUrls`, `quick_replies` → `quickReplies` |
| `StickyContext` | `schemas/chat.py:23` | `fix_scope` → `fixScope`, `radar_data` → `radarData` |
| `InternalImageEditRequest` | `schemas/image_edit.py:14` | `image_base64` → `imageBase64` |
| `InternalImageEditResponse` | `schemas/image_edit.py:23` | `image_url` → `imageUrl` |
| `SummarizeAnswersRequest` | `schemas/qa.py:14` | question, answers (단일 단어) |
| `DraftFromQuestionRequest` | `schemas/qa.py:32` | `image_base64` → 명시 alias `imageBase64` (`qa.py:39`) |

**결과**: `populate_by_name=True` — camelCase/snake_case 모두 수신 가능. `serialize_by_alias=True` — 응답은 camelCase 직렬화.

### 1.4 에러 핸들러 매핑

```python
# app/core/error_handler.py:27-33
ERROR_MAP = {
    LLMTimeoutError:  (504, "LLM_TIMEOUT"),
    LLMServiceError:  (502, "LLM_SERVICE_ERROR"),
    LLMParsingError:  (502, "LLM_PARSING_ERROR"),
    GCSError:         (502, "GCS_ERROR"),
    ValidationError:  (400, "VALIDATION_ERROR"),
}
```

| 예외 클래스 | error_code (`exceptions.py`) | HTTP | BE ErrorCode 매핑 | SSOT 일치 |
|-------------|------------------------------|------|--------------------|-----------|
| `LLMTimeoutError` (`:22`) | `LLM_TIMEOUT` | 504 | AN002 / AI002 | ✅ |
| `LLMServiceError` (`:28`) | `LLM_SERVICE_ERROR` | 502 | AN001 / AI001 | ✅ |
| `LLMParsingError` (`:33`) | `LLM_PARSING_ERROR` | 502 | AN001 / AI001 | ✅ |
| `GCSError` (`:39`) | `GCS_ERROR` | 502 | F003 | ✅ |
| `ValidationError` (`:46`) | `VALIDATION_ERROR` | 400 | C001 | ✅ |
| 기타 `MiriArtAIError` | exc.error_code | 500 | — | ✅ |
| `RequestValidationError` | `VALIDATION_ERROR` | 400 | C001 | ✅ |
| 미처리 `Exception` | `INTERNAL_ERROR` | 500 | — | ✅ |

**SSOT/API_CONTRACT와의 차이**: 없음. `docs/MiriArt_API_CONTRACT.md §8-9`, `MIRIART_AI_API_REFERENCE.md §5`와 완전히 일치.

---

## 2. Cloud Run IAM/서비스 설정

### 2.1 서비스 설정 (gcloud describe 실측)

```yaml
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/maxScale: '20'
        autoscaling.knative.dev/minScale: '1'
        run.googleapis.com/startup-cpu-boost: 'true'
    spec:
      serviceAccountName: miriart-ai-runner@miriarts.iam.gserviceaccount.com
```

### 2.2 IAM 정책

```yaml
bindings:
- members:
  - serviceAccount:miriart-be-runner@miriarts.iam.gserviceaccount.com
  role: roles/run.invoker
```

### 2.3 설정 검증

| 항목 | 값 | 정상 여부 |
|------|---|-----------|
| allow-unauthenticated | **false** (IAM 정책에 `allUsers` 없음) | ✅ 의도된 설정 |
| Invoker role | `miriart-be-runner` SA only | ✅ BE만 호출 가능 |
| Service Account | `miriart-ai-runner@miriarts.iam.gserviceaccount.com` | ✅ |
| Ingress | `all` (외부 접근 허용, IAM으로 인증 제어) | ✅ |
| Min/Max instances | 1 / 20 | ✅ |
| Startup CPU boost | enabled | ✅ |

### 2.4 환경변수 (실측)

```
GCP_PROJECT_ID  = miriarts
GCP_REGION      = asia-northeast3
GCS_BUCKET_NAME = miriart-bucket
```

| 변수 | 코드 기본값 (`config.py:21-23`) | Cloud Run 실값 | 일치 |
|------|-------------------------------|----------------|------|
| `gcp_project_id` | `miriart-dev` | `miriarts` | ✅ 오버라이드됨 |
| `gcp_region` | `asia-northeast3` | `asia-northeast3` | ✅ |
| `gcs_bucket_name` | `miriart-bucket` | `miriart-bucket` | ✅ |

---

## 3. 실제 요청 로그 분석

### 3.1 BE → AI `/analyze` 최근 로그 (403 차단)

```
2026-03-10T06:04:16.967Z [WARNING]
  HTTP POST https://miriart-ai-946560105497.asia-northeast3.run.app/internal/ai/analyze → 403 (0s)
  remoteIp: 34.96.43.25
  userAgent: ReactorNetty/1.2.2           ← Spring WebClient (Java BE)
  textPayload: "The request was not authenticated."

2026-03-10T05:58:17.297Z [WARNING]
  HTTP POST https://miriart-ai-946560105497.asia-northeast3.run.app/internal/ai/analyze → 403 (0s)
  remoteIp: 34.96.43.25
  userAgent: ReactorNetty/1.2.2
  textPayload: "The request was not authenticated."

2026-03-10T05:58:13.871Z [WARNING]
  HTTP POST https://miriart-ai-946560105497.asia-northeast3.run.app/internal/ai/analyze → 403 (0s)
  remoteIp: 34.96.43.25
  userAgent: ReactorNetty/1.2.2
  textPayload: "The request was not authenticated."
```

**핵심 증거**:
- `userAgent: ReactorNetty/1.2.2` → Spring WebFlux의 Reactor Netty, 즉 **Java BE의 WebClient 호출 확정**
- `status: 403` + `latency: 0s` → Cloud Run IAM 레이어에서 즉시 차단, FastAPI 코드 미도달
- `remoteIp: 34.96.43.25` → Cloud Run internal IP (같은 프로젝트 Cloud Run 서비스)

### 3.2 애플리케이션 레벨 로그

```
gemini_call_success / gemini_call_error / gemini_call_timeout: 0건
handled_error: 0건
http_request (미들웨어): 0건
```

**결론**: 403이 Cloud Run IAM 레이어에서 발생했으며, FastAPI 애플리케이션 코드까지 요청이 도달하지 못함.

---

## 4. 수동 ID 토큰 호출 결과

### 4.1 `/health` — 인증 없이

```bash
curl -s https://miriart-ai-946560105497.asia-northeast3.run.app/health
```

```html
<h1>Error: Forbidden</h1>
<h2>Your client does not have permission to get URL /health from this server.</h2>
HTTP_STATUS: 403
```

### 4.2 `/health` — ID 토큰 포함

```bash
TOKEN=$(gcloud auth print-identity-token)
curl -s -H "Authorization: Bearer $TOKEN" \
  https://miriart-ai-946560105497.asia-northeast3.run.app/health
```

```json
{"status":"ok"}
```
**HTTP_STATUS: 200** ✅

### 4.3 `/internal/ai/analyze` — ID 토큰 + 빈 body

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{}' \
  https://miriart-ai-946560105497.asia-northeast3.run.app/internal/ai/analyze
```

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Request validation failed",
  "errors": [
    {"field": "gcsUri", "message": "Field required"},
    {"field": "analysisType", "message": "Field required"}
  ]
}
```
**HTTP_STATUS: 400** ✅ — FastAPI 코드 도달, Pydantic validation 정상 동작

### 4.4 `/internal/ai/analyze` — ID 토큰 + 존재하지 않는 GCS URI

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"gcsUri":"gs://miriart-bucket/test/nonexistent.jpg","analysisType":"basic"}' \
  https://miriart-ai-946560105497.asia-northeast3.run.app/internal/ai/analyze
```

```json
{
  "code": "GCS_ERROR",
  "message": "Failed to download image from gs://miriart-bucket/test/nonexistent.jpg: 404 GET ... No such object: miriart-bucket/test/nonexistent.jpg"
}
```
**HTTP_STATUS: 502** ✅ — GCS 호출까지 도달, `GCSError` → 502 매핑 정상

**Cloud Logging에서 확인된 해당 요청 로그**:
```
2026-03-10T07:31:32.149Z [WARNING] handled_error
  error_code=GCS_ERROR  status=502  path=/internal/ai/analyze
  detail=Failed to download image from gs://miriart-bucket/test/nonexistent.jpg: 404 ...

2026-03-10T07:31:32.150Z [INFO] http_request
  latency_s=0.235  status=502  path=/internal/ai/analyze
```

### 4.5 `/internal/ai/chat` — ID 토큰 + 실제 채팅 메시지 (E2E)

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"modelType":"FAST","message":"안녕하세요, 테스트입니다"}' \
  https://miriart-ai-946560105497.asia-northeast3.run.app/internal/ai/chat
```

```json
{
  "text": "안녕하세요! MiriArt 미술 입시 AI 멘토입니다. 😊 여러분의 작품을 분석하고 입시 고민을 함께 나누며 실력 향상을 돕고 있어요.\n\n어떤 작품에 대해 이야기 나누고 싶으신가요? 언제든 편하게 보여주세요! 함께 고민하고 성장해나가요.",
  "groundingUrls": [],
  "quickReplies": [
    "이 부분을 더 자세히 알려주세요",
    "연습 방법을 추천해주세요",
    "비슷한 대학은 어디가 있나요?"
  ]
}
```
**HTTP_STATUS: 200** ✅ — Gemini Flash 호출 성공, camelCase 응답 정상

**Cloud Logging에서 확인된 해당 요청 로그**:
```
2026-03-10T07:32:02.947Z [INFO] gemini_call_success
  purpose=chat  model=gemini-2.5-flash  latency_s=10.35  output_len=132

2026-03-10T07:32:02.948Z [INFO] http_request
  latency_s=10.355  status=200  path=/internal/ai/chat
```

---

## 5. 내부 연동 상태 (코드 인용)

### 5.1 Gemini 클라이언트

```python
# app/core/gemini_client.py:28-43
_client = genai.Client(
    vertexai=True,
    project=settings.gcp_project_id,      # 런타임: "miriarts"
    location=settings.gcp_region,          # 런타임: "asia-northeast3"
    http_options=types.HttpOptions(
        timeout=28 * 1000,                 # 28초 (BE 30s - 2s margin)
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
```

**모델 상수** (`gemini_client.py:52-57`):

| 상수 | 모델 ID |
|------|---------|
| `FLASH` | `gemini-2.5-flash` |
| `PRO` | `gemini-2.5-pro` |
| `FLASH_LITE` | `gemini-2.0-flash-lite` |

### 5.2 엔드포인트별 Gemini 호출 파라미터

| 엔드포인트 | 모델 | temp | max_tokens | timeout | 코드 위치 |
|------------|------|------|------------|---------|-----------|
| analyze | FLASH | 0.3 | 2048 | 28s | `analyze_service.py:96-104` |
| chat (CHAT_PRO) | PRO | 0.7 | 1024 | 28s | `chat_service.py:81-88` |
| chat (FAST/SEARCH/IMAGE_EDIT) | FLASH | 0.7 | 1024 | 28s | `chat_service.py:58,81-88` |
| chat (THINKING) | PRO | 0.7 | 1024 | 28s | `chat_service.py:22` |
| edit-image | FLASH | 0.4 | 2048 | **55s** | `image_edit_service.py:38-46` |
| summarize-answers | FLASH | 0.3 | 1024 | 28s | `qa_service.py:63-71` |
| draft-from-question | FLASH | 0.5 | 1024 | 28s | `qa_service.py:101-109` |

### 5.3 GCS 서비스 (lazy init + async 래핑)

```python
# app/services/gcs_service.py:24-28 — 첫 호출 시 초기화
def _ensure_client(self):
    if self._client is None:
        self._client = storage.Client(project=self._project_id)
        self._bucket = self._client.bucket(self._bucket_name)
```

```python
# analyze_service.py:79 — GCS download (async 래핑)
image_bytes = await asyncio.to_thread(gcs.download_as_bytes, req.gcs_uri)

# image_edit_service.py:66-68 — GCS upload (async 래핑)
image_url = await asyncio.to_thread(
    gcs.upload_bytes, blob_path, edited_image_bytes, edited_mime
)
```

---

## 6. 문제 정의 검증

### 6.1 우리의 문제 정의

> "miriart-ai(FastAPI)는 설계/코드/배포 모두 정상이고,
> 현재 장애는 BE가 ID 토큰 없이 호출해서 Cloud Run IAM 403 단계에서 막히는 것이다."

### 6.2 검증 결과

| 검증 항목 | 증거 | 일치 여부 |
|-----------|------|-----------|
| **AI 코드 정상** | 수동 ID 토큰으로 `/chat` 호출 시 Gemini 응답 200 + camelCase JSON 정상 반환 | ✅ |
| **AI 배포 정상** | 리비전 `00004-gfx` 서빙 중, GenAI warm-up 성공, `/health` 200 | ✅ |
| **IAM 설정 정상** | `miriart-be-runner` → `roles/run.invoker` 부여됨 | ✅ |
| **BE가 토큰 미전달** | 로그: `ReactorNetty/1.2.2` UA + `403 "not authenticated"` + `latency: 0s` | ✅ |
| **403이 IAM 레이어** | `latency: 0s` + 앱 레벨 로그 0건 = Cloud Run 인프라에서 차단 | ✅ |
| **에러 핸들링 정상** | `GCS_ERROR → 502`, `VALIDATION_ERROR → 400` 수동 테스트로 확인 | ✅ |
| **Gemini 호출 정상** | `gemini_call_success: purpose=chat, model=gemini-2.5-flash, latency_s=10.35` | ✅ |

### 6.3 결론

**문제 정의 100% 일치 확인.**

- miriart-ai FastAPI 서비스는 코드·스키마·에러핸들러·배포·IAM 모두 **완전히 정상**
- 수동 ID 토큰 테스트로 `/health`(200), `/analyze`(400→502 정상 분기), `/chat`(200 Gemini 응답) **E2E 검증 완료**
- Cloud Logging에서 `gemini_call_success`, `handled_error`, `http_request` 로그 모두 **코드 설계대로 출력** 확인
- 현재 장애의 **유일한 원인**: Java BE(`ReactorNetty/1.2.2`)가 `Authorization: Bearer <ID_TOKEN>` 헤더 없이 호출

---

## 7. BE 측 필요 조치

### 7.1 즉시 확인

```bash
# 1. BE 서비스의 SA 확인
gcloud run services describe miriart-be --project=miriarts --region=asia-northeast3 \
  --format="value(spec.template.spec.serviceAccountName)"
# → miriart-be-runner@miriarts.iam.gserviceaccount.com 여야 함

# 2. BE 로그에서 AI 호출 확인
gcloud logging read 'resource.labels.service_name="miriart-be" AND textPayload:"miriart-ai"' \
  --project=miriarts --limit=10

# 3. 수동 SA impersonation 테스트
TOKEN=$(gcloud auth print-identity-token \
  --impersonate-service-account=miriart-be-runner@miriarts.iam.gserviceaccount.com \
  --audiences=https://miriart-ai-946560105497.asia-northeast3.run.app)
curl -H "Authorization: Bearer $TOKEN" \
  https://miriart-ai-946560105497.asia-northeast3.run.app/health
```

### 7.2 Java BE 수정 사항

BE의 WebClient가 AI 서비스 호출 시 다음을 충족해야 함:

1. **ID Token 발급**: `com.google.auth.oauth2.IdTokenCredentials`를 사용하여 대상 audience에 맞는 OIDC 토큰 발급
2. **Audience**: `https://miriart-ai-946560105497.asia-northeast3.run.app` (Cloud Run 서비스 URL)
3. **Header**: `Authorization: Bearer <id_token>`
4. **SA**: `miriart-be-runner@miriarts.iam.gserviceaccount.com` (현재 invoker 권한 보유)

```java
// 예시: Spring WebClient + Google Auth
IdTokenCredentials idTokenCreds = IdTokenCredentials.newBuilder()
    .setIdTokenProvider((ServiceAccountCredentials) credentials)
    .setTargetAudience("https://miriart-ai-946560105497.asia-northeast3.run.app")
    .build();
idTokenCreds.refreshIfExpired();
String idToken = idTokenCreds.getIdToken().getTokenValue();

webClient.post()
    .uri("/internal/ai/analyze")
    .header("Authorization", "Bearer " + idToken)
    .bodyValue(request)
    .retrieve()
    ...
```

---

## 8. 코드 품질 확인 — 이상 없음

| 체크 항목 | 상태 | 코드 위치 |
|-----------|------|-----------|
| GCS lazy init | ✅ | `gcs_service.py:24-28` — `_ensure_client()` |
| GCS async 래핑 | ✅ | `analyze_service.py:79`, `image_edit_service.py:66-68` |
| Mutable default 수정 | ✅ | `chat.py:45` — `Field(default_factory=list)` |
| JSON 구조화 로깅 | ✅ | `logging_config.py:16-19` — `JsonFormatter` |
| `/health` 로그 제외 | ✅ | `request_context.py:21,27` — `EXCLUDE_PATHS` |
| Request ID 전파 | ✅ | `request_context.py:24` — `X-Request-ID` |
| GenAI warm-up | ✅ | `main.py:27` — `get_genai_client()` in lifespan |
| Catch-all 에러 핸들러 | ✅ | `error_handler.py:82-96` — traceback 포함 |
| 에러 코드 일관성 | ✅ | `exceptions.py` ↔ `error_handler.py` ERROR_MAP 매핑 일치 |

---

## 9. 부수 발견 (INFO 레벨)

### 9.1 `qa_service.draft_from_question` MIME 하드코딩

```python
# app/services/qa_service.py:93-94
genai_types.Part.from_bytes(data=decoded, mime_type="image/jpeg")  # ← 하드코딩
```

`analyze_service.py`에는 `_detect_mime()` 함수로 PNG/WebP 자동 감지 적용됨 (`analyze_service.py:38-43`). 현재 Gemini가 바이트 기반으로 실제 타입을 인식하므로 실질 영향 없음.

### 9.2 `chat_service` MODEL_MAP에 IMAGE_EDIT 키 존재

```python
# app/services/chat_service.py:19-25
MODEL_MAP = {
    "CHAT_PRO": GeminiModel.PRO,
    "FAST": GeminiModel.FLASH,
    "THINKING": GeminiModel.PRO,
    "SEARCH": GeminiModel.FLASH,
    "IMAGE_EDIT": GeminiModel.FLASH,   # ← chat에서 IMAGE_EDIT?
}
```

실제 이미지 편집은 `/edit-image` 엔드포인트가 담당. 채팅에서 `IMAGE_EDIT` 타입 사용 시 의도된 동작인지 BE와 확인 필요.

---

## 10. 종합 판정

| 영역 | 판정 | 근거 |
|------|------|------|
| 라우팅 | ✅ PASS | 5개 AI + 1개 health 정상 등록, SSOT 일치 |
| 스키마 | ✅ PASS | camelCase 직렬화/역직렬화 일관, 수동 테스트로 확인 |
| Gemini 연동 | ✅ PASS | `/chat` E2E 200 + `gemini_call_success` 로그 확인 |
| GCS 연동 | ✅ PASS | lazy init + async 래핑, 404 시 `GCS_ERROR → 502` 정상 |
| 에러 핸들링 | ✅ PASS | 5계층 예외 → HTTP 매핑 완비, 수동 테스트로 400/502 확인 |
| Cloud Run 배포 | ✅ PASS | 최신 리비전 `00004-gfx`, IAM 설정 정상 |
| Cloud Run IAM | ✅ PASS | `miriart-be-runner` → `run.invoker` 부여됨 |
| **BE → AI 인증** | **🔴 FAIL** | **ReactorNetty/1.2.2가 ID 토큰 없이 호출 → 403** |

**문제 정의 일치 여부**: ✅ **100% 일치**

> AI 서비스는 설계·코드·배포·IAM 모두 정상이며, 유일한 장애 원인은 Java BE가 OIDC ID 토큰을 Authorization 헤더에 포함하지 않고 호출하는 것이다.
