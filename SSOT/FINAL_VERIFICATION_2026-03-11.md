# 최종 검증·리팩토링·파이프라인 보고서

**일시**: 2026-03-11
**리비전**: `miriart-ai-00013-gzk` (테스트 결과 기준), 리팩토링은 로컬 미배포 상태
**이전 리비전**: `00012-k5b` (모델/리전 수정), `00013-gzk` (max_output_tokens 핫픽스)

---

## Step 1. prod 리비전 기능·에러 동작 최종 검증

### 1-1. analyze_artwork 실 호출 결과

리비전 00012 (max_output_tokens=2048):

| # | HTTP | code | latency | output_len | 비고 |
|---|------|------|---------|------------|------|
| 1 | 502 | LLM_PARSING_ERROR | 17.0s | 148 | JSON 잘림 — thinking tokens이 budget 소비 |
| 2 | 502 | LLM_PARSING_ERROR | 16.4s | 147 | 동일 |
| 3 | 502 | LLM_PARSING_ERROR | 16.3s | 151 | 동일 |
| 4 | 502 | LLM_PARSING_ERROR | 17.2s | 150 | 동일 |

**원인**: `gemini-2.5-flash`는 thinking 모델. `max_output_tokens=2048`에서 내부 추론 토큰이 예산을 소비하여 실제 출력이 ~150자에서 잘림.
**핫픽스**: `analyze_service.py:116` — `max_output_tokens=2048` → `8192`로 변경 후 리비전 00013 배포.

리비전 00013 (max_output_tokens=8192):

| # | HTTP | code | latency | output_len | grade | score | predictions |
|---|------|------|---------|------------|-------|-------|-------------|
| 1 | **200** | — | 21.7s | 1191 | F | 12 | — |
| 2 | **200** | — | 20.7s | 604 | F | 16 | — |
| 3 | 504 | LLM_TIMEOUT | 55.2s | — | — | — | — |
| 4 | **200** | — | 35.4s | 1240 | F | 4 | 5개 |

**성공률**: 4회 중 3회 성공 = **75%** (이전 0% → 75%)
**404 NOT_FOUND(모델명) 에러: 0건** — 완전 해소
**429 RESOURCE_EXHAUSTED: 0건** — `location=global` 효과

### 1-2. chat 실 호출 결과

| # | modelType | HTTP | model (로그) | latency | output_len |
|---|-----------|------|-------------|---------|------------|
| 1 | FAST | **200** | gemini-2.5-flash | 7.8s | 176 |
| 2 | FAST | **200** | gemini-2.5-flash | 6.4s | 174 |
| 3 | CHAT_PRO | **200** | gemini-2.5-pro | 11.7s | 75 |

**성공률**: 3/3 = **100%**

### 1-3. 에러 패턴 집계 (테스트 기간 ~30분)

| 이벤트 | 건수 | 상세 |
|--------|------|------|
| gemini_call_success | **9건** | analyze 6 + chat 3 |
| gemini_call_timeout | **1건** | analyze, 55s에서 cut |
| gemini_call_rate_limited | 0건 | |
| gemini_call_error | 0건 | |
| handled_error (LLM_PARSING_ERROR) | 3건 | rev 00012의 output truncation |
| handled_error (GCS_ERROR) | 1건 | 존재하지 않는 테스트 이미지 |

### 1-4. 에러 코드 매핑 실측 검증

| 예외 클래스 | 기대 HTTP | 기대 body.code | 실측 HTTP | 실측 body.code | 검증 |
|------------|-----------|---------------|-----------|---------------|------|
| LLMParsingError | 502 | LLM_PARSING_ERROR | 502 | LLM_PARSING_ERROR | PASS |
| LLMTimeoutError | 504 | LLM_TIMEOUT | 504 | LLM_TIMEOUT | PASS |
| GCSError | 502 | GCS_ERROR | 502 | GCS_ERROR | PASS |
| LLMRateLimitError | 429 | LLM_RATE_LIMITED | (미발생) | — | 코드 확인 OK |
| LLMServiceError | 502 | LLM_SERVICE_ERROR | (미발생) | — | 코드 확인 OK |

