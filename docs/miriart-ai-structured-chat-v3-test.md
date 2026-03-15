# miriart-ai Structured Chat v3 테스트 보고

**테스트일:** 2026-03-15
**브랜치:** FEAT/CHAT
**테스트 환경:** 로컬 유닛 테스트 + Cloud Run E2E (리비전 miriart-ai-00022-mpx)

---

## PHASE 0 — 맥락 점검 결과

| 항목 | 값 |
|------|-----|
| Cloud Run URL | `https://miriart-ai-gzjczkus6q-du.a.run.app` |
| Region | `asia-northeast3` |
| 배포 리비전 | `miriart-ai-00022-mpx` (2026-03-15, v3 배포 완료) |
| SSOT 문서 | `InternalChatResponse`에 `summary`, `sections` 미반영 (갱신 필요) |

---

## PHASE 1 — 파싱 로직 유닛 테스트 (8건)

### 테스트 결과 요약

| # | 테스트 케이스 | 기대 결과 | 실제 결과 | 상태 |
|---|-------------|----------|----------|------|
| 1 | 정상 JSON 응답 | structured, 3 sections, camelCase dump | 일치 | PASS |
| 2 | 마크다운 래핑 JSON | 래핑 제거 후 structured | 일치 | PASS |
| 3 | 빈 sections 배열 | fallback, reason=empty_sections | 일치 | PASS |
| 4 | 비-JSON 텍스트 | fallback, reason=json_parse_error | 일치 | PASS |
| 5 | 빈 응답 문자열 | fallback, text=_FALLBACK_TEXT | 일치 | PASS |
| 6 | 잘못된 section type ("invalid") | fallback, reason=validation_error | 일치 | PASS |
| 7 | section에 type 키 누락 | fallback, reason=json_parse_error (KeyError) | 일치 | PASS |
| 8 | text 하위호환 형식 ([제목]\n본문) | Redis 호환 텍스트 생성 | 일치 | PASS |

### 테스트 1: 구조화 성공 케이스 (유닛)

**입력 (Gemini 응답 시뮬레이션):**

```json
{
  "summary": "구도는 안정적이나 명암 대비 보강이 시급합니다",
  "sections": [
    {"type": "strength", "title": "잘하고 있는 것", "text": "구도 배치가 안정적입니다."},
    {"type": "improvement", "title": "지금 당장 바꿔야 할 것", "text": "명암 대비가 부족합니다."},
    {"type": "action", "title": "다음 2주 실천 전략", "text": "1. 톤 스케일 연습. 2. 석고상 크로키."}
  ]
}
```

**InternalChatResponse (by_alias=True):**

```json
{
  "text": "[잘하고 있는 것]\n구도 배치가 안정적입니다.\n\n[지금 당장 바꿔야 할 것]\n명암 대비가 부족합니다.\n\n[다음 2주 실천 전략]\n1. 톤 스케일 연습. 2. 석고상 크로키.",
  "summary": "구도는 안정적이나 명암 대비 보강이 시급합니다",
  "sections": [...],
  "groundingUrls": [],
  "quickReplies": ["구도 분석 요청", "색감 피드백", "합격 확률 보기"]
}
```

---

## PHASE 1.5 — Cloud Run E2E 테스트 (6건)

### 테스트 요청

| # | session_id | 메시지 | HTTP | format | sections |
|---|-----------|--------|------|--------|----------|
| 1 | test-cloudrun-v3-001 | 잘한 점/고칠 점/2주 계획 | 200 | structured | 3 |
| 2 | test-cloudrun-v3-002 | 색채 사용 부족한 점 | 200 | structured | 3 |
| 3 | test-cloudrun-v3-003 | 구도 개선 방법 | 200 | structured | 3 |
| 4 | test-cloudrun-v3-004 | 입시 중요 요소 | 200 | structured | 3 |
| 5 | test-cloudrun-v3-005 | 완성도 높이기 연습 | 200 | structured | 3 |
| 6 | test-cloudrun-v3-006 | 명암 대비 강화 연습 | 200 | structured | 3 |

