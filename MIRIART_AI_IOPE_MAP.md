# MiriArt AI I-P-O-E 플로우 맵

> **대상**: miriart-ai (FastAPI, Cloud Run) — `/internal/ai/*` 엔드포인트
> **작성일**: 2026-03-10
> **목적**: 기능별 입력(I)·처리(P)·출력(O)·에러(E) 플로우를 한 눈에 파악

---

## A. 작품 분석 (`POST /internal/ai/analyze`)

### 시퀀스 다이어그램

```
BE (Spring)                    AI (FastAPI)                   GCS              Vertex AI (Gemini)
    │                              │                           │                    │
    │  POST /internal/ai/analyze   │                           │                    │
    │  {gcs_uri, analysis_type,    │                           │                    │
    │   problem_text}              │                           │                    │
    │─────────────────────────────>│                           │                    │
    │                              │  download_as_bytes(uri)   │                    │
    │                              │──────────────────────────>│                    │
    │                              │  <── image bytes ─────────│                    │
    │                              │                           │                    │
    │                              │  call_gemini(Flash, image+prompt, JSON)        │
    │                              │──────────────────────────────────────────────> │
    │                              │  <── JSON {grade, totalScore, radarData, ...} │
    │                              │                           │                    │
    │  200 InternalAnalyzeResponse │                           │                    │
    │<─────────────────────────────│                           │                    │
```

### I — Input

| 항목 | 값 |
|------|-----|
| Path | `POST /internal/ai/analyze` |
| Request Body | `InternalAnalyzeRequest` |
| Content-Type | `application/json` |

```json
{
  "gcs_uri": "gs://miriart-bucket/artworks/2026-03-03/aa8ac12c-...jpeg",
  "analysis_type": "basic",
  "problem_text": "정물화 구도와 명암 표현을 평가해주세요"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `gcs_uri` | str | ✅ | GCS 이미지 URI (`gs://` 또는 상대경로) |
| `analysis_type` | str | ✅ | `"basic"` \| `"major"` |
| `problem_text` | str | ❌ | 출제 주제/맥락 |

### P — Processing

| 단계 | 모듈 | 동작 | 파라미터 |
|------|------|------|----------|
| 1 | `gcs_service.download_as_bytes()` | GCS에서 이미지 다운로드 | `gcs_uri` → bytes |
| 2 | 프롬프트 구성 | 시스템: 미대입시 평가 전문가, 5축 채점 | — |
| 3 | `gemini_client.call_gemini()` | Gemini Flash 호출 | model=Flash, temp=0.3, max_tokens=2048, mime=`application/json`, timeout=55s |
| 4 | JSON 파싱 | LLM 응답 → 구조화 데이터 | `json.loads()` |

**Gemini 호출 파라미터**:
- Model: `gemini-2.5-flash`
- Temperature: `0.3` (결정론적)
- Max Output Tokens: `2048`
- Response MIME: `application/json`
- Timeout: `55s`
- 리트라이: 2회 (1회 재시도), initial_delay 1s, max_delay 8s, HTTP [429,500,502,503,504]

### O — Output

| 항목 | 값 |
|------|-----|
| HTTP Status | `200 OK` |
| Response Body | `InternalAnalyzeResponse` |

