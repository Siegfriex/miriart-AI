# 이미지 분석 502 Bad Gateway — 전체 도메인 종합 진단서

> **작성일**: 2026-03-11
> **현상**: `POST /api/analyses` → `502 Bad Gateway` (AN001)
> **목적**: FE · Java BE · FastAPI AI 전 도메인에 걸쳐 개별 가설을 수립하고, 로그 근거로 소거하여 근본 원인을 특정한다.

---

## 0. 관측 로그 원본 (FE 개발자콘솔)

### 0.1 FE 콘솔 타임라인 (2026-03-11 UTC)

| # | 시각(UTC) | 요청 | 결과 | 비고 |
|---|-----------|------|------|------|
| 1 | ~04:00 | POST /api/analyses | 502 Bad Gateway | 1차 시도 |
| 2 | ~04:05 | POST /api/analyses | 502 Bad Gateway | 2차 시도 |
| 3a | 04:06:19 | OPTIONS /api/analyses | 200 OK | preflight |
| 3b | 04:06:24 | POST /api/analyses | 502 `AN001` | 3차 시도, 응답시간 ~5s |

### 0.2 3차 시도 상세 (FE 네트워크 탭)

**OPTIONS (preflight)**
```
Status: 200 OK
access-control-allow-origin: https://miri-art.vercel.app
access-control-allow-methods: GET,POST,PUT,PATCH,DELETE,OPTIONS
access-control-allow-headers: authorization
access-control-allow-credentials: true
```

**POST (본 요청)**
```
Status: 502 Bad Gateway
Content-Type: application/json
Authorization: Bearer eyJhbG...(유효 JWT)
Content-Type: multipart/form-data
Payload: image(KakaoTalk_20260310_104833922.jpg) + analysisType(basic) + problemText(test3)
```

**응답 Body**
```json
{
  "timestamp": "2026-03-11T04:06:24.161738314",
  "status": 502,
  "code": "AN001",
  "message": "AI 분석 서비스 연결에 실패했습니다",
  "errors": []
}
```

### 0.3 AI 서비스 Cloud Run 로그 (대조)

| 시각(UTC) | 로그 이벤트 | 에러 상세 |
|-----------|-------------|-----------|
| 04:00:25 | `gemini_call_error` | `gemini-3-flash-preview` → 404 NOT_FOUND |
| 04:04:57 | `gemini_call_error` | `gemini-3-flash-preview` → 404 NOT_FOUND (13.99s) |
| 04:06:24 | `gemini_call_error` | `gemini-3-flash-preview` → 404 NOT_FOUND (2.25s) |

---

## 1. FE 도메인 (React / Vercel)

### 가설 목록

| ID | 가설 | 판정 | 근거 |
|----|------|------|------|
| **FE-1** | JWT 미전송 또는 만료 | ❌ **소거** | 네트워크 탭: `Authorization: Bearer eyJhbG...` 정상 포함. POST가 BE 비즈니스 로직까지 도달함 (AI 서비스 호출 발생). |
| **FE-2** | CORS preflight 실패 | ❌ **소거** | OPTIONS → 200 OK, `access-control-allow-origin: https://miri-art.vercel.app` 확인. |
| **FE-3** | multipart 페이로드 불량 | ❌ **소거** | `content-type: multipart/form-data`, image/analysisType/problemText 3필드 모두 포함. BE가 수신 후 AI 서비스까지 호출 진행됨. |
| **FE-4** | 요청 URL 미스매치 | ❌ **소거** | `https://miriart-be-946560105497.asia-northeast3.run.app/api/analyses` — BE Cloud Run URL 정확히 일치. |
| **FE-5** | `127.0.0.1:3001/ingest` 디버그 코드 | ⚠️ **부수 이슈** | `miriartApi.ts`에 로컬 디버그 엔드포인트 9곳 하드코딩. `.catch(()=>{})` 무시로 동작에 영향 없으나 CORS 에러 발생 중. 분석 502의 직접 원인은 아님. |
| **FE-6** | 재시도/폴링 로직 과도 | △ **확인 필요** | 동일 요청이 짧은 간격으로 반복됨 (04:00→04:05→04:06). 자동 재시도인지 사용자 수동 클릭인지 FE 코드 확인 필요. 자동이면 BE/AI 쿼터 소진 가중. |

### FE 결론

> **FE는 502의 원인이 아님.** 요청 구성·전송·인증 모두 정상. BE까지 올바르게 도달 확인.
> FE-5(디버그 코드)와 FE-6(재시도 패턴)은 별도 정리 대상.

