# 리비전 00012 배포 후 테스트·리팩토링·파이프라인 계획

**일시**: 2026-03-11
**대상 리비전**: `miriart-ai-00012-k5b`
**Service URL**: `https://miriart-ai-gzjczkus6q-du.a.run.app`

---

## Step 1. 최종 기능 테스트 & 디버깅 (prod 기준)

### 1-1. 로그 기반 smoke test — 통과

Cloud Logging 조회 결과 (배포 직후, 11:33:16 UTC):

```json
{
  "message": "GenAI client initialized (project=miriarts, gemini_location=global, cloud_run_region=asia-northeast3)",
  "name": "app.core.gemini_client",
  "timestamp": "2026-03-11T11:33:16.676651Z"
}
```

| 필드 | 기대값 | 실측값 | 판정 |
|------|--------|--------|------|
| project | miriarts | miriarts | PASS |
| gemini_location | global | global | PASS |
| cloud_run_region | asia-northeast3 | asia-northeast3 | PASS |

기동 순서 로그도 정상:
```
11:33:16.547 miriart-ai starting up
11:33:16.676 GenAI client initialized (...)
11:33:16.676 GenAI client warmed up
```

### 1-2 / 1-3. analyze_artwork · chat 실 호출 테스트 — 미수행

**이유**: Cloud Run 서비스가 `--no-allow-unauthenticated` + `--invoker-iam-check`로 IAM 보호.
로컬 CLI에서 직접 호출하려면 인증 토큰이 필요하다.

**수행 방법 (수동 실행용)**:

```bash
# 1. 인증 토큰 획득
TOKEN=$(gcloud auth print-identity-token --audiences=https://miriart-ai-gzjczkus6q-du.a.run.app)

# 2. analyze 호출 (테스트 이미지 GCS URI 필요)
curl -X POST https://miriart-ai-gzjczkus6q-du.a.run.app/internal/ai/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"gcsUri":"gs://miriart-bucket/test/sample.jpg","analysisType":"PRACTICE","problemText":"정물 소묘"}' \
  -w "\n%{http_code} %{time_total}s"

# 3. chat 호출 (FAST)
curl -X POST https://miriart-ai-gzjczkus6q-du.a.run.app/internal/ai/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"modelType":"FAST","message":"데생 연습 방법 알려줘","history":[],"stickyContext":{}}' \
  -w "\n%{http_code} %{time_total}s"
```

**검증 체크리스트**:

- [ ] analyze: HTTP 200 + body에 `grade`, `radarData`, `totalScore` 존재
- [ ] analyze: 로그에 `gemini_call_success`, `purpose=analyze_artwork`, `model=gemini-2.5-flash`
- [ ] analyze: 404 NOT_FOUND (`gemini-3-flash`) 에러 **미발생**
- [ ] chat FAST: HTTP 200 + body에 `reply`, `quickReplies` 존재
- [ ] chat CHAT_PRO: HTTP 200 + `model=gemini-2.5-pro` 로그

### 1-4. 단기 에러 패턴 — 트래픽 없음

배포 후 1시간 로그 조회 결과:

| 이벤트 | 건수 |
|--------|------|
| gemini_call_success | 0 |
| gemini_call_timeout | 0 |
| gemini_call_rate_limited | 0 |
| gemini_call_error | 0 |
| handled_error | 0 |

기동 로그만 존재하고 실 트래픽이 없다.
**서비스 자체는 정상 기동 확인됨. 실 기능 검증은 1-2/1-3 수동 테스트 또는 BE 연동 시점에 수행 필요.**

---

## Step 2. 코드/구조 리팩토링

### 2-1. 설정/상수 SSOT 현황

현재 타임아웃·리트라이·모델 관련 상수가 3개 파일에 흩어져 있다:

