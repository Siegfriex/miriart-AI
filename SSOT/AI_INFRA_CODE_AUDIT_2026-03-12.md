# MiriArt AI — 스토리지 · 세션 · 맥락 유지 · 플랜별 분기 코드 감사

> 기준일: 2026-03-12 · rev `48fb3d8` · Cloud Run revision `miriart-ai-00019-ww7`

---

## 1. 스토리지 (GCS)

### 1-1. GcsService 클래스

**`app/services/gcs_service.py`**

```python
# :15-22 — lazy init 패턴
class GcsService:
    def __init__(self, bucket_name: str, project_id: str):
        self._bucket_name = bucket_name
        self._project_id = project_id
        self._client: Optional[storage.Client] = None   # 첫 호출 시 초기화
        self._bucket = None

# :24-28 — 첫 호출 시 클라이언트 생성
    def _ensure_client(self):
        if self._client is None:
            self._client = storage.Client(project=self._project_id)
            self._bucket = self._client.bucket(self._bucket_name)
```

| 메서드 | 라인 | 용도 | 호출처 |
|--------|------|------|--------|
| `download_as_bytes(gcs_uri)` | `:30-38` | GCS URI → bytes 다운로드 | analyze_service |
| `upload_bytes(blob_path, data, content_type)` | `:60-70` | bytes → GCS 업로드, 공개 URL 반환 | image_edit_service |
| `generate_signed_url(blob_path)` | `:40-58` | Phase 2 Signed URL (미사용) | — |

### 1-2. GCS 사용처

#### 작품 분석 — 이미지 다운로드

**`app/services/analyze_service.py`**

```python
# :28-29 — 모듈 레벨 GcsService 인스턴스
_settings = get_settings()
gcs = GcsService(bucket_name=_settings.gcs_bucket_name, project_id=_settings.gcp_project_id)

# :81 — analyze_artwork() 내부에서 GCS 다운로드
image_bytes = await asyncio.to_thread(gcs.download_as_bytes, req.gcs_uri)
```

#### 이미지 편집 — 결과 업로드

**`app/services/image_edit_service.py`**

```python
# :22-23 — 동일 패턴
_settings = get_settings()
gcs = GcsService(bucket_name=_settings.gcs_bucket_name, project_id=_settings.gcp_project_id)

# :64-68 — 편집 결과 GCS 업로드
blob_path = f"edited/{uuid.uuid4()}.jpg"
image_url = await asyncio.to_thread(
    gcs.upload_bytes, blob_path, edited_image_bytes, edited_mime
)
```

### 1-3. GCS 설정

**`app/core/config.py`**

```python
# :21-26
gcp_project_id: str = "miriart-dev"
gcs_bucket_name: str = "miriart-bucket"        # prod: miriart-bucket
gcp_region: str = "asia-northeast3"             # Cloud Run 배포 리전
gemini_location: str = "global"                 # Gemini API 호출 리전 (분리)
```

### 1-4. 스토리지 흐름 요약

```
[Java BE] → POST /internal/ai/analyze  { gcsUri: "gs://miriart-bucket/artworks/..." }
                 ↓
         gcs.download_as_bytes(gcsUri)  →  GCS에서 이미지 bytes 수신
                 ↓
         call_gemini(FLASH, image+prompt)  →  분석 JSON 반환
                 ↓
         [Java BE가 결과를 Cloud SQL에 저장]

[Java BE] → POST /internal/ai/edit-image  { imageBase64, prompt }
                 ↓
         call_gemini(FLASH, image+prompt, return_response=True)
                 ↓
         gcs.upload_bytes("edited/{uuid}.jpg", bytes)  →  GCS에 업로드
                 ↓
         imageUrl: "https://storage.googleapis.com/miriart-bucket/edited/{uuid}.jpg"
```

---

## 2. 채팅 세션 유지

### 2-1. 핵심: AI 서비스는 Stateless — 세션은 Java BE(Redis)가 관리

**`app/services/chat_service.py`** 파일 독스트링:

