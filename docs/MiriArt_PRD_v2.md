# MiriArt PRD v2.2 — 제품 요구 명세서

> **목적**: Legacy PRD v1.1 갭 메우기 + 현 구현 상태 반영 + 커뮤니티 비전 통합
> **버전**: 2.2 | **작성일**: 2026-02-22 | **최종 수정**: 2026-03-02
> **검증 기준선**: `docs/SSOT/miriarts_infra.md` + 코드베이스 (문서 정합성 검증일: 2026-03-02)
> **기반**: Legacy PRD v1.1, `MiriArt_FSD_v2.md`, `MiriArt_ERD_v2.md`, Community Design v1.0, FE Disassembly Report v1.0

---

## 0. 실행 요약

### 0.1 한 줄 요약

| 구분 | 내용 |
|------|------|
| **제품** | MiriArt (미리미대) — AI 기반 미대 입시 평가·코칭 + 수험생 커뮤니티 플랫폼 |
| **한 줄 정의** | Vision AI 작품 평가 + 입시 빅데이터 + 수험생 간 Q&A 커뮤니티를 결합한, 미대 입시 수험생 전용 AI 코칭 앱 |
| **타겟** | 기초디자인·기초소양 입시 수험생 (핵심 타겟: 학원 미이용 4만명/년) |
| **가치 제안** | "AI가 8초 만에 내 작품을 분석하고, 선배들의 실전 Q&A로 부족함을 채운다" |

### 0.2 Legacy PRD v1.1 vs MiriArt PRD v2.2 변경점

| 항목 | Legacy PRD v1.1 | MiriArt PRD v2.2 |
|------|-----------------|-------------------|
| 프로젝트명 | dysprime | MiriArt (미리미대) |
| BE 스택 | React Native + Next.js + Firebase | Java/Spring Boot + FastAPI + MySQL/Redis |
| Auth | 이메일/비밀번호 | 카카오 + 구글 OAuth2 only |
| AI 서비스 | Cloud Run 단일 | Java BE + FastAPI 분리 |
| 커뮤니티 | 없음 | 에브리타임 × 지식인 Q&A + 평판 시스템 추가 |
| Chat 저장 | Firestore | Phase 1: Redis TTL → Phase 2: MySQL |
| 파일 스토리지 | Cloud Storage | GCS (동일) |

---

## 1. Why — 문제 정의

### 1.1 핵심 문제

| 문제 | 현황 | 영향 |
|------|------|------|
| 실력 진단 불가 | "내 작품이 A급인지 C급인지?" 주관적 판단만 가능 | 성장 추적 어려움 |
| 대학 라인 추정 불가 | 실기 30~50%가 암흑 | 지원 전략 수립 불가 |
| 개선 방향 모호 | "완성도를 높이세요" 수준의 추상 피드백 | 우선순위 불명, 비효율 |
| 또래 정보 단절 | 학원 간 정보 공유 없음, 커뮤니티 부재 | 지역/비용 정보 비대칭 |

### 1.2 MiriArt 솔루션

| 솔루션 계층 | 내용 |
|------------|------|
| **Layer 1 — Vision AI** | 8초 내 A~F 등급 + 5축 레이더 분석 (density/form/completion/relevance/thinking) |
| **Layer 2 — 입시 DB** | 수능 등급 + 작품 점수 → 대학별 합격 확률 (TOP/HIGH/MID/LOW) |
| **Layer 3 — AI 멘토** | fixScope 기반 1:1 AI 코칭 채팅 |
| **Layer 4 — 커뮤니티** | 에브리타임 피드 + 지식인 Q&A + 평판 기반 멘토 시스템 |

---

## 2. Who — 타겟과 역할

### 2.1 타겟 세그먼트

| Segment | 인원 | 특징 | ARPU |
|---------|------|------|------|
| 학원 미이용 재수/3수생 | 12,000명 | 비용 민감, 멘토 절실 | 월 2~5만원 |
| 지방 학생 | 15,000명 | 서울 학원 접근 불가 | 월 2~3만원 |
| 학원 보조 현역생 | 10,000명 | 학원 외 개인 연습 피드백 필요 | 월 2만원 |
| 학부모 | - | 자녀 학습 모니터링, 결제자 | Phase 3 Family |