| 상수/매직넘버 | 값 | 위치 | 비고 |
|-------------|-----|------|------|
| SDK HTTP timeout | `55 * 1000` | `gemini_client.py:34` | ms 단위 |
| asyncio timeout | `55` | `gemini_client.py:82` | s 단위 |
| SDK retry attempts | `3` | `gemini_client.py:36` | |
| retry initial_delay | `1.0` | `gemini_client.py:37` | |
| retry max_delay | `8.0` | `gemini_client.py:38` | |
| image_edit timeout | `25` | `image_edit_service.py:48` | timeout_override_s |
| FLASH model | `"gemini-2.5-flash"` | `gemini_client.py:57` | |
| PRO model | `"gemini-2.5-pro"` | `gemini_client.py:58` | |
| FLASH_LITE model | `"gemini-2.0-flash-lite"` | `gemini_client.py:59` | |
| analyze temperature | `0.3` | `analyze_service.py:116` | |
| chat temperature | `0.7` | `gemini_client.py:69` (기본값) | |
| qa temperature | `0.3` / `0.5` | `qa_service.py:64,102` | |
| analyze max_tokens | `2048` | `analyze_service.py:117` | |
| chat max_tokens | `4096` | `gemini_client.py:70` (기본값) | |
| qa max_tokens | `1024` | `qa_service.py:65,103` | |

**제안: `gemini_client.py` 상단에 상수 블록 추가**

```python
# gemini_client.py — 변경 제안

# ── Gemini 공통 상수 (SSOT) ──────────────────────────────
GEMINI_TIMEOUT_S = 55          # BE 65s - 10s margin
GEMINI_TIMEOUT_MS = GEMINI_TIMEOUT_S * 1000
GEMINI_RETRY_ATTEMPTS = 3     # 초회 + 재시도 2회
GEMINI_RETRY_INITIAL_DELAY = 1.0
GEMINI_RETRY_MAX_DELAY = 8.0
GEMINI_IMAGE_EDIT_TIMEOUT_S = 25

class GeminiModel:
    FLASH = "gemini-2.5-flash"
    PRO = "gemini-2.5-pro"
    FLASH_LITE = "gemini-2.0-flash-lite"
# ─────────────────────────────────────────────────────────
```

diff (gemini_client.py):

```diff
  logger = logging.getLogger(__name__)

+# ── Gemini 공통 상수 (SSOT) ──────────────────────────────
+GEMINI_TIMEOUT_S = 55          # BE 65s - 10s margin
+GEMINI_TIMEOUT_MS = GEMINI_TIMEOUT_S * 1000
+GEMINI_RETRY_ATTEMPTS = 3     # 초회 + 재시도 2회
+GEMINI_RETRY_INITIAL_DELAY = 1.0
+GEMINI_RETRY_MAX_DELAY = 8.0
+GEMINI_IMAGE_EDIT_TIMEOUT_S = 25
+

  _client: Optional[genai.Client] = None

             http_options=types.HttpOptions(
-                timeout=55 * 1000,  # 55s (BE 60s - 5s margin)
+                timeout=GEMINI_TIMEOUT_MS,
                 retry_options=types.HttpRetryOptions(
-                    attempts=3,  # 429 등 일시적 에러 시 2회 재시도 (SDK 55s 내에서 완료)
-                    initial_delay=1.0,
-                    max_delay=8.0,
+                    attempts=GEMINI_RETRY_ATTEMPTS,
+                    initial_delay=GEMINI_RETRY_INITIAL_DELAY,
+                    max_delay=GEMINI_RETRY_MAX_DELAY,

-    effective_timeout = timeout_override_s or 55
+    effective_timeout = timeout_override_s or GEMINI_TIMEOUT_S
```

diff (image_edit_service.py):

```diff
+ from app.core.gemini_client import call_gemini, GeminiModel, GEMINI_IMAGE_EDIT_TIMEOUT_S

-        timeout_override_s=25,
+        timeout_override_s=GEMINI_IMAGE_EDIT_TIMEOUT_S,
```

