# 코드 vs 문서 갭 리포트

> **기준**: 현 코드라인을 유일 SSOT로 두고, 문서와 불일치하는 항목을 단계별로 정리함.  
> **작성일**: 2026-03-10 · **갱신일**: 2026-03-11 (현 코드라인 검수 반영)  
> **목적**: 문서 스위트를 코드에 맞춰 수정할 때 체크리스트로 사용.

---

## §0. 현 코드라인 기준 메타 (SSOT)

**기준 시점**: 2026-03-11 검수 (app/ 및 인프라 설정 실제 파일 기준).

### 0.1 app/ 폴더별 파일·심볼·라인범위

#### app/main.py (마지막 엔드: 51)

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| function | lifespan | 23 | 31 |
| config | app (FastAPI 인스턴스) | 34 | 41 |
| route | (router mount prefix) | 44 | 44 |
| route | health | 47 | 50 |

#### app/core/config.py (마지막 엔드: 32)

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| class | Settings | 12 | 25 |
| function | get_settings | 28 | 31 |

#### app/core/exceptions.py (마지막 엔드: 57)

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| class | MiriArtAIError | 9 | 15 |
| class | LLMTimeoutError | 18 | 22 |
| class | LLMRateLimitError | 25 | 29 |
| class | LLMServiceError | 32 | 36 |
| class | LLMParsingError | 39 | 43 |
| class | GCSError | 46 | 50 |
| class | ValidationError | 53 | 57 |

#### app/core/error_handler.py (마지막 엔드: 98)

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| constant | ERROR_MAP | 28 | 34 |
| function | register_exception_handlers | 38 | 98 |

#### app/core/gemini_client.py (마지막 엔드: 206)

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| function | get_genai_client | 27 | 52 |
| class | GeminiModel | 56 | 61 |
| function | call_gemini | 64 | 205 |

**핵심 값 (코드 기준)**: timeout=55*1000 (36), attempts=2 (38), effective_timeout or 55 (84), FLASH/PRO/FLASH_LITE (59-61), automatic_function_calling disable (90), 429→LLMRateLimitError (186-191).

#### app/core/logging_config.py (마지막 엔드: 25)

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| function | setup_logging | 13 | 25 |

#### app/middleware/request_context.py (마지막 엔드: 46)

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| class | RequestContextMiddleware | 18 | 45 |
| constant | EXCLUDE_PATHS | 21 | 21 |

#### app/routers/ai.py (마지막 엔드: 81)

| Method | Path | Handler | 시작행 | 끝행 |
|--------|------|---------|--------|------|
| POST | /internal/ai/analyze | analyze | 28 | 30 |
| POST | /internal/ai/chat | chat | 39 | 41 |
| POST | /internal/ai/edit-image | edit_image | 50 | 52 |
| POST | /internal/ai/summarize-answers | api_summarize_answers | 61 | 64 |
| POST | /internal/ai/draft-from-question | api_draft_from_question | 73 | 80 |

#### app/schemas/analyze.py (마지막 엔드: 59)

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| class | InternalAnalyzeRequest | 14 | 22 |
| class | RadarData | 24 | 34 |
| class | UniversityPrediction | 36 | 46 |
| class | InternalAnalyzeResponse | 48 | 59 |

#### app/schemas/chat.py (마지막 엔드: 56)

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| class | HistoryItem | 14 | 20 |
| class | StickyContext | 23 | 31 |
| class | InternalChatRequest | 34 | 45 |
| class | InternalChatResponse | 48 | 56 |

#### app/schemas/image_edit.py (마지막 엔드: 29)

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| class | InternalImageEditRequest | 14 | 20 |
| class | InternalImageEditResponse | 23 | 29 |

#### app/schemas/qa.py (마지막 엔드: 47)

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| class | SummarizeAnswersRequest | 14 | 20 |
| class | SummarizeAnswersResponse | 23 | 28 |
| class | DraftFromQuestionRequest | 32 | 38 |
| class | DraftFromQuestionResponse | 41 | 47 |

#### app/services/analyze_service.py (마지막 엔드: 143)

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| function | _detect_mime | 38 | 42 |
| constant | ANALYZE_SYSTEM_PROMPT, ANALYZE_USER_TEMPLATE | 45 | 71 |
| function | analyze_artwork | 74 | 142 |

