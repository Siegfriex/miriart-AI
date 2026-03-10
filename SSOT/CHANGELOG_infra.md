# 인프라 SSOT 변경 이력 (에이전트 반영)

> **목적**: 에이전트가 인프라·배포·설정 관련 수정 후 SSOT를 갱신할 때, **날짜·롤·구체적 수정 내역**을 기록한다.  
> **규칙**: 최신이 **위**에 오도록 추가. 시크릿 값은 기재하지 않음.  
> **지침**: `.cursor/INFRA_SSOT_GUIDE.md` §5.

---

## 이력

### 2026-03-10 | Signed URL Go-Live 인프라 최종 정리 (INFRA_DEV)

- **대시보드 실제 생성**: "MiriArt - BE Signed URL" (ID: `707df634-a515-4226-9e73-edf7f9e9db91`) — 위젯 3개 (발급 수 ALIGN_RATE, 실패 수 ALIGN_SUM, Top objectPath 텍스트).
- **알람 정책 실제 생성**: "Signed URL Errors Spike" (Policy ID: `10494294328358958245`) — `miriart-be-signed-url-errors > 0` 5분 지속 → CTO Email.
- **SSOT 갱신**:
  - `DASHBOARD_SIGNED_URL_SPEC.md`: 대시보드 URL, 알람 Policy ID 추가.
  - `RUNBOOK_AI_INFRA_v1.md` §5.1: 대시보드 표 형식으로 2개 대시보드 정리, 직접 링크 추가. §5.3: Alert Policies 표로 2개 정책 정리.
  - `miriarts_infra.md` §6.2: 메트릭 6개, 대시보드 2개, 알람 2개로 갱신.
- **Go-Live 리포트**: `SSOT/INFRA_SIGNED_URL_GO_LIVE_REPORT_2026-03-10.md` 생성 — 메트릭/대시보드/알람 내역, BE/FE/AI 상태, 배포 체크리스트 상태, 모니터링 플로우, 남은 TODO 7건.
- **인프라 검증**: BE SA tokenCreator ✅, GCS CORS ✅, AI 코드 경로 `edited/{uuid}.jpg` SSOT 일치 ✅, AI Cloud Run IAM 403 외부 ✅, 양 서비스 GCS_BUCKET_NAME=miriart-bucket ✅.

### 2026-03-10 | Signed URL 관측성·디버깅·배포 체크리스트 정형화 (INFRA_DEV)

- **메트릭 이름 정규화**: 기존 `miriart-be-signed-url-issued` / `miriart-be-signed-url-error` 삭제 → 지침 기준 `miriart-be-signed-url-count` / `miriart-be-signed-url-errors` 재생성 (동일 필터).
- **신규 문서**: `SSOT/DASHBOARD_SIGNED_URL_SPEC.md` 생성 — §1 메트릭 정의, §2 대시보드 위젯 3개(발급 수/실패 수/Top objectPath), §3 알람 임계값(`errors > 0` 5분 지속 → CTO), §4 BE 로그 출력 규격(JSON 구조, 필수 필드).
- **Runbook 갱신**:
  - §4 Step 2 증상 표 확장: 에러코드 F005/I001 매핑 포함 11행 (기존 9행 → 해결 액션 컬럼 추가).
  - §4.3 신규: "이미지 로딩 실패 시 디버깅 절차" 5단계 (증상 파악 → Signed URL 판별 → GCS 오브젝트 확인 → SA/권한 확인 → CORS 확인). 15분 초과 시 CTO 에스컬레이트.
  - §5.2 Log-based Metrics 표에 `miriart-be-signed-url-count`, `miriart-be-signed-url-errors` 2행 추가.
  - §8 신규: "Signed URL 관련 변경 배포 체크리스트" (배포 전/직후/1일 후, BE/FE/인프라 담당별).
- **SSOT 갱신**: `miriarts_infra.md` §3.4 — "AI가 새 경로 패턴을 도입하면..." 문구를 구체적 3단계 프로세스로 교체 (SSOT 선수정 → BE 허용 목록 → PR 체크).

### 2026-03-10 | GCS Signed URL 인프라 준비 (INFRA_DEV)
- **BE SA tokenCreator 부여**: `miriart-be-runner` SA에 `roles/iam.serviceAccountTokenCreator` 추가 (자기 자신 바인딩). GCS V4 Signed URL 서명 가능.
- **GCS CORS 설정**: `miriart-bucket`에 CORS 적용 — origin: `https://miriart.app`, `http://localhost:3000`, method: GET, maxAge: 3600s.
- **SSOT 갱신**: §3.4 이미지 전달 정책(Signed URL) 신규 섹션 추가, §4.3 SA 역할 업데이트, §2 GCS 버킷 CORS 반영.
- **Runbook 갱신**: §4 장애 대응 증상 표에 Signed URL 관련 4개 항목 추가, §6에 GCS 디버깅 명령어 추가, §7 제약사항 상태 갱신.
- **제안서**: `SSOT/SIGNED_URL_INFRA_PROPOSAL_2026-03-10.md` 생성 — A/B안 비교, TTL/경로/보안/관측성 정책.

### 2026-03-10 | INFRA-T1~T4 최종 검증 및 런북 작성 (INFRA_DEV)
- **INFRA-T1** E2E 스모크: AI 403(외부)/200(내부), BE 200 정상 확인. 실 E2E 트래픽(analyze/chat) 없음 — FE 테스트 필요.
- **INFRA-T2** 관측성: 메트릭 4개, Alert Policy 1개, Dashboard 1개 정상 존재 확인. 5xx 0건으로 알림 트리거 미검증.
- **INFRA-T3** imageUrl: GCS `https://storage.googleapis.com/miriart-bucket/...` → 403. allUsers 바인딩 없음. Phase1(BE 프록시) vs Phase2(Signed URL) 정책 제안 문서화.
- **INFRA-T4** 런북: `SSOT/RUNBOOK_AI_INFRA_v1.md` 생성 — 배포/롤백/장애대응/관측성/운영명령어 7섹션.
- 검증 리포트: `SSOT/INFRA_VERIFICATION_REPORT_2026-03-10.md` 생성.

### 2026-03-10 | 조직 정책·DRS 완화 상태 문서화 (INFRA_DEV)
- miriarts_infra.md §4.2.1 신규 섹션 추가: 조직 정책 `iam.allowedPolicyMemberDomains` 현황, BE `invoker-iam-disabled: true` 완화 상태 명시, 릴리즈 전 태그 기반 예외 구조(`sa-api-key-policy` enforced/exempt) 전환 계획 기술.
- §7 TODO-009 추가: BE IAM 정상화 — 릴리즈 전 보안 점검 시 조직 태그 예외 적용 후 `--allow-unauthenticated --invoker-iam-check` 전환.

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
