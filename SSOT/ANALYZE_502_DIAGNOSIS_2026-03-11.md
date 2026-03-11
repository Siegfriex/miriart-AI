# 이미지 분석 502 Bad Gateway 종합 진단 리포트

> **작성일**: 2026-03-11 13:10 KST
> **현상**: `POST /api/analyses` → `502 Bad Gateway` (code: AN001, "AI 분석 서비스 연결에 실패했습니다")
> **현재 활성 리비전**: `miriart-ai-00011-zgf` (gemini-3-flash-preview — 404), 롤백 대기 중

---

## 1. 문제 정의

### 1.1 관측된 에러 체인

```
FE (miri-art.vercel.app)
  └─ POST /api/analyses (multipart: image + analysisType + problemText)
      └─ OPTIONS preflight → 200 OK ✅
      └─ POST with Bearer JWT → BE 도달 ✅
          └─ Java BE (miriart-be)
              └─ WebClient POST /internal/ai/analyze → FastAPI AI 서비스
                  └─ GCS download → ✅
                  └─ Gemini API call → ❌ 실패
                      └─ 현재: 404 NOT_FOUND (gemini-3-flash-preview 모델 미지원)
                      └─ 롤백 시: 429 RESOURCE_EXHAUSTED (gemini-2.5-flash 쿼터 초과)
              └─ AI 서비스가 502 반환 → BE가 AN001로 매핑 → FE에 502 전달
```

### 1.2 FE 콘솔 로그 타임라인 (04:00~04:06 UTC)

| 시각(UTC) | 요청 | 결과 |
|---|---|---|
| ~04:00 | POST /api/analyses (1차) | 502 Bad Gateway |
| ~04:04 | POST /api/analyses (2차) | 502 Bad Gateway |
| 04:06:19 | OPTIONS /api/analyses (preflight) | 200 OK |
| 04:06:24 | POST /api/analyses (3차) | 502 `{"code":"AN001","message":"AI 분석 서비스 연결에 실패했습니다"}` |

### 1.3 Cloud Run 로그 일치 확인

| 시각(UTC) | AI 서비스 로그 | 에러 |
|---|---|---|
| 04:00:25 | `gemini_call_error` | `gemini-3-flash-preview` → 404 NOT_FOUND |
| 04:04:57 | `gemini_call_error` | `gemini-3-flash-preview` → 404 NOT_FOUND (13.99s) |
| 04:06:24 | `gemini_call_error` | `gemini-3-flash-preview` → 404 NOT_FOUND (2.25s) |

---

## 2. 도메인별 경우의 수 분석

### 2.1 FE (React / Vercel)

| # | 가설 | 가능성 | 근거 |
|---|---|---|---|
| FE-1 | JWT 미전송 / 만료 | ❌ 배제 | 네트워크 탭 확인: `Authorization: Bearer eyJhbG...` 정상 포함. OPTIONS 200 후 POST 도달. |
| FE-2 | CORS preflight 실패 | ❌ 배제 | OPTIONS → 200, `access-control-allow-origin: https://miri-art.vercel.app` 확인 |
| FE-3 | multipart 페이로드 불량 | ❌ 배제 | `content-type: multipart/form-data`, image/analysisType/problemText 모두 정상. BE가 수신하여 AI 서비스 호출까지 진행함. |
| FE-4 | `127.0.0.1:3001/ingest` 디버그 코드 | ⚠️ 부수 이슈 | `miriartApi.ts`에 9곳 하드코딩. CORS 에러 발생하지만 `.catch(()=>{})` 무시. 분석 502의 직접 원인은 아님. **별도 정리 필요.** |

**FE 결론**: 분석 502의 원인 아님. 요청 정상 전달 확인.

---

### 2.2 Java BE (Spring Boot / Cloud Run)

| # | 가설 | 가능성 | 근거 |
|---|---|---|---|
| BE-1 | OIDC ID Token 인증 실패 (BE→AI) | ❌ 배제 | AI 서비스 로그에 `analyze_pre_gemini` + `gemini_call_start` 출력됨 = 요청이 AI 서비스에 도달. OIDC 정상. |
| BE-2 | WebClient 타임아웃 (65s) | △ 간접 가능 | `RESPONSE_TIMEOUT_SECONDS=65`. AI 서비스가 55s 내 실패 반환하므로 현재는 해당 안됨. 단, Gemini가 55s 가까이 걸리면 BE 타임아웃 먼저 발동 가능. |
| BE-3 | AI 서비스 URL 미스매치 | ❌ 배제 | `miriart.fastapi.internal-url` → AI Cloud Run URL. 로그상 정상 도달. |
| BE-4 | AI 응답 502를 BE가 AN001로 매핑 | ✅ 확인 | AI 서비스가 `LLMServiceError` → HTTP 502 + `{"code":"LLM_SERVICE_ERROR","message":"..."}` 반환. BE의 `AiProxyService`가 이를 받아 AN001로 변환하여 FE에 전달. **정상 동작** — 근본 원인은 AI 서비스. |
| BE-5 | Spring Security 차단 | ❌ 배제 | `/api/analyses`는 인증 필요 엔드포인트이나 JWT 검증 통과 확인 (요청이 BE 비즈니스 로직까지 도달). |

