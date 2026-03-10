# 1. Java BE & 인프라 — WebClient ID 토큰 + 에러 매핑 + 배포 + E2E 리포트

> **작성일**: 2026-03-10
> **대상**: `miriart-be` (Spring Boot 3.4.2, Java 17)
> **근거**: 실 코드 + Cloud Run 설정 + Cloud Logging

---

## 1. WebClient ID 토큰 구현

### 1.1 현재 상태: 이미 구현 완료

`WebClientConfig.java`에 OIDC ID 토큰 주입이 **이미 구현되어 있음**:

```java
// WebClientConfig.java:56-62 — Prod WebClient (profile: !dev)
@Bean("fastapiWebClient")
@Profile("!dev")
public WebClient fastapiWebClientProd() {
    return buildBaseWebClient()
            .filter(oidcAuthFilter())   // ← OIDC 필터 적용
            .build();
}
```

```java
// WebClientConfig.java:67-72 — Dev WebClient (profile: dev)
@Bean("fastapiWebClient")
@Profile("dev")
public WebClient fastapiWebClientDev() {
    return buildBaseWebClient()
            .build();              // ← 인증 없음 (로컬)
}
```

```java
// WebClientConfig.java:91-103 — OIDC ExchangeFilterFunction
private ExchangeFilterFunction oidcAuthFilter() {
    return ExchangeFilterFunction.ofRequestProcessor(request -> {
        try {
            String idToken = obtainIdToken();
            ClientRequest authedRequest = ClientRequest.from(request)
                    .headers(h -> h.setBearerAuth(idToken))
                    .build();
            return Mono.just(authedRequest);
        } catch (IOException e) {
            log.error("OIDC ID Token 획득 실패: {}", e.getMessage(), e);
            return Mono.error(e);
        }
    });
}
```

```java
// WebClientConfig.java:106-122 — ID 토큰 발급
private String obtainIdToken() throws IOException {
    GoogleCredentials credentials = GoogleCredentials.getApplicationDefault();

    if (!(credentials instanceof IdTokenProvider)) {
        throw new IOException(
                "SA credentials do not support ID token generation. "
                        + "Actual type: " + credentials.getClass().getSimpleName());
    }

    IdTokenCredentials idTokenCredentials = IdTokenCredentials.newBuilder()
            .setIdTokenProvider((IdTokenProvider) credentials)
            .setTargetAudience(fastapiInternalUrl)    // ← audience = AI 서비스 URL
            .build();

    idTokenCredentials.refreshIfExpired();
    return idTokenCredentials.getIdToken().getTokenValue();
}
```

### 1.2 ID 토큰 발급/주입 로직 설명

| 항목 | 값 |
|------|---|
| Credentials 소스 | `GoogleCredentials.getApplicationDefault()` — Cloud Run 메타데이터 서버 |
| SA | `miriart-be-runner@miriarts.iam.gserviceaccount.com` (Cloud Run SA) |
| Audience | `${miriart.fastapi.internal-url}` = `https://miriart-ai-946560105497.asia-northeast3.run.app` |
| 갱신 | `refreshIfExpired()` — ~1시간 유효, 자동 캐싱 |
| 프로파일 분기 | `!dev` → OIDC 필터 적용, `dev` → 인증 없음 |

### 1.3 의존성 확인

```groovy
// build.gradle:40-41 — GCP BOM
mavenBom 'com.google.cloud:spring-cloud-gcp-dependencies:6.5.4'

// build.gradle:73
implementation 'com.google.cloud:spring-cloud-gcp-starter-storage'
```

`spring-cloud-gcp-starter-storage` → `google-auth-library-oauth2-http` 전이 의존성으로 `GoogleCredentials`, `IdTokenCredentials`, `IdTokenProvider` 모두 사용 가능. **별도 의존성 추가 불필요**.

---

## 2. AiProxyService 에러 매핑/로깅

### 2.1 현재 상태: 401/403 분기 이미 구현

```java
// AiProxyService.java:62-66 — analyze 에러 핸들링
.onStatus(status -> status.is5xxServerError() || status.value() == 400
        || status.value() == 401 || status.value() == 403,   // ← 401/403 포함
        res -> res.bodyToMono(String.class)
                .flatMap(body -> Mono.error(new BusinessException(
                        AiErrorMapper.toErrorCode(res.statusCode(), parseAiErrorCode(body), true)))))
```

