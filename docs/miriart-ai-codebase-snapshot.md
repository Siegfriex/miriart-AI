# miriart-ai 코드베이스 현시점 점검 (infra / back / aiml)

이 레포는 **AI 전용 서비스(miriart-ai)** 만 포함하며, Java 백엔드(miriart-be)는 별도 레포에 있다. 아래에서 "back"은 **이 서비스가 백엔드에 제공하는 API 계약(엔드포인트·스키마)** 관점으로 정리한다.

---

## 1. 인프라(infra) 도메인

### 1.1 루트 YAML·Docker

| 항목 | 경로 | 내용 |
|------|------|------|
| **Cloud Build** | [cloudbuild.yaml](../cloudbuild.yaml) | Docker 빌드 → Artifact Registry 푸시 → Cloud Run 배포(miriart-ai). 이미지: `asia-northeast3-docker.pkg.dev/.../miriart-ai:$COMMIT_SHA`. `--no-allow-unauthenticated`, port 8080, 1Gi/1 CPU, timeout 120s. env: GCP_PROJECT_ID, GCP_REGION, GCS_BUCKET_NAME. |
| **Dockerfile** | [Dockerfile](../Dockerfile) | `python:3.11-slim`, WORKDIR `/app`, `requirements.txt` 설치 후 소스 복사, EXPOSE 8080, `uvicorn app.main:app --host 0.0.0.0 --port 8080`. |
| **docker-compose** | — | **없음**. 로컬 실행은 `uvicorn` 직접 또는 별도 스크립트. |

### 1.2 인프라 요약

- **배포**: GCP Cloud Run (asia-northeast3), 내부 전용(비공개).
- **이미지 레지스트리**: Artifact Registry `miriart-images`.
- **환경 변수**: `.env` 또는 Cloud Run `--set-env-vars` (config는 [app/core/config.py](../app/core/config.py)에서 `pydantic_settings`로 로드).

---

## 2. 백엔드 연동(back) 도메인 — API 계약

이 서비스는 **Java BE가 WebClient로 호출하는 내부 API**만 노출한다. FE는 직접 접근하지 않는다.

### 2.1 엔드포인트 일람

| 메서드 | 경로 | 용도 | 구현 상태 |
|--------|------|------|-----------|
| GET | `/health` | 헬스체크 (로드밸런서/배포 검사) | 구현됨 |
| POST | `/internal/ai/analyze` | 작품 분석 (GCS URI → 5축 채점) | 구현됨 |
| POST | `/internal/ai/chat` | AI 멘토 채팅 (히스토리·스티키 컨텍스트) | 구현됨 |
| POST | `/internal/ai/edit-image` | 이미지 편집 (base64 + 프롬프트 → GCS URL) | 구현됨 |
| POST | `/internal/ai/summarize-answers` | Q&A 답변 요약 | **501 스텁** (Phase C4 예정) |
| POST | `/internal/ai/draft-from-question` | 질문 기반 AI 초안 생성 | **501 스텁** (Phase C4 예정) |

### 2.2 CORS·인증

- **CORS**: **미적용**. [app/main.py](../app/main.py)에 `CORSMiddleware` 없음. BE만 호출하므로 의도된 설계(SSOT 문서와 일치).
- **인증**: Cloud Run `--no-allow-unauthenticated`로 서비스 수준 비공개. IAM으로 호출 주체 제한.

### 2.3 CRUD

- 이 서비스는 **DB/CRUD 없음**. stateless AI·GCS 연동만 수행. 영속화는 Java BE·MySQL에서 담당.

---

## 3. AI/ML(aiml) 도메인 — app/ 구조

### 3.1 디렉터리 구조 (스키마 → 라우터 → 코어 → 서비스)

```
app/
├── __init__.py          # 패키지 설명 (Java BE 전용 FastAPI)
├── main.py              # FastAPI 앱, lifespan(Vertex AI 초기화), 라우터 마운트, /health
├── schemas/             # 요청·응답 Pydantic 모델 (camelCase 직렬화)
│   ├── __init__.py
│   ├── analyze.py       # InternalAnalyzeRequest/Response, RadarData, UniversityPrediction
│   ├── chat.py          # InternalChatRequest/Response, HistoryItem, StickyContext
│   ├── image_edit.py    # InternalImageEditRequest/Response
│   └── stub.py          # SummarizeRequest/Response, DraftRequest/Response (Phase C4 스텁)
├── routers/
│   ├── __init__.py
│   └── ai.py            # prefix /internal/ai, 5개 POST 라우트
├── core/                # 설정·Vertex AI·GCS 클라이언트
│   ├── __init__.py
│   ├── config.py        # Settings(BaseSettings), get_settings()
│   └── gemini_client.py # init_vertex_ai, get_generative_model, GCS download/upload, parse_gcs_uri
└── services/            # 비즈니스 로직
    ├── __init__.py
    ├── analyze_service.py   # Gemini Vision 5축 분석, 총점/등급/fix_scope
    ├── chat_service.py      # 멀티모델 채팅, 퀵리플라이 생성
    └── image_edit_service.py # Gemini 이미지 편집, GCS 업로드
```

