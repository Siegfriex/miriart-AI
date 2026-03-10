# MiriArt AI 코드베이스 탐색 보고서

> 코드베이스 기준 정리. 추론 없이 실제 파일·라인·코드만 인용.

---

## 1. 프로젝트 구조

### 1.1 디렉터리 및 주요 파일

| 구분 | 경로 | 설명 |
|------|------|------|
| **Backend (FastAPI)** | `app/` | AI 전용 FastAPI 앱. Java BE가 WebClient로만 호출. |
| **진입점** | `app/main.py` | FastAPI 앱 생성, lifespan, 라우터 마운트, `/health` |
| **라우터** | `app/routers/ai.py` | prefix `/internal/ai`, 5개 POST + 스텁 2개 |
| **서비스** | `app/services/` | `analyze_service.py`, `chat_service.py`, `image_edit_service.py` |
| **코어** | `app/core/` | `config.py`, `gemini_client.py` (Vertex AI·GCS) |
| **스키마** | `app/schemas/` | `analyze.py`, `chat.py`, `image_edit.py`, `stub.py` |
| **설정** | `app/core/config.py` | GCP·Vertex·GCS 환경 변수 (Pydantic BaseSettings) |
| **문서** | `docs/` | API 계약, 인프라, ERD, PRD, 스냅샷 등 |
| **인프라** | 루트 | `Dockerfile`, `cloudbuild.yaml`, `.env`, `.env.example` |
| **Frontend** | — | **이 레포에 없음** (별도 레포) |
| **DB/스키마** | — | **이 레포에 없음**. 영속화는 Java BE·MySQL 담당. |

### 1.2 app/ 트리

```
app/
├── __init__.py
├── main.py
├── core/
│   ├── __init__.py
│   ├── config.py
│   └── gemini_client.py
├── routers/
│   ├── __init__.py
│   └── ai.py
├── schemas/
│   ├── __init__.py
│   ├── analyze.py
│   ├── chat.py
│   ├── image_edit.py
│   └── stub.py
└── services/
    ├── __init__.py
    ├── analyze_service.py
    ├── chat_service.py
    └── image_edit_service.py
```

---

## 2. FastAPI

### 2.1 메인 앱 진입점

**파일**: `app/main.py`

- **라인 18–25**: lifespan에서 Vertex AI 초기화 (실패 시 경고 후 계속)
- **라인 27–33**: FastAPI 앱 생성 (`title`, `version`, `description`, `lifespan`)
- **라인 34**: 라우터 마운트  
  `app.include_router(ai.router, prefix="/internal/ai", tags=["AI Internal"])`
- **라인 37–40**: `GET /health` → `{"status": "ok"}`

```34:34:app/main.py
app.include_router(ai.router, prefix="/internal/ai", tags=["AI Internal"])
```

### 2.2 라우터

**파일**: `app/routers/ai.py`

| 메서드 | 경로 (prefix 포함) | 핸들러 | 비고 |
|--------|---------------------|--------|------|
| POST | `/internal/ai/analyze` | `analyze` | analyze_service.analyze_artwork |
| POST | `/internal/ai/chat` | `chat` | chat_service.chat |
| POST | `/internal/ai/edit-image` | `edit_image` | image_edit_service.edit_image |
| POST | `/internal/ai/summarize-answers` | `summarize_answers` | 501 스텁 |
| POST | `/internal/ai/draft-from-question` | `draft_from_question` | 501 스텁 |

```16:17:app/routers/ai.py
router = APIRouter()


```

### 2.3 미들웨어

- **미들웨어**: `app/main.py` 및 `app/` 하위에 `add_middleware`, `Middleware`, `CORSMiddleware` **없음**.
- **CORS**: 이 서비스에는 CORS 설정이 없음 (아래 §8 참고).

---

## 3. AI 호출 (Vertex AI / Gemini)

### 3.1 클라이언트 초기화 및 모델 취득

**파일**: `app/core/gemini_client.py`

- **라인 22–29**: `init_vertex_ai()` — 프로젝트/리전으로 Vertex AI 초기화
- **라인 32–36**: `get_generative_model(model_name, system_instruction?)` — `GenerativeModel` 반환

```22:36:app/core/gemini_client.py
def init_vertex_ai() -> None:
    """Vertex AI를 초기화한다. 앱 시작 시 main.lifespan에서 1회 호출."""
    global _initialized
    if _initialized:
        return
    settings = get_settings()
    vertexai.init(project=settings.gcp_project_id, location=settings.gcp_region)
    _initialized = True


def get_generative_model(model_name: str, system_instruction: Optional[str] = None) -> GenerativeModel:
    """Vertex AI GenerativeModel 인스턴스 반환. chat_service, analyze_service, image_edit_service에서 사용."""
    init_vertex_ai()
    if system_instruction:
        return GenerativeModel(model_name, system_instruction=system_instruction)
    return GenerativeModel(model_name)
```

