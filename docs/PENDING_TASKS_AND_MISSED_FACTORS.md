# 미이행 요인 분석 및 앞으로 실행 태스크

> **기준**: CODE_VS_DOCS_GAP_REPORT.md, PRD·FSD 갭 반영 플랜 실행 후 잔여 사항  
> **작성일**: 2026-03-10

---

## 1. 미이행 요인 분석

### 1.1 갭 리포트 §10 상시 유지 항목 (트리거 기반)

| 항목 | 상태 | 미이행 사유 |
|------|------|-------------|
| §0 코드라인 인벤토리 유지 | `[ ]` | 코드 변경 시에만 수행하는 **정기/트리거 태스크**. 일회성 플랜 범위 아님. |
| 인프라 변경 시 §0.2 및 cloudbuild/config 반영 | `[ ]` | 동일 — 인프라/배포 설정 변경 시에만 수행. |

→ **이행 주기**: 코드/인프라 변경이 있을 때마다 갭 리포트 §0·§0.2·관련 표를 갱신.

---

### 1.2 §9 선택 항목 (의도적 미수행)

| 문서 | 항목 | 비고 |
|------|------|------|
| MIRIART_AI_API_REFERENCE.md | "(선택) 타임아웃/리트라이/모델 값이 §0·§1과 일치하는지 검토" | 선택으로 남겨 둠. 필요 시 1회 검토 태스크로 실행. |

---

### 1.3 추가 갭 요인 A1~A8 중 부분·미반영

| ID | 내용 | 반영 여부 | 미이행 요인 |
|----|------|-----------|-------------|
| **A1** | 리트라이 2회, initial_delay 1s, max_delay 8s | IOPE_MAP·RUNBOOK 등 반영됨 | — |
| **A2** | GEMINI_LOCATION | RUNBOOK §4.1, SSOT §3.2 반영 | — |
| **A3** | INTERNAL_ERROR "Internal server error" | RUNBOOK 반영 | — |
| **A4** | 400 VALIDATION_ERROR 시 **errors** 배열 (field, message) 구조 | **일부만** (BE_REFACTOR_REVIEW 등에 언급) | API_REFERENCE·IOPE_MAP에 400 body 예시/표로 **명시 미완** |
| **A5·A6** | gemini_call_start, gemini_call_rate_limited, analyze_pre_gemini | RUNBOOK §1.2 반영 | — |
| **A7** | draft 필드: 스키마엔 길이 제한 없음, 프롬프트 유도만 | API_REFERENCE §2.5 수정됨 | — |
| **A8** | 로컬 8000 vs Docker/Cloud Run 8080, BE FASTAPI_INTERNAL_URL 선택 기준 | RUNBOOK에 8000/8080 예시 있음 | **"선택 기준"**(로컬 vs prod URL 사용 조건) 한 줄 정리 **미추가** |

요약: **A4**(400 errors 배열 문서 명시), **A8**(BE FASTAPI_INTERNAL_URL 선택 기준 한 줄) 가 추가 반영 권장.

---

### 1.4 갭 리포트 §9 체크리스트 외 문서 (플랜 대상 아님 → 구버전 유지)

다음 문서는 §9 문서별 수정 대상에 포함되지 않아, 구버전 수치·설명이 남아 있을 수 있음.

| 문서 | 잔여 구버전 예시 | 비고 |
|------|------------------|------|
| docs/MiriArt_PRD_v2.md | §6 리스크 표 "Java BE Retry **3회**" (213행) | BE 재시도 정책은 BE 코드 기준으로 할 것. AI 쪽은 2회. |
| docs/AI_AGENT_DEBUG_REPORT_2026-03-10.md | 기본 timeout **28s** | 과거 디버그 스냅샷. 갱신 시 55s로 정리 가능. |
| docs/AI_AGENT_CODE_PARSING_REPORT.md | 타임아웃 28s(이미지편집 55s), 리트라이 **3회** | 동일. |
| docs/BE_REFACTOR_REVIEW_REPORT.md | timeout **28** * 1000 (34행) | 과거 리뷰 시점. |
| docs/miriarts_infra.md | AI "문서상 placeholder" 등 | **SSOT는 루트 SSOT/miriarts_infra.md**. docs/ 복사본은 구버전일 수 있음. |