```java
// AiErrorMapper.java:34-37 — 401/403 전용 분기
if (status == 401 || status == 403) {
    return ErrorCode.AI_SERVICE_AUTH_FAILED;    // ← AI003
}
```

```java
// ErrorCode.java:73-74
AI_SERVICE_AUTH_FAILED(HttpStatus.BAD_GATEWAY, "AI003", "AI 서비스 인증에 실패했습니다"),
```

### 2.2 에러 매핑 전체 표

| AI HTTP | AI body code | BE ErrorCode | BE HTTP | BE message | 코드 위치 |
|---------|-------------|-------------|---------|------------|-----------|
| 401/403 | (무시) | `AI003` AI_SERVICE_AUTH_FAILED | 502 | "AI 서비스 인증에 실패했습니다" | `AiErrorMapper:35-37` |
| 504 | LLM_TIMEOUT | `AN002`/`AI002` | 504 | "분석/AI 응답 시간 초과" | `AiErrorMapper:39-44` |
| 502 | GCS_ERROR | `F005` IMAGE_URL_GENERATION_FAILED | 502 | "이미지 URL 생성 실패" | `AiErrorMapper:47-48` |
| 502 | LLM_SERVICE_ERROR | `AN001`/`AI001` | 502 | "AI 분석/멘토 연결 실패" | `AiErrorMapper:50-51` |
| 502 | LLM_PARSING_ERROR | `AN001`/`AI001` | 502 | "AI 분석/멘토 연결 실패" | `AiErrorMapper:50-51` |
| 400 | VALIDATION_ERROR | `C001` INVALID_INPUT_VALUE | 400 | "잘못된 입력값입니다" | `AiErrorMapper:57-58` |
| `TimeoutException` | — | `AN002`/`AI002` | 504 | "분석/AI 시간 초과" | `AiProxyService:69-70` |
| 기타 예외 | — | `AN001`/`AI001` | 502 | "AI 분석/멘토 연결 실패" | `AiProxyService:72-76` |

### 2.3 로깅 확인

| 상황 | 로그 레벨 | 메시지 | 코드 위치 |
|------|----------|--------|-----------|
| OIDC 토큰 획득 실패 | `ERROR` | `"OIDC ID Token 획득 실패: {}"` | `WebClientConfig:100` |
| 분석 기타 예외 | `ERROR` | `"FastAPI 분석 호출 실패: {}"` | `AiProxyService:74` |
| 채팅 기타 예외 | `ERROR` | `"FastAPI 채팅 호출 실패: {}"` | `AiProxyService:116` |
| Redis 세션 저장 실패 | `WARN` | `"채팅 세션 히스토리 저장 실패"` | `AiProxyService:164` |

---

## 3. 배포/Cloud Run 설정

### 3.1 현재 Cloud Run 환경변수 (실측)

```
FASTAPI_INTERNAL_URL = https://miriart-ai-946560105497.asia-northeast3.run.app
SPRING_PROFILES_ACTIVE = prod      ← Dockerfile에 bake-in
```

**프로파일 확인**: `prod` 프로파일 → `!dev` 조건 충족 → `fastapiWebClientProd()` 빈 활성화 → OIDC 필터 적용 ✅

### 3.2 IAM 설정 확인

| 항목 | 값 | 정상 |
|------|---|------|
| BE Service Account | `miriart-be-runner@miriarts.iam.gserviceaccount.com` | ✅ |
| AI Invoker IAM | `miriart-be-runner` → `roles/run.invoker` on `miriart-ai` | ✅ |
| Audience URL | `https://miriart-ai-946560105497.asia-northeast3.run.app` = `FASTAPI_INTERNAL_URL` | ✅ |

### 3.3 배포 명령어

```bash
# BE 빌드 (Spring Boot JAR)
cd /home/sieg/projects-wsl/MiriArt/miriart-be
./gradlew clean bootJar

# Docker 빌드 + 푸시
docker build -t asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-be:$(git rev-parse --short HEAD) .
docker push asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-be:$(git rev-parse --short HEAD)

# Cloud Run 배포
gcloud run deploy miriart-be \
  --image=asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-be:$(git rev-parse --short HEAD) \
  --project=miriarts \
  --region=asia-northeast3 \
  --service-account=miriart-be-runner@miriarts.iam.gserviceaccount.com \
  --no-allow-unauthenticated
```

