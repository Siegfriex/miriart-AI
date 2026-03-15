# MiriArt Structured Chat v3 — 최종 확정 설계안

**버전:** v3 FINAL (v2 → 3개 에이전트 v2 재검증 → 외부 인프라 벤치마크 반영)  
**확정일:** 2026-03-15  
**설계 결정:** A3 / B2 / C3 / D3 / E1  
**저장 계층(Redis, ChatSession):** v1 범위 외 — 기존 text 유지 확정  
**이 문서는 최종 픽스 기준이며, 이후 변경은 별도 버전으로 관리**

***

## 0. v2→v3 델타 요약

| 계층 | v2 이슈 | v3 수정 내용 |
|------|---------|------------|
| **FastAPI** | `ConfigDict`에 `serialize_by_alias=True` 누락 — FastAPI endpoint 외 경로(`model_dump()` 직접 호출)에서 camelCase 보장 안 됨 | `serialize_by_alias=True` 추가 확정 |
| **FastAPI** | Pydantic 내부 `ValidationError`와 앱 레이어 `ValidationError` 혼용 위험 | `from pydantic import ValidationError as PydanticValidationError` import 분리 |
| **FastAPI** | `response_schema` 미제공 — `response_mime_type`만으로는 간헐적 마크다운 래핑 발생 가능 | `response_schema` 선택적 제공 패턴 추가 (constrained decoding 강화) |
| **FastAPI** | fallback 시 `raw.strip()`이 빈 문자열 가능성 | 최소 안내 문구 fallback 처리 명시 |
| **Java BE** | Redis `updateSessionHistory` 내부 `response.getText()` null 미방어 | `null → ""` 한 줄 수정 필수 |
| **Java BE** | `log.debug` — 배포 환경(INFO) 로그 미출력 → 구조화 성공률 메트릭 불가 | `log.info`로 레벨 변경 + structured/fallback 구분 키 |
| **FE** | `response.sections && response.sections.length > 0` — `null` 케이스 누락 | `(response.sections ?? []).length > 0` 통합 처리 |
| **FE** | action 타입: `border-blue-500/50`, `text-blue-600` — raw Tailwind | `semantic-info` 계열 토큰으로 교체 |
| **FE** | 출처 링크: `text-text-link` — 앱에 없는 토큰 | `text-primary-lime` 기존 링크 스타일 |
| **FE** | groundingUrls/quickReplies DOM 위치 — 말풍선 내부 vs 외부 | **(B안 확정)** 말풍선 `div` 밖 형제 구조 유지. 말풍선에만 `wrapperClass` 적용 |
| **FE** | 섹션 버블 간격 `mb-2` 고정 | 섹션 버블 `mb-2`, 마지막 섹션(`isLastSection`) 또는 일반 AI 버블 `mb-6` 분기 |

***

## 1. 섹션 스키마 계약 (전 레포 공유, 변경 없음)

### 1.1 섹션 타입 · 톤 규칙

| type | 역할 | 톤 |
|------|------|----|
| `strength` | 잘한 점 | 격려 + 구체 근거 1개 이상 |
| `improvement` | 당장 고칠 점 | 직설·단호. `~인 것 같아요` 금지. 문제→이유→영향 순서. |
| `action` | 다음 2주 실천 전략 | 번호 매긴 구체 행동 2~3개. 동사 시작. |

### 1.2 JSON Wire 계약 (camelCase 전 구간)

```json
{
  "summary": "한 줄 핵심 요약 (50자 이내)",
  "sections": [
    { "type": "strength",    "title": "잘하고 있는 것",        "text": "..." },
    { "type": "improvement", "title": "지금 당장 바꿔야 할 것", "text": "..." },
    { "type": "action",      "title": "다음 2주 실천 전략",     "text": "..." }
  ]
}
```

**JSON Wire 키:** 전 구간 **camelCase** 확정.  
FastAPI: `Pydantic alias_generator=to_camel + serialize_by_alias=True` 로 강제.  
Java BE: DTO 필드명 = camelCase 그대로 → `@JsonProperty` 불필요.

***

## 2. FastAPI 변경 설계 (`miriart-ai`) — v3 확정

### 2.1 변경 파일 목록

| 파일 | 변경 |
|------|------|
| `app/schemas/chat.py` | `ChatSection`, `InternalChatResponse` 확장 — `serialize_by_alias=True` 포함 |
| `app/services/chat_service.py` | 프롬프트 교체 + JSON 전처리 + 파싱 + `PydanticValidationError` 분리 + 로깅 |
| `app/core/gemini_client.py` | **변경 없음** — `response_mime_type` 이미 지원(79, 98–99행) |

### 2.2 `app/schemas/chat.py` — v3 확정 스키마

```python
from typing import Literal, Optional, List
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# 기존 _CAMEL 패턴과 동일하게 serialize_by_alias=True 포함
_CHAT_CAMEL = ConfigDict(
    alias_generator=to_camel,
    populate_by_name=True,
    serialize_by_alias=True,   # ← v2 누락, v3 필수 추가
)

class ChatSection(BaseModel):
    """AI 채팅 응답 섹션 — JSON Wire: camelCase"""
    model_config = _CHAT_CAMEL

    type: Literal["strength", "improvement", "action"]
    title: str
    text: str

class InternalChatResponse(BaseModel):
    """FastAPI → BE 채팅 응답 — JSON Wire: camelCase"""
    model_config = _CHAT_CAMEL

    text: str
    summary: Optional[str] = None
    sections: Optional[List[ChatSection]] = None
    grounding_urls: List[str] = []    # Wire: groundingUrls
    quick_replies: List[str] = []     # Wire: quickReplies
```

