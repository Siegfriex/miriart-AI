# MiriArt AI 전수 점검 리포트 (코드베이스 라인 인용)

> **기준**: miriart-ai 레포 코드 및 SSOT 문서(API_CONTRACT §8·§9, FSD_v2 F3/F4/C4, miriarts_infra).  
> **인용 규칙**: 모든 진술은 `app/...:라인` 또는 `docs/...:라인` 형태로 소스 위치를 명시함.

---

## 0. 스코프·검토 대상

| 구분 | 경로 |
|------|------|
| 진입점 | `app/main.py` |
| 라우터 | `app/routers/ai.py` |
| 스키마 | `app/schemas/analyze.py`, `app/schemas/chat.py`, `app/schemas/image_edit.py`, `app/schemas/stub.py` |
| 서비스 | `app/services/analyze_service.py`, `app/services/chat_service.py`, `app/services/image_edit_service.py` |
| 코어 | `app/core/config.py`, `app/core/gemini_client.py` |
| 배포 | `Dockerfile`, `cloudbuild.yaml`, `requirements.txt` |
| 참조 문서 | `docs/MiriArt_API_CONTRACT.md` §8·§9, `docs/MiriArt_FSD_v2.md` F3/F4/C4, `docs/miriarts_infra.md` |

---

## 1. 엔드포인트·DTO·에러 코드 정합성

### 1.1 실제 FastAPI 엔드포인트 목록 (코드 기준)

| method | path | request schema | response schema | status codes | 예외/에러 처리 (코드 위치) |
|--------|------|----------------|-----------------|--------------|----------------------------|
| GET | /health | — | `{"status": "ok"}` | 200 | 없음. `app/main.py:37-40` |
| POST | /internal/ai/analyze | InternalAnalyzeRequest | InternalAnalyzeResponse | 200, 400, 502 | 400: `analyze_service.py:110-111` (ValueError → HTTPException). 502: `analyze_service.py:115-116`, `135-136`, `140-141` (detail 문자열만) |
| POST | /internal/ai/chat | InternalChatRequest | InternalChatResponse | 200, 502 | 502: `chat_service.py:116-117` (detail만) |
| POST | /internal/ai/edit-image | InternalImageEditRequest | InternalImageEditResponse | 200, 400, 502 | 400: `image_edit_service.py:22-23`. 502: `image_edit_service.py:38-39`, `62-63` |
| POST | /internal/ai/summarize-answers | SummarizeRequest | SummarizeResponse | 501 | `routers/ai.py:59-62` HTTPException 501, detail 한글 메시지 |
| POST | /internal/ai/draft-from-question | DraftRequest | DraftResponse | 501 | `routers/ai.py:74-76` 동일 |

- prefix `/internal/ai` 마운트: `app/main.py:34` — `app.include_router(ai.router, prefix="/internal/ai", ...)`.

### 1.2 API_CONTRACT §8 vs 코드 — Diff (라인 인용)

**GET /health**  
- 계약 `docs/MiriArt_API_CONTRACT.md` §8.0: GET /health, 헬스체크.  
- 코드 `app/main.py:37-40`: `@app.get("/health")` → `return {"status": "ok"}`. **일치.**

**POST /internal/ai/analyze**  
- 계약 §8.1·§9.5: 요청 gcsUri, analysisType, problemText(optional). 응답 grade, totalScore, radarData, fixScope, comment, universityPredictions.  
  에러: 400 GCS URI 파싱 실패, **502 AN001**, **504 AN002** (분석 시간 초과).  
- 코드  
  - 요청/응답: `app/schemas/analyze.py:14-21` (InternalAnalyzeRequest), `46-56` (InternalAnalyzeResponse). 필드·camelCase 일치.  
  - 에러: `app/services/analyze_service.py:110-111` 400(문자열), `115-116` 502 "GCS 이미지 로드 실패", `135-136` 502 "Gemini Vision 호출 실패", `140-141` 502 "AI 응답 파싱 실패".  
