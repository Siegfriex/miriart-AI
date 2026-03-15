# miriart-ai 변경 이력

> **목적**: miriart-ai(FastAPI, Cloud Run) 인프라·코드·문서 변경 시 **날짜·롤·수정 내역**을 기록.
> **규칙**: 최신이 **위**에 오도록 추가. 시크릿 값은 기재하지 않음.
> **SSOT 문서**: miriart-ai-infra.md, miriart-ai-api.md, miriart-ai-flows.md, miriart-ai-runbook.md.

---

## 이력

### 2026-03-15 | GCP Cloud SQL 실 DB 기준 SSOT 정합 (에이전트)
- **DB 스키마 반영**: GCP Cloud SQL 프로덕션 12개 테이블 전수 조회 → SSOT 문서 교차검증.
- **api.md §2.2 수정**: chat.py UniversityPrediction 필드 (university/major/line → name/type/probability), StickyContext 누락 필드 5개 추가 (university_predictions, analysis_comment, target_major, target_university, summary_text).
- **api.md §5 신설**: DB 스키마 정합 섹션 — InternalAnalyzeResponse↔analyses, StickyContext 조립 기준, chat_sessions/analysis_usage_logs 테이블 명세.
- **infra.md 수정**: gemini_client.py 핵심 값에 GEMINI_RETRY_INITIAL_DELAY(24), GEMINI_RETRY_MAX_DELAY(25) 추가, 429 라인 범위 184-194→184-196, GeminiModel ID 명시. chat_service.py에 _SUMMARY_TEXT_MAX_LEN(48) 추가.
- **flows.md 수정**: B.P 단계 2 _build_system_prompt summary_text 분기 반영.

### 2026-03-15 | miriart-ai SSOT 4개 문서 코드 정합 + 삭제 안전화 (에이전트)
- **Phase 0-4**: 코드 라인 스냅샷 기준선 확보 → 4개 문서 전체 라인 번호 교차검증 → 불일치 40건+ 수정 (ai.py, config.py, error_handler.py, gemini_client.py, 스키마, 서비스 파일 전수).
- **문서 간 정합**: infra §0.1 ↔ api §1 ↔ flows A-E ↔ runbook §5 엔드포인트·에러·타임아웃·스키마 교차검증 PASS.
- **삭제 안전성**: runbook:57 miriarts_infra.md 참조 → inline 정보로 대체. 4개 문서 외부 참조 0건 확인.
- **Phase 5**: SSOT/ 폴더 25개 파일 삭제, CHANGELOG_infra → miriart-ai-changelog.md 대체, 규칙 파일 갱신.

### 2026-03-15 | miriart-ai 4개 문서화 통합 (에이전트)
- **원칙**: 문서는 코드를 따른다. 코드가 SSOT. 유일 참조는 코드.
- **신규 SSOT 문서 (4개)**: `SSOT/miriart-ai-infra.md` (코드 메타·배포·로깅), `SSOT/miriart-ai-api.md` (엔드포인트·스키마·에러), `SSOT/miriart-ai-flows.md` (I-P-O-E), `SSOT/miriart-ai-runbook.md` (실행·배포·로그·디버깅).
- **삭제**: MIRIART_AI_RUNBOOK.md, MIRIART_AI_API_REFERENCE.md, MIRIART_AI_IOPE_MAP.md, CODE_VS_DOCS_GAP_REPORT.md 등 8개 (내용은 4개 문서로 편입·통합).