> **`serialize_by_alias=True` 필요성:** FastAPI `response_model` 경로는 기본 `by_alias=True`로 직렬화하지만, 서비스 내부에서 `model_dump()` 직접 호출, 테스트, 로깅 등 다른 경로에서는 기본 `by_alias=False`로 snake_case가 나온다. 기존 코드베이스의 `_CAMEL` 패턴이 `serialize_by_alias=True`를 포함한 이유와 동일하며, 일관성 확보를 위해 필수.

### 2.3 `app/services/chat_service.py` — v3 확정 구현

#### 2.3.1 `response_schema` 활용 (constrained decoding 강화)

2025년 11월 Google이 Gemini API Structured Outputs 개선을 발표하여 Pydantic 모델을 `response_schema`에 직접 전달하는 방식이 공식 지원된다. `response_mime_type`만으로도 99%+ 신뢰성이 보고되지만, `response_schema`를 함께 제공하면 토큰 레벨의 constrained decoding이 적용되어 마크다운 래핑을 포함한 파싱 실패를 실질적으로 제거할 수 있다.

```python
from typing import Optional, List
from pydantic import BaseModel, ValidationError as PydanticValidationError
import json as _json
import re
import logging

logger = logging.getLogger(__name__)

_DEFAULT_QUICK_REPLIES = ["구도 분석 요청", "색감 피드백", "합격 확률 보기"]
_FALLBACK_TEXT = "(응답을 구조화하지 못했습니다. 내용을 다시 확인해 주세요.)"

# ── response_schema용 내부 Pydantic 모델 (SDK가 JSON Schema로 변환)
class _SectionSchema(BaseModel):
    type: str   # Literal은 SDK 변환 시 enum으로 처리됨
    title: str
    text: str

class _ChatResponseSchema(BaseModel):
    summary: str
    sections: List[_SectionSchema]

CHAT_SYSTEM_PROMPT = """당신은 MiriArt의 미술 입시 AI 멘토입니다.
학생의 미술 작품 분석 결과와 맥락을 바탕으로 실질적인 피드백을 제공합니다.

[응답 형식 — 반드시 아래 JSON만 출력하세요. 코드블록 없이 순수 JSON만.]
{
  "summary": "이번 피드백의 핵심 한 줄 (50자 이내)",
  "sections": [
    { "type": "strength",    "title": "잘하고 있는 것",        "text": "구체적 근거와 함께 격려. 3~5문장." },
    { "type": "improvement", "title": "지금 당장 바꿔야 할 것", "text": "포장 없이 직설적으로. 문제→이유→영향 순서. 3~5문장." },
    { "type": "action",      "title": "다음 2주 실천 전략",     "text": "번호 매긴 구체 행동 2~3개. 동사로 시작. 3~5문장." }
  ]
}

[톤 규칙]
- strength: 격려하되 근거를 반드시 포함. '잘했어요'로만 끝내지 말 것.
- improvement: 단호하게. '~인 것 같아요' 표현 금지. 문제를 직접 명시.
- action: 오늘 당장 실행 가능한 수준으로. 추상적 조언 금지.
- 전체: 고등학생이 이해할 수 있는 미술 전문 용어. 총 1,200자 이내.
- JSON 외 다른 텍스트(코드블록 포함) 절대 출력 금지."""


async def chat(request: InternalChatRequest) -> InternalChatResponse:
    # ── 기존 chat 파이프라인 그대로 유지 ──
    # _build_system_prompt, _get_effective_history, _flatten_history, contents 구성
    # (이미지 유무 분기 포함) — 현재 코드 변경 없음
    system = _build_system_prompt(request)
    history_text = _flatten_history(_get_effective_history(request.history))
    contents = _build_contents_as_before(history_text, request)   # 기존 로직 그대로

    raw = await call_gemini(
        model=model,
        contents=contents,
        system_instruction=system,
        response_mime_type="application/json",
        # response_schema 선택 제공: constrained decoding 강화
        # SDK가 _ChatResponseSchema를 JSON Schema로 변환해 Gemini에 전달
        # → 토큰 레벨에서 스키마 위반 불가 (마크다운 래핑 실질적 제거)
        response_schema=_ChatResponseSchema,
    )

    # ── JSON 전처리: 간헐적 마크다운 래핑 방어 (response_schema 있어도 유지) ──
    cleaned = re.sub(r'^\s*```(?:json)?\s*', '', raw.strip())
    cleaned = re.sub(r'\s*```\s*$', '', cleaned).strip()

    # ── 구조화 파싱 시도 ──
    try:
        parsed = _json.loads(cleaned)
        raw_sections = parsed.get("sections") or []

        if not raw_sections:
            raise ValueError("empty_sections")

        sections = [
            ChatSection(type=s["type"], title=s.get("title", ""), text=s.get("text", ""))
            for s in raw_sections
        ]
        summary = parsed.get("summary", "")

        # 하위 호환 text: [제목]\n본문 join (Redis 저장·히스토리 재로드 호환)
        fallback_text = "\n\n".join(f"[{s.title}]\n{s.text}" for s in sections)

        logger.info(
            "chat_response_format",
            extra={
                "response_format": "structured",
                "sections_count": len(sections),
                "session_id": request.session_id,
            },
        )
        return InternalChatResponse(
            text=fallback_text,
            summary=summary,
            sections=sections,
            grounding_urls=[],
            quick_replies=_DEFAULT_QUICK_REPLIES,
        )

    except (_json.JSONDecodeError, KeyError, PydanticValidationError, ValueError) as e:
        reason = (
            "empty_sections" if isinstance(e, ValueError)
            else "validation_error" if isinstance(e, PydanticValidationError)
            else "json_parse_error"
        )
        logger.warning(
            "chat_response_format",
            extra={
                "response_format": "fallback",
                "reason": reason,
                "session_id": request.session_id,
            },
        )
        # fallback text: 빈 문자열이면 최소 안내 문구 (기획 선택사항 — 기본 활성화)
        text_out = raw.strip() or _FALLBACK_TEXT
        return InternalChatResponse(
            text=text_out,
            summary=None,
            sections=None,
            grounding_urls=[],
            quick_replies=_DEFAULT_QUICK_REPLIES,
        )