#### app/services/chat_service.py (마지막 엔드: 98)

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| constant | MODEL_MAP, CHAT_SYSTEM_PROMPT | 19 | 35 |
| function | _flatten_history | 38 | 53 |
| function | chat | 56 | 98 |

#### app/services/image_edit_service.py (마지막 엔드: 79)

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| function | edit_image | 26 | 78 |

**핵심 값**: timeout_override_s=25 (44).

#### app/services/qa_service.py (마지막 엔드: 115)

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| constant | SUMMARIZE_*, DRAFT_* | 18 | 53 |
| function | summarize_answers | 56 | 76 |
| function | draft_from_question | 79 | 115 |

#### app/services/gcs_service.py (마지막 엔드: 71)

| 심볼종류 | 심볼이름 | 시작행 | 끝행 |
|----------|----------|--------|------|
| class | GcsService | 15 | 71 |
| method | download_as_bytes, generate_signed_url, upload_bytes | 31 | 70 |

---

### 0.2 인프라 기준 코드라인

| 파일 | 행 | 설정/의미 |
|------|-----|-----------|
| cloudbuild.yaml | 29 | --port=8080 |
| cloudbuild.yaml | 32 | --timeout=120 |
| cloudbuild.yaml | 40 | --set-env-vars=GCP_PROJECT_ID=miriarts,... |
| cloudbuild.yaml | 41 | --project=miriarts |
| app/core/config.py | 22 | gcp_project_id 기본값 "miriart-dev" |
| app/core/config.py | 26 | gemini_location 기본값 "global" (Gemini API 호출 리전) |
| app/core/config.py | 23-25 | gcp_region, gcs_bucket_name, google_application_credentials |
| Dockerfile | 10 | EXPOSE 8080 |
| Dockerfile | 12 | CMD uvicorn --port 8080 |

---

## 1. gemini_client / 타임아웃·리트라이·모델

**코드 기준**: [app/core/gemini_client.py](app/core/gemini_client.py)

| 항목 | 문서 기재 | 문서 위치 | 코드 실제 (파일:행) |
|------|-----------|-----------|------------------------|
| SDK HTTP timeout | 28초 (BE 30s - 2s 마진) | IOPE_MAP §A P, RUNBOOK 등 | **55초** `timeout=55*1000` (36) |
| 기본 effective_timeout | 28s | IOPE_MAP §A, §B, §D, §E, 표 "Timeout 28s" | **55s** `effective_timeout = timeout_override_s or 55` (84) |
| 리트라이 attempts | 3회 | IOPE_MAP §A "리트라이: 3회", 표 "리트라이 3회" | **2회** `attempts=2` (38) |
| Gemini 모델 ID (Flash) | `gemini-2.5-flash` (문서 일부 일치) | IOPE_MAP §A "Model: gemini-2.5-flash" | **gemini-2.5-flash** `FLASH = "gemini-2.5-flash"` (59) |
| Gemini 모델 ID (Pro) | `gemini-2.5-pro` (문서 일치) | IOPE_MAP §B CHAT_PRO/THINKING | **gemini-2.5-pro** `PRO = "gemini-2.5-pro"` (60) |
| Flash Lite | `gemini-2.0-flash-lite` (문서 일치) | (일부 문서) | **gemini-2.0-flash-lite** (61) |
| AFC (Automatic Function Calling) | 미기재 | — | **비활성** `automatic_function_calling=...disable=True` (90) |
| image_edit timeout_override | 55s | IOPE_MAP §C "timeout=55s", RUNBOOK | **25s** [app/services/image_edit_service.py:44](app/services/image_edit_service.py) |

---

## 2. 에러 응답 형식 (body 필드명)

**코드 기준**: [app/core/error_handler.py](app/core/error_handler.py) → JSON body는 `code` + **`message`** 사용.

| 문서 기재 | 문서 위치 | 코드 실제 (파일:행) |
|-----------|-----------|------------------------|
| `"detail": "..."` | MIRIART_AI_API_REFERENCE.md §5, MIRIART_AI_IOPE_MAP 에러 표, RUNBOOK §2.3 | **`"message"`** (56, 73, 97) |

