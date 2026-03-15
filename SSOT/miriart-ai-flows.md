# miriart-ai I-P-O-E 플로우 (SSOT)

> **대상**: miriart-ai (FastAPI, Cloud Run) — `/internal/ai/*` 엔드포인트  
> **목적**: 기능별 입력(I)·처리(P)·출력(O)·에러(E) 플로우.  
> **원칙**: 유일 참조는 코드. 타임아웃·리트라이·에러 값은 문서에 고정하지 않고 코드 라인만 인용.

---

## 공통 규칙

- **타임아웃·리트라이**: 소스 `app/core/gemini_client.py:21,23,26,42,44,90`. 이미지 편집만 timeout_override_s: `app/core/gemini_client.py:26`, `app/services/image_edit_service.py:44`.
- **에러 매핑**: 소스 `app/core/error_handler.py:28-35` (ERROR_MAP), body 필드 `:55-56`.
- **Request/Response 스키마**: 참조 [miriart-ai-api.md](miriart-ai-api.md) §2 또는 app/schemas/* 해당 파일:행.

---

## A. 작품 분석 (`POST /internal/ai/analyze`)

소스: `app/routers/ai.py:49-57`, `app/services/analyze_service.py:74-141`.

### I — Input

Path: `POST /internal/ai/analyze`. Request Body: InternalAnalyzeRequest.  
참조: [miriart-ai-api.md](miriart-ai-api.md) §2.1 또는 `app/schemas/analyze.py:14-21`.

### P — Processing

| 단계 | 모듈 | 소스 |
|------|------|------|
| 1 | GCS에서 이미지 다운로드 | gcs_service.download_as_bytes — app/services/gcs_service.py |
| 2 | 프롬프트 구성 | analyze_service ANALYZE_SYSTEM_PROMPT, ANALYZE_USER_TEMPLATE (analyze_service.py:45-71) |
| 3 | Gemini Flash 호출 | gemini_client.call_gemini — app/core/gemini_client.py:70-210. model=Flash(65), timeout·리트라이: gemini_client.py:21,23,42,44,90 |
| 4 | JSON 파싱 | LLM 응답 → 구조화 데이터 |

### O — Output

HTTP 200. Response: InternalAnalyzeResponse. 참조 [miriart-ai-api.md](miriart-ai-api.md) §2.1.

### E — Error

소스: `app/core/error_handler.py:28-35, 55-56`.

| 예외 | HTTP | body.code | BE 매핑 |
|------|------|-----------|---------|
| GCSError | 502 | GCS_ERROR | F003 |
| LLMTimeoutError | 504 | LLM_TIMEOUT | AN002 |
| LLMServiceError | 502 | LLM_SERVICE_ERROR | AN001 |
| LLMParsingError | 502 | LLM_PARSING_ERROR | AN001 |
| LLMRateLimitError | 429 | LLM_RATE_LIMITED | (BE 정책) |

---

## B. AI 채팅 (`POST /internal/ai/chat`)

소스: `app/routers/ai.py:60-68`, `app/services/chat_service.py:128-181`.

### I — Input

Path: `POST /internal/ai/chat`. Request Body: InternalChatRequest.  
참조: [miriart-ai-api.md](miriart-ai-api.md) §2.2 또는 `app/schemas/chat.py:49-60`.

### P — Processing

| 단계 | 동작 | 소스 |
|------|------|------|
| 1 | modelType → Gemini 모델 매핑 | chat_service MODEL_MAP (chat_service.py:22-38) |
| 2 | 시스템 프롬프트 + stickyContext 병합 (summary_text 있으면 한 덩어리 사용, 없으면 개별 필드 조합) | _build_system_prompt (chat_service.py:51-107), _SUMMARY_TEXT_MAX_LEN (48) |
| 3 | history 플랫텐 | _flatten_history (chat_service.py:110-125), _get_effective_history (:41-45) |
| 4 | call_gemini | gemini_client.py:70-210. timeout·리트라이: gemini_client.py:21,23,42,44,90 |

### O — Output

HTTP 200. Response: InternalChatResponse. 참조 [miriart-ai-api.md](miriart-ai-api.md) §2.2.

### E — Error

소스: `app/core/error_handler.py:28-35, 55-56`.

| 예외 | HTTP | body.code | BE 매핑 |
|------|------|-----------|---------|
| ValidationError | 400 | VALIDATION_ERROR | C001 |
| LLMTimeoutError | 504 | LLM_TIMEOUT | AI002 |
| LLMServiceError | 502 | LLM_SERVICE_ERROR | AI001 |
| LLMRateLimitError | 429 | LLM_RATE_LIMITED | (BE 정책) |

---

## C. 이미지 편집 (`POST /internal/ai/edit-image`)

소스: `app/routers/ai.py:71-79`, `app/services/image_edit_service.py:26-78`.

### I — Input

Path: `POST /internal/ai/edit-image`. Request Body: InternalImageEditRequest.  
참조: [miriart-ai-api.md](miriart-ai-api.md) §2.3 또는 `app/schemas/image_edit.py:14-20`.

### P — Processing

| 단계 | 동작 | 소스 |
|------|------|------|
| 1 | base64 디코딩 | image_edit_service |
| 2 | call_gemini (timeout_override_s 사용) | gemini_client.py:70-210. timeout_override_s: gemini_client.py:26, image_edit_service.py:44 |
| 3 | 응답 파싱 (text + inline_data) | image_edit_service |
| 4 | GCS 업로드 | gcs_service.upload_bytes — app/services/gcs_service.py |

### O — Output

HTTP 200. Response: InternalImageEditResponse. 참조 [miriart-ai-api.md](miriart-ai-api.md) §2.3.

### E — Error

소스: `app/core/error_handler.py:28-35, 55-56`.

| 예외 | HTTP | body.code | BE 매핑 |
|------|------|-----------|---------|
| ValidationError | 400 | VALIDATION_ERROR | C001 |
| LLMTimeoutError | 504 | LLM_TIMEOUT | AI002 |
| LLMServiceError | 502 | LLM_SERVICE_ERROR | AI001 |
| GCSError | 502 | GCS_ERROR | F003 |
| LLMRateLimitError | 429 | LLM_RATE_LIMITED | (BE 정책) |

---

## D. QA 답변 요약 (`POST /internal/ai/summarize-answers`)

소스: `app/routers/ai.py:82-91`, `app/services/qa_service.py:56-76`.

### I — Input

Path: `POST /internal/ai/summarize-answers`. Request Body: SummarizeAnswersRequest.  
참조: [miriart-ai-api.md](miriart-ai-api.md) §2.4 또는 `app/schemas/qa.py:14-20`.

### P — Processing

| 단계 | 동작 | 소스 |
|------|------|------|
| 1 | 답변 목록 포맷 | qa_service.summarize_answers |
| 2 | call_gemini (Flash, JSON) | gemini_client.py:21,23,42,44,90 |
| 3 | JSON 파싱 | qa_service |

### O — Output

HTTP 200. Response: SummarizeAnswersResponse. 참조 [miriart-ai-api.md](miriart-ai-api.md) §2.4.

### E — Error

소스: `app/core/error_handler.py:28-35, 55-56`.

| 예외 | HTTP | body.code |
|------|------|-----------|
| LLMTimeoutError | 504 | LLM_TIMEOUT |
| LLMServiceError | 502 | LLM_SERVICE_ERROR |
| LLMParsingError | 502 | LLM_PARSING_ERROR |
| LLMRateLimitError | 429 | LLM_RATE_LIMITED |

---

## E. QA 답변 초안 (`POST /internal/ai/draft-from-question`)

소스: `app/routers/ai.py:94-107`, `app/services/qa_service.py:79-114`.

### I — Input

Path: `POST /internal/ai/draft-from-question`. Request Body: DraftFromQuestionRequest.  
참조: [miriart-ai-api.md](miriart-ai-api.md) §2.5 또는 `app/schemas/qa.py:32-39`.

### P — Processing

| 단계 | 동작 | 소스 |
|------|------|------|
| 1 | 프롬프트 구성 (title + content, imageBase64 옵션) | qa_service.draft_from_question |
| 2 | call_gemini (Flash, JSON) | gemini_client.py:21,23,42,44,90 |
| 3 | JSON 파싱 | qa_service |

### O — Output

HTTP 200. Response: DraftFromQuestionResponse. 참조 [miriart-ai-api.md](miriart-ai-api.md) §2.5.

### E — Error

소스: `app/core/error_handler.py:28-35, 55-56`.

| 예외 | HTTP | body.code |
|------|------|-----------|
| ValidationError | 400 | VALIDATION_ERROR |
| LLMTimeoutError | 504 | LLM_TIMEOUT |
| LLMServiceError | 502 | LLM_SERVICE_ERROR |
| LLMParsingError | 502 | LLM_PARSING_ERROR |
| LLMRateLimitError | 429 | LLM_RATE_LIMITED |

---

## 에러 코드 통합 참조

AI error_code → HTTP·body: 소스 `app/core/error_handler.py:28-35, 55-56`.  
전체 목록: [miriart-ai-api.md](miriart-ai-api.md) §3.2.

---

## Gemini 호출 파라미터 (코드 기준)

값의 유일 출처: `app/core/gemini_client.py` (21, 23, 26, 42, 44, 90), `app/services/image_edit_service.py:44`.

| 기능 | 모델 | Timeout | 리트라이 |
|------|------|---------|----------|
| 작품 분석 | Flash (65) | effective_timeout (90) → 기본 GEMINI_TIMEOUT_S (21) | GEMINI_RETRY_ATTEMPTS (23), attempts (44) |
| AI 채팅 | PRO/Flash (66,65) | 동일 | 동일 |
| 이미지 편집 | Flash | timeout_override_s (90) = GEMINI_IMAGE_EDIT_TIMEOUT_S (26), image_edit_service:44 | 동일 |
| QA 요약/초안 | Flash | 동일 | 동일 |

---

*문서 끝. 유일 참조는 코드. 타임아웃·리트라이·에러 값은 app/core/gemini_client.py, app/core/error_handler.py 라인으로만 인용.*