### 3.2 스키마(schemas)

- **공통**: `ConfigDict(alias_generator=to_camel, serialize_by_alias=True)` — Java DTO와 camelCase 호환.
- **analyze**: `InternalAnalyzeRequest`(gcs_uri, analysis_type, problem_text), `InternalAnalyzeResponse`(grade, total_score, radar_data, fix_scope, comment, university_predictions).
- **chat**: `InternalChatRequest`(model_type, message, session_id, sticky_context, image_base64, image_mime_type, history), `InternalChatResponse`(text, grounding_urls, quick_replies).
- **image_edit**: `InternalImageEditRequest`(image_base64, prompt), `InternalImageEditResponse`(text, image_url).
- **stub**: Phase C4용 `Summarize*`, `Draft*` — 라우터에서 501 반환.

### 3.3 라우터(routers)

- 단일 라우터 [app/routers/ai.py](../app/routers/ai.py): `APIRouter()`를 `prefix="/internal/ai"`, `tags=["AI Internal"]`로 [main.py](../app/main.py)에서 마운트.
- 각 POST는 해당 서비스 1:1 호출 (analyze → analyze_service, chat → chat_service, edit-image → image_edit_service).

### 3.4 코어(core)

- **config**: `Settings`(gcp_project_id, gcp_region, gcs_bucket_name, google_application_credentials), `get_settings()` 캐시.
- **gemini_client**: Vertex AI 초기화, `get_generative_model(model_name, system_instruction?)`, GCS `download_from_gcs`/`upload_to_gcs`, `parse_gcs_uri`.

### 3.5 서비스(services)

- **analyze_service**: GCS에서 이미지 다운로드 → Gemini Vision(gemini-2.5-pro-preview) → JSON 파싱 → 총점/등급/fix_scope/radar_data 반환.
- **chat_service**: `MODEL_MAP`(CHAT_PRO/FAST/THINKING/SEARCH/IMAGE_EDIT → Gemini 모델명), sticky_context 기반 시스템 프롬프트, 히스토리 변환, 퀵리플라이 생성(gemini-2.5-flash-lite).
- **image_edit_service**: base64 디코딩 → Gemini 2.0 Flash 이미지 편집 → 결과 이미지 GCS `edited/{uuid}.jpg` 업로드 → 공개 URL 반환.

### 3.6 main.py / __init__.py 최종 체크

- **main.py**: `lifespan`에서 `init_vertex_ai()` 1회 호출(실패 시 경고 후 계속). FastAPI 앱 생성 후 `include_router(ai.router, prefix="/internal/ai")`, `GET /health` 정의. 미들웨어 추가 없음(CORS 없음).
- **app/__init__.py**: 패키지 docstring만 있음.

---

## 4. 프레임워크·스택 요약

| 구분 | 스택 |
|------|------|
| **런타임** | Python 3.11 |
| **웹** | FastAPI 0.115.8, uvicorn 0.34.0 |
| **설정** | pydantic-settings 2.7.1, pydantic 2.10.6 |
| **GCP** | google-cloud-aiplatform 1.79.0, google-cloud-storage 2.19.0 |
| **기타** | python-multipart, httpx, python-dotenv (requirements.txt 기준) |

---

## 5. 도메인별 요약표

| 도메인 | 포함 내용 | 비고 |
|--------|-----------|------|
| **infra** | Dockerfile, cloudbuild.yaml, GCP Cloud Run 배포, env (GCP_PROJECT_ID, GCP_REGION, GCS_BUCKET_NAME) | docker-compose 없음 |
| **back** | `/internal/ai/*` 5개 POST + `/health` GET, CORS 없음, CRUD 없음, Java BE 호출 전용 | 스텁 2개(501) |
| **aiml** | app/schemas → routers → core → services, Vertex AI(Gemini), GCS 입출력, Pydantic camelCase | 단일 라우터(ai), 3개 서비스 |

---

이 문서는 **현 시점 코드베이스 기준**이며, SSOT 갱신이 필요하면 `docs/SSOT/miriarts_infra.md` 및 `docs/SSOT/CHANGELOG_infra.md`를 해당 규칙에 따라 수정한다.
