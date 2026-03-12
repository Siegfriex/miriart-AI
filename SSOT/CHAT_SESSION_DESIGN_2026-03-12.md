# `/internal/ai/chat` 세션·히스토리 처리 설계 문서

> 기준: 2026-03-12 · rev `48fb3d8` · 대상 레포 `miriart-ai` (FastAPI)

---

## 1. 파일별 역할 요약

### 1-1. `app/routers/ai.py` — 라우터 (진입점)

- **`POST /chat`** (`:60-68`) — `InternalChatRequest`를 받아 `chat_service.chat(request)`에 위임하고 `InternalChatResponse`를 그대로 반환한다.
- 라우터 레벨에서 세션 조회, 히스토리 저장, 인증 등의 로직은 **일절 없다**. Java BE가 IAM 인증을 통과한 뒤 호출하는 내부 전용 엔드포인트.
- prefix `/internal/ai`는 `app/main.py:44`에서 마운트:
  ```python
  app.include_router(ai.router, prefix="/internal/ai", tags=["AI Internal"])
  ```

### 1-2. `app/schemas/chat.py` — Pydantic 스키마

| 클래스 | 라인 | 핵심 필드 |
|--------|------|-----------|
| `HistoryItem` | `:14-20` | `role: str` ("user" \| "model"), `parts: List[Dict[str, Any]]` ([{"text": "..."}]) |
| `UniversityPrediction` | `:23-30` | `name`, `type` (TOP/MID/SAFE), `probability` |
| `StickyContext` | `:33-46` | `grade`, `score`, `fix_scope`, `radar_data?`, `university_predictions?`, `analysis_comment?`, `target_major?`, `target_university?`, **`summary_text?`** |
| `InternalChatRequest` | `:48-59` | `model_type`, `message`, `session_id?`, `sticky_context?`, `image_base64?`, `image_mime_type?`, `history?` |
| `InternalChatResponse` | `:62-69` | `text`, `grounding_urls`, `quick_replies` |

- 모든 모델에 `_CAMEL` ConfigDict (`:11`) 적용 → Java BE의 camelCase JSON과 자동 매핑 (`sessionId` ↔ `session_id`, `summaryText` ↔ `summary_text` 등).

### 1-3. `app/services/chat_service.py` — 서비스 (핵심 로직)

| 함수/상수 | 라인 | 역할 |
|-----------|------|------|
| `_MAX_HISTORY_TURNS = 8` | `:19` | 히스토리 슬라이싱 기준 |
| `_CHAT_MAX_OUTPUT_TOKENS = 4096` | `:20` | Gemini 응답 최대 토큰 |
| `MODEL_MAP` | `:22-28` | `model_type` → `GeminiModel` 매핑 |
| `CHAT_SYSTEM_PROMPT` | `:30-38` | 기본 시스템 프롬프트 (미술 입시 멘토) |
| `_get_effective_history()` | `:41-45` | history[-8:] 슬라이싱 |
| `_SUMMARY_TEXT_MAX_LEN = 500` | `:48` | summary_text 최대 길이 |
| `_build_system_prompt()` | `:51-107` | stickyContext → 시스템 프롬프트 조합 |
| `_flatten_history()` | `:110-125` | HistoryItem[] → `"[role]: text"` 문자열 |
| `chat()` | `:128-181` | 메인 진입점. 모델 선택 → 프롬프트 구성 → Gemini 호출 → 응답 |

---

## 2. `history` 필드의 실제 사용 흐름

### 2-1. 슬라이싱

```
req.history  (Java BE가 Redis에서 꺼내 전달)
     │
     ▼
_get_effective_history(req.history)          ← chat_service.py:133
     │  history[-_MAX_HISTORY_TURNS:]        ← :45, _MAX_HISTORY_TURNS=8 (:19)
     ▼
effective_history  (최대 8턴)
```

**`chat_service.py:41-45`**
```python
def _get_effective_history(history: Optional[List[HistoryItem]]) -> List[HistoryItem]:
    if not history:
        return []
    return history[-_MAX_HISTORY_TURNS:]          # 최근 8턴만
```

### 2-2. 텍스트 변환

```
effective_history
     │
     ▼
_flatten_history(effective_history)           ← chat_service.py:148
     │
     ▼
history_text = "[user]: 안녕\n[model]: 반갑습니다\n[user]: 구도 조언 부탁\n..."
```

**`chat_service.py:110-125`**
```python
def _flatten_history(history: Optional[list]) -> str:
    if not history:
        return ""
    lines = []
    for h in history:
        role = getattr(h, "role", None) or (...)       # :116 — "user" | "model"
        parts = getattr(h, "parts", None) or (...)      # :117
        text = ""
        if parts and isinstance(parts, list) and len(parts) > 0:
            first = parts[0]
            text = first.get("text", "") if isinstance(first, dict) else getattr(first, "text", "")
        ...
        lines.append(f"[{role}]: {text}")               # :124
    return "\n".join(lines)                              # :125
```

