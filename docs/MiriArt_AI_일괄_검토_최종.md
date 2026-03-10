# MiriArt AI 서비스 일괄 검토 최종 보고서

> **목적**: AI 호출 방식, FastAPI 로직, 이미지 처리, Vertex/Gemini 사용, CORS, CRUD, 스토리지·스키마·엔터티·파라미터, AI 호출 빈도/방식/타임을 실 코드 라인 인용으로 정리  
> **기준**: miriart-ai 레포 코드 및 docs/ API 계약·ERD·인프라 문서  
> **작성일**: 2026-03-09

---

## 1. AI 호출 방식 (실 코드 인용)

### 1.1 Vertex AI 초기화 및 모델 취득

| 항목 | 파일:라인 | 내용 |
|------|-----------|------|
| Vertex 초기화 | `app/core/gemini_client.py:22-29` | `init_vertex_ai()` — `vertexai.init(project=settings.gcp_project_id, location=settings.gcp_region)` |
| 앱 시작 시 1회 호출 | `app/main.py:20-24` | lifespan에서 `init_vertex_ai()` 호출, 실패 시 경고만 남기고 계속 |
| GenerativeModel 취득 | `app/core/gemini_client.py:32-37` | `get_generative_model(model_name, system_instruction?)` → `GenerativeModel(model_name)` 반환 |

```22:29:app/core/gemini_client.py
def init_vertex_ai() -> None:
    """Vertex AI를 초기화한다. 앱 시작 시 main.lifespan에서 1회 호출."""
    global _initialized
    if _initialized:
        return
    settings = get_settings()
    vertexai.init(project=settings.gcp_project_id, location=settings.gcp_region)
    _initialized = True
```

```32:37:app/core/gemini_client.py
def get_generative_model(model_name: str, system_instruction: Optional[str] = None) -> GenerativeModel:
    """Vertex AI GenerativeModel 인스턴스 반환. chat_service, analyze_service, image_edit_service에서 사용."""
    init_vertex_ai()
    if system_instruction:
        return GenerativeModel(model_name, system_instruction=system_instruction)
    return GenerativeModel(model_name)
```

### 1.2 작품 분석 (analyze) — Gemini Vision

| 항목 | 파일:라인 | 내용 |
|------|-----------|------|
| 모델명 | `app/services/analyze_service.py:126` | `gemini-2.5-pro-preview` |
| 호출 방식 | `app/services/analyze_service.py:127-133` | `model.generate_content([Part.from_bytes(image_bytes, mime_type=mime_type), prompt])` |
| 실행 컨텍스트 | `app/services/analyze_service.py:135` | `await asyncio.to_thread(_call_gemini)` — 블로킹 호출을 스레드로 비동기화 |

```125:135:app/services/analyze_service.py
        model = get_generative_model("gemini-2.5-pro-preview")

        def _call_gemini() -> str:
            response = model.generate_content([
                Part.from_bytes(image_bytes, mime_type=mime_type),
                prompt,
            ])
            return response.text

        response_text = await asyncio.to_thread(_call_gemini)
```

### 1.3 AI 채팅 (chat) — 멀티모델·채팅 세션·퀵리플라이

| 항목 | 파일:라인 | 내용 |
|------|-----------|------|
| 모델 매핑 | `app/services/chat_service.py:18-24` | `MODEL_MAP`: CHAT_PRO→gemini-2.5-pro-preview, FAST→gemini-2.5-flash-lite, THINKING→gemini-2.5-pro, SEARCH→gemini-2.5-flash, IMAGE_EDIT→gemini-2.0-flash-exp |
| 시스템 프롬프트 | `app/services/chat_service.py:37-52` | `build_system_prompt(sticky_context)` — 등급·점수·fix_scope에 따라 StructureRebuild vs DetailTuning 분기 |
| 채팅 호출 | `app/services/chat_service.py:104-115` | `model.start_chat(history=history_contents).send_message(...)` — 이미지 있으면 `Part.from_bytes`+텍스트, 없으면 텍스트만 |
| 퀵리플라이용 모델 | `app/services/chat_service.py:72` | `gemini-2.5-flash-lite` — `model.generate_content(prompt).text` (라인 77) |