- **Diff**: 계약은 502 시 **AN001**, 504 시 **AN002** 및 ErrorResponse(code, message) 형식을 전제하나, 코드는 **502만 사용**하며 **504 분기·body의 code 필드 없음**. `analyze_service.py` 전역에 `AN001`/`AN002` 문자열 없음.

**POST /internal/ai/chat**  
- 계약 §8.2·§9.7: 요청 modelType, message, sessionId, stickyContext, imageBase64, imageMimeType, history. 응답 text, groundingUrls, quickReplies.  
  에러: **502 AI001**, **504 AI002**.  
- 코드: `app/schemas/chat.py:34-44` (InternalChatRequest), `47-54` (InternalChatResponse).  
  에러: `app/services/chat_service.py:116-117` `raise HTTPException(status_code=502, detail=f"AI 멘토 연결에 실패했습니다: {e}")` 만 존재.  
- **Diff**: **504·AI001·AI002 미구현**. 타임아웃 분기 없음. body에 code 없음.

**POST /internal/ai/edit-image**  
- 계약 §8.3: 요청 imageBase64, prompt. 응답 text, imageUrl. §8.0 에러 "(서비스 구현에 따름)". §9에 이미지 편집 전용 ErrorCode 없음.  
- 코드: `app/schemas/image_edit.py:14-21`, `23-28`. `app/services/image_edit_service.py:22-23` 400, `38-39`·`62-63` 502.  
- **Diff**: 스키마 일치. 에러는 400/502 + detail 문자열. 계약에 edit-image 전용 코드 없음 → 현재 "일반 502" 사용 상태와 문서 불명시.

**POST /internal/ai/summarize-answers, draft-from-question**  
- 계약 §8.4·§8.5: 요청/응답 스키마 명시. 501 Phase C4 스텁.  
- 코드: `app/schemas/stub.py:13-28` (SummarizeRequest/Response), `31-45` (DraftRequest/Response).  
  `app/routers/ai.py:57-62`, `72-76`: `raise HTTPException(status_code=501, detail="이 엔드포인트는 Phase C4에서 구현될 예정입니다.")`.  
- **Diff**: 요청/응답 스키마 계약과 일치. 501 body는 FastAPI 기본 형식(detail 등). 계약에 501 시 **code** 필드 명시 없음 — BE 기대 여부 확인 필요.

### 1.3 Pydantic alias 정합성 (app/schemas/*)

| 파일 | 모델 | ConfigDict(camelCase) 적용 위치 |
|------|------|----------------------------------|
| `app/schemas/analyze.py` | InternalAnalyzeRequest, RadarData, UniversityPrediction, InternalAnalyzeResponse | `11` `_CAMEL = ConfigDict(populate_by_name=True, alias_generator=to_camel, serialize_by_alias=True)`, 각 클래스 `model_config = _CAMEL` (`17`, `27`, `39`, `49`) |
| `app/schemas/chat.py` | HistoryItem, StickyContext, InternalChatRequest, InternalChatResponse | `11` 동일, `17`·`26`·`37`·`50` |
| `app/schemas/image_edit.py` | InternalImageEditRequest, InternalImageEditResponse | `11`, `18`, `26` |
| `app/schemas/stub.py` | SummarizeRequest/Response, DraftRequest/Response | `11`, `17`, `26`, `35`, `44` |

**결론**: 모든 해당 모델에 동일 설정 적용. **누락/불일치 없음.**

---

## 2. 서비스 로직·I-P-O-E 정합성 (FSD 기준)

### 2.1 analyze_service — F3 대비 (라인 인용)