---

## 2. Java BE 도메인 (Spring Boot / Cloud Run)

### 아키텍처 경로

```
FE → POST /api/analyses (Java BE)
     → JWT 검증 (Spring Security)
     → 이미지 GCS 업로드
     → OIDC ID Token 발급
     → WebClient POST /internal/ai/analyze (FastAPI AI 서비스)
     → AI 응답 파싱 → FE 응답 반환
```

### 가설 목록

| ID | 가설 | 판정 | 근거 |
|----|------|------|------|
| **BE-1** | Spring Security JWT 차단 | ❌ **소거** | 요청이 BE 비즈니스 로직까지 도달 (AI 서비스 호출 로그 존재). JWT 검증 통과. |
| **BE-2** | OIDC ID Token 인증 실패 (BE→AI) | ❌ **소거** | AI 서비스 Cloud Run 로그에 `analyze_pre_gemini` + `gemini_call_start` 출력 = 요청이 AI 서비스 FastAPI 비즈니스 로직까지 도달. OIDC 정상. |
| **BE-3** | AI 서비스 URL 설정 오류 | ❌ **소거** | `miriart.fastapi.internal-url` → AI Cloud Run URL. 로그상 정상 도달 확인. |
| **BE-4** | WebClient 타임아웃 (65s) 선행 발동 | △ **간접 가능** | BE `RESPONSE_TIMEOUT_SECONDS=65`. AI 서비스가 55s timeout 내에서 실패 반환하므로 현재는 해당 안 됨. 단, Gemini가 55s 근접 소요 시 BE timeout 선행 발동 가능. 현재 로그상 AI 응답 2~14초이므로 당장 해당 없음. |
| **BE-5** | AI 502 응답을 AN001로 매핑 | ✅ **정상 동작 확인** | AI 서비스가 `LLMServiceError` → HTTP 502 + `LLM_SERVICE_ERROR` 반환 → BE `AiProxyService`가 수신하여 AN001로 재매핑 → FE에 전달. 이것은 에러 전파이지 BE의 결함이 아님. |
| **BE-6** | BE→AI 네트워크 레이턴시 | △ **확인 필요** | 3차 시도 기준 OPTIONS(04:06:19) → POST 응답(04:06:24) = ~5초. 이 중 AI 서비스 Gemini 호출 2.25초 + 나머지 BE 처리/네트워크. GCS 업로드 시간 포함이므로 현재로선 정상 범위. |
| **BE-7** | Cloud Run 콜드스타트 | △ **간접 가능** | BE는 min instance 설정 의존. 첫 요청 시 콜드스타트로 추가 지연 가능. 단, 502 원인은 아님 (지연만 가중). |

### BE 결론

> **BE는 502의 근본 원인이 아님.** AI 서비스의 에러(502)를 정상적으로 수신·매핑·전달하는 역할.
> BE-4(타임아웃 경합) 시나리오는 Gemini 응답이 길어지면 잠재적 위험 — 모니터링 대상.

---

## 3. FastAPI AI 서비스 도메인 (Python / Cloud Run) — 근본 원인 영역

### 아키텍처 경로

```
BE → POST /internal/ai/analyze (FastAPI)
     → app/routers/ai.py:28-30
     → app/services/analyze_service.py:74-142
       → GCS download (gcs_uri → bytes)
       → MIME type detection
       → call_gemini(model=FLASH, contents=[text+image])
         → app/core/gemini_client.py:64-204
           → GenAI Client (project=miriarts, location=asia-northeast3)
           → Vertex AI API 호출
           → 에러 시 예외 발생
       → JSON 파싱
     → 응답 반환 or 예외 → error_handler → HTTP 에러
```

### 가설 목록