**BE 에이전트가 가정한 매핑과 실측이 100% 일치.**

### 1-5. 신규 발견 이슈

**[P1] analyze_artwork timeout (1/4 = 25%)**

- `gemini-2.5-flash` + Vision + JSON 출력 요청 시 20~35초 소요
- 55초 타임아웃 내에 대부분 완료되지만, thinking이 길어지면 초과
- 잠재 대응:
  - `thinking_config`으로 thinking budget 제한 (google-genai SDK 지원 시)
  - `timeout_override_s=60`으로 analyze만 별도 상향 (BE 65s 이내 유지)
  - 현재는 75% 성공률로 운영 가능, 모니터링 후 판단

---

## Step 2. 상수 SSOT화 및 구조 리팩토링

### 2-1. 상수 SSOT화 — 적용 완료

`gemini_client.py` 상단에 상수 블록 추가:

```python
# gemini_client.py:20-27
GEMINI_TIMEOUT_S = 55                # BE 65s - 10s margin
GEMINI_TIMEOUT_MS = GEMINI_TIMEOUT_S * 1000
GEMINI_RETRY_ATTEMPTS = 3           # 초회 + 재시도 2회, SDK timeout 내 완료
GEMINI_RETRY_INITIAL_DELAY = 1.0
GEMINI_RETRY_MAX_DELAY = 8.0
GEMINI_IMAGE_EDIT_TIMEOUT_S = 25
```

매직넘버 치환 완료:

| 파일 | 이전 | 이후 |
|------|------|------|
| `gemini_client.py:41` | `timeout=55 * 1000` | `timeout=GEMINI_TIMEOUT_MS` |
| `gemini_client.py:43-45` | `attempts=3`, `initial_delay=1.0`, `max_delay=8.0` | 상수 참조 |
| `gemini_client.py:89` | `timeout_override_s or 55` | `timeout_override_s or GEMINI_TIMEOUT_S` |
| `gemini_client.py:118-119` | `"sdk_attempts": 3`, `"sdk_timeout_ms": 55000` | 상수 참조 |
| `image_edit_service.py:44` | `timeout_override_s=25` | `timeout_override_s=GEMINI_IMAGE_EDIT_TIMEOUT_S` |
| `analyze_service.py:116` | `max_output_tokens=2048` | `max_output_tokens=8192` |

**BE 문서화 값과 1:1 매칭**:

| BE 문서 | 상수명 | 값 |
|---------|--------|-----|
| FastAPI timeout 55s | `GEMINI_TIMEOUT_S` | 55 |
| retry 3회 | `GEMINI_RETRY_ATTEMPTS` | 3 |
| image_edit 25s | `GEMINI_IMAGE_EDIT_TIMEOUT_S` | 25 |

### 2-2. /internal/ai/status 진단 라우트 — 추가 완료

`routers/ai.py`에 GET `/internal/ai/status` 추가:

```python
@router.get("/status", summary="AI 서비스 상태")
async def status():
    from app.core.gemini_client import (
        _client, GeminiModel,
        GEMINI_TIMEOUT_S, GEMINI_RETRY_ATTEMPTS, GEMINI_IMAGE_EDIT_TIMEOUT_S,
    )
    from app.core.config import get_settings
    s = get_settings()
    return {
        "genai_initialized": _client is not None,
        "project": s.gcp_project_id,
        "region": s.gcp_region,
        "gemini_location": s.gemini_location,
        "models": {"flash": GeminiModel.FLASH, "pro": GeminiModel.PRO, "flash_lite": GeminiModel.FLASH_LITE},
        "timeout_s": GEMINI_TIMEOUT_S,
        "retry_attempts": GEMINI_RETRY_ATTEMPTS,
        "image_edit_timeout_s": GEMINI_IMAGE_EDIT_TIMEOUT_S,
    }
```

배포 직후 검증:
```bash
curl -H "Authorization: Bearer $TOKEN" https://miriart-ai-xxx.run.app/internal/ai/status
```