| 구분 | 내용 | 코드 위치 |
|------|------|-----------|
| **Input** | gcs_uri, analysis_type, problem_text(optional). parse_gcs_uri 실패 시 400 | `analyze_service.py:106-111` (request 사용, parse_gcs_uri, ValueError → HTTPException 400) |
| **Process** | GCS 다운로드 → Gemini Vision 호출 → JSON 파싱 → 총점·등급·fix_scope·radar_data·comment·university_predictions([]) | `112-114` download_from_gcs. `118-120` prompt 선택(ANALYSIS_PROMPT_MAJOR/BASIC). `122-132` get_generative_model("gemini-2.5-pro-preview"), Part.from_bytes+generate_content, asyncio.to_thread. `138-146` parse_analysis_json, calculate_total_score/grade/fix_scope. `148-162` InternalAnalyzeResponse 반환, university_predictions=[] |
| **Output** | InternalAnalyzeResponse (grade, total_score, radar_data, fix_scope, comment, university_predictions) | `148-162` |
| **Exception** | 400: `110-111`. 502: `115-116` GCS, `135-136` Gemini, `140-141` 파싱. **504·AN002 없음** | FSD F3 Exception: AN001(502), AN002(504). `analyze_service.py`에는 timeout 분기·AN001/AN002 코드 미사용. |

**FSD와의 차이**  
- `docs/MiriArt_FSD_v2.md` 166행: Exception에 AN001/AN002(AiProxyService 62-73) 명시. 504(AN002) "분석 시간이 초과됐습니다" — **코드에 해당 분기 없음** (`analyze_service.py` 전역).  
- fix_scope 계산: `analyze_service.py:75-78` (structure_score ≥ 70 → DetailTuning). FSD 추가 명세 없음, 계약과 일치.  
- university_predictions: `analyze_service.py:161` 빈 배열. 계약·FSD와 일치.

### 2.2 chat_service — F4 대비 (라인 인용)

| 구분 | 내용 | 코드 위치 |
|------|------|-----------|
| **Input** | model_type, message, session_id, sticky_context, image_base64, image_mime_type, history | `chat_service.py:89-97` (request.model_type, request.sticky_context, request.history 등) |
| **Process** | MODEL_MAP으로 모델명 선택 → system_prompt(sticky_context) → history 변환 → start_chat + send_message(이미지 포함 시 Part.from_bytes) → quick_replies 생성 | `92` MODEL_MAP.get. `94-95` build_system_prompt. `97` convert_history. `99-114` get_generative_model, start_chat, send_message (image_base64 시 `104-110`). `118` generate_quick_replies. |
| **Output** | InternalChatResponse(text, grounding_urls=[], quick_replies) | `121-124` |
| **Exception** | 502만. `116-117` "AI 멘토 연결에 실패했습니다". **504·AI002·타임아웃 없음** | FSD 192행: 5xx→AI_CHAT_FAILED, Timeout→AI_CHAT_TIMEOUT. 206행: 타임아웃 30초. `chat_service.py`에 asyncio.wait_for·timeout·504 미구현. |

**MODEL_MAP**  
- `chat_service.py:17-23`: CHAT_PRO→gemini-2.5-pro-preview, FAST→gemini-2.5-flash-lite, THINKING→gemini-2.5-pro, SEARCH→gemini-2.5-flash, IMAGE_EDIT→gemini-2.0-flash-exp.

**sticky_context / history / image**  
- `chat_service.py:36-51` build_system_prompt(sticky_context): grade, score, fix_scope 분기.  
- `54-65` convert_history: HistoryItem → Content(role, parts).  
- `104-110`: image_base64 있을 때 Part.from_bytes(image_bytes, mime), send_message([Part, request.message]).

**quick_replies**  
- `chat_service.py:68-86` generate_quick_replies: get_generative_model("gemini-2.5-flash-lite"), QUICK_REPLY_PROMPT.format(response_text[:500]), generate_content, JSON 배열 파싱. 실패 시 `84-85` except pass → 빈 리스트.

### 2.3 image_edit_service — FSD/PRD 대비 (라인 인용)

| 구분 | 내용 | 코드 위치 |
|------|------|-----------|
| **역할** | base64 이미지 + prompt → Gemini 2.0 Flash → 편집 결과 GCS 업로드(edited/{uuid}.jpg) → 공개 URL + text | `image_edit_service.py:18-70` |
| **Input** | InternalImageEditRequest (image_base64, prompt) | `app/schemas/image_edit.py:14-20` |
| **Output** | InternalImageEditResponse (text, image_url) | `67-70` |
| **Exception** | 400: `22-23` base64 디코딩 실패. 502: `38-39` Gemini, `62-63` GCS 업로드. 계약 §9에 이미지 편집 전용 ErrorCode 없음 | `image_edit_service.py:20-23`, `37-39`, `55-63` |