### 2-3. 최종 메시지 합성 → Gemini 전달

**`chat_service.py:148-170`**
```python
history_text = _flatten_history(effective_history)                     # :148
messages = f"{history_text}\n[user]: {req.message}\n"                  # :149
    if history_text else f"[user]: {req.message}\n"

# 이미지가 있으면 Part 리스트, 없으면 문자열
if req.image_base64:                                                   # :151
    contents = [
        genai_types.Part.from_text(text=messages),                     # :158
        genai_types.Part.from_bytes(data=image_bytes, mime_type=mime),  # :159
    ]
else:
    contents = messages                                                # :162

raw = await call_gemini(
    model=model_name,              # MODEL_MAP 분기 결과    :165
    contents=contents,             # 히스토리+메시지(+이미지) :166
    system_instruction=system,     # 시스템프롬프트          :167
    purpose="chat",                #                        :168
    temperature=0.7,               #                        :169
    max_output_tokens=_CHAT_MAX_OUTPUT_TOKENS,  # 4096      :170
)
```

**Gemini에 전달되는 최종 구조:**

```
┌─ system_instruction ─────────────────────────────────┐
│  CHAT_SYSTEM_PROMPT (미술 입시 멘토 규칙 5개)          │
│  + "\n\n학생 분석 요약:\n{stickyContext 내용}"         │
└──────────────────────────────────────────────────────┘

┌─ contents ───────────────────────────────────────────┐
│  [user]: 이전 질문 1                                  │
│  [model]: 이전 답변 1                                 │  ← history (최대 8턴)
│  [user]: 이전 질문 2                                  │
│  [model]: 이전 답변 2                                 │
│  [user]: 현재 메시지                                  │  ← req.message
│  (+ image Part, 있는 경우)                            │
└──────────────────────────────────────────────────────┘
```

---

## 3. `session_id` — 로깅 전용, 상태 저장 없음

`session_id`가 코드에서 참조되는 곳은 **단 한 곳**, 로그 출력뿐이다:

**`chat_service.py:136-146`**
```python
logger.info(
    "chat_request",
    extra={
        "session_id": req.session_id,              # ← 여기만. 조건 분기·저장·조회 없음
        "model_type": req.model_type,
        "history_len": len(effective_history),
        "history_len_raw": raw_history_len,
        "sticky_context_present": req.sticky_context is not None,
        "has_image": req.image_base64 is not None,
    },
)
```

- `session_id`를 key로 Redis/DB/메모리에 접근하는 코드는 **전체 레포에 존재하지 않는다**.
- 세션 생성·갱신·만료 로직도 없다.
- `session_id`는 Cloud Logging에서 세션 단위 로그 필터링(`session_id="abc123"`)에만 쓰인다.

---

## 4. `stickyContext` → 시스템 프롬프트 반영

### 4-1. 분기 조건

**`chat_service.py:51-107`** `_build_system_prompt(req)`

```
ctx = req.sticky_context             # :73
         │
         ├─ ctx가 None → 기본 CHAT_SYSTEM_PROMPT만 반환           (:74-75)
         │
         ├─ ctx.summary_text 존재 → (a) 경로                      (:78)
         │     summary 500자 초과 시 절단 + logger.warning         (:80-82)
         │     "\n\n학생 분석 요약:\n{summary}" 추가               (:83)
         │     target_major/university가 summary에 없으면 보충     (:85-88)
         │
         └─ ctx.summary_text 없음 → (b) 경로                      (:91)
               등급/점수/fixScope 기본 문장                        (:92)
               + radar_data (있으면)                               (:93-94)
               + university_predictions (있으면)                   (:95-100)
               + analysis_comment (있으면)                         (:101-102)
               + target_major (있으면)                             (:103-104)
               + target_university (있으면)                        (:105-106)
```

### 4-2. summary_text 안전장치

| 방어 | 코드 위치 | 동작 |
|------|-----------|------|
| None/빈 문자열 | `:78` `if ctx.summary_text:` | falsy면 (b) 경로로 fallback |
| 500자 초과 | `:80-82` | `summary[:500] + "…(이하 생략)"` + `logger.warning` |
| 목표 누락 보충 | `:85-88` | `target_major`/`target_university`가 summary 문자열에 없으면 별도 추가 |

### 4-3. 시스템 프롬프트 예시

