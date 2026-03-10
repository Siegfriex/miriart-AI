# MiriArt AI 에이전트 코드 파싱 보고서

에이전트 프롬프트/행동, 이미지 분석·저장 URL, 챗봇·QA, HTTP 엔드포인트를 기준으로 코드 구조를 정리한 보고서.

---

## 1. 공통 코어 (LLM, 예외, 로깅)

### 1.1 LLM 호출/타임아웃/리트라이 — `app/core/gemini_client.py`

| 항목 | 내용 |
|------|------|
| **SDK** | `google-genai` (Vertex AI 백엔드, `vertexai=True`) |
| **싱글턴** | `get_genai_client()` — project/region은 `get_settings()`에서 로드 |
| **HTTP 옵션** | `timeout=28*1000`(28초), `attempts=3`, `initial_delay=1`, `max_delay=8`, `exp_base=2`, `jitter=0.5`, `http_status_codes=[429,500,502,503,504]` |
| **진입점** | `call_gemini(model, contents, system_instruction=..., purpose=..., timeout_override_s=..., temperature, max_output_tokens, response_mime_type, return_response)` |
| **Python 타임아웃** | `asyncio.wait_for(..., timeout=effective_timeout)` — 기본 28초, image-edit만 55초 오버라이드 |
| **실행 방식** | `asyncio.to_thread(client.models.generate_content, ...)` |
| **로그** | 성공: `gemini_call_success` (purpose, model, latency_s, output_len) / 타임아웃: `gemini_call_timeout` / 에러: `gemini_call_error` |
| **예외** | `asyncio.TimeoutError` → `LLMTimeoutError`, 그 외 → `LLMServiceError` |
| **모델 상수** | `GeminiModel.FLASH`(2.5-flash), `PRO`(2.5-pro), `FLASH_LITE`(2.0-flash-lite) |

---

### 1.2 에러 모델/핸들러 — `app/core/exceptions.py` · `app/core/error_handler.py`

**예외 계층 (`exceptions.py`)**  
- `MiriArtAIError(message, error_code)` — 공통 베이스  
- `LLMTimeoutError` → `error_code="LLM_TIMEOUT"` (BE: AN002/AI002)  
- `LLMServiceError` → `error_code="LLM_SERVICE_ERROR"` (BE: AN001/AI001)  
- `LLMParsingError` → `error_code="LLM_PARSING_ERROR"` (BE: AN001/AI001)  
- `GCSError` → `error_code="GCS_ERROR"` (BE: F003)  
- `ValidationError` → `error_code="VALIDATION_ERROR"` (BE: C001)  

**HTTP 매핑 (`error_handler.py`)**  
- `LLMTimeoutError` → **504**, `LLM_TIMEOUT`  
- `LLMServiceError` / `LLMParsingError` / `GCSError` → **502**, 각각 code  
- `ValidationError` → **400**, `VALIDATION_ERROR`  
- `RequestValidationError` → **400**, `VALIDATION_ERROR`, `errors[]` (field, message)  
- `Exception` → **500**, `INTERNAL_ERROR`  

**응답 형식**  
- `MiriArtAIError`: `{"code": "<ERROR_MAP code>", "message": exc.message}`  
- 로그: `handled_error`, `request_validation_error`, `unhandled_exception` (path, method, error_code, status, detail 등)

---

### 1.3 구조화 로깅 / Request ID — `app/core/logging_config.py` · `app/middleware/request_context.py`

**로깅 설정 (`logging_config.py`)**  
- `pythonjsonlogger.JsonFormatter` — stdout JSON  
- 필드: `timestamp`, `severity`, `name`, `message`  
- `uvicorn.access` → WARNING 이상만 (요청 로그 노이즈 감소)  

**미들웨어 (`request_context.py`)**  
- `X-Request-ID`: 있으면 사용, 없으면 12자 UUID → `request.state.request_id`  
- 제외 경로: `/health`, `/internal/ai/health`  
- 그 외: `http_request` 로그 — `request_id`, `method`, `path`, `status`, `latency_s`  
- 응답 헤더에 `X-Request-ID` 설정  

