# MiriArt-AI feature/ai-refactor 최종 점검 (main 머지 직전)

**역할**: BE 수석 리뷰어  
**전제**: [BE_REFACTOR_REVIEW_REPORT.md](BE_REFACTOR_REVIEW_REPORT.md) §1~§2 정합성 검증 완료.  
**목적**: §4.1 파일별 diff 스캔, 테스트 케이스 구체화, 인프라 리스크 정리, 머지 판단.

---

## 1. §4.1 파일별 스캔: 의도된 차이 vs 잠재 이슈

### 1.1 app/core/gemini_client.py

| 구분 | 내용 |
|------|------|
| **의도된 차이** | • `return_response: bool = False` → image-edit용 raw response 반환 (Dev Spec 확장). • `get_settings()` 사용 (Spec은 `settings` 예시, 레포는 싱글턴 패턴). • `response.text` 없을 때 `candidates[0].content.parts` fallback → SDK 응답 형태 차이 대비. |
| **잠재 이슈** | 없음. |

---

### 1.2 app/core/error_handler.py

| 구분 | 내용 |
|------|------|
| **의도된 차이** | 없음. ERROR_MAP·핸들러 동작이 Dev Spec C2·API_CONTRACT §9와 일치. |
| **잠재 이슈** | 없음. |

---

### 1.3 app/core/exceptions.py

| 구분 | 내용 |
|------|------|
| **의도된 차이** | 없음. error_code·docstring(BE 매핑) 일치. |
| **잠재 이슈** | • `ValidationError` 이름이 Pydantic `RequestValidationError`와 구분되지만, `from app.core.exceptions import ValidationError` 사용처(image_edit_service)에서만 쓰이므로 충돌 없음. 혼동 방지를 위해 내부용 예외임을 docstring에 명시해 두면 좋음. |

---

### 1.4 app/services/analyze_service.py

| 구분 | 내용 |
|------|------|
| **의도된 차이** | • 모듈 로드 시 `get_settings()` → `GcsService(...)` 생성 (인프라 주입 가능 구조). |
| **잠재 이슈** | • **GCS URI가 다른 버킷**인 경우: `download_as_bytes`에서 `path = gcs_uri.replace(f"gs://{self._bucket_name}/", "", 1)`이므로 `gs://other-bucket/foo` → path `"other-bucket/foo"`가 되어, 현재 인스턴스의 버킷 안에서 `other-bucket/foo`라는 blob을 찾게 됨. Dev Spec은 “같은 버킷” 전제이므로 현재는 괜찮으나, 다른 버킷 URI가 들어오면 404/실패 → GCSError로 이어짐. (문서화 또는 URI 검증 추가 권장.) |

---

### 1.5 app/services/chat_service.py

| 구분 | 내용 |
|------|------|
| **의도된 차이** | • history를 dict/Pydantic 둘 다 처리 (`getattr`/`.get`). |
| **잠재 이슈** | • **image_base64가 잘못된 경우**: `base64.b64decode(req.image_base64)`(68행) 예외 미처리 → `Exception` → 500 + INTERNAL_ERROR. image_edit_service는 base64 실패 시 `ValidationError` → 400. **일관성·계약**: 채팅에서도 잘못된 base64는 400 VALIDATION_ERROR로 처리하는 편이 좋음. (머지 전 또는 직후 TODO 권장.) |

---

### 1.6 app/services/image_edit_service.py

| 구분 | 내용 |
|------|------|
| **의도된 차이** | • base64 실패 시 `ValidationError` → 400. • `return_response=True`, `timeout_override_s=55`. |
| **잠재 이슈** | • **Gemini가 이미지 미반환 시**: `edited_image_bytes`가 None이면 `image_url`만 None으로 두고 텍스트만 반환. API_CONTRACT상 `imageUrl` optional이면 문제 없음. • **response.candidates[0].content.parts**가 없거나 구조가 다를 경우: `parts`가 빈 리스트면 `response_text`/`edited_image_bytes` 모두 비어 있을 수 있음 → fallback 메시지로 처리됨. (SDK 버전 업 시 구조 변경만 주의.) |

---

### 1.7 app/services/qa_service.py

| 구분 | 내용 |
|------|------|
| **의도된 차이** | 없음. 프롬프트·JSON 파싱·LLMParsingError 처리 일치. |
| **잠재 이슈** | • **draft_from_question에 잘못된 image_base64**: `base64.b64decode(image_base64)`(89행) 예외 미처리 → 500. summarize는 이미지 없음. (chat과 동일하게 ValidationError 처리 권장.) |

---

### 1.8 app/schemas/qa.py

| 구분 | 내용 |
|------|------|
| **의도된 차이** | 없음. API_CONTRACT §8.4·§8.5와 필드·alias 일치. |
| **잠재 이슈** | 없음. |