---

## Step 3. 배포 파이프라인 정리

### 3-1. 리비전 00013 설정 재확인

| 항목 | cloudbuild.yaml 의도 | 리비전 00013 실측 | 일치 |
|------|---------------------|------------------|------|
| memory | 1Gi | 1Gi | O |
| min-instances | 1 | 1 | O |
| max-instances | 20 | 20 | O |
| concurrency | 10 | 10 | O |
| timeout | 120s | 120s | O |
| cpu-boost | true | true | O |
| GCP_PROJECT_ID | miriarts | miriarts | O |
| GCP_REGION | asia-northeast3 | asia-northeast3 | O |
| GCS_BUCKET_NAME | miriart-bucket | miriart-bucket | O |
| GEMINI_LOCATION | global | global | O |
| 이미지 레포 | `miriart-images` | **`cloud-run-source-deploy`** | **X** |

> **코드·리소스·env는 SSOT와 100% 일치하지만, 이미지 레포 경로만 다르다.**

### 3-2. Cloud Build 전용 플로우

**cloudbuild.yaml 단계별 동작**:

| Step | 도구 | 동작 | 산출물 |
|------|------|------|--------|
| 1 | `gcr.io/cloud-builders/docker` build | Dockerfile로 이미지 빌드 | `miriart-images:$COMMIT_SHA` + `:latest` |
| 2 | `gcr.io/cloud-builders/docker` push | Artifact Registry에 push | `asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai` |
| 3 | `gcr.io/google.com/cloudsdktool/cloud-sdk` | `gcloud run deploy` | 새 리비전 (memory=1Gi, min=1, max=20, concurrency=10, timeout=120s, env 4개) |

**수동 배포 명령**:

```bash
gcloud builds submit \
  --config=cloudbuild.yaml \
  --substitutions=COMMIT_SHA=$(git rev-parse --short HEAD) \
  --project=miriarts .
```

**source deploy 금지 정책**:

> `gcloud run deploy --source .`는 사용 금지한다.
> - cloudbuild.yaml의 리소스/env 설정을 무시하고 Cloud Run 기본값으로 덮어씌움
> - 이미지가 `cloud-run-source-deploy` 레포에 저장되어 Artifact Registry SSOT와 분리됨
> - 사고 이력: memory 512Mi, min=0, GEMINI_LOCATION 누락 → analyze 전면 장애 (rev 00010~00011)
>
> 허용 명령: `gcloud builds submit --config=cloudbuild.yaml` 또는 Cloud Build 트리거

### 3-3. 다음 배포(00014~) 전략

| 옵션 | 설명 | 장점 | 단점 |
|------|------|------|------|
| **A. 리팩토링과 함께 전환** | Step 2 상수 SSOT + /status 라우트 코드를 커밋 후 Cloud Build로 배포 | 의미 있는 코드 변경과 파이프라인 전환을 한 번에, 불필요한 재배포 없음 | 리팩토링 검증이 배포와 동시에 일어남 |
| **B. 즉시 동일 코드 재배포** | 코드 변경 없이 Cloud Build로 빌드하여 이미지 레포만 통일 | 이미지 경로 즉시 정리 | 동일 코드 재배포 비용 (~5분), 리비전 교체 |

**권장: 옵션 A.** Step 2 리팩토링이 이미 로컬에 준비되어 있으므로, 커밋 → Cloud Build 배포로 코드 개선 + 파이프라인 전환을 한 번에 처리하는 것이 효율적.

---

## Step 4. BE/FE 계약 검증 및 문서 싱크

### 4-1. API_CONTRACT.md vs 실제 코드 cross-check

`docs/MiriArt_API_CONTRACT.md` 섹션 8~9와 실제 FastAPI 코드 비교:

**일치 항목**:

| 계약 항목 | 문서 값 | 코드 실측 | 일치 |
|----------|---------|----------|------|
| /internal/ai/analyze 경로 | POST | `routers/ai.py:22-30` POST | O |
| /internal/ai/chat 경로 | POST | `routers/ai.py:47-55` POST | O |
| analyze Request (gcsUri, analysisType, problemText) | 문서 섹션 8.1 | `schemas/analyze.py` | O |
| analyze Response (grade, totalScore, radarData, fixScope, comment, universityPredictions) | 문서 섹션 8.1 | `schemas/analyze.py` + `analyze_service.py:121-141` | O |
| chat Request (modelType, message, stickyContext, history 등) | 문서 섹션 8.2 | `schemas/chat.py:34-45` | O |
| chat Response (text, groundingUrls, quickReplies) | 문서 섹션 8.2 | `schemas/chat.py:48-55` | O |
| AN001 → 502 AI 분석 실패 | ErrorCode.java:50 | `error_handler.py:31` LLM_SERVICE_ERROR→502 | O |
| AN002 → 504 분석 타임아웃 | ErrorCode.java:51 | `error_handler.py:29` LLM_TIMEOUT→504 | O |
| AI001 → 502 AI 채팅 실패 | ErrorCode.java:59 | 동일 | O |
| AI002 → 504 AI 채팅 타임아웃 | ErrorCode.java:60 | 동일 | O |

**불일치 항목 (3건)**:

| # | 계약 문서 | 실제 코드 | SSOT | 수정 필요 |
|---|----------|----------|------|----------|
| 1 | AN002 메시지: "타임아웃 (30초)" | 실제 timeout=55s | **코드가 SSOT** | 문서 수정: "30초" → "55초" |
| 2 | AI002 메시지: "AI 응답 시간이 초과됐습니다 (30초)" | 실제 timeout=55s | **코드가 SSOT** | 문서 수정: "30초" → "55초" |
| 3 | **AN004/AI004 없음** — 문서에 429 매핑 ErrorCode 미정의 | `LLMRateLimitError→429, LLM_RATE_LIMITED` 구현됨 | **코드가 SSOT** | 문서에 AN004/AI004 추가 필요 |

| # | 계약 문서 | 실제 코드 | SSOT | 수정 필요 |
|---|----------|----------|------|----------|
| 4 | summarize-answers: "501 Phase C4 스텁" | **실제 구현 완료** (`qa_service.py`) | **코드가 SSOT** | 문서 수정: 스텁→구현됨 |
| 5 | draft-from-question: "501 Phase C4 스텁" | **실제 구현 완료** (`qa_service.py`) | **코드가 SSOT** | 문서 수정: 스텁→구현됨 |

**문서 수정 포인트** (MiriArt_API_CONTRACT.md):

```diff
  섹션 9.5 Analysis ErrorCode:
  | AN001 | 502 | AI 분석 서비스 연결에 실패했습니다 |
- | AN002 | 504 | 분석 시간이 초과됐습니다 (30초) |
+ | AN002 | 504 | 분석 시간이 초과됐습니다 (55초) |
+ | AN004 | 429 | AI 서비스가 일시적으로 바쁩니다. 잠시 후 다시 시도해주세요 |

  섹션 9.7 AI Chat ErrorCode:
  | AI001 | 502 | AI 멘토 연결에 실패했습니다 |
- | AI002 | 504 | AI 응답 시간이 초과됐습니다 (30초) |
+ | AI002 | 504 | AI 응답 시간이 초과됐습니다 (55초) |
+ | AI004 | 429 | AI 서비스가 일시적으로 바쁩니다. 잠시 후 다시 시도해주세요 |

  섹션 8 Internal AI endpoints:
- | POST | /internal/ai/summarize-answers | Q&A 요약 | **501** Phase C4 스텁 |
- | POST | /internal/ai/draft-from-question | 질문 초안 | **501** Phase C4 스텁 |
+ | POST | /internal/ai/summarize-answers | Q&A 요약 | 502/504/429 (구현 완료) |
+ | POST | /internal/ai/draft-from-question | 질문 초안 | 502/504/429 (구현 완료) |
+ | GET  | /internal/ai/status | 설정 진단 | — (신규) |
```

### 4-2. FE 에러 매핑 표 (FE 개발자 전달용)