**로그 패턴 정리**  
- `http_request` — 요청 단위 (request_id, method, path, status, latency_s)  
- `gemini_call_success` / `gemini_call_timeout` / `gemini_call_error` — LLM 호출 단위  
- `handled_error` / `request_validation_error` / `unhandled_exception` — 에러 단위  

---

## 2. 이미지 분석 + GCS URL (분석/저장 경로)

### 2.1 이미지 다운로드/업로드·URL — `app/services/gcs_service.py`

| 메서드 | 용도 | 비고 |
|--------|------|------|
| `download_as_bytes(gcs_uri)` | 분석용 이미지 바이트 | `gs://{bucket}/...` 또는 blob path. 실패 시 호출부에서 `GCSError` |
| `upload_bytes(blob_path, data, content_type)` | image-edit 결과 저장 | 업로드 후 `https://storage.googleapis.com/{bucket}/{blob_path}` 반환 |
| `generate_signed_url(blob_path, expiration_minutes=60)` | Phase 2 Presigned URL | `miriart-ai-runner` SA로 v4 signed URL 생성 |

- 생성자: `GcsService(bucket_name, project_id)` — `storage.Client`, `bucket` 보유  
- analyze: 동일 버킷(`settings.gcs_bucket_name`) URI만 정식 지원

---

### 2.2 이미지 분석 프롬프트/응답 스키마 — `app/services/analyze_service.py`

**프롬프트**  
- `ANALYZE_SYSTEM_PROMPT`: 미술 입시 전문 AI 평가관, 5축(0~100) — density/form/completion/relevance/thinking, 등급 A~F, fixScope(StructureRebuild/DetailTuning), 대학 예측 5개 이내, JSON 응답  
- `ANALYZE_USER_TEMPLATE`: `분석 유형: {analysis_type}`, `문제/주제: {problem_text}`, "위 미술 작품을 분석해주세요" + 예시 JSON  

**Gemini 호출**  
- `genai_types.Part.from_text(user_text)` + `Part.from_bytes(data=image_bytes, mime_type="image/jpeg")`  
- `call_gemini(GeminiModel.FLASH, contents, system_instruction=ANALYZE_SYSTEM_PROMPT, purpose="analyze_artwork", temperature=0.3, max_output_tokens=2048, response_mime_type="application/json")`  

**파싱**  
- `json.loads(raw)` → `grade`, `totalScore`, `radarData`(density, form, completion, relevance, thinking), `fixScope`, `comment`, `universityPredictions[]`  
- `InternalAnalyzeResponse` + `RadarData` + `UniversityPrediction` 생성  
- 실패 시 `LLMParsingError`  

**GCS**  
- `req.gcs_uri` → `gcs.download_as_bytes` (실패 시 `GCSError`)

---

### 2.3 이미지 편집 + 저장 URL — `app/services/image_edit_service.py`

**플로우**  
1. `request.image_base64` → `base64.b64decode` (실패 시 `ValidationError`)  
2. `Part.from_bytes(image_bytes, image/jpeg)` + `Part.from_text(request.prompt)`  
3. `call_gemini(FLASH, contents, purpose="image_edit", temperature=0.4, max_output_tokens=2048, timeout_override_s=55, return_response=True)`  
4. `response.candidates[0].content.parts`에서 `inline_data` 추출 → `edited_image_bytes`, `edited_mime`  
5. `blob_path = "edited/{uuid}.jpg"` → `gcs.upload_bytes(...)` → `image_url` (실패 시 `GCSError`)  
6. `InternalImageEditResponse(text=response_text or "이미지 편집이 완료됐습니다.", image_url=image_url)`  

- 타임아웃 55초만 오버라이드, 나머지는 공통 28초/리트라이

---

### 2.4 요청/응답 타입 — `app/schemas/analyze.py` · `app/schemas/image_edit.py`