### 3.2 사용처 및 요청/응답 형태

**1) 작품 분석** — `app/services/analyze_service.py`

- **엔드포인트**: `POST /internal/ai/analyze`
- **모델**: `gemini-2.5-pro-preview`
- **입력**: GCS에서 받은 이미지 bytes + MIME, 프롬프트(분석 타입·문제 문맥)
- **호출**: `model.generate_content([Part.from_bytes(...), prompt])` (라인 127–133)
- **응답**: `response.text` → JSON 파싱 후 5축 점수·comment·총점·등급·fix_scope

```125:133:app/services/analyze_service.py
    try:
        from vertexai.generative_models import Part

        model = get_generative_model("gemini-2.5-pro-preview")

        def _call_gemini() -> str:
            response = model.generate_content([
                Part.from_bytes(image_bytes, mime_type=mime_type),
                prompt,
            ])
            return response.text
```

**2) AI 채팅** — `app/services/chat_service.py`

- **엔드포인트**: `POST /internal/ai/chat`
- **모델 매핑**: `MODEL_MAP` (라인 18–24) — CHAT_PRO→gemini-2.5-pro-preview, FAST→gemini-2.5-flash-lite 등
- **입력**: `sticky_context`로 시스템 프롬프트 분기, `history`(Content 목록), `message`, 선택적 `image_base64`+`image_mime_type`
- **호출**: `model.start_chat(history=...).send_message(...)` (라인 104–115)
- **퀵리플라이**: `generate_quick_replies()`에서 `gemini-2.5-flash-lite`로 후속 질문 3개 생성 (라인 70–88)

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

**3) 이미지 편집** — `app/services/image_edit_service.py`

- **엔드포인트**: `POST /internal/ai/edit-image`
- **모델**: `gemini-2.0-flash-exp`
- **입력**: base64 디코딩 이미지 bytes, 프롬프트
- **호출**: `model.generate_content([Part.from_bytes(...), request.prompt])` (라인 30–35)
- **응답**: `response.candidates[0].content.parts`에서 텍스트·`inline_data`(편집 이미지) 추출

```30:35:app/services/image_edit_service.py
        def _call_gemini():
            response = model.generate_content([
                Part.from_bytes(image_bytes, mime_type="image/jpeg"),
                request.prompt,
            ])
            return response
```

---

## 4. 이미지 처리

### 4.1 입력 형식

| 엔드포인트 | 입력 형식 | 스키마/필드 |
|------------|-----------|-------------|
| `/internal/ai/analyze` | **GCS URI** (`gs://bucket/path`) | `InternalAnalyzeRequest.gcs_uri` |
| `/internal/ai/chat` | **base64** (선택) | `InternalChatRequest.image_base64`, `image_mime_type` |
| `/internal/ai/edit-image` | **base64** | `InternalImageEditRequest.image_base64`, `prompt` |

- **multipart**: 이 코드베이스의 API에서는 사용하지 않음.
- **URL**: analyze만 GCS URI로 간접 입력. 외부 URL 직접 전달 필드는 없음.

### 4.2 처리 파이프라인

**Analyze**  
`parse_gcs_uri` → `download_from_gcs` → Gemini Vision → JSON 파싱 → 총점/등급/fix_scope/radar_data.

**Chat**  
선택적 `image_base64` 디코딩 → `Part.from_bytes` → `send_message`에 이미지+텍스트 전달.

**Edit-image**  
`base64.b64decode(request.image_base64)` → Gemini `generate_content` → 응답에서 `inline_data` 추출 → GCS 업로드.

### 4.3 저장 (GCS)

**파일**: `app/core/gemini_client.py`

- **라인 54–65**: `download_from_gcs(bucket_name, blob_path)` → `(bytes, mime_type)`
- **라인 74–82**: `upload_to_gcs(bucket_name, blob_path, data, content_type)` → 공개 URL  
  `https://storage.googleapis.com/{bucket_name}/{blob_path}`

**편집 결과 저장** — `app/services/image_edit_service.py` 라인 54–61:

```54:61:app/services/image_edit_service.py
        blob_path = f"edited/{uuid.uuid4()}.jpg"
        try:
            image_url = await upload_to_gcs(
                bucket_name=settings.gcs_bucket_name,
                blob_path=blob_path,
                data=edited_image_bytes,
                content_type=edited_mime,
            )
```

---

## 5. Storage / DB