### 2.2 플랜별 권한 매트릭스

| 기능 | Free | Basic | Premium | Admin |
|------|------|-------|---------|-------|
| 작품 분석 | 월 5회 (온보딩 전만 한도 적용) | 월 10회 | 무제한 | 무제한 |
| AI Chat (기본 모델) | 가능 | 가능 | 가능 | 가능 |
| AI Chat (이미지편집) | 불가 | 가능 | 가능 | 가능 |
| 커뮤니티 읽기 | 가능 | 가능 | 가능 | 가능 |
| 커뮤니티 쓰기/좋아요 | 로그인 필수 | 가능 | 가능 | 가능 |
| 입시 DB 상세 | 불가 | 불가 | 가능 | 가능 |

### 2.3 플랜별 가격

| 플랜 | 월 가격 | 분석 횟수 | AI 채팅 |
|------|--------|-----------|---------|
| Free | 0원 | 5회/월 | 기본 모델 |
| Basic | 19,900원 | 10회/월 | 전체 모델 |
| Premium | 49,900원 | 무제한 | 전체 + 입시DB 상세 |

---

## 3. How — 기술 아키텍처

### 3.1 기술 스택 (확정)

| 레이어 | 기술 | 용도 |
|--------|------|------|
| FE | React 19 + TypeScript + Vite 6 + Zustand + Tailwind CSS 4 | 모바일 웹 앱 |
| BE Core | Java 17 + Spring Boot 3.4.x + JPA + MySQL 8.x + Redis | 인증/도메인/커뮤니티 |
| AI Service | Python 3.11 + FastAPI + Vertex AI/Gemini SDK | AI 분석/채팅/이미지편집 |
| Storage | Google Cloud Storage (GCS) | 이미지 파일 |
| Infra | Google Cloud Run (BE + AI), GCS, MySQL (Cloud SQL 또는 자체) |

### 3.2 Cariv BE 재사용률

| 카테고리 | 재사용률 | 내용 |
|---------|---------|------|
| 글로벌 인프라 (Security/Exception/BaseEntity/Redis) | 85~95% | 패키지명·경로만 수정 |
| Auth (OAuth2 + JWT) | 70~80% | Google provider 추가 |
| CRUD 레이어링 패턴 | 60~70% | 구조 동일, 도메인 교체 |
| 커뮤니티 (Post/Answer/Reputation) | 0% | 완전 신규 |

### 3.3 UX 원칙

| 원칙 | 설명 |
|------|------|
| Zero Context Switching | 성적 입력 등 Bottom Sheet 처리, 페이지 이동 없음 |
| Thumb-First Design | 주요 CTA 화면 하단 1/3 배치 (FAB, Action Bar) |
| Zero Dead-End | 모든 단계에서 다음 액션 CTA 명확 |
| AI-First Home | 홈 탭 최상단 AI 분석 CTA, 커뮤니티는 아래로 자연 합류 |

---

## 4. What — 제품 기능 및 데이터

### 4.1 현 구현 갭 분석 (코드·인프라 SSOT 기준)

> **SSOT**: `docs/SSOT/miriarts_infra.md` + 코드베이스. 판단은 코드 우선.

| 기능 | Legacy PRD 명세 | 현 구현 상태 (코드 기준) | 상태 |
|------|-----------------|--------------------------|------|
| 회원가입/로그인 (F1) | 이메일+비밀번호 → OAuth2 | OAuth2 로그인·토큰·리프레시·로그아웃 구현 (AuthController, OAuth2TokenExchangeService) | **구현 완료** |
| 온보딩 프로필 (F2) | — | PATCH /api/users/me/profile, GET /api/users/me (UserController) | **구현 완료** |
| AI 분석 (F3) | F3 Layer 1 | POST/GET /api/analyses, BE→FastAPI 프록시 (AnalysisController, AiProxyService) | FastAPI 연동·검증 수준은 인프라 SSOT §1.2 참고 |
| AI 채팅 (F4) | F5 Layer 3 | POST /api/chat, Redis 세션, BE→FastAPI (AiChatController, AiProxyService) | **구현 완료** |
| 분석 결과 조회 (F5) | Archive | GET /api/analyses, GET /api/analyses/{id} | **구현 완료** |
| 플랜/크레딧 (F6) | F6 | GET /api/users/me/plan (UserService.getPlanInfo, PlanType) | **구현 완료** |
| 구독 결제 (F7) | F7 | 플랜 조회만. 결제 연동 없음 | 결제 미구현 |
| 합격 확률 (Layer 2) | F4 Layer 2 | analyses·university_predictions 필드 존재. 전용 Theory API 없음 | **미구현** (필드만 존재) |
| 커뮤니티 (C1) | 신규 | GET /api/posts 구현 (PostController). POST /api/posts, /api/answers, comments CRUD 없음 | **C1 일부 구현**, 나머지 **미구현(향후)** |