```json
{
  "grade": "B",
  "totalScore": 72.5,
  "radarData": {
    "density": 75.0,
    "form": 68.0,
    "completion": 80.0,
    "relevance": 65.0,
    "thinking": 74.5
  },
  "fixScope": "DetailTuning",
  "comment": "전체적인 구도는 안정적이나 명암 대비를 강화하면 좋겠습니다...",
  "universityPredictions": [
    {
      "university": "홍익대학교",
      "major": "회화과",
      "line": "MID",
      "probability": 65,
      "similarAcceptedCount": 12
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `grade` | str | `"A"` \| `"B"` \| `"C"` \| `"D"` \| `"F"` |
| `totalScore` | float | 종합 점수 |
| `radarData` | RadarData | 5축 점수 (density/form/completion/relevance/thinking, 0–100) |
| `fixScope` | str | `"StructureRebuild"` \| `"DetailTuning"` |
| `comment` | str | AI 평가 코멘트 |
| `universityPredictions` | List[UniversityPrediction] | 대학 예측 (university/major/line/probability/similarAcceptedCount) |

> **직렬화**: camelCase (`alias_generator`). BE는 이 JSON을 그대로 FE에 전달.

### E — Error

| 예외 | HTTP | body.code | 발생 조건 | BE 매핑 |
|------|------|-----------|-----------|---------|
| `GCSError` | 502 | `GCS_ERROR` | GCS 다운로드 실패 (오브젝트 없음, 권한 등) | F003 |
| `LLMTimeoutError` | 504 | `LLM_TIMEOUT` | Gemini 응답 55s 초과 | AN002 |
| `LLMServiceError` | 502 | `LLM_SERVICE_ERROR` | Gemini API 에러 (429/5xx 리트라이 소진) | AN001 |
| `LLMParsingError` | 502 | `LLM_PARSING_ERROR` | Gemini JSON 응답 파싱 실패 | AN001 |

---

## B. AI 채팅 (`POST /internal/ai/chat`)

### 시퀀스 다이어그램

```
BE (Spring)                    AI (FastAPI)                   Vertex AI (Gemini)
    │                              │                               │
    │  POST /internal/ai/chat      │                               │
    │  {model_type, message,       │                               │
    │   sticky_context, history,   │                               │
    │   image_base64?}             │                               │
    │─────────────────────────────>│                               │
    │                              │  model_type → Gemini 모델 매핑 │
    │                              │  sticky_context → 시스템 프롬프트 병합  │
    │                              │  history → 플랫텐             │
    │                              │  (image_base64 → bytes?)      │
    │                              │                               │
    │                              │  call_gemini(model, contents)  │
    │                              │──────────────────────────────>│
    │                              │  <── text response ───────────│
    │                              │                               │
    │  200 InternalChatResponse    │                               │
    │<─────────────────────────────│                               │