**(a) summary_text 있음:**
```
당신은 MiriArt의 미술 입시 AI 멘토입니다. ...규칙 5개...

학생 분석 요약:
B등급(72.5점) · 구조 재구성 필요 · 구도 3.2 / 색채 4.1 / 완성도 3.8 / 적합성 4.0 / 사고력 3.5
추천 대학: 홍익대(상향,68%) · 국민대(적정,82%) · 서울과기대(안정,91%)
목표: 시각디자인 / 홍익대
```

**(b) summary_text 없음 (기존):**
```
당신은 MiriArt의 미술 입시 AI 멘토입니다. ...규칙 5개...

학생 분석 요약: 등급=B, 점수=72.5, fixScope=StructureRebuild.
레이더 지표={'density': 3.2, 'form': 4.1, ...}.
추천 대학군=홍익대(TOP,68%), 국민대(MID,82%), 서울과기대(SAFE,91%).
분석 코멘트: 구도의 안정감이 부족하지만 색채 감각이 우수합니다.
목표 전공=시각디자인. 목표 대학=홍익대.
```

---

## 5. Gemini 호출 파라미터 정리 (Chat 기준)

### 5-1. 모델 선택

**`chat_service.py:22-28`** MODEL_MAP → **`chat_service.py:130`** 런타임 선택

| `model_type` (Java BE 전달) | Gemini 모델 | 모델 ID 정의 |
|----|----|----|
| `CHAT_PRO` | `GeminiModel.PRO` | `gemini-2.5-pro` (`gemini_client.py:66`) |
| `FAST` | `GeminiModel.FLASH` | `gemini-2.5-flash` (`gemini_client.py:65`) |
| `THINKING` | `GeminiModel.PRO` | `gemini-2.5-pro` |
| `SEARCH` | `GeminiModel.FLASH` | `gemini-2.5-flash` |
| `IMAGE_EDIT` | `GeminiModel.FLASH` | `gemini-2.5-flash` |
| (알 수 없는 값) | `GeminiModel.FLASH` (기본값) | `gemini-2.5-flash` |

### 5-2. 호출 파라미터

| 파라미터 | 값 | 정의 위치 |
|----------|-----|-----------|
| `model` | MODEL_MAP 분기 결과 | `chat_service.py:130` → `gemini_client.py:62-67` |
| `temperature` | `0.7` | `chat_service.py:169` |
| `max_output_tokens` | `4096` | `_CHAT_MAX_OUTPUT_TOKENS` (`chat_service.py:20`) → `:170` |
| `timeout` | `55s` (기본값, override 없음) | `GEMINI_TIMEOUT_S` (`gemini_client.py:21`) |
| `retry_attempts` | `3` (초회 + 재시도 2) | `GEMINI_RETRY_ATTEMPTS` (`gemini_client.py:23`) |
| `retry_initial_delay` | `1.0s` | `gemini_client.py:24` |
| `retry_max_delay` | `8.0s` | `gemini_client.py:25` |
| `system_instruction` | `_build_system_prompt(req)` 결과 | `chat_service.py:131` → `:167` |

### 5-3. `call_gemini` 내부 (`gemini_client.py:70-210`)

```python
# :92-97 — GenerateContentConfig 구성
config = types.GenerateContentConfig(
    temperature=temperature,
    max_output_tokens=max_output_tokens,
    system_instruction=system_instruction,
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
)

# :126-134 — Python-level timeout + asyncio.to_thread (sync SDK 래핑)
response = await asyncio.wait_for(
    asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=contents,
        config=config,
    ),
    timeout=effective_timeout,
)
```

---

## 6. 결론: FastAPI는 세션/히스토리를 저장하지 않는다

FastAPI AI 서비스(`miriart-ai`)는 **완전한 stateless 서비스**다. 세션 ID(`session_id`)는 `chat_service.py:139`의 로그 extra 필드에서만 참조되며, Redis·DB·인메모리 등 어떤 저장소에도 접근하지 않는다. 히스토리는 매 요청마다 Java BE가 Redis에서 조회하여 `InternalChatRequest.history` 필드(`schemas/chat.py:59`)로 전달하고, AI 서비스는 이를 `_get_effective_history()`(`:41-45`)로 최근 8턴만 잘라 `_flatten_history()`(`:110-125`)로 텍스트 변환한 뒤, 현재 메시지와 결합하여(`:148-149`) Gemini에 단발성 호출(`:164-171`)을 수행할 뿐이다. `stickyContext` 역시 동일하게 요청에 포함된 값만 사용하여 시스템 프롬프트를 구성하며(`:51-107`), AI 서비스 자체가 이를 저장하거나 다음 요청에 재사용하는 경로는 존재하지 않는다. **모든 상태 관리(세션 생성·히스토리 append·만료)는 Java BE + Redis의 책임이다.**