GCS 경로: `image_edit_service.py:54` `blob_path = f"edited/{uuid.uuid4()}.jpg"`.  
모델: `image_edit_service.py:27` get_generative_model("gemini-2.0-flash-exp").

---

## 3. Vertex AI·GCS·환경 설정 점검 (라인 인용)

### 3.1 app/core/config.py

| 항목 | 값/매핑 | 코드 위치 |
|------|---------|-----------|
| Settings 필드 | gcp_project_id, gcp_region, gcs_bucket_name, google_application_credentials | `config.py:12-24` (BaseSettings, model_config env_file=".env", case_sensitive=False) |
| 기본값 | gcp_project_id="miriart-dev", gcp_region="asia-northeast3", gcs_bucket_name="miriart-bucket", google_application_credentials="" | `config.py:21-24` |
| env 매핑 | GCP_PROJECT_ID, GCP_REGION, GCS_BUCKET_NAME, GOOGLE_APPLICATION_CREDENTIALS (Pydantic 기본 env 대문자·snake_case) | BaseSettings + case_sensitive=False |

`docs/miriarts_infra.md` 196행: FastAPI config 기본값 및 Cloud Run --set-env-vars GCP_PROJECT_ID=miriarts 등과 **의미·필드명 일치**. prod는 `cloudbuild.yaml:32`로 덮어씀.

### 3.2 app/core/gemini_client.py

| 항목 | 내용 | 코드 위치 |
|------|------|-----------|
| Vertex 초기화 시점 | lifespan에서 1회. init_vertex_ai() | `main.py:20-24` try/except init_vertex_ai(). `gemini_client.py:22-29` _initialized 플래그, get_settings(), vertexai.init(project, location) |
| get_generative_model | model_name, system_instruction(optional) | `gemini_client.py:32-36` init_vertex_ai() 호출 후 GenerativeModel 반환 |
| 사용 모델명·용도 | analyze: gemini-2.5-pro-preview (`analyze_service.py:125`). chat: MODEL_MAP (`chat_service.py:17-23`). image_edit: gemini-2.0-flash-exp (`image_edit_service.py:27`). quick_replies: gemini-2.5-flash-lite (`chat_service.py:71`) | 위 서비스 파일 해당 라인 |
| 타임아웃/재시도 | **미설정**. generate_content·send_message 호출에 timeout/retry 인자 없음 | `analyze_service.py:127-131`, `chat_service.py:74-75`, `103-112`, `image_edit_service.py:30-35` |
| GCS download | parse_gcs_uri → download_from_gcs(bucket_name, blob_path) | `gemini_client.py:45-51` parse_gcs_uri. `54-65` download_from_gcs (get_storage_client, bucket.blob, download_as_bytes, content_type) |
| GCS upload·URL | upload_to_gcs(bucket_name, blob_path, data, content_type). 반환 `https://storage.googleapis.com/{bucket_name}/{blob_path}` | `gemini_client.py:73-82` |

`docs/miriarts_infra.md` 169행: Vertex AI Gemini Vision/Chat (miriart-ai), `miriart-ai/app/core/gemini_client.py` 인용. **Vertex 클라이언트 레벨 timeout/retry는 코드·문서 모두 미명시.**

### 3.3 cloudbuild.yaml vs config·인프라

| 항목 | 값 | 위치 |
|------|-----|------|
| --set-env-vars | GCP_PROJECT_ID=miriarts, GCP_REGION=asia-northeast3, GCS_BUCKET_NAME=miriart-bucket | `cloudbuild.yaml:32` |
| --timeout | 120 | `cloudbuild.yaml:31` |
| 포트 | 8080 | `cloudbuild.yaml:28` |