```

> **`_build_contents` 미추출:** `_build_system_prompt`, `_get_effective_history`, `_flatten_history`, contents 구성 로직은 현재 코드 그대로 유지. `call_gemini` 호출 인자와 반환 후처리만 확장하는 방식으로 변경 범위를 최소화한다.

> **`_FALLBACK_TEXT` 기획 선택사항:** 빈 raw 응답은 정상 운영 중 극히 드물다. 기본 활성화하되, 기획/PM 판단에 따라 `None`(빈 버블)으로 교체 가능.

***

## 3. Java BE 변경 설계 (`miriart-be`) — v3 확정

### 3.1 변경 파일 목록

| 파일 | 변경 |
|------|------|
| `domain/ai/dto/ChatSection.java` | 신규 DTO |
| `domain/ai/dto/InternalChatResponse.java` | `summary`, `sections` 추가 |
| `domain/ai/dto/ChatResponse.java` | `summary`, `sections` 추가 |
| `domain/ai/service/AiProxyService.java` | null 방어 2곳 + `log.info` + 매핑 |

### 3.2 `ChatSection.java` — v3 확정

```java
package com.miriart.api.domain.ai.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
@Schema(description = "AI 채팅 응답 섹션")
public class ChatSection {

    @Schema(description = "섹션 타입 — strength | improvement | action")
    private String type;

    @Schema(description = "섹션 제목")
    private String title;

    @Schema(description = "섹션 본문 (3~5문장)")
    private String text;
}
```

> **`@JsonProperty` 불필요 확인:** FastAPI가 `serialize_by_alias=True` + `alias_generator=to_camel`로 camelCase 출력. Java Jackson 기본 camelCase 필드명과 정확히 일치. 별도 네이밍 전략 불필요.

### 3.3 `InternalChatResponse.java` — v3 확정

```java
@Getter
@NoArgsConstructor
@Schema(description = "FastAPI → BE 채팅 응답 내부 DTO")
public class InternalChatResponse {

    @Schema(description = "하위 호환용 텍스트 (sections가 있으면 join된 문자열, 없으면 단일 응답)")
    private String text;

    @Schema(description = "한 줄 핵심 요약 (50자 이내, optional)")
    private String summary;

    @Schema(
        description = "역할별 섹션 배열 (없으면 단일 버블 fallback)",
        example = "[{\"type\":\"strength\",\"title\":\"...\",\"text\":\"...\"}]"
    )
    private List<ChatSection> sections;

    private List<String> groundingUrls;
    private List<String> quickReplies;
}
```

### 3.4 `ChatResponse.java` — v3 확정

```java
@Getter
@Builder
@Schema(description = "BE → FE 채팅 응답. sections가 있으면 구조화 UX, 없으면 단일 버블 fallback.")
public class ChatResponse {

    @Schema(description = "하위 호환용 텍스트")
    private String text;

    @Schema(description = "한 줄 핵심 요약 (optional)")
    private String summary;

    @Schema(description = "역할별 섹션 배열 — strength→improvement→action 순 (optional)")
    private List<ChatSection> sections;

    private List<String> groundingUrls;
    private List<String> quickReplies;
    private String sessionId;

    @JsonGetter("sessionKey")
    public String getSessionKey() { return sessionId; }
}
```

### 3.5 `AiProxyService.java` — v3 확정 (null 방어 2곳, log.info)

```java
// ① API 응답용 null 방어 (v2에서 반영)
String textForResponse = (response != null && response.getText() != null)
        ? response.getText() : "";

// ② Redis 저장용 null 방어 (v3 신규 필수 추가)
// updateSessionHistory 내부, modelMsg.put("text", ...) 라인:
// 변경 전: modelMsg.put("text", response.getText());
// 변경 후:
modelMsg.put("text", response.getText() != null ? response.getText() : "");
// 이유: FastAPI fallback/버그 시 text=null → Redis에 "null" 문자열 저장 방지

// ③ 구조화 성공 로그 (v3: debug → info, 배포 환경 메트릭 연동)
if (response != null && response.getSections() != null) {
    log.info("chat response structured, sections_count={}", response.getSections().size());
    // Cloud Logging 쿼리: jsonPayload.message =~ "chat response structured"
}

// ④ ChatResponse 빌드
return ChatResponse.builder()
        .text(textForResponse)
        .summary(response != null ? response.getSummary() : null)
        .sections(response != null ? response.getSections() : null)
        .groundingUrls(response != null ? response.getGroundingUrls() : List.of())
        .quickReplies(response != null ? response.getQuickReplies() : List.of())
        .sessionId(sessionId)
        .build();

// ⑤ Redis/ChatSession 저장 경계 명시 주석 (updateSessionHistory 상단)
// 저장 계층은 sections 미반영 — Structured Chat v1 설계.
// text: sections가 있으면 "[제목]\n본문" join 문자열, 없으면 단일 텍스트.
// 히스토리 재로드 시 과거 턴은 단일 버블 렌더링됨 (의도된 동작).
```

***

## 4. FE 변경 설계 (React/Vite) — v3 확정

### 4.1 변경 파일 목록

| 파일 | 변경 |
|------|------|
| `src/shared/api/schemas/chat.ts` | `chatSectionSchema`, `chatResponseSchema` 확장 |
| `src/shared/model/types.ts` | `Message` 타입 섹션 필드 추가 |
| `src/pages/chat-room/ui/Page.tsx` | sections → 여러 Message 생성 |
| `src/features/chat/ui/MessageBubble.tsx` | sectionType별 디자인 토큰 스타일 + DOM 구조 |

### 4.2 `src/shared/api/schemas/chat.ts`

```typescript
import { z } from 'zod';