→ 모든 "에러 body의 `detail`" 설명을 **`message`**로 통일 필요.

---

## 3. 에러 코드·예외 계층 (429 / LLM_RATE_LIMITED)

**코드 기준**: [app/core/exceptions.py](app/core/exceptions.py), [app/core/error_handler.py](app/core/error_handler.py), [app/core/gemini_client.py](app/core/gemini_client.py)

| 항목 | 문서 기재 | 문서 위치 | 코드 실제 (파일:행) |
|------|-----------|-----------|------------------------|
| 429 전용 예외/코드 | 없음 (502 LLM_SERVICE_ERROR로만 기술) | API_REFERENCE §5, IOPE_MAP 에러 표, RUNBOOK §2.1 | **LLMRateLimitError** → HTTP **429**, body.code **LLM_RATE_LIMITED** (exceptions.py:25-29, error_handler.py:29, gemini_client.py:186-191) |
| 예외 계층도 | LLMTimeoutError, LLMServiceError, LLMParsingError, GCSError, ValidationError | RUNBOOK §2.1 | 위 5개 + **LLMRateLimitError** (exceptions.py:25-29) |

→ API_REFERENCE §5 에러 코드 표에 **429 / LLM_RATE_LIMITED** 행 추가, RUNBOOK 예외 계층에 **LLMRateLimitError** 추가.

---

## 4. health 엔드포인트·미들웨어 제외 경로

**코드 기준**: [app/main.py:47-50](app/main.py), [app/middleware/request_context.py:21](app/middleware/request_context.py)

| 항목 | 문서 기재 | 문서 위치 | 코드 실제 |
|------|-----------|-----------|-----------|
| health 경로 | `/health` 및 `/internal/ai/health` 제외 | RUNBOOK §1.2 "제외: `/health`, `/internal/ai/health`" | **라우트는 `/health`만 존재** (main.py:47-50). 미들웨어는 EXCLUDE_PATHS = {"/health", "/internal/ai/health"} (21) → `/internal/ai/health`는 정의된 라우트 없음 |

→ RUNBOOK은 "제외: `/health`"만 명시하거나, "미들웨어에서 `/internal/ai/health`도 제외 대상으로 등록되어 있으나 해당 경로 라우트는 없음"으로 정리 가능.

---

## 5. config 기본값 (GCP 프로젝트)

**코드 기준**: [app/core/config.py:22-25](app/core/config.py)

| 항목 | 문서 기재 | 문서 위치 | 코드 실제 |
|------|-----------|-----------|-----------|
| GCP_PROJECT_ID 기본값 | (일부 문서에서 miriarts 전제) | SSOT/infra, cloudbuild | **`gcp_project_id: str = "miriart-dev"`** (22). Prod는 cloudbuild.yaml:40으로 GCP_PROJECT_ID=miriarts 오버라이드 |

→ "기본값은 miriart-dev, Prod에서는 env로 miriarts 사용" 명시 권장.

---

## 6. analyze·chat·qa 타임아웃 (문서 28s vs 코드 55s)

**코드 기준**: [app/core/gemini_client.py:84](app/core/gemini_client.py), [app/services/image_edit_service.py:44](app/services/image_edit_service.py). analyze/chat/qa는 timeout_override_s 미지정 → call_gemini 기본값 **55s** 사용.

| 기능 | 문서 | 코드 (파일:행) |
|------|------|----------------|
| 작품 분석 | 28s | **55s** (gemini_client 84, analyze_service에 override 없음) |
| AI 채팅 | 28s | **55s** (gemini_client 84, chat_service에 override 없음) |
| QA 요약/초안 | 28s | **55s** (gemini_client 84, qa_service에 override 없음) |
| 이미지 편집 | 55s (문서) | **25s** (image_edit_service.py:44) |

→ IOPE_MAP, RUNBOOK, API_REFERENCE 등 **모든 "28s"/"55s"** 표기를 위 코드 기준으로 수정 필요.

---

## 7. 기타 문서 참조 경로