### 2-2. 예외/에러 핸들링 구조

**현재 예외 계층** (`exceptions.py`):

```
MiriArtAIError (base)
 ├── LLMTimeoutError      → 504, LLM_TIMEOUT
 ├── LLMRateLimitError    → 429, LLM_RATE_LIMITED
 ├── LLMServiceError      → 502, LLM_SERVICE_ERROR
 ├── LLMParsingError      → 502, LLM_PARSING_ERROR
 ├── GCSError             → 502, GCS_ERROR
 └── ValidationError      → 400, VALIDATION_ERROR
```

**에러 흐름 (call_gemini → error_handler)**:

```
call_gemini()
  ├─ asyncio.TimeoutError   → LLMTimeoutError   ─┐
  ├─ 429/RESOURCE_EXHAUSTED → LLMRateLimitError  ─┤ error_handler.py
  └─ 기타 Exception         → LLMServiceError    ─┤ → JSONResponse
                                                    │   {code, message}
서비스 레이어                                       │
  ├─ json.loads 실패        → LLMParsingError    ─┤
  ├─ GCS 다운/업로드 실패   → GCSError           ─┤
  └─ 입력 검증 실패         → ValidationError    ─┘
```

**판정: 구조 자체는 깔끔함. 중복 try/except 없음.**

- `call_gemini`이 유일한 Gemini 진입점이므로 에러 분류가 한 곳에 집중됨 (L158~202)
- 각 서비스(`analyze`, `chat`, `qa`, `image_edit`)는 `call_gemini`을 호출할 뿐, 자체 try/except를 추가하지 않음
- JSON 파싱만 각 서비스에서 `LLMParsingError`로 처리 — 이 패턴이 4곳에서 반복되지만, 파싱 로직이 서비스마다 다르므로 통합 불필요

**개선 포인트 1건**: `gemini_call_error` 로그의 `error` 필드가 500자 truncate (`err_str[:500]`).
대부분의 Vertex AI 에러 메시지는 200자 이내이므로 현재 값 적절. 변경 불필요.

### 2-3. 라우터/서비스 구조

**현재 책임 분리**:

| 레이어 | 파일 | 책임 |
|--------|------|------|
| 라우터 | `routers/ai.py` | 요청 수신, 스키마 검증(Pydantic), 서비스 위임, 응답 반환 |
| 미들웨어 | `middleware/request_context.py` | request_id 생성, HTTP 요청 로깅 |
| 서비스 | `services/*.py` | GCS/Gemini 호출, 비즈니스 로직, JSON 파싱 |
| 공통 | `core/gemini_client.py` | Gemini SDK 래핑, 타임아웃/에러 분류, 구조화 로깅 |
| 공통 | `core/error_handler.py` | 예외→HTTP 매핑, 에러 로깅 |

**판정: 라우터가 얇고(위임만), 비즈니스 로직이 서비스에 집중 — 적절한 구조.**

`routers/ai.py`의 5개 엔드포인트가 모두 1줄 위임 (`return await xxx_service.xxx(request)`).
입력 검증은 Pydantic 스키마(`schemas/*.py`)가 자동 처리. 추가 라우터 로직 불필요.

**진단용 라우트 제안**: `/internal/ai/status`

현재 `/health`는 단순 `{"status": "ok"}` 반환. GenAI/GCS 연결 상태를 확인할 수 없다.

```python
# routers/ai.py — 추가 제안

@router.get("/status", summary="AI 서비스 상태")
async def status():
    """GenAI client 초기화 여부 + 설정값 리포트. 디버깅/운영용."""
    from app.core.gemini_client import _client, GeminiModel, GEMINI_TIMEOUT_S, GEMINI_RETRY_ATTEMPTS
    from app.core.config import get_settings
    s = get_settings()
    return {
        "genai_client_initialized": _client is not None,
        "gemini_location": s.gemini_location,
        "gcp_project_id": s.gcp_project_id,
        "gcp_region": s.gcp_region,
        "models": {
            "flash": GeminiModel.FLASH,
            "pro": GeminiModel.PRO,
            "flash_lite": GeminiModel.FLASH_LITE,
        },
        "timeout_s": GEMINI_TIMEOUT_S,
        "retry_attempts": GEMINI_RETRY_ATTEMPTS,
    }
```