```python
# :4-5 — 연계 설명
# "Java AiProxyService가 /internal/ai/chat 호출, Redis에 히스토리 저장."
```

**`app/schemas/chat.py`**

```python
# :48-59 — InternalChatRequest
class InternalChatRequest(BaseModel):
    model_type: str                              # :53 — CHAT_PRO | FAST | THINKING | SEARCH | IMAGE_EDIT
    message: str                                 # :54 — 현재 사용자 메시지
    session_id: Optional[str] = None             # :55 — Java가 관리, AI는 로깅용 pass-through
    sticky_context: Optional[StickyContext] = None  # :56 — 분석 결과 고정 맥락
    image_base64: Optional[str] = None           # :57
    image_mime_type: Optional[str] = None        # :58
    history: Optional[List[HistoryItem]] = Field(default_factory=list)  # :59 — Java가 Redis에서 꺼내 전달
```

### 2-2. 세션 ID 사용 — 로깅 전용

**`app/services/chat_service.py`**

```python
# :136-145 — chat() 내부 로깅
logger.info(
    "chat_request",
    extra={
        "session_id": req.session_id,              # ← 로깅에만 사용
        "model_type": req.model_type,
        "history_len": len(effective_history),
        "history_len_raw": raw_history_len,
        "sticky_context_present": req.sticky_context is not None,
        "has_image": req.image_base64 is not None,
    },
)
```

> **결론**: `session_id`는 AI 서비스 내에서 어떠한 상태 저장/조회에도 사용되지 않음. 순수 pass-through.

### 2-3. 세션 흐름 (Java BE ↔ Redis ↔ AI)

```
[FE] → POST /api/chat { sessionId, message, ... }
          ↓
[Java AiProxyService]
  1) Redis에서 sessionId로 히스토리 조회
  2) stickyContext 조합 (분석 결과 + 학생 목표)
  3) POST /internal/ai/chat 호출 (history + stickyContext + message)
          ↓
[FastAPI AI 서비스]
  - session_id → 로깅만
  - history → 최근 8턴 슬라이싱 → 프롬프트에 삽입
  - stickyContext → 시스템 프롬프트에 반영
  - Gemini 호출 → 응답 반환
          ↓
[Java AiProxyService]
  4) 응답 + 사용자 메시지를 Redis 히스토리에 append
  5) FE에 응답 전달
```

---

## 3. 맥락 유지 (stickyContext + History)

### 3-1. History 관리

**`app/services/chat_service.py`**

```python
# :19 — 히스토리 최대 턴수
_MAX_HISTORY_TURNS = 8

# :41-45 — 슬라이싱
def _get_effective_history(history: Optional[List[HistoryItem]]) -> List[HistoryItem]:
    """최근 N턴만 사용하여 컨텍스트 윈도우 절약."""
    if not history:
        return []
    return history[-_MAX_HISTORY_TURNS:]

# :110-125 — 히스토리를 텍스트로 변환
def _flatten_history(history: Optional[list]) -> str:
    """히스토리를 [role]: text 형식의 단일 텍스트로 변환."""
    ...
    lines.append(f"[{role}]: {text}")
    return "\n".join(lines)

# :148-149 — 메시지 합성
history_text = _flatten_history(effective_history)
messages = f"{history_text}\n[user]: {req.message}\n" if history_text else f"[user]: {req.message}\n"
```

### 3-2. StickyContext 스키마

**`app/schemas/chat.py`**

```python
# :33-46
class StickyContext(BaseModel):
    model_config = _CAMEL                                    # camelCase alias 자동생성

    grade: str                                               # :38 — A/B/C/D/F
    score: float                                             # :39 — 0~100
    fix_scope: str                                           # :40 — StructureRebuild | DetailTuning
    radar_data: Optional[Dict[str, float]] = None            # :41 — 5축 지표
    university_predictions: Optional[List[UniversityPrediction]] = None  # :42
    analysis_comment: Optional[str] = None                   # :43
    target_major: Optional[str] = None                       # :44
    target_university: Optional[str] = None                  # :45
    summary_text: Optional[str] = None                       # :46 — FE summaryText (신규)
```