export const chatSectionSchema = z.object({
  type: z.enum(['strength', 'improvement', 'action']),
  title: z.string(),
  text: z.string(),
});
export type ChatSection = z.infer<typeof chatSectionSchema>;

export const chatResponseSchema = z.object({
  text: z.string(),
  summary: z.string().optional(),
  // sections: null 허용 (BE가 null 전송 가능) — .optional()로 null/undefined 통합
  sections: z.array(chatSectionSchema).optional(),
  sessionId: z.string().optional(),
  sessionKey: z.string().optional(),
  groundingUrls: z.array(z.string()).optional(),
  quickReplies: z.array(z.string()).optional(),
});
export type ChatResponse = z.infer<typeof chatResponseSchema>;
```

### 4.3 `src/shared/model/types.ts`

```typescript
// 기존 Message 타입에 아래 필드 추가
export type Message = {
  id: string;
  sender: Sender;
  type: MessageType;
  content: string;
  timestamp: number;
  groundingUrls?: string[];
  quickReplies?: string[];
  // ── Structured Chat v1 추가 ──
  sectionType?: 'strength' | 'improvement' | 'action' | 'summary';
  sectionTitle?: string;
  isLastSection?: boolean;   // quickReplies·groundingUrls를 붙일 마지막 섹션 여부
};
```

### 4.4 `src/pages/chat-room/ui/Page.tsx`

```typescript
const DEFAULT_QUICK_REPLIES = ['구도 분석 요청', '색감 피드백', '합격 확률 보기'] as const;

// AI 응답 수신 후:
const baseId = String(Date.now() + 1);
const now = Date.now();  // 동일 턴 timestamp 통일

// ── v3 수정: (response.sections ?? []).length > 0 ──
// null / undefined / [] 를 모두 fallback으로 처리
if ((response.sections ?? []).length > 0) {
  const summaryMsg: Message | null = response.summary
    ? {
        id: `${baseId}-summary`,
        sender: Sender.AI,
        type: MessageType.TEXT,
        content: response.summary,
        timestamp: now,
        sectionType: 'summary',
        isLastSection: false,
      }
    : null;

  const sectionMsgs: Message[] = response.sections!.map((sec, idx) => {
    const isLast = idx === response.sections!.length - 1;
    return {
      id: `${baseId}-${idx}`,
      sender: Sender.AI,
      type: MessageType.TEXT,
      content: sec.text,
      timestamp: now,
      sectionType: sec.type,
      sectionTitle: sec.title,
      isLastSection: isLast,
      // groundingUrls·quickReplies는 마지막 섹션에만 할당
      groundingUrls: isLast ? (response.groundingUrls ?? []) : undefined,
      quickReplies: isLast ? (response.quickReplies ?? DEFAULT_QUICK_REPLIES) : undefined,
    };
  });

  setMessages(prev => [
    ...prev,
    ...(summaryMsg ? [summaryMsg] : []),
    ...sectionMsgs,
  ]);

} else {
  // Fallback: 기존 단일 버블
  setMessages(prev => [...prev, {
    id: baseId,
    sender: Sender.AI,
    type: MessageType.TEXT,
    content: response.text,
    timestamp: now,
    groundingUrls: response.groundingUrls,
    quickReplies: response.quickReplies ?? DEFAULT_QUICK_REPLIES,
  }]);
}
```

### 4.5 `src/features/chat/ui/MessageBubble.tsx` — v3 확정 (디자인 토큰 + DOM 구조 B안)

```tsx
// ── v3 확정: 전체 기존 디자인 토큰 사용. action = semantic-info. 출처 = primary-lime. ──
const SECTION_STYLE: Record<
  'strength' | 'improvement' | 'action' | 'summary',
  { wrapperClass: string; iconEmoji: string; titleClass: string }
> = {
  summary: {
    wrapperClass: 'border-l-4 border-border-default bg-surface-tertiary',
    iconEmoji: '💬',
    titleClass: 'text-text-mid text-xs font-medium',
  },
  strength: {
    wrapperClass: 'border-l-4 border-primary-lime/50 bg-primary-lime/10',
    iconEmoji: '✅',
    titleClass: 'text-primary-lime text-xs font-semibold uppercase',
  },
  improvement: {
    // D3: semantic-error ring 강조
    wrapperClass:
      'border-l-4 border-semantic-error ring-1 ring-semantic-error/20 bg-semantic-error/5',
    iconEmoji: '🔴',
    titleClass: 'text-semantic-error text-xs font-bold uppercase',
  },
  action: {
    // v3: blue-500 raw → semantic-info 토큰으로 교체
    wrapperClass: 'border-l-4 border-semantic-info/50 bg-semantic-info/5',
    iconEmoji: '📋',
    titleClass: 'text-semantic-info text-xs font-semibold uppercase',
  },
};