```18:24:app/services/chat_service.py
MODEL_MAP: dict[str, str] = {
    "CHAT_PRO": "gemini-2.5-pro-preview",
    "FAST": "gemini-2.5-flash-lite",
    "THINKING": "gemini-2.5-pro",
    "SEARCH": "gemini-2.5-flash",
    "IMAGE_EDIT": "gemini-2.0-flash-exp",
}
```

```104:115:app/services/chat_service.py
        def _call_gemini() -> str:
            chat_session = model.start_chat(history=history_contents)
            if request.image_base64:
                image_bytes = base64.b64decode(request.image_base64)
                mime = request.image_mime_type or "image/jpeg"
                response = chat_session.send_message([
                    Part.from_bytes(image_bytes, mime_type=mime),
                    request.message,
                ])
            else:
                response = chat_session.send_message(request.message)
            return response.text
```

### 1.4 이미지 편집 (edit-image) — Gemini 2.0 Flash

| 항목 | 파일:라인 | 내용 |
|------|-----------|------|
| 모델명 | `app/services/image_edit_service.py:28` | `gemini-2.0-flash-exp` |
| 호출 방식 | `app/services/image_edit_service.py:30-35` | `model.generate_content([Part.from_bytes(image_bytes, mime_type="image/jpeg"), request.prompt])` |
| 응답 처리 | `app/services/image_edit_service.py:45-50` | `response.candidates[0].content.parts`에서 `text`·`inline_data`(편집 이미지 bytes) 추출 |

```28:35:app/services/image_edit_service.py
        model = get_generative_model("gemini-2.0-flash-exp")

        def _call_gemini():
            response = model.generate_content([
                Part.from_bytes(image_bytes, mime_type="image/jpeg"),
                request.prompt,
            ])
            return response
```

### 1.5 AI 호출 빈도·방식·타임 (코드 기준)

| 항목 | 코드/문서 | 내용 |
|------|-----------|------|
| **호출 빈도 제한** | FastAPI 앱 내 | **없음** — rate limit/throttle/retry 로직 없음. *검색: app/ 내 timeout, rate, limit, throttle, retry 미사용.* |
| **타임아웃** | FastAPI 앱 내 | **미설정** — `generate_content`/`send_message` 호출에 timeout 인자 없음. |
| **BE 쪽 타임아웃** | API 계약·인프라 | 분석·채팅 시 Java BE WebClient 30초 타임아웃 → AN002/AI002(504). *docs/MiriArt_API_CONTRACT.md §4.1, §5.1, §9.5, §9.7.* |
| **호출 방식** | 전부 | 동기 Vertex SDK를 `asyncio.to_thread()`로 감싸 비동기 처리. 요청당 1회 Gemini 호출(채팅은 본문 1회 + 퀵리플라이 1회 = 최대 2회). |

---

## 2. FastAPI 로직 (실 코드 인용)

### 2.1 진입점·라우터 마운트

| 항목 | 파일:라인 | 내용 |
|------|-----------|------|
| 앱 생성 | `app/main.py:27-33` | `FastAPI(title="MiriArt AI Service", version="1.0.0", description="...", lifespan=lifespan)` |
| 라우터 | `app/main.py:34` | `app.include_router(ai.router, prefix="/internal/ai", tags=["AI Internal"])` |
| 헬스 | `app/main.py:37-40` | `@app.get("/health")` → `{"status": "ok"}` |

```27:34:app/main.py
app = FastAPI(
    title="MiriArt AI Service",
    version="1.0.0",
    description="MiriArt 내부 AI 서비스 (Java BE → FastAPI). FE 직접 접근 불가.",
    lifespan=lifespan,
)

app.include_router(ai.router, prefix="/internal/ai", tags=["AI Internal"])
```