| ID | 가설 | 판정 | 심각도 | 코드 위치 | 해결 방안 |
|----|------|------|--------|-----------|-----------|
| **AI-1** | **Gemini 모델 404 (현재 활성 리비전)** | ✅ **확정·활성** | 🔴 P0 | `gemini_client.py:59` `FLASH = "gemini-3-flash"` → Vertex AI asia-northeast3에서 미지원 | 모델명 롤백 → `gemini-2.5-flash` (로컬 반영 완료, 배포 대기) |
| **AI-2** | **Gemini 429 쿼터 초과 (롤백 후)** | ✅ **재현됨** | 🔴 P0 | `gemini_client.py:120-128` → 429 RESOURCE_EXHAUSTED. SDK retry 1회 후에도 429면 `LLMRateLimitError` | 아래 §4 옵션 참조 |
| **AI-3** | **asia-northeast3 리전 Gemini 쿼터 한계** | ✅ **근본 원인** | 🔴 P0 | `config.py:22` `gcp_region = "asia-northeast3"` → `gemini_client.py:35` `location=settings.gcp_region` | Gemini API 호출 리전을 `us-central1`로 분리 |
| **AI-4** | SDK retry가 404를 재시도 안 함 | ✅ **정상 동작** | — | `gemini_client.py:44` `http_status_codes=[429,500,502,503,504]` — 404 미포함 | 404는 재시도 불필요. 모델명 수정이 답. |
| **AI-5** | SDK retry 횟수 부족 (attempts=2) | ⚠️ **기여 요인** | 🟡 P1 | `gemini_client.py:38` `attempts=2` (초기 1 + 재시도 1) | 429 시나리오에서 2회로는 부족할 수 있음. 3~4회 고려. |
| **AI-6** | asyncio timeout (55s) 도달 | △ **과거 발생** | 🟡 P2 | `gemini_client.py:84,120` `effective_timeout=55`. 과거 `gemini_call_timeout` 2건 확인. | 현재 설정 적절. BE 65s > AI 55s 마진 확보됨. |
| **AI-7** | GCS 다운로드 실패 | ❌ **소거** | — | `analyze_service.py:80-84`. 로그 `analyze_pre_gemini` 출력 = GCS 성공 후 Gemini 호출 단계에서 실패. | — |
| **AI-8** | Gemini JSON 파싱 실패 | ❌ **소거** | — | `analyze_service.py:120-141`. Gemini 호출 자체가 실패하여 파싱 단계 미도달. | — |
| **AI-9** | GenAI Client 초기화 실패 | ❌ **소거** | — | `gemini_client.py:27-53`. 로그 `gemini_call_start` 출력 = 클라이언트 정상 초기화. | — |
| **AI-10** | DEBUG 로깅 프로드 잔존 | ⚠️ **부수 이슈** | 🟡 P2 | `gemini_client.py:21-22` `google.genai`+`httpx` DEBUG 레벨. 성능 영향 + 로그 노이즈. | 배포 전 제거 필요. |
| **AI-11** | AFC(Automatic Function Calling) 설정 | ❌ **소거** | — | `gemini_client.py:90` `disable=True`. 이미 비활성. 영향 없음. | — |
| **AI-12** | Cloud Run 콜드스타트 (AI) | △ **간접 가능** | 🟡 P2 | `cloudbuild.yaml:35` `min-instances=1`. min 1이므로 완전 콜드 아님. 단, 동시 요청 폭증 시 스케일아웃 인스턴스는 콜드. | 현재 트래픽 수준에서는 해당 없음. |
| **AI-13** | Cloud Run concurrency=10 병목 | △ **확인 필요** | 🟡 P2 | `cloudbuild.yaml:34` `concurrency=10`. Gemini 호출이 2~55초 블로킹이므로 10 동시 요청 초과 시 queuing. | 현재 트래픽 낮아 해당 없음. 향후 모니터링. |

### AI 서비스 결론

> **근본 원인은 AI-1 + AI-2 + AI-3의 조합.**
> - 현재: AI-1 (gemini-3-flash 404) → 즉시 실패
> - 롤백 후: AI-2 + AI-3 (gemini-2.5-flash + asia-northeast3 쿼터 한계) → 간헐 429
> - 근본: AI-3 (리전 쿼터) — 모델을 바꿔도 asia-northeast3의 Gemini 쿼터가 근본적으로 제한적

---

## 4. 에러 흐름 코드라인 추적

### 4.1 현재 에러 (404 — gemini-3-flash-preview)

```
FE: POST /api/analyses
  → Java BE: JWT 검증 → GCS 업로드 → WebClient POST /internal/ai/analyze
    → FastAPI: app/routers/ai.py:28-30
      → app/services/analyze_service.py:74
        → :80-84   GCS download ✅
        → :110-118  call_gemini(model=GeminiModel.FLASH)
          → app/core/gemini_client.py:59  FLASH = "gemini-3-flash" ← 미지원 모델
          → :35     location="asia-northeast3"
          → :120-128 asyncio.wait_for → client.models.generate_content
          → Vertex AI 404 NOT_FOUND 반환
          → :44     http_status_codes=[429,500,502,503,504] — 404 미포함, 재시도 안함
          → :191-204 except Exception → LLMServiceError(502, "LLM_SERVICE_ERROR")
      → app/core/error_handler.py:31  LLMServiceError → HTTP 502
    → Java BE: AI 502 수신 → AN001 매핑
  → FE: 502 {"code":"AN001","message":"AI 분석 서비스 연결에 실패했습니다"}
```