---

### 1.9 app/routers/ai.py

| 구분 | 내용 |
|------|------|
| **의도된 차이** | • 501 스텁 제거, C4 실구현 연결. |
| **잠재 이슈** | 없음. |

---

### 1.10 app/main.py

| 구분 | 내용 |
|------|------|
| **의도된 차이** | • lifespan에서 `setup_logging()` → `get_genai_client()` warm up. • 미들웨어·예외 핸들러 등록 순서. |
| **잠재 이슈** | • **lifespan 실패 시**: `get_genai_client()`에서 Vertex/ADC 설정이 없으면 예외 발생 → 앱 기동 실패. Cloud Run에서는 SA로 동작하므로 정상. 로컬에서 ADC 미설정이면 기동 시점에 바로 실패하므로 “설정 오류”로 파악 가능. |

---

### 1.11 app/services/gcs_service.py

| 구분 | 내용 |
|------|------|
| **의도된 차이** | • Phase 2용 `generate_signed_url`. • `upload_bytes`는 공개 URL 반환(Phase 1 명세). |
| **잠재 이슈** | • **upload_bytes 반환 URL**: `https://storage.googleapis.com/{bucket}/{path}`. 버킷이 public이 아니면 해당 URL로 접근 시 403. 인프라에서 버킷 정책이 “공개 읽기”가 아니면 image-edit 응답의 imageUrl이 동작하지 않음. (인프라·API_CONTRACT Phase 2 Signed URL 전환 시 대체 예정.) |

---

### 1.12 .dockerignore

| 구분 | 내용 |
|------|------|
| **의도된 차이** | • Dev Spec D3 반영: docs/, .cursor/, *.md(단 !requirements.txt), cloudbuild.yaml 등. |
| **잠재 이슈** | • **`*.json`**: 앱 루트나 `app/` 하위에 필요한 설정 json이 있으면 제외됨. 현재는 .env·키 파일 제외 목적이면 괜찮음. |

---

## 2. 테스트 케이스 제안 (단위 / 통합 / 수동)

### 2.1 단위 테스트

| 테스트 (권장 경로) | 내용 |
|--------------------|------|
| `tests/unit/test_error_handler.py::test_llm_timeout_maps_to_504` | `MiriArtAIError` 핸들러에 `LLMTimeoutError` 전달 → status 504, body `code=="LLM_TIMEOUT"`. |
| `tests/unit/test_error_handler.py::test_llm_service_error_maps_to_502` | `LLMServiceError` → 502, `code=="LLM_SERVICE_ERROR"`. |
| `tests/unit/test_error_handler.py::test_gcs_error_maps_to_502` | `GCSError` → 502, `code=="GCS_ERROR"`. |
| `tests/unit/test_error_handler.py::test_validation_error_maps_to_400` | `ValidationError` → 400, `code=="VALIDATION_ERROR"`. |
| `tests/unit/test_error_handler.py::test_llm_parsing_error_maps_to_502` | `LLMParsingError` → 502, `code=="LLM_PARSING_ERROR"`. |
| `tests/unit/test_exceptions.py::test_exception_error_codes` | 각 예외 클래스 인스턴스의 `error_code` 속성이 Spec 문자열과 동일한지. |
| `tests/unit/test_analyze_service.py::test_analyze_artwork_raises_gcs_error_on_download_failure` | `GcsService.download_as_bytes`를 mock하여 예외 발생 → `analyze_artwork`에서 `GCSError` raise. |
| `tests/unit/test_analyze_service.py::test_analyze_artwork_raises_llm_parsing_error_on_invalid_json` | `call_gemini`를 mock하여 비-JSON 문자열 반환 → `LLMParsingError` raise. |
| `tests/unit/test_qa_service.py::test_summarize_answers_raises_llm_parsing_error_on_invalid_json` | `call_gemini`가 비-JSON 반환 → `LLMParsingError`. |
| `tests/unit/test_qa_service.py::test_draft_from_question_raises_llm_parsing_error_on_invalid_json` | 동일. |
| `tests/unit/test_image_edit_service.py::test_edit_image_raises_validation_error_on_invalid_base64` | 잘못된 base64 → `ValidationError`. |
| `tests/unit/test_image_edit_service.py::test_edit_image_raises_gcs_error_on_upload_failure` | `upload_bytes` mock 예외 → `GCSError`. |

---

### 2.2 통합 테스트 (FastAPI TestClient)