### 2.2 라우터 엔드포인트 일람

| 메서드 | 경로 (prefix 포함) | 핸들러 | 파일:라인 |
|--------|---------------------|--------|-----------|
| POST | `/internal/ai/analyze` | `analyze_service.analyze_artwork` | `app/routers/ai.py:19-27` |
| POST | `/internal/ai/chat` | `chat_service.chat` | `app/routers/ai.py:30-38` |
| POST | `/internal/ai/edit-image` | `image_edit_service.edit_image` | `app/routers/ai.py:41-49` |
| POST | `/internal/ai/summarize-answers` | 501 스텁 | `app/routers/ai.py:51-63` |
| POST | `/internal/ai/draft-from-question` | 501 스텁 | `app/routers/ai.py:65-76` |
| GET | `/health` | `health()` | `app/main.py:37-40` |

```19:27:app/routers/ai.py
@router.post(
    "/analyze",
    response_model=InternalAnalyzeResponse,
    summary="작품 분석",
    description="GCS URI의 이미지를 Gemini Vision으로 분석하여 5축 채점 결과를 반환한다.",
)
async def analyze(request: InternalAnalyzeRequest) -> InternalAnalyzeResponse:
    """GCS URI 이미지를 Gemini Vision으로 5축 분석. Java AnalysisController → AnalysisService에서 호출."""
    return await analyze_service.analyze_artwork(request)
```

### 2.3 미들웨어

- **CORS/기타 미들웨어**: `app/main.py` 및 `app/` 하위에 `add_middleware`, `CORSMiddleware` **없음**. (BE 전용 호출 설계.)

---

## 3. 이미지 처리 방식·이미지 인풋

### 3.1 엔드포인트별 이미지 입력 형식

| 엔드포인트 | 입력 형식 | 스키마 필드 | 파일:라인 |
|------------|-----------|-------------|-----------|
| `/internal/ai/analyze` | **GCS URI** (`gs://bucket/path`) | `InternalAnalyzeRequest.gcs_uri` | `app/schemas/analyze.py:19` |
| `/internal/ai/chat` | **base64** (선택) | `InternalChatRequest.image_base64`, `image_mime_type` | `app/schemas/chat.py:42-43` |
| `/internal/ai/edit-image` | **base64** (필수) | `InternalImageEditRequest.image_base64`, `prompt` | `app/schemas/image_edit.py:19-20` |

- **multipart/form-data**: 이 FastAPI 서비스의 API에서는 사용하지 않음 (BE의 `POST /api/analyses`에서만 multipart 사용).
- **외부 URL 직접**: analyze는 GCS URI만 지원. URL 문자열 필드 없음.

### 3.2 처리 파이프라인 (실 코드)

**Analyze**  
`parse_gcs_uri(request.gcs_uri)` → `download_from_gcs(bucket_name, blob_path)` → Gemini Vision → JSON 파싱 → 총점/등급/fix_scope/radar_data.

- GCS 파싱: `app/core/gemini_client.py:46-51`
- 다운로드: `app/core/gemini_client.py:55-66` (비동기, `asyncio.to_thread`)
- analyze 서비스에서 사용: `app/services/analyze_service.py:109-114`

**Chat**  
선택적 `image_base64` → `base64.b64decode` → `Part.from_bytes(..., mime_type)` → `send_message([Part, message])`.  
- `app/services/chat_service.py:105-110`

**Edit-image**  
`base64.b64decode(request.image_base64)` → Gemini `generate_content` → 응답 `parts`에서 `inline_data` 추출 → GCS 업로드.  
- 디코딩: `app/services/image_edit_service.py:21-23`  
- 업로드 경로: `app/services/image_edit_service.py:54-61` — `edited/{uuid}.jpg`

### 3.3 GCS 다운로드/업로드 (스토리지 API)