- 이 레포에는 **DB 접속, 스키마, 테이블, 엔티티 정의 코드가 없음**.
- 영속화·세션은 문서/주석 상으로 **Java BE(MySQL·Redis)** 담당.
- **GCS**: 버킷/블롭 경로만 사용. 스키마 이름·메타데이터 필드는 `app/`에 정의되어 있지 않음.
- **설정**: `app/core/config.py` — `gcs_bucket_name`, `gcp_project_id`, `gcp_region` 등 환경 변수만 사용.

```20:24:app/core/config.py
    gcp_project_id: str = "miriart-dev"
    gcp_region: str = "asia-northeast3"
    gcs_bucket_name: str = "miriart-bucket"
    google_application_credentials: str = ""
```

---

## 6. CRUD

- 이 서비스는 **CRUD 엔드포인트를 제공하지 않음**.
- 제공하는 것은 **POST 기반 AI/이미지 처리**와 **GET /health** 뿐.
- **Create/Read/Update/Delete** 동작은 Java BE가 수행하며, FastAPI는 분석/채팅/이미지 편집 결과만 반환.

| 메서드 | 경로 | 역할 |
|--------|------|------|
| POST | `/internal/ai/analyze` | 분석 결과 생성 (BE가 DB에 저장) |
| POST | `/internal/ai/chat` | 채팅 응답 생성 (BE가 Redis 등에 세션 저장) |
| POST | `/internal/ai/edit-image` | 편집 이미지 생성 후 GCS URL 반환 |
| POST | `/internal/ai/summarize-answers` | 501 스텁 |
| POST | `/internal/ai/draft-from-question` | 501 스텁 |
| GET | `/health` | 헬스체크 (상태 조회만) |

---

## 7. 파라미터 (Query / Path / Body)

- 모든 AI API는 **Body만 사용** (JSON, camelCase). Query/Path 파라미터는 없음.

### 7.1 POST /internal/ai/analyze

**Body**: `InternalAnalyzeRequest` — `app/schemas/analyze.py` 라인 15–22

```15:22:app/schemas/analyze.py
class InternalAnalyzeRequest(BaseModel):
    """작품 분석 요청. Java AnalysisService에서 GCS URI·분석 타입·문제 문맥 전달."""

    model_config = _CAMEL

    gcs_uri: str
    analysis_type: str  # basic | major
    problem_text: Optional[str] = None
```

### 7.2 POST /internal/ai/chat

**Body**: `InternalChatRequest` — `app/schemas/chat.py` 라인 33–44

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

### 7.3 POST /internal/ai/edit-image

**Body**: `InternalImageEditRequest` — `app/schemas/image_edit.py` 라인 14–20

```14:20:app/schemas/image_edit.py
class InternalImageEditRequest(BaseModel):
    """이미지 편집 요청. base64 이미지와 편집 지시 프롬프트."""

    model_config = _CAMEL

    image_base64: str
    prompt: str
```

### 7.4 스텁 (501)

- **summarize-answers**: `SummarizeRequest` — `question: str`, `answers: List[str]` (`app/schemas/stub.py` 14–20)
- **draft-from-question**: `DraftRequest` — `title: str`, `content: str`, `image_base64?: str` (`app/schemas/stub.py` 31–37)

### 7.5 GET /health

- **Query/Path/Body**: 없음. 응답 `{"status": "ok"}`.

---

## 8. CORS

- **구성 코드 없음**: `app/main.py` 및 `app/` 전체에 `CORSMiddleware`, `add_middleware` 호출이 **없음**.
- **설계**: Java BE만 호출하고 FE는 직접 접근하지 않으므로 CORS 미적용이 의도된 상태로 문서화되어 있음.

**근거**  
- `docs/miriart-ai-codebase-snapshot.md` 40–42: "CORS: 미적용. app/main.py에 CORSMiddleware 없음. BE만 호출하므로 의도된 설계"  
- `SSOT/miriarts_infra.md` 311–312: "miriart-ai | CORS 미들웨어 없음. BE만 호출 | — | miriart-ai/app/main.py"

---

## 요약 표

| 항목 | 내용 |
|------|------|
| 진입점 | `app/main.py` (FastAPI, lifespan, `/internal/ai` 라우터, `/health`) |
| 라우터 | `app/routers/ai.py` (POST 5개, 스텁 2개는 501) |
| 미들웨어 | 없음 |
| CORS | 없음 (BE 전용 호출) |
| Vertex/Gemini | `app/core/gemini_client.py` + analyze/chat/image_edit 서비스 |
| 이미지 입력 | analyze: GCS URI / chat·edit-image: base64 |
| 저장 | GCS (gemini_client.upload_to_gcs, edited/{uuid}.jpg) |
| DB/스키마 | 이 레포 없음 (Java BE) |
| CRUD | 없음 (AI/이미지 처리 + health 만) |
| Body 스키마 | Pydantic, camelCase alias (analyze/chat/image_edit/stub) |