| 문서 내용 | 문제 | 코드/설정 기준 |
|-----------|------|-----------------|
| "전체 엔드포인트: docs/miriart-ai-codebase-snapshot.md §2.1" | 레포 내 경로는 **docs/miriart-ai-codebase-snapshot.md** 로 존재함 | [app/routers/ai.py](app/routers/ai.py), [app/main.py:44](app/main.py) |
| INFRA_SSOT_GUIDE "인프라 SSOT \| docs/SSOT/miriarts_infra.md" | 실제 파일은 **SSOT/miriarts_infra.md** (루트의 SSOT/) | 레포 루트 기준 `SSOT/miriarts_infra.md` |

---

## 8. 요약 체크리스트 (문서 수정 시)

- [x] **gemini_client**: timeout 55s (36), attempts=2 (38), 기본 effective_timeout 55s (84), 모델 ID gemini-2.5-flash / gemini-2.5-pro / gemini-2.0-flash-lite (59-61), AFC 비활성 (90) 반영.
- [x] **image_edit**: timeout_override_s=**25s** (image_edit_service.py:44) — 문서의 55s 제거.
- [x] **에러 body**: 모든 "detail" → **"message"** (error_handler.py:56,73,97) 로 통일.
- [x] **429**: LLMRateLimitError, HTTP 429, code LLM_RATE_LIMITED 문서 전반 추가 (exceptions.py:25-29, error_handler.py:29).
- [x] **예외 계층**: RUNBOOK에 LLMRateLimitError 추가.
- [x] **health**: RUNBOOK에서 `/internal/ai/health` 설명을 "미들웨어 제외만 있고 라우트 없음" 또는 "제외: /health"로 정리 (main.py:47-50, request_context.py:21).
- [x] **config**: GCP_PROJECT_ID 기본값 miriart-dev (config.py:22), prod는 miriarts (cloudbuild.yaml:40) 명시.
- [x] **참조 경로**: INFRA_SSOT_GUIDE에서 docs/SSOT → SSOT/ 수정. codebase-snapshot은 docs/ 존재 확인됨.

---

## 추가 갭 요인 (동일 층위 미식별 → 문서 반영 권장)

- **(A1)** 리트라이 백오프: 문서 "1→2→4s, 3회" → 코드는 **2회(1회 재시도), initial_delay 1s, max_delay 8s** (gemini_client.py:38-41).
- **(A2)** **GEMINI_LOCATION** (gemini_location): config.py:26 기본값 "global", Gemini API 호출에 사용. 문서 env 인벤토리에 반영 (RUNBOOK §4.1, SSOT §3.2).
- **(A3)** INTERNAL_ERROR 응답 메시지: 코드 `"Internal server error"` (error_handler.py:97). 문서 한글 "내부 서버 오류가 발생했습니다"와 불일치 → 영문으로 통일.
- **(A4)** 400 VALIDATION_ERROR 시 body에 **errors** 배열 (field, message) 포함 — error_handler.py:70-79. 문서에 구조 명시.
- **(A5)(A6)** 로그 이벤트: **gemini_call_start**, **gemini_call_rate_limited**, 서비스 레벨(예: analyze_pre_gemini) RUNBOOK §1.2 카탈로그 반영.
- **(A7)** draft 필드: 문서 "200자 이내" — 코드 스키마에는 길이 제한 없음(schemas/qa.py). 프롬프트 유도만 있음.
- **(A8)** 로컬 포트: uvicorn 8000 vs Docker/Cloud Run 8080, BE FASTAPI_INTERNAL_URL 선택 기준 문서 정리.

**PRD·FSD 갱신 규칙** (코드·API_CONTRACT 변경 시): (1) FSD 해당 기능(F3/F4/C4 등) I-P-O-E·Exception·구현 상태 점검. (2) PRD §4.1 갭 표·SSOT 경로 점검. (3) 갭 리포트 §0·§1 값과 불일치 수치(타임아웃·에러코드) 정리.

---

## §9. 문서별 수정 체크리스트

### MIRIART_AI_API_REFERENCE.md — 적용 완료

- [x] §5 에러 응답: `detail` → `message` 로 변경.
- [x] §5 에러 코드 표: **429 / LLM_RATE_LIMITED** 행 추가.
- [x] §1 health Handler명 `health` 반영, §2.5 draft 200자 문구 수정.
- (선택) 타임아웃/리트라이/모델 값이 §0·§1과 일치하는지 검토.

