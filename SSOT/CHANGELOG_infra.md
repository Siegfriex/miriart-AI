# 인프라 SSOT 변경 이력 (에이전트 반영)

> **목적**: 에이전트가 인프라·배포·설정 관련 수정 후 SSOT를 갱신할 때, **날짜·롤·구체적 수정 내역**을 기록한다.  
> **규칙**: 최신이 **위**에 오도록 추가. 시크릿 값은 기재하지 않음.  
> **지침**: `.cursor/INFRA_SSOT_GUIDE.md` §5.

---

## 이력

### 2026-03-10 | INFRA_DEV Phase 2 실행 (INFRA_DEV_PLAN_v1.0)
- **TASK-A2**: miriart-be `--invoker-iam-check` 활성화 시도 → `allUsers` Invoker 바인딩이 조직 정책 `iam.allowedPolicyMemberDomains`에 의해 차단 → FE→BE 403 발생 → **즉시 롤백** (`--no-invoker-iam-check`). BE는 `invoker-iam-disabled` 유지, 인증은 Spring Security JWT로 처리.
- **TASK-H1**: BE `GCS_BUCKET_NAME` `miriart-uploads`(404 버킷) → `miriart-bucket`으로 수정 (SSOT 기준 통일).
- **TASK-D2**: BE `FASTAPI_INTERNAL_URL` 수정 — 기존 `https://miriart-ai-svc-946560105497...`(404) → `https://miriart-ai-gzjczkus6q-du.a.run.app`(200). BE memory 512Mi → 1Gi 증설. 리비전 `miriart-be-00032-jnx`.
- **TASK-D3**: `.dockerignore` 보완 — SSOT/, .claude/, .env.*, package-lock.json 추가.
- **TASK-D4**: `cloudbuild.yaml` 최종안 적용 — 듀얼 태그($COMMIT_SHA+latest), min-instances=1, max-instances=20, concurrency=10, cpu-boost, invoker-iam-check, options.logging 추가.
- **TASK-E2**: Alert Policy "miriart-ai 5xx Spike" 생성 (5분간 5xx > 5건 → CTO Email). 알림 채널 `CTO Email` 생성.
- SSOT 갱신: §2 BE(memory, invoker-iam 상태), §3.2 FASTAPI_INTERNAL_URL 확정값, §6.2 Alert Policy 추가, TODO-006 완료.

### 2026-03-10 | INFRA_DEV Phase 0-1 실행 (INFRA_DEV_PLAN_v1.0)
- **TASK-A1**: miriart-ai `--invoker-iam-check` 활성화. 외부 /health → 403 검증 완료. BE SA `roles/run.invoker` 바인딩 재확인.
- **TASK-D1**: miriart-ai min-instances=1, concurrency=10, cpu-boost 적용. 리비전 `miriart-ai-00003-85b` 배포, 100% 트래픽. describe로 spec 확인.
- **TASK-C2**: miriart-ai-runner SA에 `roles/iam.serviceAccountTokenCreator` 추가 (Phase 2 Signed URL 준비).
- **TASK-E1**: Log-based Metrics 4개 생성 (miriart-ai-5xx-errors, miriart-ai-502-gateway, miriart-ai-504-timeout, miriart-be-5xx-errors).
- **TASK-E3**: Monitoring Dashboard "MiriArt-AI BE/AI Overview" 생성 (7패널: AI/BE Request Count, Latency, 5xx Rate, Instance Count).
- SSOT 갱신: §2 Cloud Run(AI concurrency/min/max/IAM), §4.3 SA(serviceAccountTokenCreator), §6.2 관측성(metrics, dashboard).

### 2026-03-09 | 코드베이스 현시점 점검 (infra/back/aiml)
- docs/miriart-ai-codebase-snapshot.md 추가: 루트 yml·Docker, app/ 스키마·라우터·코어·서비스, main/__init__.py, 프레임워크·API·CORS·CRUD를 infra/back/aiml 3도메인으로 정리.
- SSOT(miriarts_infra.md) §1 운영 요약·요청 플로우: BE→AI 호출 path에 `/internal/ai/edit-image` 추가, 전체 엔드포인트 참조를 docs/miriart-ai-codebase-snapshot.md §2.1로 명시. (SSOT 본문, docs/miriarts_infra.md 동기 반영)

### 2026-03-02 | 백엔드/P1 정책 반영
- P1 구현 갭 수정 반영: PlanType FREE 2→5회/월, needsProfile=false 시 분석 한도 스킵. POST /api/auth/token 응답에 role·planType, GET /api/users/me에 planType 추가.
- miriarts_infra.md §4.4: PlanType FREE(5), 한도 체크 조건·GET /api/users/me(planType)·POST /api/analyses(한도 정책) 문구 갱신.
- FSD_v2, PRD_v2, API_CONTRACT: Free 5회/월, 토큰·me 응답 필드(role, planType), plan 응답 monthlyLimit 예시 5 반영. 레포 전제 문서에 P1 크레딧·응답 필드 요약 추가.

### 2026-03-02 | 인프라 에이전트
- miriarts_infra.md §2 Cloud SQL: Cloud Shell 접속용 공개 IP·승인된 네트워크 안내 추가. Cloud Shell egress IP는 환경변수로 두지 않고 세션별 확인 후 승인된 네트워크에 `x.x.x.x/32` 추가하도록 명시. §2 내 "Cloud Shell에서 MySQL 접속 절차" 절차 4단계(변수 설정 → Proxy → Secret 비밀번호 → mysql 접속) 문서화.

### 2026-03-02 | 인프라 에이전트
- miriarts_infra.md §4.4 추가: API 구현 현황(검증됨). 유저/온보딩·AI 분석·AI Chat·성적 입시·전역 에러 정책을 코드 기준으로 정리 후 단일 진실만 반영. 구현 엔드포인트·PlanType·analysis_usage_logs·Redis 채팅 키 패턴·미구현(/api/theory 등)·GlobalExceptionHandler/ErrorCode 참조 명시.
- miriarts_infra.md §7: TODO-008 성적/입시 전용 API 미구현 추가.

### 2026-03-02 | 인프라 에이전트
- CHANGELOG_infra.md 생성. 에이전트 변경 시 SSOT 자동 업데이트 규칙·가이드(infra-ssot.mdc, INFRA_SSOT_GUIDE.md §5) 추가.

### 2026-03-02 | 백엔드 에이전트
- **스키마 SSOT** 명시: 실제 DB(MySQL) 테이블·컬럼·인덱스의 단일 참조를 `docs/mysql_erd_v1.md`(역추출·§4 정합성 점검)로 지정.
- `.cursor/rules/infra-ssot.mdc`: 스키마 SSOT 조항 추가. glob에 `docs/mysql_erd_v1.md`, `docs/MiriArt_ERD_v2.md` 추가.
- `.cursor/INFRA_SSOT_GUIDE.md`: 참조 문서 표에 스키마 SSOT 행 추가. §3 변경 시 동기화에 "DB 스키마/엔티티 → mysql_erd_v1.md §1·§2·§4 갱신, ERD_v2와 조율" 추가.
- miriarts_infra.md §2 Cloud SQL: "실제 스키마 SSOT" 행 추가(mysql_erd_v1.md, Cursor 규칙 참조).
