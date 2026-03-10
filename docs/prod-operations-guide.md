# MiriArt BE — Production 운영 가이드

> **SSOT(Single Source of Truth)**: Java 백엔드 코드가 스키마·정책·에러 코드의 기준이다.
> **작성일**: 2026-03-08
> **기준 브랜치**: `BE/community`

---

## A. Prod DB 스키마 가이드

### A-1. analyses.analysis_type

**현재 코드/SQL 상태**:

| 소스 | 설정 | 파일:라인 |
|------|------|----------|
| JPA 엔티티 | `@Column(name = "analysis_type", nullable = false, length = 50)` | `Analysis.java:48` |
| Dev init SQL | `analysis_type varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL` | `init-miriart-dev.sql:29` |
| Prod | `ddl-auto: validate` — Hibernate가 스키마를 변경하지 않음 | `application-prod.yml:26` |

**Prod 운영 기준 (SSOT)**:
- `analysis_type` 컬럼은 반드시 `varchar(50) NOT NULL` 이어야 한다.
- `varchar(10)` 상태에서 `basic_design`(12자) 등의 값이 들어오면 `DataTruncation` → 500 C003 에러 발생.

**배포 전 체크**:
```sql
-- 1. 현재 컬럼 타입 확인
DESCRIBE analyses;

-- 2. varchar(10)이면 반드시 변경
ALTER TABLE analyses MODIFY COLUMN analysis_type varchar(50) NOT NULL;

-- 3. 변경 확인
SHOW COLUMNS FROM analyses WHERE Field = 'analysis_type';
-- 기대 결과: Type = varchar(50)
```

### A-2. 전체 스키마 정합성 체크

Prod `ddl-auto: validate`는 앱 기동 시 엔티티와 DB 스키마를 대조한다.
불일치가 있으면 앱이 기동하지 않는다. 배포 전 아래 사항을 확인:

| 엔티티 필드 | Java 설정 | DB 컬럼 | 확인 포인트 |
|------------|----------|---------|------------|
| `Analysis.analysisType` | `varchar(50)` | `varchar(50)` | 길이 일치 |
| `Analysis.status` | `EnumType.STRING` | `ENUM('COMPLETED','FAILED','PENDING')` | 값 일치 |
| `Analysis.grade` | `EnumType.STRING, length=2` | `ENUM('A','B','C','D','F')` | 값 일치 |
| `Analysis.fixScope` | `EnumType.STRING, length=20` | `ENUM('DetailTuning','StructureRebuild')` | 값 일치 |

---

## B. FastAPI AI 서비스 의존 가이드

### B-1. 연결 구조

```
┌─────────────────┐     HTTP/JSON      ┌──────────────────┐
│  Java BE        │ ──────────────────▶ │  FastAPI AI      │
│  (Cloud Run)    │   POST /internal/   │  (Cloud Run)     │
│  port 8080      │   ai/analyze        │  port 8000       │
│                 │   ai/chat           │                  │
└─────────────────┘                     └──────────────────┘
```

**Java BE 설정**:

| 항목 | 설정 키 | 기본값 | 파일 |
|------|---------|-------|------|
| FastAPI URL | `miriart.fastapi.internal-url` | `http://localhost:8000` | `application.yml:31` |
| 환경변수 | `FASTAPI_INTERNAL_URL` | — | Cloud Run env |
| 연결 타임아웃 | 5초 | 하드코딩 | `WebClientConfig.java:30` |
| 응답 타임아웃 | 35초 | 하드코딩 | `WebClientConfig.java:31` |
| 최대 응답 크기 | 10MB | 하드코딩 | `WebClientConfig.java:45` |

**코드 근거** — `WebClientConfig.java:33-48`:
```java
@Value("${miriart.fastapi.internal-url:http://localhost:8000}")
private String fastapiInternalUrl;

@Bean
public WebClient fastapiWebClient() {
    HttpClient httpClient = HttpClient.create()
            .responseTimeout(Duration.ofSeconds(RESPONSE_TIMEOUT_SECONDS))   // 35s
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, CONNECT_TIMEOUT_MS); // 5s
    return WebClient.builder()
            .baseUrl(fastapiInternalUrl)
            ...
}
```

### B-2. 에러 매핑

| 상황 | 에러 코드 | HTTP Status | 코드 위치 |
|------|----------|-------------|----------|
| FastAPI 5xx 응답 | AN001 / AI001 | 502 | `AiProxyService.java:62-63` |
| FastAPI 응답 타임아웃 (>30s) | AN002 / AI002 | 504 | `AiProxyService.java:66-67` |
| FastAPI 연결 불가 (Connection refused) | AN001 / AI001 | 502 | `AiProxyService.java:69-72` |