export function MessageBubble({ message, onQuickReply }: MessageBubbleProps) {
  const isUser = message.sender === Sender.USER;
  const sectionStyle = message.sectionType
    ? SECTION_STYLE[message.sectionType]
    : null;

  // ── v3 확정: DOM 구조 B안 ──
  // 말풍선 div에만 sectionStyle.wrapperClass 적용
  // groundingUrls / quickReplies / timestamp는 말풍선 밖 형제 구조 그대로 유지
  return (
    <div
      className={`flex ${isUser ? 'justify-end' : 'justify-start'}
        ${message.isLastSection ? 'mb-6' : 'mb-2'}`}   // 섹션 간 mb-2, 마지막만 mb-6
    >
      <div className="flex flex-col max-w-[85%] gap-1">
        {/* ① 말풍선 — sectionStyle.wrapperClass만 적용 */}
        <div
          className={[
            'rounded-2xl px-4 py-3',
            isUser
              ? 'bg-primary-lime text-text-inverse'
              : sectionStyle
                ? `bg-surface-alt ${sectionStyle.wrapperClass}`
                : 'bg-surface-alt border border-border-default shadow-sm',
          ].filter(Boolean).join(' ')}
        >
          {/* 섹션 헤더 */}
          {sectionStyle && message.sectionTitle && (
            <div className={`flex items-center gap-1 mb-2 ${sectionStyle.titleClass}`}>
              <span>{sectionStyle.iconEmoji}</span>
              <span>{message.sectionTitle}</span>
            </div>
          )}
          <BodyText>{message.content}</BodyText>
        </div>

        {/* ② groundingUrls — 말풍선 밖 형제 (기존 구조 유지) */}
        {!isUser && message.groundingUrls && message.groundingUrls.length > 0 && (
          <div className="flex flex-wrap gap-2 px-1">
            {message.groundingUrls.map((url, idx) => (
              <a
                key={idx} href={url} target="_blank" rel="noopener noreferrer"
                // v3: text-text-link(없는 토큰) → text-primary-lime
                className="text-xs text-primary-lime underline hover:opacity-80"
              >
                출처 {idx + 1}
              </a>
            ))}
          </div>
        )}

        {/* ③ quickReplies — 말풍선 밖 형제 (기존 구조 유지) */}
        {!isUser && message.quickReplies && message.quickReplies.length > 0 && onQuickReply && (
          <div className="flex flex-wrap gap-2">
            {message.quickReplies.map((reply) => (
              <button
                key={reply} onClick={() => onQuickReply(reply)}
                className="text-xs bg-surface-tertiary hover:bg-surface-alt
                           border border-border-default rounded-full px-3 py-1 text-text-primary"
              >
                {reply}
              </button>
            ))}
          </div>
        )}

        {/* ④ 타임스탬프 — 기존 위치·스타일 유지 */}
        {!isUser && (
          <span className="text-micro text-text-mid self-start px-1">
            {formatTimestamp(message.timestamp)}
          </span>
        )}
      </div>
    </div>
  );
}
```

***

## 5. 전체 변경 범위 확정

| 계층 | 파일 수 | 핵심 변경 |
|------|---------|----------|
| FastAPI | 2개 | 스키마(`serialize_by_alias`, `PydanticValidationError`) + 서비스(프롬프트, 파싱, 로깅) |
| Java BE | 4개 | DTO 3개 + `AiProxyService`(null 방어 2곳, `log.info`, 매핑) |
| FE | 4개 | 스키마, 타입, Page(sections 분기), MessageBubble(토큰, DOM) |
| Redis/DB | **0개** | 변경 없음 — text 저장 형식 유지 |
| API 계약 문서 | 5개 | 하단 §7 참조 |

***

## 6. 배포 전략 · 롤백 (확정)

### 배포 순서

```
권장: FastAPI → BE → FE
허용: BE → FastAPI → FE  (BE 선배포 가능, sections=null → FE fallback)
금지: FE 단독 선배포  (sections 파싱 로직 추가로 인한 미처리 시 렌더 에러)
```

**하위 호환 보장 시나리오:**

| 시나리오 | 동작 |
|----------|------|
| FastAPI v3 + BE 구버전 | BE `InternalChatResponse`에 `sections` 없음 → Jackson unknown field 무시 → `text`만 전달 → FE fallback |
| BE v3 + FastAPI 구버전 | `sections=null` 전달 → FE `(response.sections ?? []).length === 0` → fallback |
| FE v3 + BE 구버전 | `response.sections === undefined` → fallback 단일 버블 |

### 롤백 기준 및 절차

| 조건 | 대응 |
|------|------|
| FastAPI JSON 파싱 실패율 > 5% (배포 후 1시간) | `CHAT_SYSTEM_PROMPT` 내 JSON 예시 단순화 또는 `response_mime_type` 제거 후 재배포 |
| FE 렌더 에러 | `sections` 없으면 자동 fallback — 코드 수정 불필요 |
| BE 배포 문제 | `sections` 필드만 제거하면 구버전 호환 |
| 전체 롤백 순서 | FE → BE → FastAPI |

***

## 7. 문서 업데이트 확정 목록

| 문서 | 추가 내용 |
|------|----------|
| `MiriArt_API_CONTRACT.md` | `POST /api/chat` 응답에 `summary`(optional), `sections[]`(type/title/text, optional) 추가. "sections 있으면 구조화 UX, 없으면 단일 버블" 추가 |
| `docs/SSOT/miriarts_infra.md §4.4` | BE→AI 계약 표에 `summary`, `sections(optional)` 추가. "채팅 구조화는 런타임만 반영, Redis/DB 저장 형식 변경 없음" 유지 |
| `miriart-be/docs/AI_INTERNAL_API_CONTRACT.md` | `InternalChatResponse` 스키마에 `summary`, `sections(ChatSection[])` 추가. "JSON Wire 전 구간 camelCase — FastAPI Pydantic alias_generator=to_camel + serialize_by_alias=True" 명시. "하위 호환: text는 sections join 문자열 또는 단일 텍스트" 추가 |
| `miriart-ai-api.md §2.2` | `InternalChatResponse` 스키마 갱신. 구조화 실패 fallback 로직 설명 추가 |
| `miriart-ai-changelog.md` | Structured Chat v1 (2026-03-15): 변경 파일·계약·롤백 기준 요약 추가 |

***

## 8. 모니터링 체크리스트 (배포 후 24시간)

```bash
# 구조화 성공률 확인 (FastAPI — Cloud Logging)
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-ai"
   AND jsonPayload.message="chat_response_format"' \
  --project=miriarts --limit=200 --format=json \
  | jq '[.[] | {format: .jsonPayload.response_format, reason: .jsonPayload.reason}] | group_by(.format)'

# BE 구조화 로그 확인 (GCP Cloud Run)
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-be"
   AND textPayload=~"chat response structured"' \
  --project=miriarts --limit=100