### 4.2 롤백 후 에러 (429 — gemini-2.5-flash)

```
FE: POST /api/analyses
  → Java BE → FastAPI
    → call_gemini(model="gemini-2.5-flash")
      → :120-128 Vertex AI 429 RESOURCE_EXHAUSTED
      → SDK retry (line 38-45): 1.0s~1.27s 대기 후 재시도 (attempts=2)
      → 재시도도 429 → tenacity 최종 실패
      → :178-190 is_429=True → LLMRateLimitError(429, "LLM_RATE_LIMITED")
    → error_handler.py:30 → HTTP 429
  → Java BE: AI 429 수신 → 에러 매핑 → FE 전달
```

---

## 5. 인프라 계층 문제

| ID | 문제 | 도메인 | 현황 | 영향 |
|----|------|--------|------|------|
| **INFRA-1** | Gemini 쿼터: asia-northeast3 제한적 | GCP/Vertex AI | 🔴 활성 | 429 간헐 발생. 롤백해도 지속. |
| **INFRA-2** | Cloud Run 리전 = Gemini 호출 리전 동일 | AI 서비스 배포 | 🟡 설계 이슈 | Cloud Run은 asia-northeast3 유지하되 Gemini 호출만 us-central1로 분리 가능 |
| **INFRA-3** | Cloud Build 자동 배포 (main push 트리거 추정) | CI/CD | ⚠️ 확인 필요 | 현재 로컬 수정이 배포 안 됨 → 어떤 브랜치/트리거로 배포되는지 확인 필요 |
| **INFRA-4** | `--no-allow-unauthenticated` + OIDC | 서비스 간 인증 | ✅ 정상 | BE→AI OIDC 토큰 정상 발급·검증됨 (로그 확인) |
| **INFRA-5** | min-instances=1, concurrency=10 | 스케일링 | ✅ 현재 적절 | 현 트래픽 수준 적절. 트래픽 증가 시 재검토. |

---

## 6. 전체 문제 우선순위 매트릭스

| 순위 | ID | 문제 | 도메인 | 상태 | 조치 |
|------|----|------|--------|------|------|
| **P0-1** | AI-1 | gemini-3-flash 404 (현재 활성) | AI 코드 | 🔴 로컬 수정 완료, 미배포 | **즉시 배포** |
| **P0-2** | AI-2+AI-3+INFRA-1 | gemini-2.5-flash 429 (롤백 후 재발) | AI 코드 + 인프라 | 🔴 근본 미해결 | §7 옵션 선택 |
| P1 | AI-5 | retry attempts=2 부족 | AI 코드 | 🟡 | attempts 3~4로 증가 |
| P1 | AI-10 | DEBUG 로깅 프로드 잔존 | AI 코드 | 🟡 | 배포 전 제거 |
| P2 | FE-5 | localhost:3001 디버그 코드 | FE 코드 | 🟡 | miriartApi.ts 9곳 제거 |
| P2 | FE-6 | FE 재시도 패턴 확인 | FE 코드 | △ | 자동 재시도 여부 확인 |
| P2 | BE-4 | BE 65s vs AI 55s 타임아웃 경합 | BE 설정 | △ | 모니터링 |
| P3 | AI-12 | AI Cloud Run 콜드스타트 | 인프라 | △ | 현재 해당 없음 |
| P3 | AI-13 | concurrency=10 병목 | 인프라 | △ | 향후 모니터링 |

---

## 7. P0-2 해결 옵션 (429 쿼터 문제)

| 옵션 | 설명 | 변경 범위 | 장점 | 단점 |
|------|------|-----------|------|------|
| **A. Gemini 호출 리전 분리** | `gemini_client.py:35`에서 Gemini API만 `us-central1`로 변경. Cloud Run은 asia-northeast3 유지. | `config.py` 또는 `gemini_client.py` 1줄 | 쿼터 여유 대폭 증가, 최신 모델 우선 지원 | 네트워크 레이턴시 +200~500ms |
| **B. 모델 폴백 체인** | `call_gemini()` 내 429/5xx 시 `gemini-2.0-flash-lite`로 자동 폴백 | `gemini_client.py` ~20줄 | 가용성 향상 | 폴백 모델 품질 하락, 코드 복잡도 |
| **C. Vertex AI 쿼터 증가** | GCP 콘솔 → IAM & Admin → Quotas에서 asia-northeast3 쿼터 증가 신청 | GCP 콘솔 (코드 변경 없음) | 근본 해결 | 승인 1~3 영업일 |
| **D. A+C 조합 (권장)** | 즉시 리전 분리(A)로 unblock + 병행하여 쿼터 증가(C) 신청 | A 수준 | 즉시 해결 + 장기 안정 | 레이턴시 소폭 증가 (C 승인 후 원복 가능) |