**에러 처리 코드** — `AiProxyService.java:58-74` (analyze 기준):
```java
return fastapiWebClient.post()
    .uri("/internal/ai/analyze")
    .bodyValue(request)
    .retrieve()
    .onStatus(status -> status.is5xxServerError(),
            res -> Mono.error(new BusinessException(ErrorCode.AI_ANALYSIS_FAILED)))   // AN001
    .bodyToMono(InternalAnalyzeResponse.class)
    .timeout(Duration.ofSeconds(AI_TIMEOUT_SECONDS))                                  // 30s
    .onErrorMap(TimeoutException.class,
            e -> new BusinessException(ErrorCode.AI_ANALYSIS_TIMEOUT))                // AN002
    .onErrorMap(BusinessException.class, e -> e)
    .onErrorMap(e -> !(e instanceof BusinessException),
            e -> new BusinessException(ErrorCode.AI_ANALYSIS_FAILED))                 // AN001
    .block();
```

### B-3. Prod 운영 기준 (SSOT)

**정책**: Prod에서는 FastAPI가 항상 같이 떠 있는 구조를 전제한다.

**Prod 배포 전 체크리스트**:
```
[ ] FastAPI Cloud Run 배포 상태: Healthy
[ ] FASTAPI_INTERNAL_URL env 설정 확인 (BE Cloud Run → AI Cloud Run URL)
[ ] VPC/Egress 설정: BE → AI 내부 통신 허용
[ ] Smoke test:
    - POST /api/analyses (이미지 + analysisType) → 202 PENDING 또는 502 AN001
    - POST /api/chat (message) → 200 또는 502 AI001
```

**Dev 환경에서의 동작**:
- FastAPI 미기동 시 502 AN001/AI001이 나는 것이 **정상 동작**
- 별도 AI Mock 도입 여부는 차후 결정

---

## C. 커뮤니티 채택 락 (findByIdForUpdate)

### C-1. 정책

QnA 답변 채택(`acceptAnswer`)은 동시에 두 번 눌러도 **한 번만 성공**해야 한다.
`SELECT ... FOR UPDATE` (PESSIMISTIC_WRITE)로 Post 행을 잠근 뒤 채택 여부를 확인한다.

### C-2. 수정 내용

**수정 전** — `AnswerCommandService.java:82`:
```java
Post post = postRepository.findById(postId)
        .orElseThrow(() -> new BusinessException(ErrorCode.POST_NOT_FOUND));
```

**수정 후** — `AnswerCommandService.java:82`:
```java
Post post = postRepository.findByIdForUpdate(postId)
        .orElseThrow(() -> new BusinessException(ErrorCode.POST_NOT_FOUND));
```

**PostRepository.java:36-38** (기존 정의, 변경 없음):
```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@Query("select p from Post p where p.id = :id")
Optional<Post> findByIdForUpdate(@Param("id") Long id);
```

### C-3. 레이스 컨디션 방지 효과

```
Thread A: BEGIN → SELECT ... FOR UPDATE (Post#1 락 획득) → acceptedAnswerId=null → accept() → COMMIT → 락 해제
Thread B: BEGIN → SELECT ... FOR UPDATE (Post#1 락 대기) ──── 락 획득 → acceptedAnswerId≠null → ANSWER_ALREADY_ACCEPTED
```

- `findById` (락 없음): 두 스레드가 동시에 `acceptedAnswerId=null`을 읽고 둘 다 채택 시도 → **이중 채택 가능**
- `findByIdForUpdate` (행 락): 한 스레드가 락을 잡고 있는 동안 다른 스레드는 대기 → **이중 채택 불가**

### C-4. 테스트 검증

**기존 테스트** — `CommunityCommandServiceConcurrencyTest.java:116-162`:
```java
@Test
@DisplayName("동시에 두 스레드가 같은 답변 채택 시도 시 하나만 성공")
void acceptAnswer_concurrent_onlyOneSucceeds() {
    // CountDownLatch로 두 스레드 동시 실행
    // 성공 1건, 실패 1건 (ANSWER_ALREADY_ACCEPTED) 검증
    // post.getAcceptedAnswerId() == answerId 확인
}
```

**결과**: `findByIdForUpdate` 적용 후 **22/22 테스트 PASS** (동시성 테스트 포함)

---

## D. Community C1 배포 가이드

### D-1. Prod DB 마이그레이션 (기동 전 필수)