| 함수 | 파일:라인 | 동작 |
|------|-----------|------|
| `parse_gcs_uri` | `app/core/gemini_client.py:46-51` | `gs://` 제거 후 `(bucket_name, blob_path)` 반환 |
| `download_from_gcs` | `app/core/gemini_client.py:55-66` | `bucket.blob(blob_path).download_as_bytes()`, MIME은 `blob.content_type` 또는 경로 확장자 추론 |
| `upload_to_gcs` | `app/core/gemini_client.py:74-83` | `blob.upload_from_string(data, content_type=content_type)` 후 `https://storage.googleapis.com/{bucket}/{path}` 반환 |

```46:51:app/core/gemini_client.py
def parse_gcs_uri(gcs_uri: str) -> tuple[str, str]:
    """GCS URI를 (bucket_name, blob_path) 튜플로 파싱. download_from_gcs 등에서 사용."""
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"유효하지 않은 GCS URI: {gcs_uri}")
    path = gcs_uri[len("gs://"):]
    bucket_name, _, blob_path = path.partition("/")
    return bucket_name, blob_path
```

---

## 4. Vertex API / Gemini 사용 방식 요약

| 구분 | analyze | chat | edit-image |
|------|---------|------|------------|
| **Vertex 초기화** | `gemini_client.init_vertex_ai()` (앱 시작 1회) | 동일 | 동일 |
| **모델** | gemini-2.5-pro-preview | MODEL_MAP[model_type], 퀵리플라이는 gemini-2.5-flash-lite | gemini-2.0-flash-exp |
| **API 패턴** | `generate_content([image_part, prompt])` | `start_chat(history).send_message(...)` | `generate_content([image_part, prompt])` |
| **이미지 전달** | GCS 다운로드 → bytes → Part.from_bytes | optional base64 → Part.from_bytes | base64 → Part.from_bytes |
| **출력** | response.text → JSON 파싱 | response.text + 퀵리플라이 별도 generate_content | response.candidates[0].content.parts (text + inline_data) |

---

## 5. CORS

| 항목 | 코드/문서 | 내용 |
|------|-----------|------|
| **FastAPI(miriart-ai)** | `app/main.py` 전체 | `CORSMiddleware`, `add_middleware` **없음**. |
| **설계** | docs/ SSOT·스냅샷 | Java BE만 호출, FE는 직접 접근하지 않으므로 CORS 미적용이 의도된 설계. |
| **BE(Spring)** | API 계약 §10.2 | allowedOrigins: localhost:5173, miri-art.vercel.app; allowedMethods: GET,POST,PUT,PATCH,DELETE,OPTIONS; allowCredentials: true. *(Java BE 쪽 설정, miriart-ai와 무관.)* |

---

## 6. CRUD

- 이 FastAPI 서비스는 **CRUD 엔드포인트를 제공하지 않음** (Create/Read/Update/Delete 리소스 없음).
- 제공 기능: **POST** 기반 AI·이미지 처리 3종 + 스텁 2종(501) + **GET** `/health` 상태 조회만.
- 분석/채팅/이미지 편집 결과의 **영속화·조회·수정·삭제**는 **Java BE(MySQL·Redis)** 에서 수행.  
  - 예: 분석 결과 저장·목록/단건 조회 → `POST /api/analyses`, `GET /api/analyses`, `GET /api/analyses/{id}` (API 계약 §4).

---

## 7. 스토리지 API·스키마 명세·메타데이터·테이블

### 7.1 이 레포(miriart-ai) 기준

- **DB/테이블/엔터티**: **없음**. MySQL 접속·스키마·엔티티 정의 코드 없음.
- **GCS**: 버킷명·블롭 경로만 사용. 스키마 이름·메타데이터 필드는 `app/`에 정의되어 있지 않음.
- **설정**: `app/core/config.py:21-24` — `gcp_project_id`, `gcp_region`, `gcs_bucket_name`, `google_application_credentials` (환경 변수).

