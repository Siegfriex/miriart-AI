# MiriArt-AI BE 수석 리뷰 보고서 (feature/ai-refactor)

**역할**: BE 수석 리뷰어  
**대상**: miriart-ai 레포, 브랜치 `feature/ai-refactor` (1차 리팩터링 완료)  
**기준 문서**: Dev Spec v1.0, SSOT v1.2, API_CONTRACT v1.0  
**작성일**: 2026-03-10  

---

## 1. Dev Spec v1.0 vs 실코드 정합성 검증

### 1.1 call_gemini 시그니처 및 HttpOptions / RetryOptions

| 항목 | Dev Spec | 실코드 | 일치 |
|------|----------|--------|------|
| Client 초기화 | `genai.Client(vertexai=True, project=..., location=..., http_options=...)` | 동일 (`app/core/gemini_client.py` 28-42행) | ✓ |
| timeout | `28 * 1000` (28s) | 당시 28s. **현재 AI: 55s** (gemini_client.py GEMINI_TIMEOUT_S). | — |
| retry attempts | 3 | 36행 `attempts=3` | ✓ |
| initial_delay | 1.0 | 37행 `initial_delay=1.0` | ✓ |
| max_delay | 8.0 | 38행 `max_delay=8.0` | ✓ |
| exp_base | 2.0 | 39행 `exp_base=2.0` | ✓ |
| jitter | 0.5 | 40행 `jitter=0.5` | ✓ |
| http_status_codes | [429, 500, 502, 503, 504] | 41행 동일 | ✓ |
| call_gemini 반환 타입 | `-> str` | 실코드 71행 `return_response: bool = False` 추가 시 `-> Any` (str 또는 response 객체) | △ 확장 |

**인용 (실코드)**:

```28:42:app/core/gemini_client.py
        _client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_region,
            http_options=types.HttpOptions(
                timeout=28 * 1000,  # 당시 28s. 현재 코드: GEMINI_TIMEOUT_MS (55s, gemini_client.py:22).
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

**결론**: HttpOptions/RetryOptions는 Dev Spec과 100% 일치. `return_response=True`는 Dev Spec에 없는 **의도적 확장**으로, image-edit에서 원시 response 파싱용으로 사용되며 Spec 의도(55초 타임아웃 + 이미지 바이트 추출)와 부합.

---

### 1.2 예외 계층(error_code) 및 error_handler HTTP 매핑

| 예외 클래스 | error_code (실코드) | Dev Spec C1/C2 | HTTP (실코드) | Dev Spec C2/API_CONTRACT §9 |
|-------------|---------------------|----------------|---------------|-----------------------------|
| LLMTimeoutError | "LLM_TIMEOUT" | 동일 | 504 | 504 ✓ |
| LLMServiceError | "LLM_SERVICE_ERROR" | 동일 | 502 | 502 ✓ |
| LLMParsingError | "LLM_PARSING_ERROR" | 동일 | 502 | 502 ✓ |
| GCSError | "GCS_ERROR" | 동일 | 502 | 502 ✓ |
| ValidationError | "VALIDATION_ERROR" | 동일 | 400 | 400 ✓ |

**인용 (실코드)**:

```27:33:app/core/error_handler.py
ERROR_MAP = {
    LLMTimeoutError: (504, "LLM_TIMEOUT"),
    LLMServiceError: (502, "LLM_SERVICE_ERROR"),
    LLMParsingError: (502, "LLM_PARSING_ERROR"),
    GCSError: (502, "GCS_ERROR"),
    ValidationError: (400, "VALIDATION_ERROR"),
}
```

```39:54:app/core/error_handler.py
    @app.exception_handler(MiriArtAIError)
    async def miriart_error_handler(request: Request, exc: MiriArtAIError):
        status, code = ERROR_MAP.get(type(exc), (500, exc.error_code))
        ...
        return JSONResponse(
            status_code=status,
            content={"code": code, "message": exc.message},
        )
