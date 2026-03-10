# MiriArt-AI 로그 구조 및 에러 코드 매핑 (인프라 쿼리·알람용)

인프라에서 **Cloud Logging 쿼리** 및 **log-based metrics/알람**을 만들 때 참조하는 한 페이지 정리.  
표준 출력은 JSON 구조화 로깅(`pythonjsonlogger`)이며, 공통 필드: `timestamp`, `severity`, `name`, `message` + 각 로그별 `extra` 필드.

---

## 1. 로그 메시지별 구조

### 1.1 `http_request`

**발생 시점**: 매 HTTP 요청 완료 시 (단, `/health`, `/internal/ai/health` 제외)

| 필드 | 타입 | 설명 |
|------|------|------|
| `message` | string | `"http_request"` (고정) |
| `request_id` | string | 요청별 ID (X-Request-ID 또는 12자 UUID) |
| `method` | string | HTTP 메서드 (GET, POST 등) |
| `path` | string | URL 경로 (예: `/internal/ai/chat`) |
| `status` | int | HTTP 응답 코드 (200, 400, 502 등) |
| `latency_s` | float | 요청 처리 시간(초), 소수점 3자리 |

**쿼리 예 (Cloud Logging)**  
- `jsonPayload.message="http_request"`  
- `jsonPayload.status>=500` (5xx만)  
- `jsonPayload.latency_s>10` (지연 10초 초과)

---

### 1.2 `gemini_call_success`

**발생 시점**: Gemini 호출이 정상 종료되었을 때

| 필드 | 타입 | 설명 |
|------|------|------|
| `message` | string | `"gemini_call_success"` (고정) |
| `purpose` | string | 호출 목적 (예: `analyze_artwork`, `chat`, `summarize_answers`) |
| `model` | string | 모델 ID (예: `gemini-2.5-flash`) |
| `latency_s` | float | Gemini 응답 시간(초) |
| `output_len` | int | 응답 텍스트 길이 (return_response 사용 시 0) |

**쿼리 예**  
- `jsonPayload.message="gemini_call_success"`  
- `jsonPayload.purpose="analyze_artwork"`  
- `jsonPayload.latency_s>5`

---

### 1.3 `gemini_call_timeout`

**발생 시점**: Gemini 호출이 asyncio.wait_for 타임아웃에 걸렸을 때

| 필드 | 타입 | 설명 |
|------|------|------|
| `message` | string | `"gemini_call_timeout"` (고정) |
| `purpose` | string | 호출 목적 |
| `model` | string | 모델 ID |
| `timeout_s` | int | 적용된 타임아웃(초) |
| `latency_s` | float | 타임아웃까지 걸린 시간(초) |

**쿼리 예**  
- `jsonPayload.message="gemini_call_timeout"`  
- 알람: 해당 로그 건수 > 0 또는 비율 상한 초과

---

### 1.4 `gemini_call_error`

**발생 시점**: Gemini 호출 중 타임아웃 이외 예외(5xx, SDK 에러 등) 발생 시

| 필드 | 타입 | 설명 |
|------|------|------|
| `message` | string | `"gemini_call_error"` (고정) |
| `purpose` | string | 호출 목적 |
| `model` | string | 모델 ID |
| `error` | string | 예외 메시지 |
| `latency_s` | float | 실패 시점까지 걸린 시간(초) |

**쿼리 예**  
- `jsonPayload.message="gemini_call_error"`  
- `jsonPayload.error!=""`

---

### 1.5 `handled_error`

**발생 시점**: MiriArtAIError 계열 예외가 전역 핸들러에서 처리되었을 때

| 필드 | 타입 | 설명 |
|------|------|------|
| `message` | string | `"handled_error"` (고정) |
| `path` | string | 요청 경로 |
| `method` | string | HTTP 메서드 |
| `error_code` | string | AI 서비스 에러 코드 (아래 표 참고) |
| `status` | int | 반환된 HTTP status |
| `detail` | string | 예외 메시지 |

**쿼리 예**  
- `jsonPayload.message="handled_error"`  
- `jsonPayload.error_code="LLM_TIMEOUT"`  
- `jsonPayload.status>=500`

---

### 1.6 `request_validation_error`

**발생 시점**: FastAPI RequestValidationError (요청 body/쿼리 검증 실패)

| 필드 | 타입 | 설명 |
|------|------|------|
| `message` | string | `"request_validation_error"` (고정) |
| `path` | string | 요청 경로 |
| `errors` | string | Pydantic errors 요약 (최대 500자) |

---

### 1.7 `unhandled_exception`

**발생 시점**: 위에 해당하지 않는 미처리 예외

| 필드 | 타입 | 설명 |
|------|------|------|
| `message` | string | `"unhandled_exception"` (고정) |
| `path` | string | 요청 경로 |
| `method` | string | HTTP 메서드 |
| `error` | string | 예외 메시지 |
| `traceback` | string | traceback 문자열 (최대 2000자) |

---

## 2. 에러 코드 ↔ HTTP status 매핑표

| AI error_code | HTTP status | 용도 / BE 매핑 |
|---------------|-------------|------------------|
| `LLM_TIMEOUT` | 504 | Gemini 타임아웃 → BE: AN002(분석) / AI002(채팅) |
| `LLM_SERVICE_ERROR` | 502 | Gemini 5xx/SDK 에러 → BE: AN001 / AI001 |
| `LLM_PARSING_ERROR` | 502 | Gemini 응답 JSON 파싱 실패 → BE: AN001 / AI001 |
| `GCS_ERROR` | 502 | GCS 다운로드/업로드 실패 → BE: F003 |
| `VALIDATION_ERROR` | 400 | 입력 검증 실패(요청 스키마/base64 등) → BE: C001 |
| `INTERNAL_ERROR` | 500 | 미처리 예외 (catch-all) |

**응답 body 공통 형식** (4xx/5xx):  
`{"code": "<error_code>", "message": "<message>"}`  
요청 검증 실패(400)일 때만 `errors` 배열 추가 가능.

---

## 3. 알람/메트릭 제안

- **5xx 비율**: `http_request` 중 `jsonPayload.status>=500` 비율.  
- **타임아웃**: `gemini_call_timeout` 건수 또는 비율.  
- **Gemini 실패**: `gemini_call_error` 건수.  
- **비즈니스 에러**: `handled_error` 중 `jsonPayload.error_code in ("LLM_TIMEOUT","GCS_ERROR")` 등.  
- **지연**: `http_request.latency_s` 또는 `gemini_call_success.latency_s`의 percentile(99) 등.

위 필드명은 실제 앱 코드(`app/core/gemini_client.py`, `app/core/error_handler.py`, `app/middleware/request_context.py`)와 동일하다.