```21:24:app/core/config.py
    gcp_project_id: str = "miriart-dev"
    gcp_region: str = "asia-northeast3"
    gcs_bucket_name: str = "miriart-bucket"
    google_application_credentials: str = ""
```

- **GCS 경로 사용처**  
  - analyze: `parse_gcs_uri` → `download_from_gcs` (입력 이미지).  
  - edit-image: `upload_to_gcs(..., blob_path=f"edited/{uuid.uuid4()}.jpg", ...)` (출력 이미지).  
  - `app/services/image_edit_service.py:54-61`

### 7.2 스토리지·테이블 (문서·BE 기준)

- **GCS 버킷**: `miriart-bucket` — 작품/편집/프로필/커뮤니티 이미지. *docs/MiriArt_GCP_INFRA.md §3, docs/SSOT/miriarts_infra.md.*
- **MySQL 테이블(예시)**: `users`, `plans`, `analysis_usage_logs`, `analyses`, `posts`, `answers`, `comments`, `likes`, `personas`, `reputation_ledger`, `reports` 등. *docs/MiriArt_ERD_v2.md §1, §2.*  
- **분석 관련**: `analyses`(분석 결과), `analysis_usage_logs`(월별 사용 카운트·CR001 한도). *API 계약 §4, 인프라 문서.*

---

## 8. 엔터티·스키마 (Pydantic 요청/응답)

### 8.1 Analyze — `app/schemas/analyze.py`

| 스키마 | 용도 | 필드 (파일:라인) |
|--------|------|------------------|
| InternalAnalyzeRequest | 요청 | `gcs_uri`, `analysis_type` (basic\|major), `problem_text` (optional). *15-22* |
| RadarData | 5축 점수 | `density`, `form`, `completion`, `relevance`, `thinking`. *25-33* |
| UniversityPrediction | 대학 예측(Phase2) | `university`, `major`, `line`, `probability`, `similar_accepted_count`. *36-44* |
| InternalAnalyzeResponse | 응답 | `grade`, `total_score`, `radar_data`, `fix_scope`, `comment`, `university_predictions`. *48-58* |

```15:22:app/schemas/analyze.py
class InternalAnalyzeRequest(BaseModel):
    """작품 분석 요청. Java AnalysisService에서 GCS URI·분석 타입·문제 문맥 전달."""

    model_config = _CAMEL

    gcs_uri: str
    analysis_type: str  # basic | major
    problem_text: Optional[str] = None
```

### 8.2 Chat — `app/schemas/chat.py`

| 스키마 | 용도 | 필드 (파일:라인) |
|--------|------|------------------|
| HistoryItem | 히스토리 1건 | `role` (user\|model), `parts` ([{"text": "..."}]). *14-20* |
| StickyContext | 고정 맥락 | `grade`, `score`, `fix_scope`, `radar_data` (optional). *23-30* |
| InternalChatRequest | 요청 | `model_type`, `message`, `session_id`, `sticky_context`, `image_base64`, `image_mime_type`, `history`. *33-44* |
| InternalChatResponse | 응답 | `text`, `grounding_urls`, `quick_replies`. *47-54* |

```33:44:app/schemas/chat.py
class InternalChatRequest(BaseModel):
    """채팅 요청. Java AiChatController에서 세션 ID·히스토리·스티키 컨텍스트·메시지(이미지可选) 전달."""

    model_config = _CAMEL

    model_type: str  # CHAT_PRO | FAST | THINKING | SEARCH | IMAGE_EDIT
    message: str
    session_id: Optional[str] = None
    sticky_context: Optional[StickyContext] = None
    image_base64: Optional[str] = None
    image_mime_type: Optional[str] = None
    history: Optional[List[HistoryItem]] = []
```

### 8.3 Image Edit — `app/schemas/image_edit.py`

| 스키마 | 용도 | 필드 (파일:라인) |
|--------|------|------------------|
| InternalImageEditRequest | 요청 | `image_base64`, `prompt`. *14-20* |
| InternalImageEditResponse | 응답 | `text`, `image_url` (optional). *23-29* |