`docs/miriarts_infra.md` §5.2 (307-315행): miriart-ai Cloud Run 파라미터 SSOT. config.py 필드명·의미와 **일치**. 차이: **Vertex 호출 자체 timeout/retry 정책 없음.**

---

## 4. C4 스텁 준비 상태 (라인 인용)

### 4.1 스텁 구현

| 엔드포인트 | 라우트·스키마 | 501 반환 |
|------------|----------------|----------|
| POST /internal/ai/summarize-answers | `routers/ai.py:51-62`. SummarizeRequest/SummarizeResponse `stub.py:13-28` | `ai.py:59-62` HTTPException(status_code=501, detail="이 엔드포인트는 Phase C4에서 구현될 예정입니다.") |
| POST /internal/ai/draft-from-question | `routers/ai.py:65-76`. DraftRequest/DraftResponse `stub.py:31-45` | `ai.py:74-76` 동일 |

### 4.2 API_CONTRACT 대비

- §8.4·§8.5 요청/응답 필드와 `app/schemas/stub.py` (question, answers; summary, supplement / title, content, image_base64?; draft) **일치**.  
- 501 body: FastAPI 기본 형식. 계약에 501 시 code 필드 명시 없음.

### 4.3 C4 구현 시 설계 제안 (리포트 권장안, 코드 수정 없음)

- **서비스 분리**: `app/services/summarize_service.py`, `app/services/draft_service.py` (또는 `qa_ai_service.py` 단일) 신규 추가 권장. `routers/ai.py`는 analyze→analyze_service, chat→chat_service, edit_image→image_edit_service 패턴 유지.  
- **공통 재사용**: gemini_client에 timeout/retry 래퍼 도입 시 C4 서비스에서도 동일 사용. 502/504 시 ErrorResponse(code, message) 공통 예외 핸들러 적용 시 C4 포함 일관성 확보.

---

## 5. 정리 — 3가지 목록 (현재 상태 → 문제/위험 → 권장 수정 방향)

### 5.1 계약/스키마 정합성 이슈

| # | 현재 상태 (코드 위치) | 문제/위험 | 권장 수정 방향 |
|---|----------------------|-----------|----------------|
| 1 | 502/504 시 body가 `detail` 문자열만 반환 (`analyze_service.py:115-116`, `135-136`, `140-141`, `chat_service.py:116-117`, `image_edit_service.py:38-39`, `62-63`) | API_CONTRACT §1.3·§9 ErrorResponse(code, message)와 불일치. BE/FE가 code로 분기 불가 | FastAPI 예외 핸들러에서 502/504 시 body에 code·message 포함. 또는 계약에 "FastAPI는 status+detail만" 명시 후 BE에서 매핑 |
| 2 | Analyze: 504/AN002 미구현. 502만 사용 | FSD 166행·API_CONTRACT §9.5 AN002(504) "분석 시간이 초과됐습니다" 미반환 | Vertex 호출에 timeout 설정, TimeoutError 시 504 + code AN002 반환 |
| 3 | Chat: 504/AI002 미구현. 502만 사용 (`chat_service.py:116-117`) | FSD 192·206행 AI_CHAT_TIMEOUT(30초)·§9.7 AI002 미반환 | asyncio.wait_for 또는 Vertex 옵션으로 30s 제한, 초과 시 504 + code AI002 |
| 4 | 501 스텁: FastAPI 기본 에러 body (`ai.py:59-62`, `74-76`) | BE가 ErrorResponse(code, message) 기대 시 불일치 | API_CONTRACT에 501 body 형식 명시하거나, 스텁에서도 동일 형식으로 반환 |
| 5 | edit-image: 400/502만 사용. §9에 전용 코드 없음 | 이미지 편집 실패 시 코드 구분 불가 | 계약에 이미지 편집용 ErrorCode 추가하거나 "일반 502 사용"으로 문서화 |

### 5.2 AI 로직/품질 관점 TODO