**analyze**  
- `InternalAnalyzeRequest`: `gcs_uri`, `analysis_type`, `problem_text` (optional) — camelCase  
- `RadarData`: density, form, completion, relevance, thinking  
- `UniversityPrediction`: university, major, line, probability, similar_accepted_count  
- `InternalAnalyzeResponse`: grade, total_score, radar_data, fix_scope, comment, university_predictions  

**image_edit**  
- `InternalImageEditRequest`: `image_base64`, `prompt`  
- `InternalImageEditResponse`: `text`, `image_url` (optional)  

- 공통: `ConfigDict(populate_by_name=True, alias_generator=to_camel, serialize_by_alias=True)`

---

## 3. 챗봇/QA 에이전트 (프롬프트/히스토리/QA 기능)

### 3.1 챗봇(멘토) — `app/services/chat_service.py`

**시스템 프롬프트**  
- `CHAT_SYSTEM_PROMPT`: MiriArt 미술 입시 AI 멘토, 전문 용어+고등학생 수준 설명, 구체적·실천 가능 조언, grade/fixScope 반영, 격려+현실적 피드백, 200자 이내  

**sticky_context 반영**  
- `req.sticky_context` 있으면: `system += "\n\n학생 분석 결과: grade={ctx.grade}, score={ctx.score}, fixScope={ctx.fix_scope}"`  

**히스토리**  
- `_flatten_history(req.history)`: `[role]: text` 줄 단위로 합친 문자열  
- `messages = history_text + "\n[user]: " + req.message` (이미지 있으면 멀티모달 contents로 전달)  

**모델 매핑**  
- `MODEL_MAP`: CHAT_PRO→PRO, FAST/SEARCH/IMAGE_EDIT→FLASH, THINKING→PRO  

**호출**  
- 이미지 있으면: `Part.from_text(messages)` + `Part.from_bytes(image_bytes, image_mime_type or image/jpeg)`  
- 없으면: `contents = messages` (텍스트만)  
- `call_gemini(model_name, contents, system_instruction=system, purpose="chat", temperature=0.7, max_output_tokens=1024)`  

**응답**  
- `InternalChatResponse(text=raw.strip(), grounding_urls=[], quick_replies=["이 부분을 더 자세히 알려주세요", "연습 방법을 추천해주세요", "비슷한 대학은 어디가 있나요?"])` — 퀵리플라이 3개 고정

---

### 3.2 C4 QA — `app/services/qa_service.py`

**summarize-answers**  
- `SUMMARIZE_SYSTEM_PROMPT`: QA 조교, 답변 요약(summary 3줄 이내), 추가 조언(supplement 1~2줄), JSON 응답  
- `SUMMARIZE_USER_TEMPLATE`: 질문 + 답변 목록 + `{"summary":"...","supplement":"..."}`  
- `call_gemini(FLASH, user_prompt, system_instruction=..., purpose="summarize_answers", temperature=0.3, max_output_tokens=1024, response_mime_type="application/json")`  
- `json.loads` → `{"summary", "supplement"}` / 실패 시 `LLMParsingError`  

**draft-from-question**  
- `DRAFT_SYSTEM_PROMPT`: 질문 기반 답변 초안, 맥락·구체적 조언·200자 이내·이미지 첨부 시 참고·JSON  
- `DRAFT_USER_TEMPLATE`: 제목 + 내용 + `{"draft":"..."}`  
- `image_base64` 있으면: `Part.from_text(user_prompt)` + `Part.from_bytes(decoded, image/jpeg)`  
- 없으면: `contents = user_prompt`  
- `call_gemini(FLASH, ..., purpose="draft_from_question", temperature=0.5, response_mime_type="application/json")`  
- `json.loads` → `{"draft"}` / 실패 시 `LLMParsingError`  

---

### 3.3 QA/Chat 스키마 — `app/schemas/chat.py` · `app/schemas/qa.py`

**chat**  
- `HistoryItem`: role, parts (Vertex Content 대응)  
- `StickyContext`: grade, score, fix_scope, radar_data (optional)  
- `InternalChatRequest`: model_type, message, session_id, sticky_context, image_base64, image_mime_type, history  
- `InternalChatResponse`: text, grounding_urls, quick_replies  