→ **선택**: 위 문서들을 "참고용 과거 스냅샷"으로 두거나, 필요 시 별도 태스크로 갱신.

---

## 2. 앞으로 실행 태스크 (우선순위)

### 2.1 즉시·단기 (갭 완결용)

| # | 태스크 | 대상 | 액션 |
|---|--------|------|------|
| T1 | **A4 반영** — 400 body에 errors 배열 명시 | MIRIART_AI_API_REFERENCE.md, MIRIART_AI_IOPE_MAP.md | §5(또는 에러 섹션)에 400 응답 예시 추가: `"code":"VALIDATION_ERROR", "message":"Request validation failed", "errors":[{"field":"...", "message":"..."}]` 및 필드 설명 표. |
| T2 | **A8 반영** — 로컬 vs prod URL 한 줄 | MIRIART_AI_RUNBOOK.md (또는 SSOT 인프라 문서) | "로컬 개발: BE는 FASTAPI_INTERNAL_URL=http://localhost:8000; prod: Cloud Run AI URL" 수준 한 줄 추가. |

### 2.2 트리거 기반 (변경 시 수행)

| # | 트리거 | 태스크 | 대상 |
|---|--------|--------|------|
| T3 | **코드 변경** (app/ 라우터·서비스·스키마·core 등) | §0 코드라인 인벤토리 갱신 | CODE_VS_DOCS_GAP_REPORT.md §0.1 표 |
| T4 | **인프라/배포 변경** (cloudbuild, config, env) | §0.2 및 관련 표 갱신 | CODE_VS_DOCS_GAP_REPORT.md §0.2, §8 |
| T5 | **API_CONTRACT·갭 리포트 갱신** | FSD F3/F4/C4 Exception·구현 상태 점검, PRD §4.1·SSOT 경로 점검 | FSD 문서 갱신 규칙, PRD §4.1 |

### 2.3 선택 (여유 시)

| # | 태스크 | 대상 |
|---|--------|------|
| T6 | API_REFERENCE §0·§1과 타임아웃/리트라이/모델 값 일치 검토 | MIRIART_AI_API_REFERENCE.md |
| T7 | PRD §6 "Retry 3회" 문구 정리 | BE 재시도 3회 유지 시 "AI는 2회" 등으로 구분 명시 가능 |
| T8 | §9 외 문서 갱신 또는 "과거 스냅샷" 표기 | AI_AGENT_DEBUG_REPORT, AI_AGENT_CODE_PARSING_REPORT, BE_REFACTOR_REVIEW_REPORT, docs/miriarts_infra.md |

---

## 3. 실행 체크리스트 (복사용)

```
[x] T1 — API_REFERENCE / IOPE_MAP: 400 errors 배열 구조 명시 (2026-03-10 수행)
[x] T2 — RUNBOOK(또는 SSOT): FASTAPI_INTERNAL_URL 로컬 vs prod 한 줄 (2026-03-10 수행)
[ ] T3 — (트리거) 코드 변경 시 §0 인벤토리 갱신
[ ] T4 — (트리거) 인프라 변경 시 §0.2 갱신
[ ] T5 — (트리거) API_CONTRACT/갭 리포트 갱신 시 FSD·PRD 점검
[x] T6 — (선택) API_REFERENCE 타임아웃/리트라이 일치 검토 (2026-03-10 수행)
[x] T7 — (선택) PRD §6 Retry 문구 정리 (2026-03-10 수행)
[ ] T8 — (선택) §9 외 문서 갱신 또는 스냅샷 표기
```

---

*문서 끝 — 2026-03-10 (T1·T2·T6·T7 반영 2026-03-10)*