### 4.2 핵심 엔티티 요약

> **코드 기준**: JPA 엔티티는 `miriart-be/.../entity/` 및 `docs/MiriArt_레포_전제_코드문서_정의_정리.md` [ERD/스키마]와 일치. Plan은 별도 테이블 없음 — `User.planType`(PlanType enum).

| 엔티티 | Phase | 설명 | 코드 위치 |
|--------|-------|------|-----------|
| `User` | P1 | 소셜 로그인 기반 계정 (planType: FREE/BASIC/PREMIUM) | user/entity/User.java |
| `Analysis` | P1 | 작품 분석 결과 (5축 + fixScope + 합격 확률) | analysis/entity/Analysis.java |
| `PlanType` | P1 | 구독 플랜 enum (User.planType). 별도 테이블 없음 | user/entity/PlanType.java |
| `AnalysisUsageLog` | P1 | 월별 분석 카운트 | analysis/entity/AnalysisUsageLog.java |
| `ChatSession` / `ChatMessage` | P2 | P1: Redis 키로 세션/히스토리. P2: MySQL 테이블 예정 | RedisService, (P2 엔티티 미존재) |
| `Post` | C1 | 커뮤니티 게시글 (free/qna) | community/entity/Post.java |
| `Answer` | C1 | Q&A 답변 | community/entity/Answer.java |
| `Comment` | C1 | 댓글 (parent_type/parent_id로 Post 또는 Answer 소속) | community/entity/Comment.java |
| `Like` | C1 | 좋아요 (target_type/target_id) | community/entity/Like.java |
| `Persona` | C1 | 가명 시스템 | community/entity/Persona.java |
| `ReputationLedger` | C1 | 평판 포인트 이력 | community/entity/ReputationLedger.java |

### 4.3 커뮤니티 기능 가치 제안

> 기준: `MIRIART_HOME_COMMUNITY_DESIGN_v1.md`

| 기능 | 벤치마크 | 가치 |
|------|---------|------|
| 타임라인 피드 (자유글 + Q&A) | 에브리타임 자유게시판 | 학년/도메인 필터 기반 또래 정보 공유 |
| Q&A 채택 시스템 | 네이버 지식인 | 검증된 답변 큐레이션 |
| 평판/레벨 시스템 (Lv.1~12) | Stack Overflow | 전문 멘토 우선 노출 유인 |
| AI 연결 포인트 | 독자 기능 | 커뮤니티 질문 → AI 초안 → 커뮤니티 게시 |
| 가명 시스템 | 에브리타임 | 익명성 보장 + 책임 최소 확보 |

---

## 5. When — Phase 로드맵

### 5.1 Phase 구분

| Phase | 기간 | 목표 | 핵심 산출물 |
|-------|------|------|-------------|
| **P1 MVP** | 2026 Q1~Q2 | Auth + AI 분석/채팅 + Archive | OAuth2 로그인, 분석 API, 채팅 API, Archive |
| **P2** | 2026 Q2~Q3 | MySQL Chat + 구독 결제 | chat_sessions, 플랜/구독 결제 연동 |
| **C1** | 2026 Q3 | 커뮤니티 피드 MVP | posts/answers/comments CRUD, 타임라인 |
| **C2** | 2026 Q3~Q4 | Q&A 채택 + 마감 | PostStatus 전이, 배치+fallback |
| **C3** | 2026 Q4 | 평판 시스템 | reputation_ledger, 레벨/뱃지 |
| **C4** | 2026 Q4~2027 Q1 | AI 연결 + 건전성 | FastAPI summarize, 신고 시스템, 가명 |
| **C5** | 2027 Q1+ | 실시간 알림 | WebSocket/SSE, FCM (선택적) |