배포 직후 한 번 호출하면 설정 정합성을 즉시 확인 가능.

---

## Step 3. 배포 파이프라인 리팩토링

### 3-1. 배포 이력 정리

| 리비전 | 생성일 | 배포 방식 | 이미지 레포 | 문제 |
|--------|--------|----------|------------|------|
| 00001 | 02-22 | 초기 | `gcr.io/cloudrun/hello` | 플레이스홀더 |
| 00002~00009 | 02-22 ~ 03-10 | Cloud Build + source deploy 혼용 | `miriart-images` / `cloud-run-source-deploy` | 설정 불일치 발생 |
| 00010~00011 | 03-11 03:44~03:48 | **source deploy** | `cloud-run-source-deploy` | memory=512Mi, min=0, max=3, GEMINI_LOCATION 누락 |
| **00012** | **03-11 11:33** | **source deploy** (설정 명시) | `cloud-run-source-deploy` | 설정은 SSOT 일치, 이미지 경로만 상이 |

**source deploy로 설정이 덮어씌워졌던 포인트**:

`gcloud run deploy --source .`는 `cloudbuild.yaml`을 무시하고 자체 빌드 후 배포한다.
명령에 `--memory`, `--min-instances` 등을 직접 지정하지 않으면 **Cloud Run 기본값**이 적용:

| 항목 | cloudbuild.yaml 의도 | source deploy 기본값 | 00010~00011 실측 |
|------|---------------------|---------------------|-----------------|
| memory | 1Gi | 512Mi | 512Mi |
| min-instances | 1 | 0 | 0 |
| max-instances | 20 | 100 (→ 이전 설정 3 유지) | 3 |
| concurrency | 10 | 80 | 80 |
| timeout | 120s | 300s | 300s |
| GEMINI_LOCATION | global | (없음) | (없음) |

### 3-2. Cloud Build 전용 배포 플로우

**표준 플로우**:

```
① git push origin BE/MAIN
    ↓
② Cloud Build 트리거 발동 (또는 수동: gcloud builds submit)
    ↓
③ cloudbuild.yaml Step 1: Docker build → 듀얼 태그 ($COMMIT_SHA + latest)
    ↓
④ cloudbuild.yaml Step 2: Artifact Registry push (miriart-images 레포)
    ↓
⑤ cloudbuild.yaml Step 3: gcloud run deploy
   - 이미지: miriart-images:$COMMIT_SHA
   - 리소스: memory=1Gi, min=1, max=20, concurrency=10, timeout=120s
   - env: GCP_PROJECT_ID, GCP_REGION, GCS_BUCKET_NAME, GEMINI_LOCATION
    ↓
⑥ 새 리비전 활성 (트래픽 100%)
```

**수동 빌드 시 $COMMIT_SHA 전달**:

```bash
gcloud builds submit \
  --config=cloudbuild.yaml \
  --substitutions=COMMIT_SHA=$(git rev-parse --short HEAD) \
  --project=miriarts .
```

**source deploy 금지 정책문**:

> **[정책] Cloud Run 배포는 반드시 cloudbuild.yaml 경유로만 수행한다.**
>
> `gcloud run deploy --source .`는 금지한다. 이유:
> 1. cloudbuild.yaml에 정의된 리소스/env 설정을 무시하고 Cloud Run 기본값으로 덮어씌움
> 2. 이미지가 `cloud-run-source-deploy` 레포에 저장되어 Artifact Registry SSOT와 분리됨
> 3. 이전 사고: memory 512Mi, min-instances=0, GEMINI_LOCATION 누락으로 인한 분석 전면 장애
>
> 허용 명령:
> - `gcloud builds submit --config=cloudbuild.yaml --substitutions=COMMIT_SHA=xxx --project=miriarts .`
> - Cloud Build 트리거에 의한 자동 배포