**qa**  
- `SummarizeAnswersRequest`: question, answers (min/max length)  
- `SummarizeAnswersResponse`: summary, supplement  
- `DraftFromQuestionRequest`: title, content, image_base64 (alias imageBase64)  
- `DraftFromQuestionResponse`: draft  

- 모두 camelCase 직렬화

---

## 4. HTTP 엔드포인트 레벨 (AI 에이전트 진입점)

### 4.1 AI 라우터 — `app/routers/ai.py`

| 메서드 | 경로 | 서비스 | 요청/응답 |
|--------|------|--------|-----------|
| POST | `/internal/ai/analyze` | `analyze_service.analyze_artwork` | InternalAnalyzeRequest → InternalAnalyzeResponse |
| POST | `/internal/ai/chat` | `chat_service.chat` | InternalChatRequest → InternalChatResponse |
| POST | `/internal/ai/edit-image` | `image_edit_service.edit_image` | InternalImageEditRequest → InternalImageEditResponse |
| POST | `/internal/ai/summarize-answers` | `qa_service.summarize_answers` | SummarizeAnswersRequest → SummarizeAnswersResponse |
| POST | `/internal/ai/draft-from-question` | `qa_service.draft_from_question` | DraftFromQuestionRequest → DraftFromQuestionResponse |

- prefix `/internal/ai`로 마운트, Java BE WebClient가 호출

---

### 4.2 앱 엔트리포인트 — `app/main.py`

- **lifespan**: `setup_logging()` → `get_genai_client()` (GenAI 워밍업) → yield → shutdown 로그  
- **미들웨어**: `RequestContextMiddleware` (X-Request-ID, http_request 로그)  
- **핸들러**: `register_exception_handlers(app)`  
- **라우터**: `app.include_router(ai.router, prefix="/internal/ai", tags=["AI Internal"])`  
- **헬스**: `GET /health` → `{"status": "ok"}`  
- `docs_url=None`, `redoc_url=None` (내부 전용)

---

## 5. 요약 매트릭스

| 관심사 | 주요 파일 | 비고 |
|--------|-----------|------|
| 에이전트가 Gemini를 어떻게 부르는지 | `gemini_client.py` | 타임아웃 28s(이미지편집 55s), 리트라이 3회, gemini_call_* 로그 |
| 에러 → HTTP/코드 | `exceptions.py`, `error_handler.py` | LLM_TIMEOUT→504, LLM/GCS/PARSING→502, VALIDATION→400 |
| X-Request-ID, http_request | `request_context.py`, `logging_config.py` | 12자 UUID, JSON 로그, /health 제외 |
| 이미지 다운로드/업로드/URL | `gcs_service.py` | download_as_bytes(분석), upload_bytes(편집), generate_signed_url(Phase2) |
| 분석 프롬프트·파싱 | `analyze_service.py` | 5축 radar, grade, fixScope, universityPredictions, response_mime_type=application/json |
| 이미지 편집 플로우 | `image_edit_service.py` | base64 → Gemini(55s) → inline_data → GCS edited/ → imageUrl |
| 챗봇 역할·sticky·히스토리 | `chat_service.py` | CHAT_SYSTEM_PROMPT, sticky_context 문자열 추가, _flatten_history → [role]: text |
| QA summarize/draft | `qa_service.py` | 각각 시스템/유저 템플릿, JSON summary/supplement, draft, 이미지 시 멀티모달 |
| BE/FE가 부르는 API | `routers/ai.py` | 5개 POST /internal/ai/* → 각 서비스 1:1 호출 |
| 워밍업·미들웨어·핸들러 | `main.py` | lifespan에서 로깅+get_genai_client, RequestContextMiddleware, register_exception_handlers |

이 문서는 위 구조를 기준으로 “에이전트 프롬프트/행동”, “이미지 분석·저장 URL”, “챗봇·QA”, “HTTP 진입점”을 한 번에 파악할 수 있도록 정리한 파싱 보고서입니다.