| 테스트 (권장 경로) | 내용 |
|--------------------|------|
| `tests/integration/test_app.py::test_health_returns_200_ok` | `GET /health` → 200, `{"status":"ok"}`. |
| `tests/integration/test_app.py::test_analyze_returns_502_when_gcs_fails` | `POST /internal/ai/analyze` (존재하지 않는 gcsUri 등) → 502, body `code=="GCS_ERROR"` (또는 연결 실패로 502). |
| `tests/integration/test_app.py::test_chat_returns_200_with_minimal_payload` | `POST /internal/ai/chat` 최소 필수 필드만 → 200 및 `text` 존재 (또는 502/504 시 `code` 존재). |
| `tests/integration/test_app.py::test_summarize_answers_returns_200_with_valid_payload` | `POST /internal/ai/summarize-answers` `{"question":"q","answers":["a1"]}` → 200, `summary`, `supplement` 존재. |
| `tests/integration/test_app.py::test_draft_from_question_returns_200_with_valid_payload` | `POST /internal/ai/draft-from-question` `{"title":"t","content":"c"}` → 200, `draft` 존재. |
| `tests/integration/test_app.py::test_validation_error_returns_400` | `POST /internal/ai/summarize-answers` `{"question":"","answers":[]}` 등 → 400, `code=="VALIDATION_ERROR"`, `errors` 존재. |
| `tests/integration/test_app.py::test_request_id_in_response_header` | `/internal/ai/...` 호출 시 응답 헤더에 `X-Request-ID` 존재. |

---

### 2.3 로컬 수동 테스트 (curl / httpie)

| 시나리오 | 명령 예시 |
|----------|-----------|
| Health | `curl -s http://localhost:8080/health` → 200, `{"status":"ok"}`. |
| Analyze (실패 기대) | `curl -s -X POST http://localhost:8080/internal/ai/analyze -H "Content-Type: application/json" -d '{"gcsUri":"gs://miriart-bucket/nonexistent.png","analysisType":"basic"}'` → 502, body `"code":"GCS_ERROR"`. |
| Chat (최소) | `curl -s -X POST http://localhost:8080/internal/ai/chat -H "Content-Type: application/json" -d '{"message":"안녕","modelType":"FAST"}'` → 200 또는 502/504. |
| Summarize-answers | `curl -s -X POST http://localhost:8080/internal/ai/summarize-answers -H "Content-Type: application/json" -d '{"question":"질문","answers":["답1"]}'` → 200, `summary`, `supplement`. |
| Draft-from-question | `curl -s -X POST http://localhost:8080/internal/ai/draft-from-question -H "Content-Type: application/json" -d '{"title":"제목","content":"내용"}'` → 200, `draft`. |
| Validation 400 | `curl -s -X POST http://localhost:8080/internal/ai/summarize-answers -H "Content-Type: application/json" -d '{"question":"","answers":[]}'` → 400, `code":"VALIDATION_ERROR"`. |
| X-Request-ID | `curl -s -D - http://localhost:8080/health` → 응답 헤더에 `X-Request-ID` 없음(EXCLUDE_PATHS). `curl -s -D - -X POST .../chat -d '{"message":"x","modelType":"FAST"}'` → 헤더에 `X-Request-ID` 존재. |

---

## 3. 인프라 설정이 틀어졌을 때 “바로 터지는” 지점 정리

### 3.1 GcsService의 bucket_name / project_id

| 설정 | 사용처 | 잘못되면 |
|------|--------|----------|
| `gcs_bucket_name` | `analyze_service`, `image_edit_service`에서 `GcsService(bucket_name=...)`, `download_as_bytes`/`upload_bytes` | **버킷명 오타/다른 프로젝트 버킷**: 다운로드 시 404 → `download_as_bytes` 예외 → **GCSError → 502**. 업로드는 해당 버킷에 쓰기 시도 → 권한 없으면 예외 → **GCSError → 502**. |
| `gcp_project_id` | `GcsService(project_id=...)`, `storage.Client(project=project_id)` | **프로젝트 잘못**: 해당 프로젝트에 버킷/권한이 없으면 GCS API 호출 시 **403/404** → **GCSError → 502**. |

**Cloud Run에서**: `--set-env-vars=GCP_PROJECT_ID=...,GCS_BUCKET_NAME=...`가 잘못되면 위와 동일. 앱은 기동은 되고, **첫 analyze 또는 image-edit 호출 시** 502로 드러남.

---

### 3.2 image_edit_service의 upload_bytes URL 형식 (public vs signed)

| 항목 | 현재 구현 | 잘못되면 |
|------|-----------|----------|
| URL 형식 | `https://storage.googleapis.com/{bucket_name}/{blob_path}` (공개 URL 형식) | 버킷이 **public 읽기 아님** → 클라이언트가 반환된 imageUrl로 GET 시 **403**. AI 서비스 자체는 200 + imageUrl 반환하고, **실제 이미지 접근만 실패**. (Phase 2에서 Signed URL로 전환 예정.) |

즉, “앱이 터지는” 게 아니라 **이미지 링크가 안 열리는** 증상. 인프라에서 버킷 정책 또는 Signed URL 전환으로 보완 필요.