```

**기대 지표:**
- 구조화 성공률: > 95% (배포 후 24시간 기준)
- Fallback reason 분포: `json_parse_error` 주도 → `response_schema` 효과 검증
- 평균 응답 latency: 기존 대비 10% 이내 증가 허용 (JSON 모드 overhead)

***

## 9. 로컬 에이전트 구현 지시 프롬프트 — v3 최종

> **에이전트 프롬프트 작성 원칙:**  
> 세션 초기화를 고려하여 에이전트가 맥락 없이 시작할 수 있으므로,  
> (1) 사전 베이스 점검 → (2) 단계별 구현 태스크 → (3) 코드라인 근거 .md 보고  
> 3단계 구조로 모든 프롬프트를 구성한다.

***

### 9.1 [miriart-ai] 에이전트 프롬프트

```
당신은 miriart-ai 레포의 FastAPI AI 백엔드를 수정하는 시니어 엔지니어입니다.
아래 지시를 3단계 순서로 엄격히 수행하세요.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 0 — 맥락 점검 (수정 전 반드시 수행)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
다음 파일들을 읽고 현재 상태를 파악하세요:
1. app/schemas/chat.py
   - InternalChatResponse, 기존 _CAMEL ConfigDict 패턴 확인
   - serialize_by_alias 포함 여부 확인
2. app/core/gemini_client.py
   - response_mime_type 파라미터 위치(라인 번호) 확인
   - 기존 GenerateContentConfig 호출 패턴 확인
3. app/services/chat_service.py
   - 현재 chat() 함수 시그니처, _build_system_prompt, _get_effective_history,
     _flatten_history, contents 구성 로직 파악
   - 기존 call_gemini 호출 패턴 확인
4. app/core/exceptions.py (또는 유사 파일)
   - ValidationError 클래스 정의 위치·네임스페이스 확인
     (pydantic.ValidationError와 충돌 가능성 점검)

점검 완료 후 아래 내용을 한 줄씩 확인하고 진행:
- _CAMEL에 serialize_by_alias=True 있는가? (없으면 TASK 1에서 추가)
- 앱 레이어 ValidationError가 pydantic.ValidationError와 같은 이름인가? (같으면 TASK 2에서 alias import 추가)
- response_mime_type 파라미터 라인 번호 기록
- chat() 함수 내 call_gemini 호출 라인 번호 기록

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 1 — 구현 태스크 (순서대로)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TASK 1 — app/schemas/chat.py 수정
1-1. 기존 _CAMEL ConfigDict 패턴을 참조해 _CHAT_CAMEL을 동일 구조로 정의:
     ConfigDict(alias_generator=to_camel, populate_by_name=True, serialize_by_alias=True)
1-2. ChatSection(BaseModel) 신규 추가:
     - model_config = _CHAT_CAMEL
     - type: Literal["strength", "improvement", "action"]
     - title: str
     - text: str
1-3. InternalChatResponse에 동일 model_config 적용 후 필드 추가:
     - summary: Optional[str] = None
     - sections: Optional[List[ChatSection]] = None
     - grounding_urls, quick_replies는 기존 그대로 유지

TASK 2 — app/services/chat_service.py 수정
2-1. import 섹션에 추가:
     from pydantic import ValidationError as PydanticValidationError
     (앱 레이어 ValidationError 이름 충돌 확인 후 alias 결정)
2-2. CHAT_SYSTEM_PROMPT 전체를 설계안 프롬프트 전문으로 교체
2-3. 기존 chat() 함수에서:
     - _build_system_prompt, _get_effective_history, _flatten_history, contents 구성 로직
       절대 변경하지 말 것
     - call_gemini 호출에만 response_mime_type="application/json" 추가
     - (선택) response_schema=_ChatResponseSchema 추가 (내부 Pydantic 모델 정의 후)
2-4. call_gemini 반환값(raw) 이후에 다음 블록 추가:
     - re.sub으로 ```json / ``` 래핑 제거 (cleaned)
     - json.loads → raw_sections 파싱 → ChatSection 리스트 생성
     - raw_sections 비어 있으면 ValueError("empty_sections") 발생
     - 성공: logger.info("chat_response_format", extra={response_format, sections_count, session_id})
     - except (JSONDecodeError, KeyError, PydanticValidationError, ValueError): reason 분류 후
       logger.warning("chat_response_format", extra={response_format:"fallback", reason, session_id})
       text_out = raw.strip() or "(응답을 구조화하지 못했습니다. 내용을 다시 확인해 주세요.)"
       return InternalChatResponse(text=text_out, summary=None, sections=None, ...)

TASK 3 — gemini_client.py: 변경 없음 확인
3-1. PHASE 0에서 기록한 response_mime_type 파라미터 라인 번호를 보고서에만 기재

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 2 — 최종 보고 (반드시 수행)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
아래 항목을 포함한 miriart-ai-structured-chat-v3.md 파일을 작성하세요:

# miriart-ai Structured Chat v3 구현 보고

## 변경 파일 목록
| 파일 | 변경 유형 | 주요 변경 내용 |

## PHASE 0 점검 결과
- _CAMEL serialize_by_alias 여부 (변경 전/후)
- ValidationError 충돌 여부 및 처리 방법
- response_mime_type 파라미터 위치: 파일명:라인번호
- call_gemini 호출 라인: 파일명:라인번호

## TASK별 변경 코드 스니펫 (실제 수정된 라인 기반)
각 TASK마다: 변경 전 코드(라인번호 포함) / 변경 후 코드

## gemini_client.py 무변경 확인
- response_mime_type 파라미터 현황: 파일명:라인번호