### 5.2 P1 MVP 성공 지표

| 지표 | 목표 |
|------|------|
| AI 분석 완료율 | 첫 분석 완료 70% 이상 |
| DAU | 1,000명 |
| 분석 평균 소요 시간 | 8초 이내 |
| AI Chat 세션당 평균 메시지 수 | 5개 이상 |
| Crash-free rate | 99% 이상 |

### 5.3 재무 전망 (Legacy PRD 기준 유지)

| 지표 | Year 1 | Year 2 | Year 3 |
|------|--------|--------|--------|
| MAU | 3,000명 | 15,000명 | 50,000명 |
| ARPU (월) | 2.0만원 | 2.5만원 | 3.0만원 |
| ARR | 7.2억원 | 45억원 | 180억원 |
| Gross Margin | 65% | 70% | 75% |

---

## 6. 리스크 및 대응

| 리스크 | 설명 | 대응 |
|--------|------|------|
| Vision AI 정확도 한계 | 입시 도메인 등급이 실제 채점과 불일치 | 학원 MOU 데이터로 프롬프트 튜닝, 사용자 피드백 수렴 |
| 커뮤니티 저품질 | 스팸/부적절 게시글 | 신고 시스템, 가명 책임 설계, 자동 블라인드 |
| FastAPI 장애 | AI 서비스 다운 시 분석 불가 | Java BE Retry 3회, 타임아웃 시 사용자 안내 + 크레딧 환불 |
| OAuth SSO 장애 | 카카오/구글 장애 시 로그인 완전 막힘 | 운영자용 ROLE_ADMIN 백도어 (DB 수동 부여) |
| 타겟 시장 규모 | 기초디자인 수험생 유료 전환율 불확실 | MVP 단계 빠른 실증 (전환율/리텐션 측정) |

---

## 7. 문서 이력

| Version | Date | Changes |
|---------|------|---------|
| 1.0 (dysprime) | 2026-02-07 | Legacy PRD 초안 |
| 1.1 (dysprime) | 2026-02-07 | 시장 전략, 기대효과 추가 |
| 2.0 (MiriArt) | 2026-02-22 | 프로젝트명 변경, Java BE + FastAPI 스택 확정, 커뮤니티 비전 추가, OAuth2 only Auth 전환 |
| 2.1 (MiriArt) | 2026-03-02 | 참조 문서 경로 레거시(02_21dys_*) → 현행(MiriArt_*) 통일, §8 정합성 원칙·가이드 링크 추가 |
| 2.2 (MiriArt) | 2026-03-02 | §4.1 갭 표 코드·인프라 SSOT 기준 갱신(F1~F6·C1 일부 구현 완료 반영), §4.2 엔티티에 Comment·Like·PlanType 보강, SSOT= miriarts_infra+코드 우선 명시 |

---

## 8. 참조 문서

> **정합성 원칙**: PRD 수정 시 아래 문서와 Phase·기능·엔티티·API 경로가 일치하도록 유지. 경로는 **현행 문서명(MiriArt_*)** 기준. **기준선(변경 제안 금지)**: miriarts_infra.md, 실제 코드/설정.

| 문서명 | 버전 | 위치 |
|--------|------|------|
| MiriArt FSD v2.0 | 2.0 | `docs/MiriArt_FSD_v2.md` |
| MiriArt ERD v2.0 | 2.0 | `docs/MiriArt_ERD_v2.md` |
| MiriArt API Contract | 1.0 | `docs/MiriArt_API_CONTRACT.md` |
| MiriArt BE Setup Guide | 1.0 | `docs/MiriArt_BE_SETUP_GUIDE.md` |
| Community Design | 1.0 | `docs/MIRIART_HOME_COMMUNITY_DESIGN_v1.md` |
| Cariv→MiriArt 패턴 전략 | - | `docs/Cariv→MiriArt 패턴 재사용 전략.md` |
| VID v1.1 | 1.1 | `docs/VID_v1.0.md` |
| Legacy PRD | 1.1 | `docs/legacy/dysprime_PRD_v1.md` |
| PRD 업데이트·정합성 가이드 | - | `docs/PRD_업데이트_및_문서_정합성_가이드.md` |