`ddl-auto: validate`이므로 아래 DDL을 배포 전에 실행해야 한다. 미실행 시 `SchemaManagementException`으로 기동 실패.

**마이그레이션 스크립트**: `scripts/migrate-prod-c1.sql`

```sql
-- 1. analysis_type 50자 확장 (이전 이슈, 미적용 시 DataTruncation 가능)
ALTER TABLE analyses MODIFY COLUMN analysis_type varchar(50) NOT NULL;

-- 2. posts.comment_count 추가 (C1 신규 컬럼, 미적용 시 기동 실패)
ALTER TABLE posts ADD COLUMN comment_count int NOT NULL DEFAULT 0 AFTER answer_count;

-- 3. 성능 인덱스 (기동에는 무관, 피드 성능에 필요)
CREATE INDEX idx_type_status ON posts (type, status);
CREATE INDEX idx_scope_created ON posts (grade_scope, domain_scope, created_at);
CREATE INDEX idx_popularity ON posts (like_count, answer_count, created_at);
```

### D-2. 카카오 OAuth 상태

- `application-prod.yml`에 카카오 등록 블록 없음 (Google만 등록).
- `cloudrun-redeploy.ps1:30`에서 `KAKAO_CLIENT_ID`, `KAKAO_CLIENT_SECRET`을 `--set-secrets`로 전달.
- Secret Manager에 해당 secret이 없으면 `--set-secrets` 실패 → **배포 자체가 막힘**.
- 현재 상태: Secret Manager에 placeholder 등록 필요 (또는 배포 스크립트에서 카카오 관련 제거).
- SSOT TODO-001과 일치: 카카오 Secret 미등록/미연동 상태.

### D-3. C1에서 추가/변경된 BE 코드 요약

| 파일 | 변경 | 배포 영향 |
|------|------|----------|
| `SecurityConfig.java:95` | CORS `localhost:3000` 추가 | prod 무관 (localhost) |
| `PostFeedResponse.java:19` | `@JsonInclude(NON_NULL)` | null 필드 생략 — FE 정합 |
| `PostDetailResponse.java:18` | `@JsonInclude(NON_NULL)` | 동일 |
| `AnswerResponse.java:27-28` | `@JsonProperty("isAccepted")` + 필드명 `accepted` | JSON key `isAccepted` 보장 |
| `PostRepository.java:46` | `flushAutomatically = true` 추가 | 좋아요 토글 likeCount 음수 버그 수정 |
| `AnswerRepository.java:28` | `flushAutomatically = true` 추가 | 동일 |
| 신규 14개 파일 | Controller 3, Service 3, DTO 8 | 커뮤니티 6개 API |

### D-4. 배포 체크리스트

```
[ ] Prod DB: migrate-prod-c1.sql 실행 (analysis_type 50자 + comment_count + 인덱스)
[ ] Secret Manager: 카카오 secret placeholder 존재 확인 (없으면 등록 또는 스크립트에서 제거)
[ ] 로컬 테스트: ./gradlew test 27/27 PASS
[ ] Docker 빌드: gcloud builds submit --tag ... (또는 로컬 docker build)
[ ] Cloud Run 배포: cloudrun-redeploy.ps1 또는 bash 등가 명령
[ ] 기동 확인: GET /actuator/health → 200
[ ] 스모크: GET /api/posts → 200 + posts 배열
[ ] 스모크: POST /api/likes/toggle (인증) → 200 + liked/likeCount
```

---

## E. 변경 파일 요약

| 파일 | 변경 | 비고 |
|------|------|------|
| `Analysis.java:48` | `length=10` → `length=50` | 이전 세션에서 수정 완료 |
| `init-miriart-dev.sql:29` | `varchar(10)` → `varchar(50)` | 이전 세션에서 수정 완료 |
| `AnalysisService.java` | `@Transactional` 제거, 3단계 오케스트레이션 | 이전 세션에서 수정 완료 |
| `AnalysisFailHandler.java` (신규) | 트랜잭션 헬퍼 (savePending/complete/markFailed) | 이전 세션에서 생성 |
| `AnswerCommandService.java:82` | `findById` → `findByIdForUpdate` | 이번 세션에서 수정 |
| `PostRepository.java:32-34` | 주석 업데이트 ("사용 중") | 이번 세션에서 수정 |
| `logback-spring.xml` (신규) | dev 파일 로그 + prod JSON stdout | 이전 세션에서 생성 |
| `.gitignore` | `logs/` 추가 | 이전 세션에서 수정 |