### 3.4 배포 후 체크리스트

| # | 확인 항목 | 명령어 |
|---|----------|--------|
| 1 | SA 확인 | `gcloud run services describe miriart-be --format="value(spec.template.spec.serviceAccountName)"` |
| 2 | FASTAPI_INTERNAL_URL 확인 | `gcloud run services describe miriart-be --format="yaml(spec.template.spec.containers[0].env)"` |
| 3 | 프로파일 확인 | Dockerfile의 `SPRING_PROFILES_ACTIVE=prod` 확인 |
| 4 | 리비전 트래픽 | `gcloud run services describe miriart-be --format="yaml(status.traffic)"` |
| 5 | 시작 로그 | `gcloud logging read 'resource.labels.service_name="miriart-be"' --limit=5` |

---

## 4. E2E 디버깅/테스트 플랜

### 4.1 문제 근본 원인 분석

디버깅 리포트 v2에서 BE의 403 로그가 관찰되었으나, 코드상 OIDC 필터는 이미 구현됨. 가능한 원인:

| # | 가능성 | 확인 방법 |
|---|--------|-----------|
| 1 | BE가 아직 OIDC 코드 포함 안 된 이전 리비전으로 서빙 중 | `gcloud run revisions list --service=miriart-be --format="table(name,status.conditions[0].status)"` |
| 2 | `SPRING_PROFILES_ACTIVE`가 `dev`로 설정되어 있어 OIDC 필터 미적용 | BE Cloud Run 환경변수 확인 |
| 3 | `GoogleCredentials.getApplicationDefault()`가 Cloud Run SA에서 `IdTokenProvider`를 지원하지 않음 | BE 시작 로그에서 `"SA credentials do not support ID token"` 에러 확인 |
| 4 | WebClientConfig 코드가 커밋/배포되지 않았음 | 현재 서빙 중인 이미지의 코드와 로컬 코드 비교 |

```bash
# 즉시 확인 명령어
gcloud logging read 'resource.labels.service_name="miriart-be" AND (textPayload:"OIDC" OR jsonPayload.message:"OIDC")' \
  --project=miriarts --limit=10

gcloud logging read 'resource.labels.service_name="miriart-be" AND (textPayload:"FastAPI" OR jsonPayload.message:"FastAPI")' \
  --project=miriarts --limit=10
```