**BE 결론**: BE는 AI 서비스의 에러를 정상 전달하는 역할. 근본 원인 아님.

---

### 2.3 FastAPI AI 서비스 (Python / Cloud Run) — 근본 원인

| # | 가설 | 가능성 | 코드 근거 | 해결 방안 |
|---|---|---|---|---|
| **AI-1** | **Gemini 3 모델 404 (현재 활성)** | ✅ **확정** | `gemini_client.py:59` `FLASH = "gemini-3-flash-preview"` → Vertex AI `asia-northeast3`에서 미지원. 에러: `Publisher Model ... was not found or your project does not have access to it` | **모델명 롤백** → `gemini-2.5-flash` |
| **AI-2** | **Gemini 2.5-flash 429 쿼터 초과 (롤백 시)** | ✅ **재현됨** | `gemini_client.py:120-128` → `call_gemini()` → Vertex AI 429 RESOURCE_EXHAUSTED. SDK `retry_options` (line 38-45)가 429에 대해 1회 재시도하나 재시도도 429면 최종 실패. | **리전 변경** 또는 **쿼터 증가** 또는 **모델 폴백** |
| AI-3 | Gemini 응답 타임아웃 (55s) | △ 과거 발생 | `gemini_client.py:84` `effective_timeout=55`. `asyncio.wait_for` (line 120) 55s 초과 시 `LLMTimeoutError`. 과거 로그: `gemini_call_timeout` 2건 확인. | 이미 55s로 조정 완료. BE 65s > AI 55s 마진 확보. |
| AI-4 | GCS 다운로드 실패 | ❌ 배제 | `analyze_service.py:80-83`. 로그상 `analyze_pre_gemini` 출력 = GCS 다운로드 성공 후 Gemini 호출 단계에서 실패. |
| AI-5 | Gemini JSON 파싱 실패 | ❌ 배제 | `analyze_service.py:120-141`. Gemini 호출 자체가 실패하여 파싱 단계 미도달. |
| AI-6 | GenAI Client 리전 설정 | ⚠️ 핵심 | `config.py:22` `gcp_region = "asia-northeast3"` → `gemini_client.py:35` `location=settings.gcp_region`. Gemini 3 모델은 이 리전에서 미지원. 2.5-flash는 지원되나 쿼터 제한적. | **Gemini 호출 리전을 `us-central1`로 분리** 가능 |
| AI-7 | SDK 재시도가 404에 작동 안 함 | ✅ 확인 | `gemini_client.py:44` `http_status_codes=[429, 500, 502, 503, 504]` — **404는 재시도 대상 아님**. 즉시 실패. 정상 동작이나, 429일 때도 재시도 후 또 429면 최종 실패. | — |

---

## 3. 에러 흐름 코드라인 추적 (FastAPI)

### 3.1 현재 에러 (404 — gemini-3-flash-preview)

```
요청 수신
  → app/routers/ai.py:28-30          # POST /internal/ai/analyze
  → app/services/analyze_service.py:74-118  # analyze_artwork()
    → :80-83   GCS download ✅
    → :110-118 call_gemini(model=GeminiModel.FLASH, ...)
      → app/core/gemini_client.py:59   # FLASH = "gemini-3-flash-preview" ← 문제
      → :83     get_genai_client()
      → :35     location="asia-northeast3" ← 이 리전에서 gemini-3-flash-preview 미지원
      → :120-128 asyncio.wait_for → client.models.generate_content
      → Vertex AI API 404 반환
      → :175-204 except Exception → LLMServiceError
  → app/core/error_handler.py:31     # LLMServiceError → HTTP 502, "LLM_SERVICE_ERROR"
  → Java BE가 502 수신 → AN001 매핑 → FE에 전달
```

### 3.2 롤백 후 예상 에러 (429 — gemini-2.5-flash)

