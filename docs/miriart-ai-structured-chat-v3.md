# miriart-ai Structured Chat v3 구현 보고

**구현일:** 2026-03-15
**브랜치:** FEAT/CHAT

---

## 변경 파일 목록

| 파일 | 변경 유형 | 주요 변경 내용 |
|------|----------|---------------|
| `app/schemas/chat.py` | 수정 | `_CHAT_CAMEL` ConfigDict 추가, `ChatSection` 신규, `InternalChatResponse`에 `summary`·`sections` 추가 |
| `app/services/chat_service.py` | 수정 | `PydanticValidationError` alias import, 시스템 프롬프트 교체, `_ChatResponseSchema` 추가, JSON 파싱·fallback 로직 |
| `app/core/gemini_client.py` | 수정 (최소) | `response_schema` 파라미터 추가 (80행), 동적 적용 (101-102행). 설계안은 무변경 명시였으나 `response_schema` 전달을 위해 필수 추가 |

---

## PHASE 0 점검 결과

- **`_CAMEL` serialize_by_alias 여부:** 변경 전 이미 포함 (chat.py:11). 신규 `_CHAT_CAMEL`도 동일 구조로 정의 (chat.py:14)
- **ValidationError 충돌 여부:** `app.core.exceptions.ValidationError` (exceptions.py:53)와 `pydantic.ValidationError` 이름 충돌 확인. `from pydantic import ValidationError as PydanticValidationError`로 분리 (chat_service.py:14)
- **response_mime_type 파라미터 위치:** `app/core/gemini_client.py:79` (파라미터 정의), `:98-99` (동적 적용)
- **call_gemini 호출 라인:** `app/services/chat_service.py:164-171` (변경 전) → `:193-202` (변경 후)

---

## TASK별 변경 코드 스니펫

### TASK 1 — app/schemas/chat.py

**변경 1: `_CHAT_CAMEL` 추가 (line 13-14)**

```python
# 변경 전: 없음

# 변경 후:
# Structured Chat v3: 채팅 응답 전용 ConfigDict (기존 _CAMEL과 동일 구조)
_CHAT_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True)
```

**변경 2: `ChatSection` 신규 추가 (line 66-73)**

```python
class ChatSection(BaseModel):
    """AI 채팅 응답 섹션 — JSON Wire: camelCase. Structured Chat v3."""
    model_config = _CHAT_CAMEL
    type: Literal["strength", "improvement", "action"]
    title: str
    text: str
```

**변경 3: `InternalChatResponse` 확장 (line 76-85)**

```python
# 변경 전 (line 63-70):
class InternalChatResponse(BaseModel):
    model_config = _CAMEL
    text: str
    grounding_urls: List[str] = []
    quick_replies: List[str] = []

# 변경 후 (line 76-85):
class InternalChatResponse(BaseModel):
    model_config = _CHAT_CAMEL          # _CAMEL → _CHAT_CAMEL
    text: str
    summary: Optional[str] = None       # 신규
    sections: Optional[List[ChatSection]] = None  # 신규
    grounding_urls: List[str] = []      # 유지
    quick_replies: List[str] = []       # 유지
```

### TASK 2 — app/services/chat_service.py

**변경 1: import 추가 (line 8-9, 14, 18)**

```python
# 변경 전:
import base64
import logging
from typing import List, Optional
from app.core.exceptions import ValidationError
from app.schemas.chat import HistoryItem, InternalChatRequest, InternalChatResponse

# 변경 후:
import base64
import json as _json
import logging
import re
from typing import List, Optional
from pydantic import BaseModel, ValidationError as PydanticValidationError
from app.core.exceptions import ValidationError
from app.schemas.chat import ChatSection, HistoryItem, InternalChatRequest, InternalChatResponse
```

**변경 2: 상수 및 response_schema 모델 추가 (line 33-46)**

```python
_DEFAULT_QUICK_REPLIES = ["구도 분석 요청", "색감 피드백", "합격 확률 보기"]
_FALLBACK_TEXT = "(응답을 구조화하지 못했습니다. 내용을 다시 확인해 주세요.)"

class _SectionSchema(BaseModel):
    type: str
    title: str
    text: str

class _ChatResponseSchema(BaseModel):
    summary: str
    sections: List[_SectionSchema]
```

**변경 3: CHAT_SYSTEM_PROMPT 교체 (line 49-67)**

기존 5줄 규칙 프롬프트 → JSON 출력 형식 + 톤 규칙 포함 프롬프트로 전면 교체.

**변경 4: call_gemini 호출 + 후처리 (line 193-262)**

```python
# 변경 전 (line 164-181):
raw = await call_gemini(
    model=model_name, contents=contents, system_instruction=system,
    purpose="chat", temperature=0.7, max_output_tokens=_CHAT_MAX_OUTPUT_TOKENS,
)
return InternalChatResponse(text=raw.strip(), grounding_urls=[], quick_replies=[...])

# 변경 후 (line 193-262):
raw = await call_gemini(
    ...,
    response_mime_type="application/json",       # 신규
    response_schema=_ChatResponseSchema,          # 신규
)
# JSON 전처리 → 파싱 → ChatSection 리스트 생성 → fallback 분기
```

### TASK 3 — gemini_client.py 무변경 확인

설계안은 무변경을 명시했으나, `response_schema` 파라미터가 `call_gemini` 시그니처에 없어 `TypeError`가 발생하므로 최소 변경 적용:

- `response_schema: Optional[Any] = None` 파라미터 추가: `gemini_client.py:80`
- 동적 적용 로직 추가: `gemini_client.py:101-102` (`if response_schema: config.response_schema = response_schema`)

---

## gemini_client.py 변경 내역 (설계안 대비 추가)

- response_mime_type 파라미터 정의: `app/core/gemini_client.py:79`
- response_schema 파라미터 정의: `app/core/gemini_client.py:80` (신규 추가)
- response_mime_type 적용 로직: `app/core/gemini_client.py:99-100`
- response_schema 적용 로직: `app/core/gemini_client.py:101-102` (신규 추가)

---

## 검증 항목

- [x] ChatSection `model_dump(by_alias=True)` 시 camelCase 출력 확인 — `{'type': 'strength', 'title': '...', 'text': '...'}`
- [x] InternalChatResponse `serialize_by_alias=True` 적용 확인 — FastAPI response_model 경로에서 `groundingUrls`, `quickReplies` camelCase 출력
- [x] `PydanticValidationError` import 분리 확인 — `chat_service.py:14`
- [x] fallback 경로 `text_out` 빈 문자열 대체 확인 — `raw.strip() or _FALLBACK_TEXT` (chat_service.py:255)
- [x] 기존 `chat()` contents 구성 로직 미변경 확인 — `_build_system_prompt`, `_get_effective_history`, `_flatten_history`, 이미지 분기 모두 원본 유지 (chat_service.py:157-191)
- [x] `response_schema` 전달 유효성 — `call_gemini`에 파라미터 추가 완료 (gemini_client.py:80, :101-102)