### 3-3. 마이그레이션 전략

**현재 상태**: 00012는 source deploy 이미지지만 리소스/env/코드 모두 SSOT와 일치.

| 옵션 | 설명 | 장점 | 단점 |
|------|------|------|------|
| **A. 다음 배포부터 전환** | 00012는 그대로 두고, 다음 코드 변경 시 Cloud Build로 배포 | 불필요한 재배포 없음, 리스크 0 | 이미지 레포 이력이 혼재 상태로 남음 |
| **B. 즉시 재배포** | 동일 코드를 Cloud Build로 빌드하여 00013을 miriart-images로 배포 | 이미지 레포까지 완전 통일, 깔끔한 이력 | 동일 코드 재배포 비용 (빌드 ~5분), 리비전 교체에 따른 미세 다운타임 |

**권장: 옵션 A.**
00012의 설정이 이미 정확하고, 다음 코드 변경(2-1 상수 리팩토링 등) 시 자연스럽게 Cloud Build 경로를 사용하면 된다.

---

## Step 4. BE/FE 연동 최종 검증 계획

### 4-1. BE 연동 테스트 플랜

**경로 A: 분석 (POST /api/analyses → /internal/ai/analyze)**

| # | 시나리오 | 발생 조건 | FastAPI 응답 | BE ErrorCode | FE 동작 |
|---|---------|----------|-------------|-------------|---------|
| A1 | 정상 분석 | 유효 이미지 + 정상 Gemini 응답 | 200, `{grade, radarData, ...}` | — (성공) | 결과 화면 표시 |
| A2 | GCS 이미지 없음 | 잘못된 gcsUri | 502, `GCS_ERROR` | F003 | "파일을 찾을 수 없습니다" |
| A3 | Gemini 타임아웃 | 55s 초과 | 504, `LLM_TIMEOUT` | AN002 | "분석 시간이 초과되었습니다. 다시 시도해주세요" |
| A4 | Gemini 429 | rate limit | 429, `LLM_RATE_LIMITED` | AN004 (신규) | "잠시 후 다시 시도해주세요" |
| A5 | Gemini 5xx | 서비스 에러 | 502, `LLM_SERVICE_ERROR` | AN001 | "분석에 실패했습니다" |
| A6 | JSON 파싱 실패 | Gemini가 비정상 출력 | 502, `LLM_PARSING_ERROR` | AN001 | "분석에 실패했습니다" |

**경로 B: 채팅 (POST /api/chat → /internal/ai/chat)**

| # | 시나리오 | FastAPI 응답 | BE ErrorCode | FE 동작 |
|---|---------|-------------|-------------|---------|
| B1 | 정상 채팅 | 200, `{reply, quickReplies}` | — (성공) | 답변 표시 |
| B2 | Gemini 타임아웃 | 504, `LLM_TIMEOUT` | AI002 | "응답 시간이 초과되었습니다" |
| B3 | Gemini 429 | 429, `LLM_RATE_LIMITED` | AI004 (신규) | "잠시 후 다시 시도해주세요" |
| B4 | Gemini 5xx | 502, `LLM_SERVICE_ERROR` | AI001 | "채팅에 실패했습니다" |

### 4-2. FE 관점 에러 매핑 표

FE 개발자가 그대로 구현할 수 있는 매핑:

| BE ErrorCode | HTTP Status | 조건 | FE 메시지 (ko) | FE UX |
|-------------|-------------|------|---------------|-------|
| — | 200 | 성공 | — | 결과 렌더링 |
| AN001 | 502 | 분석 AI 에러 | "작품 분석에 실패했습니다. 다시 시도해주세요." | 재시도 버튼 |
| AN002 | 504 | 분석 타임아웃 | "분석 시간이 초과되었습니다. 다시 시도해주세요." | 재시도 버튼 |
| AN004 | 429 | 분석 rate limit | "요청이 많아 잠시 후 다시 시도해주세요." | 10초 후 자동 재시도 or 대기 안내 |
| AI001 | 502 | 채팅 AI 에러 | "답변 생성에 실패했습니다." | 재전송 버튼 |
| AI002 | 504 | 채팅 타임아웃 | "응답 시간이 초과되었습니다." | 재전송 버튼 |
| AI004 | 429 | 채팅 rate limit | "요청이 많아 잠시 후 다시 시도해주세요." | 10초 후 재시도 |
| F003 | 502 | GCS 에러 | "이미지를 불러올 수 없습니다." | 재업로드 유도 |
| C001 | 400 | 입력 검증 실패 | "입력값을 확인해주세요." | 필드 하이라이트 |

**BE에서 FastAPI body.code → ErrorCode 분기 로직**:

```
FastAPI status=429, body.code="LLM_RATE_LIMITED"
  → path가 /analyze → AN004
  → path가 /chat    → AI004

FastAPI status=504, body.code="LLM_TIMEOUT"
  → path가 /analyze → AN002
  → path가 /chat    → AI002

FastAPI status=502, body.code in ("LLM_SERVICE_ERROR","LLM_PARSING_ERROR")
  → path가 /analyze → AN001
  → path가 /chat    → AI001

FastAPI status=502, body.code="GCS_ERROR" → F003
FastAPI status=400, body.code="VALIDATION_ERROR" → C001
```

### 4-3. 릴리즈 OK 기준

**최소 통과 조건**:

- [ ] **analyze_artwork 성공률 ≥ 80%** (5회 호출 중 4회 이상 200)
- [ ] **404 NOT_FOUND (모델명) 에러 = 0건**
- [ ] **chat 성공률 = 100%** (FAST, CHAT_PRO 각 2회)
- [ ] **429 발생 시 HTTP 429 + code=LLM_RATE_LIMITED 확인** (의도적 연속 호출로 유도 가능)
- [ ] **504 발생 시 HTTP 504 + code=LLM_TIMEOUT 확인**
- [ ] **analyze p95 latency ≤ 30s**
- [ ] **chat p95 latency ≤ 20s**
- [ ] **GenAI client initialized 로그에 gemini_location=global 확인**
- [ ] **5xx 비율 ≤ 10%** (Gemini 외적 에러)

---

## 기대되는 최종 상태

리비전 00012 검증 + 리팩토링 + 파이프라인 전환이 완료되면:

1. **모델/리전**: `gemini-2.5-flash` + `location=global`이 코드·env·Cloud Run 모두에서 단일 진실 소스(SSOT)로 확정되고, 404/429 재발 불가.
2. **타임아웃 체인**: SDK 55s → asyncio 55s → BE 65s → Cloud Run 120s 가 코드 상수(`GEMINI_TIMEOUT_S`)로 명시되어, 향후 변경 시 한 곳만 수정하면 됨.
3. **에러 계약**: FastAPI `{status, body.code}` → BE `ErrorCode` → FE 메시지까지 end-to-end 매핑이 문서화되어, 429(AN004/AI004) 포함 모든 케이스가 분류됨.
4. **배포 파이프라인**: source deploy 금지 정책이 수립되고, 다음 배포부터 `cloudbuild.yaml` → `miriart-images` 단일 경로로 통일됨.
5. **관측성**: `/internal/ai/status` 진단 엔드포인트 + 상수 SSOT화로, 배포 직후 설정 정합성을 로그/API 한 번으로 검증 가능.