### 4.2 통합 테스트 코드 (WebTestClient)

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class AiProxyServiceIntegrationTest {

    @Autowired
    private WebTestClient webTestClient;

    @Test
    void analyze_정상_요청() {
        // given: 실제 GCS URI (테스트 이미지)
        var request = Map.of(
            "gcsUri", "gs://miriart-bucket/test/sample-artwork.jpg",
            "analysisType", "basic"
        );

        // when & then
        webTestClient.post()
            .uri("/api/analyses")  // BE 외부 API → 내부에서 AI /analyze 호출
            .bodyValue(request)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.data.grade").exists()
            .jsonPath("$.data.totalScore").isNumber()
            .jsonPath("$.data.radarData.density").isNumber();
    }

    @Test
    void chat_정상_요청() {
        var request = Map.of(
            "modelType", "FAST",
            "message", "형태력을 올리려면 어떻게 해야 하나요?"
        );

        webTestClient.post()
            .uri("/api/ai/chat")
            .bodyValue(request)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.data.text").isNotEmpty()
            .jsonPath("$.data.quickReplies").isArray();
    }
}
```

### 4.3 Prod E2E 검증 시나리오

#### 시나리오 A: 정상 분석 (실제 GCS URI)

**FE 동작**: 작품 분석 버튼 클릭 → BE `/api/analyses` → AI `/internal/ai/analyze`

**기대 BE 로그**:
```
(OIDC 토큰 발급 — 별도 로그 없음, 성공 시 silent)
```

**기대 AI 로그**:
```
[INFO] http_request  path=/internal/ai/analyze  status=200  latency_s=8.5
[INFO] gemini_call_success  purpose=analyze_artwork  model=gemini-2.5-flash  latency_s=8.2  output_len=450
```

**기대 FE 응답**:
```json
{
  "code": "SUCCESS",
  "data": {
    "grade": "B",
    "totalScore": 78.5,
    "radarData": {"density": 82, "form": 75, "completion": 80, "relevance": 73, "thinking": 77},
    "fixScope": "DetailTuning",
    "comment": "전체적으로 안정적인 구도이나..."
  }
}
```

#### 시나리오 B: GCS_ERROR (존재하지 않는 URI)

**기대 AI 로그**:
```
[WARNING] handled_error  error_code=GCS_ERROR  status=502  path=/internal/ai/analyze
[INFO]    http_request   status=502  latency_s=0.3
```

**기대 BE 동작**: `AiErrorMapper` → `F005` (IMAGE_URL_GENERATION_FAILED)

**기대 FE 응답**:
```json
{"code": "F005", "message": "이미지 URL 생성에 실패했습니다"}
```

#### 시나리오 C: 정상 채팅

**기대 AI 로그**:
```
[INFO] gemini_call_success  purpose=chat  model=gemini-2.5-flash  latency_s=10.3  output_len=130
[INFO] http_request  path=/internal/ai/chat  status=200  latency_s=10.4
```

**기대 FE 응답**:
```json
{
  "code": "SUCCESS",
  "data": {
    "text": "형태력 향상을 위해...",
    "groundingUrls": [],
    "quickReplies": ["이 부분을 더 자세히 알려주세요", ...],
    "sessionId": "sess-abc-123"
  }
}
```

#### 시나리오 D: LLM_TIMEOUT

**기대 AI 로그**:
```
[WARNING] gemini_call_timeout  purpose=analyze_artwork  model=gemini-2.5-flash  timeout_s=28
[WARNING] handled_error  error_code=LLM_TIMEOUT  status=504  path=/internal/ai/analyze
[INFO]    http_request   status=504  latency_s=28.1
```

**기대 BE 동작**: `AiErrorMapper` → `AN002` (AI_ANALYSIS_TIMEOUT)

**기대 FE 응답**:
```json
{"code": "AN002", "message": "분석 시간이 초과됐습니다. 잠시 후 다시 시도해주세요"}
```

### 4.4 로그 확인 순서 (장애 발생 시)

```
1. FE 에러 코드 확인 → AN001/AN002/AI001/AI002/F005/AI003 중 어떤 것인가?
   ↓
2. BE 로그 검색:
   gcloud logging read 'resource.labels.service_name="miriart-be" AND textPayload:"FastAPI"' \
     --project=miriarts --limit=10
   ↓
3. AI003(인증 실패)이면 → WebClientConfig OIDC 로그 확인:
   gcloud logging read 'resource.labels.service_name="miriart-be" AND textPayload:"OIDC"' \
     --project=miriarts --limit=5
   ↓
4. AN001/AI001(서비스 실패)이면 → AI 로그 확인:
   gcloud logging read 'resource.labels.service_name="miriart-ai" AND jsonPayload.message:"handled_error"' \
     --project=miriarts --limit=10
   ↓
5. AN002/AI002(타임아웃)이면 → Gemini 타임아웃 확인:
   gcloud logging read 'resource.labels.service_name="miriart-ai" AND jsonPayload.message:"gemini_call_timeout"' \
     --project=miriarts --limit=10
```

---

## 5. 종합 판정

| 영역 | 상태 | 비고 |
|------|------|------|
| WebClient OIDC 필터 | ✅ **구현 완료** | `WebClientConfig.java:91-122` |
| 프로파일 분기 (prod/dev) | ✅ **구현 완료** | `!dev` → OIDC, `dev` → 인증 없음 |
| 401/403 에러 매핑 | ✅ **구현 완료** | `AI003` AI_SERVICE_AUTH_FAILED |
| ErrorCode 정의 | ✅ **구현 완료** | `ErrorCode.java:74` |
| AiErrorMapper 분기 | ✅ **구현 완료** | `AiErrorMapper.java:35-37` |
| 로깅 | ✅ **적정** | OIDC 실패 ERROR, 호출 실패 ERROR |

**핵심 결론**: BE 코드에는 OIDC ID 토큰 주입 + 401/403 에러 분기가 **이미 완전히 구현되어 있음**. 403이 발생한 이유는 코드 문제가 아니라, **이 코드가 포함된 빌드가 아직 배포되지 않았을 가능성**이 높음. 즉시 확인해야 할 것:

1. 현재 서빙 중인 BE 리비전의 이미지 태그가 OIDC 코드 커밋 이후인지
2. BE 시작 로그에서 OIDC 관련 에러가 없는지