### MIRIART_AI_IOPE_MAP.md — 적용 완료

- [x] §A P (analyze): timeout 28s → 55s, 리트라이 2회·백오프 문구 수정.
- [x] §B: timeout 28s → 55s.
- [x] §C (edit-image): timeout 55s → **25s** (timeout_override_s=25).
- [x] §D, §E: timeout 55s, 에러 55s 초과 반영.
- [x] 에러 표: body `detail` → `message`. **LLM_RATE_LIMITED (429)** 행 추가.
- [x] 통합 참조표·Gemini 호출 파라미터 요약: 동일 반영.

### MIRIART_AI_RUNBOOK.md — 적용 완료

- [x] §2.1 예외 계층: **LLMRateLimitError** 추가.
- [x] §2.2 에러 매핑: LLMRateLimitError → 429, body.message, INTERNAL_ERROR 영문 메시지.
- [x] §2.3 에러 응답 형식: `detail` → `message`.
- [x] §1.2 HTTP 제외 경로·Gemini 로그 이벤트(gemini_call_start, gemini_call_rate_limited) 추가.
- [x] §4.1 환경변수: GCP_PROJECT_ID 기본값 miriart-dev, prod miriarts, GEMINI_LOCATION 추가.
- [x] §6.3 타임아웃/리트라이: 55s, 25s(edit), 2회. §6.4 429 → LLMRateLimitError 문구.

### SSOT/miriarts_infra.md — 적용 완료

- [x] §3.1 FastAPI: gemini_location, config 기본값 명시.
- [x] §3.2 GEMINI_LOCATION 행 추가, GCP_PROJECT_ID 기본값/prod 구분.
- [x] §5.3 miriart-ai --set-env-vars 행에 GEMINI_LOCATION 선택 언급.

### .cursor/INFRA_SSOT_GUIDE.md (및 .claude 동일본) — 적용 완료

- [x] 인프라 SSOT 경로: `docs/SSOT/miriarts_infra.md` → **SSOT/miriarts_infra.md**.

### docs/MiriArt_API_CONTRACT.md — 적용 완료

- [x] §8.0 내부 API 에러: 429 LLM_RATE_LIMITED, 55s/25s 타임아웃 반영.
- [x] §9.7 AI 429·LLM_RATE_LIMITED 안내 추가. §10 SSOT 경로 정리.

### docs/MiriArt_FSD_v2.md — 적용 완료

- [x] §1 기능 범위 요약 표 C4: 구현 상태 **구현됨 (FastAPI)**, BE/FE 공개 노출 Phase C 정책 명시.
- [x] §C4: 스텁(501) → **구현됨 (FastAPI)**. POST summarize-answers, draft-from-question (app/routers/ai.py:56-76, qa_service).
- [x] F3 Exception: AI 504/429 반환 시 BE AN002 등 매핑, API_CONTRACT §8·§9 참조 보강.
- [x] F4 Exception: 429(LLM_RATE_LIMITED) 시 BE 매핑 API_CONTRACT §9.7 참조 추가.
- [x] Document Metadata 문서 갱신 규칙 (4): API_CONTRACT·갭 리포트 갱신 시 FSD F3/F4/C4 점검.

### docs/MiriArt_PRD_v2.md — 적용 완료

- [x] §0 검증 기준선: docs/SSOT/miriarts_infra.md → **SSOT/miriarts_infra.md** (레포 루트 기준).
- [x] §4.1 갭 분석 SSOT: 동일 경로 수정.
- [x] §4.1 표: C4 행 추가 (FastAPI 구현 완료).

---

## §10. 요약 체크리스트 (최종)

- [ ] §0 코드라인 인벤토리 유지: 코드 변경 시 해당 파일·심볼·라인 갱신.
- [x] §1~§8 갭 항목: 문서 수정 완료 (2026-03-10 플랜 실행). "문서 기재" 열은 해당 문서 수정으로 반영됨.
- [x] §9 문서별 체크리스트: 위 문서별 적용 완료 표시 반영.
- [ ] 인프라 변경 시 §0.2 및 cloudbuild.yaml / config.py 라인 반영.

---

*문서 끝 — 코드 기준 2026-03-11*