```
요청 수신
  → app/services/analyze_service.py:110-118  # call_gemini(model="gemini-2.5-flash")
    → app/core/gemini_client.py:120-128
      → Vertex AI API 429 반환
      → SDK retry (line 38-45): 1.0~1.27s 대기 후 재시도
      → 재시도도 429 → tenacity 최종 실패
      → :178-190 is_429 감지 → LLMRateLimitError
  → app/core/error_handler.py:30     # LLMRateLimitError → HTTP 429, "LLM_RATE_LIMITED"
  → Java BE가 429 수신 → 에러 매핑 → FE에 전달
```

---

## 4. 최종 문제 정리 및 우선순위

| 우선순위 | 문제 | 도메인 | 상태 | 해결 방안 |
|---|---|---|---|---|
| **P0** | `gemini-3-flash-preview` 404 (asia-northeast3 미지원) | AI (FastAPI) | 🔴 활성 | **즉시 롤백**: `gemini_client.py:59` → `gemini-2.5-flash` |
| **P1** | `gemini-2.5-flash` 429 쿼터 초과 (간헐적) | AI (FastAPI) / Infra | 🟡 롤백 시 재발 | 아래 옵션 중 선택 |
| P2 | `127.0.0.1:3001/ingest` 디버그 코드 | FE | 🟡 부수 이슈 | `miriartApi.ts` 9곳 제거 |
| P3 | 디버그 로깅 프로드 잔존 | AI (FastAPI) | 🟡 | `gemini_client.py:21-22` DEBUG 레벨 제거 |

### P1 해결 옵션

| 옵션 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. Gemini 호출 리전 변경** | `gemini_client.py:35`에서 Gemini API 호출만 `us-central1`로 변경 (Cloud Run은 asia-northeast3 유지) | 쿼터 여유, Gemini 3 모델도 사용 가능 | 네트워크 레이턴시 ~200-500ms 증가 |
| **B. 모델 폴백 로직** | `call_gemini()`에서 429 시 `gemini-2.0-flash`로 자동 폴백 | 가용성 향상 | 폴백 모델 품질 하락, 코드 복잡도 증가 |
| **C. Vertex AI 쿼터 증가 요청** | GCP 콘솔에서 `gemini-2.5-flash` multimodal 쿼터 증가 신청 | 근본 해결 | 승인까지 1-3 영업일 소요 |
| **D. A+B 조합** | 리전 `us-central1` + 429 시 `gemini-2.0-flash` 폴백 | 최대 가용성 | 레이턴시 + 코드 복잡도 |

---

## 5. 즉시 조치 (P0 롤백)

### 변경 파일: `app/core/gemini_client.py`

```python
# Line 59-61: 모델 상수 롤백
class GeminiModel:
    FLASH = "gemini-2.5-flash"          # was "gemini-3-flash-preview" (404)
    PRO = "gemini-2.5-pro"              # was "gemini-3.1-pro-preview"
    FLASH_LITE = "gemini-2.0-flash-lite" # was "gemini-3.1-flash-lite-preview"
```

**이미 로컬 코드에 반영 완료. 재배포 대기 중.**

---

## 6. 참조: 코드 구조 (AI 서비스 에러 경로)

```
app/
├── core/
│   ├── config.py:22        # gcp_region = "asia-northeast3" ← 리전 설정
│   ├── gemini_client.py
│   │   ├── :32-47          # GenAI Client 싱글턴 (project, location, retry)
│   │   ├── :56-61          # GeminiModel 상수 ← P0 수정 대상
│   │   ├── :64-204         # call_gemini() 단일 진입점
│   │   ├── :120-128        # asyncio.wait_for + generate_content
│   │   ├── :160-173        # TimeoutError → LLMTimeoutError
│   │   ├── :175-190        # 429 감지 → LLMRateLimitError
│   │   └── :191-204        # 기타 에러 → LLMServiceError
│   ├── error_handler.py
│   │   ├── :28-35          # ERROR_MAP: 예외→HTTP status 매핑
│   │   └── :41-57          # MiriArtAIError 핸들러 → JSON 응답
│   └── exceptions.py       # 예외 계층 (LLMTimeout/RateLimit/Service/Parsing/GCS)
├── services/
│   └── analyze_service.py
│       ├── :74-84          # GCS 다운로드 (to_thread)
│       ├── :105-108        # contents 구성 (text + image bytes)
│       ├── :110-118        # call_gemini(model=FLASH) ← 여기서 실패
│       └── :120-141        # JSON 파싱 (미도달)
└── routers/
    └── ai.py:28-30         # POST /internal/ai/analyze 엔드포인트
```