| # | 현재 상태 (코드 위치) | 문제/위험 | 권장 수정 방향 |
|---|----------------------|-----------|----------------|
| 1 | Analyze 프롬프트 상수 (`analyze_service.py:20-51` ANALYSIS_PROMPT_BASIC/MAJOR) | basic/major 외 확장·A/B 테스트 어려움 | 프롬프트를 config/상수 파일 또는 원격 설정으로 분리 |
| 2 | WEIGHTS 하드코딩 (`analyze_service.py:54` WEIGHTS) | 가중치 변경 시 코드 수정 필요 | 설정(env/config)으로 분리 또는 계약/FSD에 명세 반영 |
| 3 | quick_replies 파싱 실패 시 except pass (`chat_service.py:84-85`) | 품질 이슈·디버깅 어려움 | 최소 로그 추가, 필요 시 재시도/fallback |
| 4 | 공통 LLM timeout/retry 래퍼 없음 (`gemini_client.py` 전역) | C4·기존 서비스에서 중복·불일치 가능 | gemini_client에 generate_with_timeout(retry=N) 등 래퍼 도입 |
| 5 | sticky_context 없을 때 system_instruction=None (`chat_service.py:94-95`) | FSD에 "sticky_context 없을 때" 동작 미정의 | FSD에 기본 동작 정의 후 기본 시스템 프롬프트 또는 "맥락 없음" 처리 추가 |

### 5.3 인프라/운영 관점 TODO

| # | 현재 상태 (코드/설정 위치) | 문제/위험 | 권장 수정 방향 |
|---|---------------------------|-----------|----------------|
| 1 | Vertex 호출에 timeout/retry 미설정 (`gemini_client.py:32-36`, `analyze_service.py:127-131` 등) | 장애·지연 시 Cloud Run 120s까지 대기 후 502, 원인 구분 어려움 | generate_content 등에 request_options timeout(예: 55s)·재시도 명시. miriarts_infra에 "Vertex timeout/retry" 절 추가 |
| 2 | Cloud Run timeout 120s만 명시 (`cloudbuild.yaml:31`) | BE WebClient 30s 등과 관계 문서화 부족 | FSD·인프라 문서에서 30s(채팅) vs 120s(Cloud Run) 관계 정리, 내부 Vertex 30s 제한 시 504 반환 가능하도록 |
| 3 | 로깅/모니터링: lifespan 경고·예외 시 로그만 (`main.py:23-24`, 서비스 내 HTTPException 직 throw) | TODO-006 관측성 부족 | 구조화 로그(요청 id, 엔드포인트, latency, error_code) 및 miriarts_infra §6·§7 갱신 |
| 4 | config 기본값 gcp_project_id="miriart-dev" (`config.py:21`) | prod는 cloudbuild로 miriarts 덮어씀 — 문서와 일치 | 문서에 "로컬 기본값 miriart-dev, prod는 env miriarts" 유지 명시 |

---

## 6. 우선순위 제안 (C4 구현 전)

1. **계약 정합성**: 502/504 에러 body에 code·message 반환 여부 결정 후 예외 핸들러 또는 계약 문서 정리.  
2. **타임아웃·에러 코드**: Analyze 504/AN002, Chat 504/AI002 반환 경로 및 Vertex timeout 설정.  
3. **공통 LLM 래퍼**: timeout/retry 적용 래퍼 도입 → analyze/chat/C4 공통화.  
4. **C4 서비스 설계**: summarize/draft 전용 서비스 파일 분리, 스텁 제거 시 위 래퍼 사용.  
5. **인프라 문서**: miriarts_infra에 Vertex timeout/retry·로깅 정책 반영 및 TODO-006 진행.

---

**문서 메타**

| 항목 | 값 |
|------|-----|
| 작성 기준 | miriart-ai 코드베이스 및 docs/MiriArt_API_CONTRACT.md, MiriArt_FSD_v2.md, miriarts_infra.md |
| 인용 규칙 | 모든 진술에 소스 파일:라인 명시. 코드베이스 수정 없이 보고서만 작성. |