```

### I — Input

```json
{
  "modelType": "CHAT_PRO",
  "message": "명암을 더 잘 표현하는 방법을 알려주세요",
  "sessionId": "abc123",
  "stickyContext": {
    "grade": "B",
    "score": 72.5,
    "fixScope": "DetailTuning",
    "radarData": {"density": 75.0, "form": 68.0, "completion": 80.0, "relevance": 65.0, "thinking": 74.5}
  },
  "history": [
    {"role": "user", "parts": [{"text": "전체적인 평가를 해주세요"}]},
    {"role": "model", "parts": [{"text": "구도는 안정적이나..."}]}
  ],
  "imageBase64": null,
  "imageMimeType": null
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `modelType` | str | ✅ | `"CHAT_PRO"` \| `"FAST"` \| `"THINKING"` \| `"SEARCH"` \| `"IMAGE_EDIT"` |
| `message` | str | ✅ | 사용자 메시지 |
| `sessionId` | str | ❌ | 세션 ID (AI에서 미사용, BE Redis에서 관리) |
| `stickyContext` | StickyContext | ❌ | 분석 결과 컨텍스트 (grade/score/fixScope/radarData) |
| `history` | List[HistoryItem] | ❌ | 대화 이력 [{role, parts: [{text}]}] |
| `imageBase64` | str | ❌ | 이미지 첨부 시 base64 |
| `imageMimeType` | str | ❌ | 이미지 MIME (기본 `image/jpeg`) |

**모델 매핑**:

| modelType | Gemini 모델 |
|-----------|------------|
| `CHAT_PRO` | `gemini-2.5-pro` |
| `FAST` | `gemini-2.5-flash` |
| `THINKING` | `gemini-2.5-pro` |
| `SEARCH` | `gemini-2.5-flash` |
| `IMAGE_EDIT` | `gemini-2.5-flash` |

### P — Processing

| 단계 | 동작 |
|------|------|
| 1 | `modelType` → Gemini 모델 매핑 (MODEL_MAP) |
| 2 | 시스템 프롬프트 구성: "미대입시 AI 멘토, 200자 이내" + stickyContext 병합 |
| 3 | history → `_flatten_history()`: "[role]: text\n" 형식 플랫텐 |
| 4 | imageBase64 있으면 디코딩 → contents에 이미지+텍스트 결합 |
| 5 | `call_gemini()`: temp=0.7, max_tokens=1024, timeout=55s |

### O — Output

```json
{
  "text": "명암 표현을 강화하려면 크로스해칭 기법을 연습해보세요...",
  "groundingUrls": [],
  "quickReplies": [
    "이 부분을 더 자세히 알려주세요",
    "연습 방법을 추천해주세요",
    "비슷한 대학은 어디가 있나요?"
  ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `text` | str | AI 멘토 응답 |
| `groundingUrls` | List[str] | 참조 URL (현재 빈 배열) |
| `quickReplies` | List[str] | 고정 3개 빠른 응답 |

> **참고**: `sessionId`는 AI에서 사용하지 않음. BE가 Redis(`miriart:chat:session:{sessionId}`, TTL 72h)에서 history를 관리하고 AI에 전달.

### E — Error

| 예외 | HTTP | body.code | 발생 조건 | BE 매핑 |
|------|------|-----------|-----------|---------|
| `ValidationError` | 400 | `VALIDATION_ERROR` | base64 이미지 디코딩 실패 | C001 |
| `LLMTimeoutError` | 504 | `LLM_TIMEOUT` | Gemini 55s 초과 | AI002 |
| `LLMServiceError` | 502 | `LLM_SERVICE_ERROR` | Gemini API 에러 | AI001 |

---

## C. 이미지 편집 (`POST /internal/ai/edit-image`)

### 시퀀스 다이어그램

```
BE (Spring)                    AI (FastAPI)                   GCS              Vertex AI (Gemini)
    │                              │                           │                    │
    │  POST /internal/ai/edit-image│                           │                    │
    │  {image_base64, prompt}      │                           │                    │
    │─────────────────────────────>│                           │                    │
    │                              │  base64 decode            │                    │
    │                              │                           │                    │
    │                              │  call_gemini(Flash, image+prompt, raw response)│
    │                              │──────────────────────────────────────────────> │
    │                              │  <── response (text + inline_data image) ─────│
    │                              │                           │                    │
    │                              │  upload_bytes(edited/{uuid}.jpg, bytes)        │
    │                              │──────────────────────────>│                    │
    │                              │  <── public URL ──────────│                    │
    │                              │                           │                    │
    │  200 InternalImageEditResponse                           │                    │
    │<─────────────────────────────│                           │                    │
```

### I — Input

```json
{
  "imageBase64": "/9j/4AAQSkZJRgABAQ...",
  "prompt": "배경을 좀 더 밝게 수정해주세요"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `imageBase64` | str | ✅ | 원본 이미지 base64 |
| `prompt` | str | ✅ | 편집 지시 프롬프트 |

### P — Processing

| 단계 | 동작 | 파라미터 |
|------|------|----------|
| 1 | base64 디코딩 | `base64.b64decode()` |
| 2 | `call_gemini()` | model=Flash, temp=0.4, max_tokens=2048, **timeout=25s** (timeout_override_s=25), `return_response=True` |
| 3 | 응답 파싱 | `candidates[0].content.parts` 순회 → text / inline_data 분리 |
| 4 | GCS 업로드 | `gcs.upload_bytes("edited/{uuid}.jpg", image_bytes)` |

**특이사항**:
- Timeout 25s (timeout_override_s=25). 기본 55s보다 짧게 설정.
- `return_response=True`로 raw 응답 객체를 받아 이미지 바이너리 추출

### O — Output

```json
{
  "text": "이미지 편집이 완료됐습니다. 배경 밝기를 조정했습니다.",
  "imageUrl": "https://storage.googleapis.com/miriart-bucket/edited/a1b2c3d4-e5f6-7890-abcd-ef1234567890.jpg"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `text` | str | AI 편집 코멘트 (기본값: "이미지 편집이 완료됐습니다.") |
| `imageUrl` | str \| null | GCS 공개 URL. Gemini가 이미지를 생성하지 않으면 null |

> **중요**: `imageUrl`은 `https://storage.googleapis.com/...` 형태의 내부 식별용 URL. FE에 직접 전달하지 않음. BE가 Signed URL로 변환하여 FE에 제공.

### E — Error

| 예외 | HTTP | body.code | 발생 조건 | BE 매핑 |
|------|------|-----------|-----------|---------|
| `ValidationError` | 400 | `VALIDATION_ERROR` | base64 디코딩 실패 | C001 |
| `LLMTimeoutError` | 504 | `LLM_TIMEOUT` | Gemini 25s 초과 | AI002 |
| `LLMServiceError` | 502 | `LLM_SERVICE_ERROR` | Gemini API 에러 | AI001 |
| `GCSError` | 502 | `GCS_ERROR` | 편집 이미지 GCS 업로드 실패 | F003 |

---

## D. QA 답변 요약 (`POST /internal/ai/summarize-answers`)

### I — Input

```json
{
  "question": "석고 데생 시 명암을 잡는 순서가 궁금합니다",
  "answers": [
    "보통 큰 면부터 잡고 세부로 들어가요...",
    "저는 경계선을 먼저 잡고 그러데이션을...",
    "하이라이트-미들톤-그림자 순서로..."
  ]
}
```

| 필드 | 타입 | 필수 | 제약 |
|------|------|------|------|
| `question` | str | ✅ | 1–2000자 |
| `answers` | List[str] | ✅ | 1–20개 |

### P — Processing

| 단계 | 동작 |
|------|------|
| 1 | 답변 목록 포맷: `"[답변 1] ...\n[답변 2] ...\n"` |
| 2 | `call_gemini(Flash, question+answers, JSON, temp=0.3, max_tokens=1024)` |
| 3 | JSON 파싱: `{"summary": ..., "supplement": ...}` |

### O — Output

```json
{
  "summary": "답변을 종합하면, 석고 데생 명암은 큰 면→세부→하이라이트 순서로 잡는 것이 일반적입니다...",
  "supplement": "추가로 반사광 처리를 연습하면 입체감이 더 살아납니다."
}
```

### E — Error

| 예외 | HTTP | body.code | 발생 조건 |
|------|------|-----------|-----------|
| `LLMTimeoutError` | 504 | `LLM_TIMEOUT` | 55s 초과 |
| `LLMServiceError` | 502 | `LLM_SERVICE_ERROR` | Gemini API 에러 |
| `LLMParsingError` | 502 | `LLM_PARSING_ERROR` | JSON 파싱 실패 |

---

## E. QA 답변 초안 (`POST /internal/ai/draft-from-question`)

### I — Input

```json
{
  "title": "수채화 채도 조절 팁",
  "content": "수채화에서 채도를 자연스럽게 낮추는 방법이 궁금합니다. 보색 혼합 외에 다른 방법이 있을까요?",
  "imageBase64": null
}
```

| 필드 | 타입 | 필수 | 제약 |
|------|------|------|------|
| `title` | str | ✅ | 1–200자 |
| `content` | str | ✅ | 1–5000자 |
| `imageBase64` | str | ❌ | 이미지 첨부 시 base64 |

### P — Processing

| 단계 | 동작 |
|------|------|
| 1 | 프롬프트 구성: title + content |
| 2 | imageBase64 있으면 디코딩 → contents에 이미지 추가 |
| 3 | `call_gemini(Flash, contents, JSON, temp=0.5, max_tokens=1024)` |
| 4 | JSON 파싱: `{"draft": ...}` |

### O — Output

```json
{
  "draft": "보색 혼합 외에 물 비율을 늘리거나, 회색 계열 물감을 소량 섞는 방법도 효과적입니다..."
}
```

### E — Error

| 예외 | HTTP | body.code | 발생 조건 |
|------|------|-----------|-----------|
| `ValidationError` | 400 | `VALIDATION_ERROR` | base64 이미지 디코딩 실패 |
| `LLMTimeoutError` | 504 | `LLM_TIMEOUT` | 55s 초과 |
| `LLMServiceError` | 502 | `LLM_SERVICE_ERROR` | Gemini API 에러 |
| `LLMParsingError` | 502 | `LLM_PARSING_ERROR` | JSON 파싱 실패 |

---

## 에러 코드 통합 참조표

### AI 내부 에러 코드 → HTTP 매핑

| AI error_code | HTTP | body 구조 | 설명 |
|---------------|------|-----------|------|
| `LLM_TIMEOUT` | 504 | `{"code": "LLM_TIMEOUT", "message": "..."}` | Gemini 응답 시간 초과 |
| `LLM_SERVICE_ERROR` | 502 | `{"code": "LLM_SERVICE_ERROR", "message": "..."}` | Gemini API 장애/에러 |
| `LLM_PARSING_ERROR` | 502 | `{"code": "LLM_PARSING_ERROR", "message": "..."}` | LLM JSON 응답 파싱 실패 |
| `GCS_ERROR` | 502 | `{"code": "GCS_ERROR", "message": "..."}` | GCS 읽기/쓰기 실패 |
| `VALIDATION_ERROR` | 400 | `{"code": "VALIDATION_ERROR", "message": "Request validation failed", "errors": [{"field": str, "message": str}, ...]}` | 입력 유효성 검증 실패 (RequestValidationError 시 errors 배열 포함) |
| `LLM_RATE_LIMITED` | 429 | `{"code": "LLM_RATE_LIMITED", "message": "..."}` | Gemini 429 |
| `INTERNAL_ERROR` | 500 | `{"code": "INTERNAL_ERROR", "message": "..."}` | 미처리 예외 |

### AI → BE 에러 코드 매핑 (참조용)

| AI error_code | BE ErrorCode | BE HTTP | 비고 |
|---------------|-------------|---------|------|
| `LLM_TIMEOUT` | AN002 / AI002 | 504 | 분석/채팅 |
| `LLM_SERVICE_ERROR` | AN001 / AI001 | 502 | 분석/채팅 |
| `LLM_PARSING_ERROR` | AN001 / AI001 | 502 | 분석/QA |
| `GCS_ERROR` | F003 | 502 | 파일 스토리지 |
| `VALIDATION_ERROR` | C001 | 400 | 공통 |

---

## Gemini 호출 파라미터 요약

| 기능 | 모델 | Temp | Max Tokens | Timeout | Response Format | 리트라이 |
|------|------|------|-----------|---------|-----------------|---------|
| 작품 분석 | Flash | 0.3 | 2048 | 55s | JSON | 2회 |
| AI 채팅 | PRO/Flash | 0.7 | 1024 | 55s | Text | 2회 |
| 이미지 편집 | Flash | 0.4 | 2048 | 25s | Raw (image+text) | 2회 |
| QA 요약 | Flash | 0.3 | 1024 | 55s | JSON | 2회 |
| QA 초안 | Flash | 0.5 | 1024 | 55s | JSON | 2회 |

**공통 리트라이 정책**: 2회 (1회 재시도), initial_delay 1s, max_delay 8s, 대상 HTTP [429, 500, 502, 503, 504]

---

*문서 끝 — 2026-03-10*