## 검증 항목
- [ ] ChatSection model_dump(by_alias=True) 시 camelCase 출력 확인
- [ ] InternalChatResponse serialize_by_alias=True 적용 확인
- [ ] PydanticValidationError import 분리 확인
- [ ] fallback 경로 text_out 빈 문자열 대체 확인
- [ ] 기존 chat() contents 구성 로직 미변경 확인
```

***

### 9.2 [miriart-be] 에이전트 프롬프트

```
당신은 miriart-be 레포의 Java Spring Boot 백엔드를 수정하는 시니어 엔지니어입니다.
아래 지시를 3단계 순서로 엄격히 수행하세요.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 0 — 맥락 점검
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
다음 파일을 읽고 현재 상태를 파악하세요:
1. domain/ai/dto/InternalChatResponse.java
   - 현재 필드 목록 및 어노테이션 확인
   - @JsonProperty 사용 여부 확인
2. domain/ai/dto/ChatResponse.java
   - 현재 필드 목록, @Builder 구조 확인
3. domain/ai/service/AiProxyService.java
   - chat() 메서드 전체 구조 확인
   - updateSessionHistory 메서드 시그니처 및 내부 modelMsg.put("text", ...) 라인 번호 확인
   - 현재 ChatResponse.builder() 구성 라인 번호 확인
   - response null 체크 로직 위치 확인
4. WebClientConfig (또는 AiWebClientConfig) — FastAPI 호출용 WebClient 설정 확인
   - ObjectMapper 커스텀 설정 여부 확인
   - FastAPI가 camelCase를 출력할 예정이므로 별도 SnakeCaseStrategy 설정이 없어야 함

점검 후 확인:
- InternalChatResponse에 ChatSection 타입이 없으면 TASK 1에서 신규 DTO 생성
- updateSessionHistory 내 modelMsg.put("text", response.getText()) 라인 번호 기록
- WebClient ObjectMapper가 snake_case 전략이면 충돌 주의 → 주석 추가

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 1 — 구현 태스크
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TASK 1 — domain/ai/dto/ChatSection.java 신규 생성
1-1. @Getter @NoArgsConstructor 적용
1-2. @Schema(description)으로 type/title/text 각각 설명
1-3. @JsonProperty 없음 — FastAPI camelCase 출력과 Java camelCase 필드명 일치 확인
1-4. 패키지 위치: domain/ai/dto/ (InternalChatResponse.java와 동일 위치)

TASK 2 — domain/ai/dto/InternalChatResponse.java 수정
2-1. private String summary; 추가 (@Schema(description="한 줄 핵심 요약") 포함)
2-2. private List<ChatSection> sections; 추가 (@Schema(description=...) 포함)
2-3. 기존 필드(text, groundingUrls, quickReplies) 절대 변경 금지

TASK 3 — domain/ai/dto/ChatResponse.java 수정
3-1. summary, sections 동일하게 추가
3-2. @Builder 체인에 추가 (@Schema 포함)
3-3. 기존 필드·sessionId·@JsonGetter 변경 금지

TASK 4 — domain/ai/service/AiProxyService.java 수정 (4곳)
4-1. API 응답 null 방어 (PHASE 0에서 위치 확인 후):
     String textForResponse = (response != null && response.getText() != null)
         ? response.getText() : "";
4-2. updateSessionHistory 내부 (PHASE 0에서 라인번호 확인 후):
     변경 전: modelMsg.put("text", response.getText());
     변경 후: modelMsg.put("text", response.getText() != null ? response.getText() : "");
     주석 추가: // null 방어 — FastAPI fallback/버그 시 text=null로 올 수 있음 (Structured Chat v3)
4-3. updateSessionHistory 메서드 상단에 주석 추가:
     // 저장 계층은 sections 미반영 — Structured Chat v1 설계.
     // text: sections가 있으면 "[제목]\n본문" join 문자열, 없으면 단일 텍스트.
4-4. 구조화 성공 로그 추가 (ChatResponse.builder() 직전):
     if (response != null && response.getSections() != null) {
         log.info("chat response structured, sections_count={}", response.getSections().size());
     }
4-5. ChatResponse.builder() 체인에 추가:
     .text(textForResponse)        // 기존 text 교체
     .summary(response != null ? response.getSummary() : null)    // 신규
     .sections(response != null ? response.getSections() : null)  // 신규
     기존 .groundingUrls(), .quickReplies(), .sessionId() 유지

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 2 — 최종 보고
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
miriart-be-structured-chat-v3.md 파일을 작성하세요:

# miriart-be Structured Chat v3 구현 보고

## 변경 파일 목록
| 파일 | 변경 유형 | 주요 변경 |

## PHASE 0 점검 결과
- InternalChatResponse 기존 필드 목록 (변경 전)
- updateSessionHistory modelMsg.put 라인: 파일명:라인번호
- ChatResponse.builder() 위치: 파일명:라인번호
- WebClient ObjectMapper snake_case 여부 및 처리

## TASK별 변경 코드 스니펫 (실제 라인번호 포함)
각 TASK마다: 변경 전 코드 / 변경 후 코드 (라인번호 주석 포함)

## 검증 항목
- [ ] ChatSection.java 생성 확인 (@JsonProperty 없음)
- [ ] updateSessionHistory null 방어 라인 적용 확인
- [ ] log.info 레벨 확인 (log.debug 아님)
- [ ] ChatResponse.builder()에 summary, sections 추가 확인
- [ ] Redis/ChatSession 로직 미변경 확인 (updateSessionHistory 로직 변경 없음)
- [ ] WebClient ObjectMapper 충돌 없음 확인
```

***

### 9.3 [FE] 에이전트 프롬프트

```
당신은 miriart-fe 레포의 React/TypeScript 프론트엔드를 수정하는 시니어 엔지니어입니다.
아래 지시를 3단계 순서로 엄격히 수행하세요.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 0 — 맥락 점검
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
다음 파일들을 읽고 현재 상태를 파악하세요:
1. src/shared/api/schemas/chat.ts
   - 현재 chatResponseSchema 필드 목록 확인
   - Zod 버전 및 사용 패턴 확인