---

### 3.3 RequestContextMiddleware의 EXCLUDE_PATHS 및 로그 필드명

| 항목 | 현재 값 | 잘못되면 |
|------|----------|----------|
| EXCLUDE_PATHS | `{"/health", "/internal/ai/health"}` | `/health`를 빼먹으면 헬스체크마다 `http_request` 로그 적재 → **로그/메트릭 노이즈**. 경로 오타 시 실제 헬스 경로가 로깅 대상이 됨. |
| 로그 필드명 | `request_id`, `method`, `path`, `status`, `latency_s` | 필드명을 바꾸면 **이미 구축한 log-based metrics / 대시보드** 쿼리가 깨짐. (현재는 일관되게 유지됨.) |

앱 크래시를 유발하지는 않고, **관측성/비용**에만 영향.

---

### 3.4 cloudbuild.yaml env와 Settings 매핑

| cloudbuild 설정 | Settings 필드 | Pydantic-settings 기본 매핑 |
|-----------------|---------------|------------------------------|
| `GCP_PROJECT_ID=miriarts` | `gcp_project_id` | env 이름을 대문자·스네이크로 매핑 → **GCP_PROJECT_ID** ✓ |
| `GCP_REGION=asia-northeast3` | `gcp_region` | **GCP_REGION** ✓ |
| `GCS_BUCKET_NAME=miriart-bucket` | `gcs_bucket_name` | **GCS_BUCKET_NAME** ✓ |

`config.model_config`에 `case_sensitive=False`(현재 적용)이면 env 대소문자 구분 없음.  
**잘못되면**: 변수명 오타(예: `GCS_BUCKET_NAM`) → 해당 필드는 **기본값** 사용. `config.py` 기본값은 `gcs_bucket_name="miriart-bucket"` 등이라, 로컬과 같은 값이 들어가 **프로덕션에서 잘못된 버킷/리전**을 쓰게 될 수 있음. **증상**: analyze/image-edit 호출 시 502 또는 잘못된 버킷 접근.

---

## 4. 머지 판단

### 결론: **OK but** — 아래 TODO 선처리 후 머지 권장

**이유**:  
- Dev Spec·API_CONTRACT와의 정합성은 이미 검증됐고, 코드 구조·예외 매핑·프롬프트·C4 스키마는 일치함.  
- 다만 **경계 케이스**에서 동작이 일관되지 않거나, 인프라 오설정 시 증상이 명확히 드러나지 않는 부분이 있어, 머지 직전에 최소한만 정리하는 편이 안전함.

---

### 머지 전 반드시 처리할 TODO

1. **chat_service.py**  
   - `req.image_base64`가 있을 때 `base64.b64decode` 예외 처리 추가.  
   - 실패 시 `ValidationError`(또는 동일한 error_code 사용) raise → **400 + VALIDATION_ERROR**.

2. **qa_service.py**  
   - `draft_from_question`에서 `image_base64`가 있는 경우 `base64.b64decode` 예외 처리 추가.  
   - 실패 시 **ValidationError** → 400.

3. **(선택이지만 강력 권장)**  
   - **analyze_service**: `req.gcs_uri`가 `gs://`로 시작하는데 버킷이 `settings.gcs_bucket_name`과 다르면, 초기 단계에서 **ValidationError** 또는 **GCSError**로 명시적으로 실패시키고 메시지에 “같은 버킷만 지원” 등 명시.  
   - 또는 Dev Spec/API 문서에 “현재는 동일 버킷 URI만 지원”이라고 한 줄 추가.

---

### 머지 후(인프라 결합 시) 확인할 것

- Cloud Run 배포 후 **env 확인**: 콘솔 또는 `gcloud run services describe miriart-ai --region=asia-northeast3`로 `GCP_PROJECT_ID`, `GCP_REGION`, `GCS_BUCKET_NAME` 값 확인.
- **이미지 URL**: image-edit 응답의 imageUrl이 실제로 열리는지(버킷 공개 정책 또는 Signed URL 전환 여부).
- **헬스/로깅**: `/health` 호출 시 200, 그 외 `/internal/ai/*` 호출 시 `X-Request-ID` 및 구조화 로그 출력 확인.

---

### NOT YET으로 보지 않는 이유

- 치명적인 잘못된 예외 매핑이나 스키마 불일치가 없음.  
- 인프라 리스크는 “설정값 오타/버킷 정책” 수준이며, 문서와 env 점검으로 커버 가능.  
- base64/채팅·draft 검증 보강은 작은 변경으로 가능하고, 머지 전 TODO로 명시해 두었음.

이 문서는 **최종 점검 결과**와 **머지 전 TODO**를 한곳에 정리한 것이며, TODO 처리 후 main 머지 + 인프라 gcloud 작업 진행을 권장한다.