```

**결론**: 예외 계층 및 ERROR_MAP이 Dev Spec §3 범주 C 및 API_CONTRACT §9 (AN002/AI002, AN001/AI001, F003, C001) 매핑과 동일함.

---

### 1.3 ANALYZE / CHAT / QA 프롬프트 및 유저 템플릿

- **ANALYZE**:  
  - `ANALYZE_SYSTEM_PROMPT`, `ANALYZE_USER_TEMPLATE` 문구가 Dev Spec 7.1과 **동일** (실코드 `app/services/analyze_service.py` 28-54행).  
  - `problem_text_line`, `analysis_type` 치환 및 응답 JSON 예시 포맷 일치.

- **CHAT**:  
  - `CHAT_SYSTEM_PROMPT` 5개 규칙이 Dev Spec 7.2와 **동일** (실코드 `app/services/chat_service.py` 25-33행).  
  - `sticky_context` 반영: `grade`, `score`, `fixScope`(실코드에서는 `ctx.fix_scope`로 값만 사용)로 시스템 프롬프트 추가 (58-61행).  
  - history flatten: `[role]: text` 형식 (Dev Spec “messages += f"[{role}]: {text}\n""”)과 동일 의도.

- **QA (summarize / draft)**:  
  - `SUMMARIZE_SYSTEM_PROMPT`, `SUMMARIZE_USER_TEMPLATE`, `DRAFT_SYSTEM_PROMPT`, `DRAFT_USER_TEMPLATE`가 Dev Spec G1/G2와 **동일** (실코드 `app/services/qa_service.py` 17-52행).  
  - 응답 형식 `{"summary":"...","supplement":"..."}`, `{"draft":"..."}` 일치.

**결론**: 누락/변형 없음. 프롬프트 및 유저 템플릿은 Dev Spec과 정합.

---

### 1.4 image_edit_service: timeout 55초 및 return_response 처리

- **timeout**: 실코드 `timeout_override_s=55` 사용 (Dev Spec B3 “image-edit: 55s” 일치).

```38:46:app/services/image_edit_service.py
    response = await call_gemini(
        model=GeminiModel.FLASH,
        contents=contents,
        purpose="image_edit",
        ...
        timeout_override_s=55,
        return_response=True,
    )
```

- **return_response=True**: `call_gemini`가 원시 response 객체를 반환하고, 실코드에서 `response.candidates[0].content.parts`로 `text` / `inline_data` 추출 후 GCS 업로드 (52-60행). Dev Spec “image-edit는 timeout override 55s를 사용” 및 편집 결과 이미지 반환 의도와 부합.

**결론**: image_edit의 55초 타임아웃 및 return_response 활용 방식이 Dev Spec 의도와 일치.

---

### 1.5 C4 QA: camelCase, 필드명, 응답 JSON (API_CONTRACT 정합)

- **API_CONTRACT §8.4 / §8.5**  
  - summarize-answers: 요청 `question`, `answers` / 응답 `summary`, `supplement`.  
  - draft-from-question: 요청 `title`, `content`, `imageBase64`(선택) / 응답 `draft`.

- **실코드**  
  - `app/schemas/qa.py`: `SummarizeAnswersRequest`(question, answers), `SummarizeAnswersResponse`(summary, supplement), `DraftFromQuestionRequest`(title, content, image_base64 alias `"imageBase64"`), `DraftFromQuestionResponse`(draft).  
  - `ConfigDict(alias_generator=to_camel, serialize_by_alias=True)`로 직렬화 시 camelCase.

```14:37:app/schemas/qa.py
class SummarizeAnswersRequest(BaseModel):
    ...
    question: str = Field(..., min_length=1, max_length=2000)
    answers: List[str] = Field(..., min_length=1, max_length=20)
...
class DraftFromQuestionRequest(BaseModel):
    ...
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=5000)
    image_base64: Optional[str] = Field(None, alias="imageBase64")
```

- **라우터**: `request.question`, `request.answers` / `request.title`, `request.content`, `request.image_base64`로 서비스 호출 후 `SummarizeAnswersResponse(**result)`, `DraftFromQuestionResponse(**result)` 반환 (`app/routers/ai.py` 61-80행).

**결론**: C4 QA 스키마·필드명·응답 JSON 구조가 API_CONTRACT §8.4·§8.5와 align됨. (요약 문서의 “SummarizeAnswersRequest(questions, answers)”는 오기이며, 실코드·계약은 `question` 단수 사용.)

---

## 2. 인프라/실행 환경 경계 리뷰

### 2.1 GcsService와 settings 사용

- **설정 주입**: `analyze_service`, `image_edit_service`에서 모듈 로드 시 `get_settings()` 호출 후 `GcsService(bucket_name=_settings.gcs_bucket_name, project_id=_settings.gcp_project_id)` 사용.

```25:26:app/services/analyze_service.py
_settings = get_settings()
gcs = GcsService(bucket_name=_settings.gcs_bucket_name, project_id=_settings.gcp_project_id)
```

```21:22:app/services/image_edit_service.py
_settings = get_settings()
gcs = GcsService(bucket_name=_settings.gcs_bucket_name, project_id=_settings.gcp_project_id)
```

- **config**: `app/core/config.py`의 `Settings`는 `gcp_project_id`, `gcp_region`, `gcs_bucket_name` 정의. Cloud Run 배포 시 `GCP_PROJECT_ID`, `GCP_REGION`, `GCS_BUCKET_NAME` 등 환경 변수와 Pydantic 설정 규칙으로 매핑 가능.

**결론**: GcsService가 `gcs_bucket_name`, `gcp_project_id`를 올바르게 사용하며, 인프라에서 주입하는 설정과 호환됨.

---

### 2.2 RequestContextMiddleware: EXCLUDE_PATHS 및 로그 필드

- **EXCLUDE_PATHS**: `{"/health", "/internal/ai/health"}` (실코드 20행). Dev Spec E2와 동일.
- **로그 필드**: `request_id`, `method`, `path`, `status`, `latency_s` (33-40행). Log-based metrics에서 `http_request` 메시지로 필터 후 `path`, `status`, `latency_s`로 지표/대시보드 구성하기에 적절함.

```33:41:app/middleware/request_context.py
        logger.info(
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_s": latency,
            },
        )