2. src/shared/model/types.ts
   - Message 타입 현재 필드 전체 확인
   - Sender, MessageType enum 위치 확인
3. src/pages/chat-room/ui/Page.tsx
   - AI 응답 수신 후 setMessages 호출 구조 확인 (라인번호)
   - 현재 baseId, timestamp 생성 방식 확인
   - DEFAULT_QUICK_REPLIES 또는 quickReplies 고정값 위치 확인
4. src/features/chat/ui/MessageBubble.tsx
   - 현재 컴포넌트 전체 구조 확인
   - isUser 분기, 기존 AI 버블 스타일 클래스 확인
   - 현재 groundingUrls, quickReplies, 타임스탬프 DOM 위치 확인 (말풍선 내부 vs 외부)
   - 현재 mb 클래스 확인
5. tailwind.config (또는 globals.css/theme 파일)
   - semantic-info 토큰 존재 여부 확인
   - semantic-error, primary-lime, surface-alt, surface-tertiary, border-default 확인

점검 후 확인:
- semantic-info 토큰 없으면 action 타입에 대한 대안 토큰 제안 후 확인 요청
- 현재 groundingUrls/quickReplies DOM 위치 기록 (내부/외부)
- 현재 mb-* 클래스 확인

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 1 — 구현 태스크
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TASK 1 — src/shared/api/schemas/chat.ts
1-1. chatSectionSchema 추가:
     z.object({ type: z.enum(['strength','improvement','action']), title: z.string(), text: z.string() })
1-2. chatResponseSchema에 추가:
     summary: z.string().optional()
     sections: z.array(chatSectionSchema).optional()
     (기존 text, sessionId, groundingUrls, quickReplies 유지)
1-3. ChatSection 타입 export 추가

TASK 2 — src/shared/model/types.ts
2-1. Message 타입에 추가:
     sectionType?: 'strength' | 'improvement' | 'action' | 'summary'
     sectionTitle?: string
     isLastSection?: boolean

TASK 3 — src/pages/chat-room/ui/Page.tsx
3-1. DEFAULT_QUICK_REPLIES 상수 정의 (파일 상단 또는 컴포넌트 외부):
     const DEFAULT_QUICK_REPLIES = ['구도 분석 요청', '색감 피드백', '합격 확률 보기'] as const;
3-2. AI 응답 setMessages 호출 직전에 아래 분기 추가:
     const now = Date.now();  // 동일 턴 timestamp 통일
     if ((response.sections ?? []).length > 0) { ... } else { /* 기존 단일 버블 */ }
3-3. 구조화 분기 내부:
     - summary 버블 (response.summary 있을 때만): id=`${baseId}-summary`, sectionType='summary', isLastSection=false
     - sections 버블 루프: id=`${baseId}-${idx}`, sectionType=sec.type, sectionTitle=sec.title
     - isLast 버블에만 groundingUrls, quickReplies 할당
     - setMessages(prev => [...prev, ...(summaryMsg ? [summaryMsg] : []), ...sectionMsgs])
3-4. 기존 단일 버블 경로에 DEFAULT_QUICK_REPLIES fallback 확인

TASK 4 — src/features/chat/ui/MessageBubble.tsx
4-1. SECTION_STYLE 맵 정의 (컴포넌트 외부):
     - summary: border-border-default, bg-surface-tertiary, text-text-mid
     - strength: border-primary-lime/50, bg-primary-lime/10, titleClass=text-primary-lime
     - improvement: border-semantic-error + ring-1 ring-semantic-error/20 + bg-semantic-error/5, titleClass=text-semantic-error 볼드
     - action: PHASE 0에서 semantic-info 토큰 확인 후
               있으면: border-semantic-info/50, bg-semantic-info/5, titleClass=text-semantic-info
               없으면: border-blue-500/50 등 대안 적용 후 보고서에 명시
4-2. DOM 구조 (B안 확정):
     - 말풍선 div에만 sectionStyle.wrapperClass 적용
     - groundingUrls, quickReplies, 타임스탬프는 말풍선 밖 형제 구조 유지 (기존과 동일)
4-3. mb 분기 적용:
     message.isLastSection ? 'mb-6' : 'mb-2' (섹션 버블 간격)
     sectionType 없는 일반 AI 메시지는 기존 mb 유지
4-4. 출처 링크: text-text-link → text-primary-lime (+ hover:opacity-80)
4-5. 기존 isUser 분기·사용자 버블 스타일 절대 변경 금지

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 2 — 최종 보고
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
miriart-fe-structured-chat-v3.md 파일을 작성하세요:

# miriart-fe Structured Chat v3 구현 보고

## 변경 파일 목록
| 파일 | 변경 유형 | 주요 변경 |

## PHASE 0 점검 결과
- chatResponseSchema 기존 필드 목록
- Message 타입 기존 필드 목록
- groundingUrls/quickReplies 현재 DOM 위치 (내부/외부)
- semantic-info 토큰 존재 여부 및 action 타입 적용 토큰 결정
- 현재 mb 클래스

## TASK별 변경 코드 스니펫 (실제 라인번호 포함)
각 TASK마다: 변경 전 코드 / 변경 후 코드

## 검증 항목
- [ ] (response.sections ?? []).length > 0 분기 적용 확인 (response.sections && ... 아님)
- [ ] groundingUrls는 마지막 섹션(isLastSection=true) 버블에만 할당 확인
- [ ] DEFAULT_QUICK_REPLIES 상수 한 곳에서만 정의 확인
- [ ] 타임스탬프 동일값(now) 사용 확인
- [ ] id 형식 `${baseId}-summary`, `${baseId}-0` 등 확인
- [ ] text-text-link 토큰 미사용 확인 (text-primary-lime 사용)
- [ ] action 타입 토큰 적용 결과 (semantic-info 또는 대안)
- [ ] isUser 분기 및 기존 사용자 버블 스타일 미변경 확인
```