### 3-3. 시스템 프롬프트 빌더 — 맥락 주입

**`app/services/chat_service.py`**

```python
# :30-38 — 기본 시스템 프롬프트
CHAT_SYSTEM_PROMPT = """당신은 MiriArt의 미술 입시 AI 멘토입니다.
학생의 미술 작품 분석 결과와 맥락을 바탕으로 친절하고 전문적인 상담을 제공합니다.

규칙:
1. 미술 전문 용어를 사용하되, 고등학생이 이해할 수 있게 설명하세요.
2. 구체적이고 실천 가능한 조언을 제공하세요.
3. 학생의 현재 수준(grade, fixScope)을 고려한 맞춤 조언을 하세요.
4. 격려와 동기부여를 포함하되, 현실적인 피드백도 함께 제공하세요.
5. 충분한 깊이로 답변하되, 핵심을 놓치지 마세요."""

# :48 — 상수: summary_text 최대 길이
_SUMMARY_TEXT_MAX_LEN = 500
```

#### (a) summary_text가 있는 경우 (신규 경로)

```python
# :77-89
if ctx.summary_text:
    summary = ctx.summary_text.strip()
    if len(summary) > _SUMMARY_TEXT_MAX_LEN:
        summary = summary[:_SUMMARY_TEXT_MAX_LEN] + "…(이하 생략)"
        logger.warning("summary_text truncated: original length=%d", len(ctx.summary_text))
    system += f"\n\n학생 분석 요약:\n{summary}"
    # summary에 포함되지 않았을 수 있는 목표 정보만 보충
    if ctx.target_major and ctx.target_major not in summary:
        system += f"\n목표 전공={ctx.target_major}."
    if ctx.target_university and ctx.target_university not in summary:
        system += f"\n목표 대학={ctx.target_university}."
```

#### (b) summary_text 없는 경우 (기존 경로)

```python
# :91-107
system += f"\n\n학생 분석 요약: 등급={ctx.grade}, 점수={ctx.score}, fixScope={ctx.fix_scope}."
if ctx.radar_data:
    system += f" 레이더 지표={ctx.radar_data}."
if ctx.university_predictions:
    ups = ", ".join(f"{u.name}({u.type},{u.probability:.0%})" for u in ctx.university_predictions)
    system += f" 추천 대학군={ups}."
if ctx.analysis_comment:
    system += f" 분석 코멘트: {ctx.analysis_comment}"
if ctx.target_major:
    system += f" 목표 전공={ctx.target_major}."
if ctx.target_university:
    system += f" 목표 대학={ctx.target_university}."
```

### 3-4. 맥락 흐름 다이어그램

```
                    ┌───────────────────────────────────────────┐
                    │          Gemini API 호출                   │
                    │                                           │
                    │  system_instruction:                      │
                    │    CHAT_SYSTEM_PROMPT                     │
                    │    + 학생 분석 요약 (stickyContext)         │
                    │                                           │
                    │  contents:                                │
                    │    [model]: 이전 답변 1                    │
                    │    [user]: 이전 질문 2                     │  ← history (최근 8턴)
                    │    [model]: 이전 답변 2                    │
                    │    [user]: 현재 메시지                     │  ← req.message
                    │    (+ 이미지 Part, 있는 경우)              │
                    └───────────────────────────────────────────┘
```

---

## 4. 플랜별 · 기능별 분기

### 4-1. 모델 타입 매핑 (chat)

**`app/services/chat_service.py`**

```python
# :22-28
MODEL_MAP = {
    "CHAT_PRO":   GeminiModel.PRO,     # gemini-2.5-pro
    "FAST":       GeminiModel.FLASH,   # gemini-2.5-flash
    "THINKING":   GeminiModel.PRO,     # gemini-2.5-pro
    "SEARCH":     GeminiModel.FLASH,   # gemini-2.5-flash
    "IMAGE_EDIT": GeminiModel.FLASH,   # gemini-2.5-flash
}

# :130 — 런타임 모델 선택
model_name = MODEL_MAP.get(req.model_type, GeminiModel.FLASH)  # 기본값: FLASH
```