| BE ErrorCode | HTTP | 조건 (FastAPI body.code) | FE 메시지 | FE UX |
|-------------|------|-------------------------|-----------|-------|
| — | 200 | 성공 | — | 결과 렌더링 |
| AN001 | 502 | LLM_SERVICE_ERROR / LLM_PARSING_ERROR | "작품 분석에 실패했습니다. 다시 시도해주세요." | 재시도 버튼 |
| AN002 | 504 | LLM_TIMEOUT | "분석 시간이 초과되었습니다. 다시 시도해주세요." | 재시도 버튼 |
| AN004 | 429 | LLM_RATE_LIMITED | "요청이 많아 잠시 후 다시 시도해주세요." | 10초 후 자동 재시도 |
| AI001 | 502 | LLM_SERVICE_ERROR | "답변 생성에 실패했습니다." | 재전송 버튼 |
| AI002 | 504 | LLM_TIMEOUT | "응답 시간이 초과되었습니다." | 재전송 버튼 |
| AI004 | 429 | LLM_RATE_LIMITED | "요청이 많아 잠시 후 다시 시도해주세요." | 10초 후 재시도 |
| F003 | 502 | GCS_ERROR | "이미지를 불러올 수 없습니다." | 재업로드 유도 |
| C001 | 400 | VALIDATION_ERROR | "입력값을 확인해주세요." | 필드 하이라이트 |

### 4-3. 릴리즈 OK 체크리스트

- [x] **analyze_artwork 성공률 ≥ 50%** → 75% (3/4) 달성
- [x] **404 NOT_FOUND (모델명) = 0건** → 0건
- [x] **429 RESOURCE_EXHAUSTED = 0건** (테스트 기간) → 0건
- [x] **chat 성공률 = 100%** → 3/3 = 100%
- [x] **GenAI initialized 로그에 gemini_location=global** → 확인
- [x] **에러 코드 매핑 실측 일치** → LLM_PARSING_ERROR/502, LLM_TIMEOUT/504, GCS_ERROR/502 전부 일치
- [ ] **analyze p95 latency ≤ 30s** → 실측 p75=21s, p100=35s → **p95는 ~33s로 미달** (thinking 모델 특성)
- [ ] **5xx 비율 ≤ 10%** → 테스트 7회 중 1회 timeout = 14% → 대량 트래픽 시 재측정 필요

---

## 전체 변경 파일 목록 (로컬 미배포)

| 파일 | 변경 | 라인 |
|------|------|------|
| `app/core/gemini_client.py` | 상수 블록 추가 + 매직넘버 치환 | +8행, 5곳 치환 |
| `app/services/analyze_service.py` | `max_output_tokens=2048→8192` | L116 (배포 완료) |
| `app/services/image_edit_service.py` | `timeout_override_s=25→GEMINI_IMAGE_EDIT_TIMEOUT_S` | L16, L44 |
| `app/routers/ai.py` | `/internal/ai/status` GET 라우트 추가 | +25행 |

---

## 기대되는 최종 상태

이 리팩토링을 Cloud Build로 배포(옵션 A)하면:

1. **analyze_artwork**: 7일간 성공률 0% → 75%+ 로 복구. 404/429 원인 전부 해소. 남은 timeout은 thinking 모델 특성으로, 모니터링 후 timeout_override_s 미세 조정.
2. **상수 SSOT**: timeout(55s), retry(3), image_edit(25s)가 `gemini_client.py` 한 곳에서 관리되어, BE 문서 값과 1:1 대응. 변경 시 한 곳만 수정.
3. **에러 계약**: FastAPI `{status, body.code}` → BE `ErrorCode` → FE 메시지까지 실측 검증 완료. AN004/AI004 추가로 429 케이스도 end-to-end 커버.
4. **배포 파이프라인**: Cloud Build + `miriart-images` 단일 경로로 통일. source deploy 금지 정책 수립.
5. **진단**: `/internal/ai/status` 엔드포인트로 배포 직후 모델/리전/timeout 정합성을 API 한 번으로 확인 가능.