**6/6 (100%) 구조화 성공. fallback 0건.**

### E2E 응답 예시 (test-cloudrun-v3-001)

```json
{
  "text": "[잘하고 있는 것]\n이번 소묘에서 구도 안정성이 매우 양호하게 나타나...",
  "summary": "구도 안정성은 좋으나, 명암 대비와 세부 묘사 개선이 시급합니다.",
  "sections": [
    {"type": "strength", "title": "잘하고 있는 것", "text": "...(246자)"},
    {"type": "improvement", "title": "지금 당장 바꿔야 할 것", "text": "...(265자)"},
    {"type": "action", "title": "다음 2주 실천 전략", "text": "...(502자)"}
  ],
  "groundingUrls": [],
  "quickReplies": ["구도 분석 요청", "색감 피드백", "합격 확률 보기"]
}
```

---

## PHASE 2 — Cloud Logging 성공률 샘플링

### 로그 쿼리 결과

```
총 10건 (2026-03-15T07:00:00Z 이후)
structured=10, fallback=0
구조화 성공률: 100%
```

| timestamp | format | sections_count | reason | session_id |
|-----------|--------|---------------|--------|------------|
| 2026-03-15T08:06:52 | structured | 3 | - | test-cloudrun-v3-003 |
| 2026-03-15T08:06:49 | structured | 3 | - | test-cloudrun-v3-002 |
| 2026-03-15T08:06:48 | structured | 3 | - | test-cloudrun-v3-004 |
| 2026-03-15T08:06:48 | structured | 3 | - | test-cloudrun-v3-006 |
| 2026-03-15T08:06:47 | structured | 3 | - | test-cloudrun-v3-005 |
| 2026-03-15T08:05:36 | structured | 3 | - | (로컬 E2E) |
| 2026-03-15T08:04:29 | structured | 3 | - | (로컬 E2E) |
| 2026-03-15T08:04:04 | structured | 3 | - | (로컬 E2E) |
| 2026-03-15T08:03:47 | structured | 3 | - | test-cloudrun-v3-001 |
| 2026-03-15T08:03:33 | structured | 3 | - | (로컬 E2E) |

### 성공률 평가

| 지표 | 기준 | 실측 | 판정 |
|------|------|------|------|
| 구조화 성공률 | ≥ 95% | 100% (10/10) | PASS |
| fallback 비율 | < 5% | 0% | PASS |
| sections 개수 | 3 (strength/improvement/action) | 전건 3 | PASS |

---

## 구현 중 발견된 버그 및 수정

### BUG-1: reason 분류 오류 (JSONDecodeError → "empty_sections"로 잘못 분류)

**원인:** `json.JSONDecodeError`는 `ValueError`의 서브클래스. 설계안 원본 코드에서 `isinstance(e, ValueError)`를 먼저 체크하여 JSONDecodeError도 "empty_sections"로 분류됨.

**수정:** `JSONDecodeError`를 `ValueError`보다 먼저 체크하도록 순서 변경 (chat_service.py:242-247).

---

## 결론

| 항목 | 판정 |
|------|------|
| 유닛 테스트 (8/8) | PASS |
| Cloud Run E2E (6/6) | PASS |
| Cloud Logging 구조화 성공률 (10/10) | **100%** — PASS |
| camelCase 직렬화 | PASS |
| fallback 경로 | PASS |
| BUG-1 수정 | 완료 |

**최종 판정: 프로덕션 노출 OK**

`response_mime_type="application/json"` + `response_schema` constrained decoding으로 Gemini 2.5 Flash 모델이 100% JSON 구조화 응답을 반환. 샘플 10건 전건 structured, fallback 0건. 프로덕션 트래픽에서 24시간 모니터링 후 최종 확인 권장.