### 4-2. Gemini 모델 상수

**`app/core/gemini_client.py`**

```python
# :62-67
class GeminiModel:
    FLASH      = "gemini-2.5-flash"
    PRO        = "gemini-2.5-pro"
    FLASH_LITE = "gemini-2.0-flash-lite"   # 선언만, 현재 미사용
```

### 4-3. 서비스별 Gemini 호출 파라미터 비교

| 서비스 | 파일:라인 | 모델 | temp | max_tokens | mime_type | timeout |
|--------|-----------|------|------|------------|-----------|---------|
| **Chat** | `chat_service.py:164` | MODEL_MAP 분기 | 0.7 | 4096 | — | 55s (기본) |
| **Analyze** | `analyze_service.py:110-118` | FLASH | 0.3 | 8192 | `application/json` | 55s (기본) |
| **Image Edit** | `image_edit_service.py:38-46` | FLASH | 0.4 | 2048 | — | **25s** (전용) |
| **QA 요약** | `qa_service.py:63-70` | FLASH | 0.3 | 1024 | `application/json` | 55s (기본) |
| **QA 초안** | `qa_service.py:101-108` | FLASH | 0.5 | 1024 | `application/json` | 55s (기본) |

### 4-4. 글로벌 타임아웃 · 재시도 설정

**`app/core/gemini_client.py`**

```python
# :20-26
GEMINI_TIMEOUT_S = 55                # BE 65s - 10s margin
GEMINI_TIMEOUT_MS = GEMINI_TIMEOUT_S * 1000
GEMINI_RETRY_ATTEMPTS = 3           # 초회 + 재시도 2회
GEMINI_RETRY_INITIAL_DELAY = 1.0
GEMINI_RETRY_MAX_DELAY = 8.0
GEMINI_IMAGE_EDIT_TIMEOUT_S = 25    # 이미지 편집 전용
```

### 4-5. 라우터 엔드포인트 매핑

**`app/routers/ai.py`** → **`app/main.py:44`** prefix `/internal/ai`

| HTTP | 엔드포인트 | 라우터 라인 | 서비스 함수 |
|------|-----------|------------|------------|
| GET | `/internal/ai/status` | `:24-46` | inline (설정 리포트) |
| POST | `/internal/ai/analyze` | `:49-57` | `analyze_service.analyze_artwork(req)` |
| POST | `/internal/ai/chat` | `:60-68` | `chat_service.chat(req)` |
| POST | `/internal/ai/edit-image` | `:71-79` | `image_edit_service.edit_image(req)` |
| POST | `/internal/ai/summarize-answers` | `:82-91` | `qa_service.summarize_answers(...)` |
| POST | `/internal/ai/draft-from-question` | `:94-107` | `qa_service.draft_from_question(...)` |
| GET | `/health` | `main.py:47-50` | inline `{"status": "ok"}` |

---

## 5. 현재 한계 및 미구현 사항

| 항목 | 현황 | 비고 |
|------|------|------|
| **사용자 플랜 기반 분기** | ❌ 미구현 | `model_type`은 Java BE가 결정. AI 서비스는 플랜 정보 없음 |
| **세션 저장/조회** | ❌ AI에서 미관리 | Java BE(Redis)가 전담. AI는 stateless |
| **히스토리 압축** | ❌ 단순 슬라이싱만 | `_MAX_HISTORY_TURNS=8` 초과 시 오래된 턴 삭제 (요약 없음) |
| **Signed URL** | 🔶 코드 준비 완료, 미사용 | `gcs_service.py:40-58` Phase 2 대비 |
| **FLASH_LITE** | 🔶 상수 선언만 | `gemini_client.py:67` 어디서도 참조 안 함 |
| **사용량 쿼터/제한** | ❌ AI 서비스에 없음 | Java BE 레벨에서 처리 추정 |
| **summary_text 활용** | ✅ 구현 완료 | `chat_service.py:77-89`, 500자 제한 + 절단 방어 |