```

**결론**: 제외 경로 및 로그 필드명이 향후 log-based metrics 설계에 적합함.

---

### 2.3 .dockerignore와 Docker 빌드

- **현재 .dockerignore**: `.env`, `*.json`, `.git/`, `docs/`, `.cursor/`, `*.md`(단 `!requirements.txt`), `__pycache__/`, 가상환경, `tests/`, `.pytest_cache/`, `*.log`, `cloudbuild.yaml` 등.
- **포함 필요**: `app/`, `requirements.txt`, `Dockerfile`.  
  - `app/` 및 `Dockerfile`은 목록에 없어 제외되지 않음.  
  - `!requirements.txt`로 `*.md` 예외 처리되어 requirements.txt는 포함됨.

**결론**: Docker 빌드에 필요한 파일이 과도하게 제외되지 않음. (단, 루트에 필요한 설정용 `.json`이 있다면 `*.json`으로 인해 제외되므로, 필요 시 예외 패턴 추가 검토.)

---

## 3. 수동 테스트 시나리오 및 테스트 코드/스크립트 제안

### 3.1 시나리오 vs 검증 방법

| 시나리오 | 검증 방법 제안 |
|----------|----------------|
| 정상 analyze / chat / image-edit / summarize-answers / draft-from-question | 통합 테스트: `TestClient`로 각 POST 호출 → 200, 응답 스키마 검증 (Pydantic `response_model`). E2E는 실제 GCS/Gemini 연동 시 스크립트 또는 수동 curl. |
| GCS 접근 실패 → GCSError → 502 + `{"code":"GCS_ERROR"}` | 단위/통합: `analyze_service`/`image_edit_service`에서 `GcsService.download_as_bytes`/`upload_bytes`를 mock하여 예외 발생 시 `GCSError` raise 및 `error_handler`가 502 + body 검증. |
| Gemini 응답 비-JSON → LLMParsingError → 502 + `{"code":"LLM_PARSING_ERROR"}` | 단위: `call_gemini`를 mock해 비-JSON 문자열 반환 → `analyze_service`/`qa_service`에서 `LLMParsingError` 발생 → 핸들러가 502 + `code` 검증. |
| LLMTimeoutError → 504 + `{"code":"LLM_TIMEOUT"}` | 단위: `call_gemini`를 mock해 `asyncio.TimeoutError` 대신 `LLMTimeoutError` 직접 raise 하거나, `call_gemini` 내부 wait_for를 짧은 timeout으로 호출해 TimeoutError 유도 → 504 + body 검증. |

### 3.2 제안 스크립트/테스트 구조

- **로컬 수동 검증용 스크립트** (예: `scripts/smoke_internal_ai.sh` 또는 `tests/integration/test_internal_ai_contracts.py`):
  - `GET /health` → 200, `{"status":"ok"}`.
  - `POST /internal/ai/analyze`: 유효하지 않은 `gcsUri`(또는 mock)로 502 + `GCS_ERROR` 또는 400 검증.
  - `POST /internal/ai/chat`: 최소 payload로 200 또는 502/504, 응답에 `text` 또는 `code` 존재 검증.
  - `POST /internal/ai/summarize-answers`: `{"question":"...", "answers":["a1"]}` → 200, `summary`, `supplement` 존재.
  - `POST /internal/ai/draft-from-question`: `{"title":"...", "content":"..."}` → 200, `draft` 존재.
  - `POST /internal/ai/edit-image`: base64 + prompt → 200 또는 502/504, `text`/`imageUrl` 또는 에러 `code` 검증.

- **단위 테스트 후보**:
  - `app/core/error_handler`: 각 `MiriArtAIError` 서브클래스별로 핸들러 호출 → `status_code`, `content["code"]`, `content["message"]` 검증.
  - `app/core/exceptions`: 각 예외의 `error_code` 속성 검증.
  - `app/services/analyze_service`: `GcsService`/`call_gemini` mock, 정상 JSON 파싱 → `InternalAnalyzeResponse` 형상; 잘못된 JSON → `LLMParsingError`.
  - `app/services/qa_service`: `summarize_answers`/`draft_from_question`에서 JSON 파싱 실패 시 `LLMParsingError` 검증.

---

## 4. main 머지 전 최종 확인 목록

### 4.1 반드시 눈으로 확인할 파일 (우선순위 순)

1. **app/core/gemini_client.py** – HttpOptions/RetryOptions 수치, `call_gemini` 시그니처 및 `return_response` 분기, 타임아웃/예외 처리.
2. **app/core/error_handler.py** – `ERROR_MAP` 및 각 핸들러의 `status_code`/`content["code"]`가 Dev Spec·API_CONTRACT와 일치하는지.
3. **app/core/exceptions.py** – 모든 `error_code` 문자열 및 docstring(BE 매핑).
4. **app/services/analyze_service.py** – GCS 실패 시 `GCSError`, 파싱 실패 시 `LLMParsingError`, 프롬프트/템플릿 문구.
5. **app/services/chat_service.py** – MODEL_MAP, CHAT_SYSTEM_PROMPT, sticky_context·history 처리, 퀵리플라이.
6. **app/services/image_edit_service.py** – `timeout_override_s=55`, `return_response=True`, GCS 실패 시 `GCSError`, base64 실패 시 `ValidationError`.
7. **app/services/qa_service.py** – summarize/draft 프롬프트, JSON 파싱 실패 시 `LLMParsingError`.
8. **app/schemas/qa.py** – 필드명, alias `imageBase64`, camelCase 설정.
9. **app/routers/ai.py** – C4 엔드포인트 요청/응답 스키마 연결 및 스텁 제거 여부.
10. **app/main.py** – lifespan에서 `setup_logging`, `get_genai_client` 호출, 미들웨어·예외 핸들러 등록 순서.
11. **app/services/gcs_service.py** – `download_as_bytes` 경로 처리, `upload_bytes` URL 형식, `generate_signed_url` Phase 2 대비.
12. **.dockerignore** – `app/`, `Dockerfile`, `requirements.txt` 포함 여부 및 `*.json` 영향.

### 4.2 추가로 작성 권장하는 단위/통합 테스트

- **error_handler**: `MiriArtAIError` 각 서브클래스 → 기대 HTTP/`code`/`message` 검증.
- **analyze_service**: GCS/Gemini mock, 정상·비정상(비-JSON) 응답에 따른 성공/LLMParsingError/GCSError 검증.
- **qa_service**: summarize_answers / draft_from_question JSON 파싱 실패 → LLMParsingError 검증.
- **image_edit_service**: GCS 업로드 실패 → GCSError, base64 오류 → ValidationError 검증.
- **통합**: `TestClient`로 `/health`, `/internal/ai/summarize-answers`, `/internal/ai/draft-from-question` 최소 payload 200 + 스키마 검증.

---

## 5. 문서·계약 보완 제안

- **API_CONTRACT §8.0**: `/internal/ai/summarize-answers`, `/internal/ai/draft-from-question`가 이제 **실구현**이므로, "501 Phase C4 스텁" 표기를 제거하고 200 응답·요청/응답 스키마(§8.4·§8.5) 기준으로 갱신 권장.
- **RequestValidationError 응답**: 현재 FastAPI 내부 AI API는 `errors` 배열에 `field`, `message` 사용. API_CONTRACT §1.3는 BE 공통 ErrorResponse에 `reason` 사용. 내부 API는 그대로 두고, BE가 AI 400 응답을 그대로 클라이언트에 전달할 경우 필드 매핑(예: `message` → `reason`)만 문서화하면 됨.

---

## 6. 종합 결론

- **call_gemini**: HttpOptions/RetryOptions는 Dev Spec과 100% 일치. `return_response`는 image-edit용 확장으로 Spec 의도와 부합.
- **예외·에러 핸들러**: error_code 및 HTTP 매핑이 Dev Spec §3 범주 C 및 API_CONTRACT §9와 일치.
- **ANALYZE/CHAT/QA 프롬프트**: Dev Spec과 동일, 누락/변형 없음.
- **image_edit**: 55초 타임아웃 및 return_response 기반 파싱이 Dev Spec 의도와 일치.
- **C4 QA**: 스키마·필드명·camelCase·응답 구조가 API_CONTRACT §8.4·§8.5와 align됨.
- **인프라 경계**: GcsService 설정 사용, RequestContextMiddleware 로그/경로, .dockerignore가 빌드 및 운영과 충돌하지 않음.

위 4.1 목록을 기준으로 diff를 한 번 더 눈으로 확인하고, 4.2 테스트를 보강한 뒤 main 머지하는 것을 권장한다.