### 8.4 Stub (501) — `app/schemas/stub.py`

| 스키마 | 용도 | 필드 |
|--------|------|------|
| SummarizeRequest/Response | summarize-answers | question, answers / summary, supplement. *14-28* |
| DraftRequest/Response | draft-from-question | title, content, image_base64(optional) / draft. *31-46* |

### 8.5 공통 설정

- 모든 요청/응답 스키마: `model_config = _CAMEL` (camelCase alias, serialize_by_alias).  
- `_CAMEL`: `ConfigDict(populate_by_name=True, alias_generator=to_camel, serialize_by_alias=True)`. *예: app/schemas/analyze.py:11-12.*

---

## 9. 파라미터 (Query / Path / Body)

- **Query / Path**: AI 엔드포인트에는 **사용하지 않음**. 모든 데이터는 **JSON Body** (camelCase).
- **Body**:  
  - `/internal/ai/analyze` → `InternalAnalyzeRequest`  
  - `/internal/ai/chat` → `InternalChatRequest`  
  - `/internal/ai/edit-image` → `InternalImageEditRequest`  
  - `/internal/ai/summarize-answers` → `SummarizeRequest`  
  - `/internal/ai/draft-from-question` → `DraftRequest`  
- `GET /health`: Query/Path/Body 없음.

---

## 10. 에러 처리 (FastAPI 쪽)

| 상황 | HTTP | 파일:라인 |
|------|------|-----------|
| GCS URI 파싱 실패 | 400 | `app/services/analyze_service.py:110-111` |
| GCS 이미지 로드 실패 | 502 | `app/services/analyze_service.py:115-116` |
| Gemini Vision 호출 실패 | 502 | `app/services/analyze_service.py:135-136` |
| AI 응답 JSON 파싱 실패 | 502 | `app/services/analyze_service.py:140-141` |
| 채팅 Gemini 호출 실패 | 502 | `app/services/chat_service.py:116-117` |
| base64 디코딩 실패(edit-image) | 400 | `app/services/image_edit_service.py:22-23` |
| 이미지 편집 Gemini 실패 | 502 | `app/services/image_edit_service.py:38-39` |
| GCS 업로드 실패(edit-image) | 502 | `app/services/image_edit_service.py:62-63` |
| summarize/draft 스텁 | 501 | `app/routers/ai.py:59-62`, `73-76` |

- **AN001/AN002/AI001/AI002** 등 **ErrorCode**는 **Java BE**에서 WebClient 응답에 따라 매핑. FastAPI는 400/502/501만 반환.

---

## 11. 요약 표

| 항목 | 내용 |
|------|------|
| **AI 호출** | Vertex AI(Gemini). analyze: gemini-2.5-pro-preview 1회; chat: MODEL_MAP 1회 + 퀵리플라이 gemini-2.5-flash-lite 1회; edit-image: gemini-2.0-flash-exp 1회. |
| **호출 빈도/타임** | 앱 내 rate limit·timeout 없음. BE 30초 타임아웃(문서). |
| **FastAPI** | main.py 진입, /internal/ai 라우터, /health. 미들웨어 없음. |
| **이미지 입력** | analyze: GCS URI; chat: optional base64; edit-image: base64. |
| **스토리지** | GCS만 (download/upload). DB/테이블/엔터티는 이 레포에 없음(Java BE·ERD 문서). |
| **CORS** | miriart-ai에는 미적용(BE 전용). |
| **CRUD** | 없음. POST AI 3종 + 스텁 2종 + GET /health. |
| **파라미터** | 전부 JSON Body, camelCase. |
| **스키마** | app/schemas/* — Internal*Request/Response, RadarData, StickyContext, HistoryItem 등. |

---

*실 코드 라인은 위 인용대로 확인 가능. 문서·ERD·API 계약은 docs/, SSOT/ 참고.*