---

## 8. 즉시 조치 사항 (배포 전 체크리스트)

### 8.1 gemini_client.py 변경 (이미 로컬 반영)

```python
# Line 59-61: 모델 상수 롤백 ✅ (현재 uncommitted diff)
class GeminiModel:
    FLASH = "gemini-2.5-flash"          # was "gemini-3-flash" (404)
    PRO = "gemini-2.5-pro"              # was "gemini-3.1-pro-preview"
    FLASH_LITE = "gemini-2.0-flash-lite" # was "gemini-3.1-flash-lite-preview"
```

### 8.2 추가 변경 필요 (P0-2 대응 시)

```python
# Option A: Gemini 호출 리전 분리
# gemini_client.py:35 또는 config.py에 gemini_region 별도 설정
GEMINI_REGION = "us-central1"  # Cloud Run 리전과 분리

# gemini_client.py:35
client = genai.Client(
    vertexai=True,
    project=settings.gcp_project_id,
    location=GEMINI_REGION,  # was: settings.gcp_region
    ...
)
```

### 8.3 DEBUG 로깅 제거

```python
# gemini_client.py:21-22 삭제
# logging.getLogger("google.genai").setLevel(logging.DEBUG)
# logging.getLogger("httpx").setLevel(logging.DEBUG)
```

---

## 9. 검증 계획

| 단계 | 검증 내용 | 방법 | 기대 결과 |
|------|-----------|------|-----------|
| 1 | 모델 롤백 배포 후 404 해소 | FE에서 분석 요청 | 502 AN001 해소 또는 429로 변경 |
| 2 | 429 발생 여부 확인 | Cloud Run 로그 `gemini_call_rate_limited` 모니터링 | 간헐 429 확인 |
| 3 | 리전 분리 적용 시 429 해소 | 동일 테스트 | 200 정상 응답 |
| 4 | 응답 품질 확인 | 분석 결과 JSON 구조 및 내용 검증 | grade, totalScore, radarData 등 정상 |

---

## 부록: 에러 코드 → 예외 → HTTP 매핑 표

| 예외 클래스 | error_code | HTTP Status | 발생 조건 | 코드 위치 |
|-------------|------------|-------------|-----------|-----------|
| `LLMTimeoutError` | LLM_TIMEOUT | 504 | asyncio.wait_for 55s 초과 | gemini_client.py:160-173 |
| `LLMRateLimitError` | LLM_RATE_LIMITED | 429 | Vertex AI 429 RESOURCE_EXHAUSTED | gemini_client.py:175-190 |
| `LLMServiceError` | LLM_SERVICE_ERROR | 502 | Vertex AI 4xx/5xx (429 제외) | gemini_client.py:191-204 |
| `LLMParsingError` | LLM_PARSING_ERROR | 502 | Gemini 응답 JSON 파싱 실패 | analyze_service.py:120-141 |
| `GCSError` | GCS_ERROR | 502 | GCS 다운로드/업로드 실패 | gcs_service.py → 호출부 |
| `ValidationError` | VALIDATION_ERROR | 400 | 입력 검증 실패 | 각 서비스 |
| (unhandled) | INTERNAL_ERROR | 500 | 미처리 예외 | error_handler.py:84-98 |

| BE 에러 코드 | 원인 | 매핑 |
|-------------|------|------|
| AN001 | AI 서비스 연결 실패 (502/5xx) | AI → LLMServiceError(502) → BE AN001(502) |

---

## 부록: 배포 인프라 참조

```
cloudbuild.yaml:
  - Image: asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:$COMMIT_SHA
  - Region: asia-northeast3
  - CPU: 1 (boost enabled)
  - Memory: 1Gi
  - Port: 8080
  - Timeout: 120s
  - Scaling: min=1, max=20
  - Concurrency: 10
  - Auth: --no-allow-unauthenticated
  - SA: miriart-ai-runner@miriarts.iam.gserviceaccount.com
  - Env: GCP_PROJECT_ID=miriarts, GCP_REGION=asia-northeast3, GCS_BUCKET_NAME=miriart-bucket
```

---

*문서 끝 — 2026-03-11 전체 도메인 종합 진단*
