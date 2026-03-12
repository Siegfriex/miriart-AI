# miriart-be 대상 클래스 코드 요약

**작성일**: 2026-03-12  
**대상 프로젝트**: miriart-be  
**경로**: `/home/sieg/projects-wsl/MiriArt/miriart-be`

**대상 클래스**: AiProxyService, RedisService, UserService, AnalysisService, UserController, AiChatController

---

## 1. 클래스별 전체 요약

### 1.1 AiProxyService

**파일**: `src/main/java/com/miriart/api/domain/ai/service/AiProxyService.java`

| 항목 | 내용 |
|------|------|
| **역할** | FastAPI AI 서비스와의 내부 통신 프록시. `/internal/ai/analyze`, `/internal/ai/chat` 호출, 채팅 세션 히스토리 Redis 저장. |
| **의존성** | WebClient(fastapiWebClient), RedisService, ObjectMapper |

**메서드 시그니처**

| 메서드 | 시그니처 | 설명 |
|--------|----------|------|
| analyze | `InternalAnalyzeResponse analyze(String gcsUrl, String analysisType, String problemText)` | 작품 분석 요청 → FastAPI POST /internal/ai/analyze |
| chat | `ChatResponse chat(ChatRequest chatRequest)` | AI 채팅 요청 → FastAPI POST /internal/ai/chat, 이후 Redis 세션 업데이트 |
| updateSessionHistory | `private void updateSessionHistory(String sessionId, ChatRequest request, InternalChatResponse response)` | Redis에 전체 메시지 이력 JSON 저장 (Bug #4 Fix) |
| parseAiErrorCode | `private String parseAiErrorCode(String bodyStr)` | AI 에러 body에서 code 필드 추출 |

**주요 분기**

- **chat()**
  - `sessionId`: `chatRequest.getSessionKey() != null` → sessionKey 사용, else → `UUID.randomUUID().toString()`
  - FastAPI 응답 5xx/400/401/403/429 → `AiErrorMapper.toErrorCode(..., false)` → BusinessException
  - `TimeoutException` → `ErrorCode.AI_CHAT_TIMEOUT`
  - 기타 예외 → `ErrorCode.AI_CHAT_FAILED`
  - `response != null`일 때만 `updateSessionHistory()` 호출
- **analyze()**
  - 동일한 onStatus/타임아웃/에러 매핑, `forAnalyze=true` → AN001/AN002 등

**사용 ErrorCode** (AiErrorMapper 경유 포함): `AI_ANALYSIS_TIMEOUT`, `AI_ANALYSIS_FAILED`, `AI_CHAT_TIMEOUT`, `AI_CHAT_FAILED`, 및 AiErrorMapper에서 매핑되는 `AI_SERVICE_AUTH_FAILED`, `AI_CHAT_RATE_LIMITED`, `AI_ANALYSIS_RATE_LIMITED`, `IMAGE_URL_GENERATION_FAILED`, `INVALID_INPUT_VALUE` 등.

---

### 1.2 RedisService

**파일**: `src/main/java/com/miriart/api/global/redis/RedisService.java`

| 항목 | 내용 |
|------|------|
| **역할** | Redis 키-값 서비스. OAuth2 코드/리프레시 토큰, **AI 채팅 세션** 등 도메인별 key prefix 메서드 제공. |
| **의존성** | StringRedisTemplate |

**메서드 시그니처**

| 메서드 | 시그니처 | 설명 |
|--------|----------|------|
| set | `void set(String key, String value, long timeoutSeconds)` | 범용 키 저장 + TTL(초) |
| get | `String get(String key)` | 범용 조회 |
| delete | `void delete(String key)` | 범용 삭제 |
| saveOAuth2Code | `void saveOAuth2Code(String code, String payload)` | OAuth2 코드 저장, TTL 60초 |
| getAndDeleteOAuth2Code | `String getAndDeleteOAuth2Code(String code)` | 코드 조회 후 삭제 |
| saveRefreshToken | `void saveRefreshToken(Long userId, String token)` | 리프레시 토큰 저장, TTL 7일 |
| getRefreshToken | `String getRefreshToken(Long userId)` | 리프레시 토큰 조회 |
| deleteRefreshToken | `void deleteRefreshToken(Long userId)` | 리프레시 토큰 삭제 |
| **saveChatSession** | `void saveChatSession(String sessionId, String data)` | 채팅 세션 저장, **TTL 72시간** |
| **getChatSession** | `String getChatSession(String sessionId)` | 채팅 세션 조회 |
| **updateChatSession** | `void updateChatSession(String sessionId, String data)` | 채팅 세션 갱신, **TTL 72시간 리셋** |

**주요 분기**  
- 없음. 모두 단순 키 연산.

**사용 ErrorCode**  
- 없음 (예외 시 상위에서 처리).

---

### 1.3 UserService

**파일**: `src/main/java/com/miriart/api/domain/user/service/UserService.java`

| 항목 | 내용 |
|------|------|
| **역할** | 사용자 프로필·플랜 조회/수정. UserRepository 조회, 프로필 수정 시 닉네임 중복 검사, 플랜 정보는 monthlyLimit과 외부 전달 usedThisMonth로 remaining 계산. |
| **의존성** | UserRepository |

**메서드 시그니처**

| 메서드 | 시그니처 | 설명 |
|--------|----------|------|
| getProfile | `UserProfileResponse getProfile(Long userId)` | 프로필 조회 |
| updateProfile | `UserProfileResponse updateProfile(Long userId, UserProfileUpdateRequest request)` | 온보딩 프로필 완성, 닉네임 중복 시 예외 |
| getPlanInfo | `UserPlanResponse getPlanInfo(Long userId, long usedThisMonth)` | 플랜·크레딧 정보 (remaining = monthlyLimit - usedThisMonth) |

**주요 분기**

- **updateProfile**
  - 닉네임 변경 시 `userRepository.existsByNickname(request.getNickname())` → true면 `ErrorCode.DUPLICATE_NICKNAME` throw.
- **getPlanInfo**
  - `remaining = Math.max(0, monthlyLimit - usedThisMonth)`, `billingPeriodStart = LocalDate.now().withDayOfMonth(1)`.

**사용 ErrorCode**: `DUPLICATE_NICKNAME`, 및 `userRepository.findByIdOrThrow` 내부에서 사용하는 회원 없음 관련 코드(리포지토리 구현에 따름).

---

### 1.4 AnalysisService

**파일**: `src/main/java/com/miriart/api/domain/analysis/service/AnalysisService.java`

| 항목 | 내용 |
|------|------|
| **역할** | 작품 분석 오케스트레이션. 파일 검증 → GCS 업로드 → 크레딧 체크 + PENDING 저장 → FastAPI 분석 → COMPLETED/usage log 또는 FAILED. |
| **의존성** | AnalysisRepository, AnalysisUsageLogRepository, FileStorageService, AiProxyService, AnalysisFailHandler, ObjectMapper |

**메서드 시그니처**

| 메서드 | 시그니처 | 설명 |
|--------|----------|------|
| startAnalysis | `AnalysisStartResponse startAnalysis(Long userId, MultipartFile image, String analysisType, String problemText)` | 업로드 + 분석 시작 (크레딧 체크는 AnalysisFailHandler.savePending 내부) |
| getAnalysis | `AnalysisDetailResponse getAnalysis(Long userId, Long analysisId)` | 분석 결과 단건 조회 (본인만) |
| getMyAnalyses | `Page<AnalysisDetailResponse> getMyAnalyses(Long userId, Pageable pageable)` | 내 분석 목록 |
| getUsedThisMonth | `long getUsedThisMonth(Long userId)` | 현재 월 사용량 (UserController 플랜 API에서 사용) |

**주요 분기**

- **startAnalysis**
  - `image == null || image.isEmpty()` → `ErrorCode.FILE_EMPTY`
  - `contentType` null 또는 ALLOWED_MIME_TYPES 미포함 → `ErrorCode.INVALID_FILE_TYPE`
  - 그 다음: 업로드 → `analysisFailHandler.savePending()` (여기서 **크레딧 체크**) → AI 호출 → 성공 시 `analysisFailHandler.complete()`, 실패 시 `analysisFailHandler.markFailed()` 후 BusinessException 또는 `ErrorCode.AI_ANALYSIS_FAILED` rethrow.
- **getAnalysis**
  - `findByIdAndUserId` 없음 → `ErrorCode.ANALYSIS_NOT_FOUND`

**사용 ErrorCode**: `FILE_EMPTY`, `INVALID_FILE_TYPE`, `ANALYSIS_NOT_FOUND`, `AI_ANALYSIS_FAILED` (그 외 AnalysisFailHandler에서 `CREDIT_LIMIT_EXCEEDED`).

---

### 1.5 UserController

**파일**: `src/main/java/com/miriart/api/domain/user/controller/UserController.java`

| 항목 | 내용 |
|------|------|
| **역할** | 사용자 API. 내 프로필 조회/수정, 플랜·크레딧 조회. |
| **의존성** | UserService, AnalysisService |

**메서드 시그니처**

| 메서드 | 시그니처 | 설명 |
|--------|----------|------|
| getMyProfile | `ResponseEntity<ApiResponse<UserProfileResponse>> getMyProfile(@AuthenticationPrincipal Long userId)` | GET /api/users/me |
| updateProfile | `ResponseEntity<ApiResponse<UserProfileResponse>> updateProfile(Long userId, @RequestBody @Valid UserProfileUpdateRequest request)` | PATCH /api/users/me/profile |
| getPlan | `ResponseEntity<ApiResponse<UserPlanResponse>> getPlan(@AuthenticationPrincipal Long userId)` | GET /api/users/me/plan (usedThisMonth는 AnalysisService에서 조회) |

**주요 분기**  
- 없음. 모두 서비스 호출 후 `ApiResponse.success()` 반환.

**사용 ErrorCode**  
- 서비스/검증 예외에 의해 간접 사용 (DUPLICATE_NICKNAME 등).

---

### 1.6 AiChatController

**파일**: `src/main/java/com/miriart/api/domain/ai/controller/AiChatController.java`

| 항목 | 내용 |
|------|------|
| **역할** | AI 채팅 API. POST /api/chat — sessionKey 정규화 후 ChatSessionService.chat() 호출. |
| **의존성** | ChatSessionKeyResolver, ChatSessionService |

**메서드 시그니처**

| 메서드 | 시그니처 | 설명 |
|--------|----------|------|
| chat | `ResponseEntity<ApiResponse<ChatResponse>> chat(@AuthenticationPrincipal Long userId, @RequestBody @Valid ChatRequest request)` | POST /api/chat |

**주요 분기**

- `ChatSessionKeyResolver.resolve(userId, request.getSessionKey())` → `resolved.sessionKey()`로 request에 set.
- `chatSessionService.chat(userId, request, resolved.chatSession())` 호출.

**사용 ErrorCode**  
- ChatSessionService/ChatSessionKeyResolver 경유: `ANALYSIS_NOT_FOUND`, `CHAT_SESSION_NOT_FOUND`, AI 관련 ErrorCode(AiProxyService 경유).

---

## 2. 상세 1: Chat 세션 히스토리 Redis 저장/조회

### 2.1 키 패턴

- **접두어**: `PREFIX = "miriart:"`  
  (`RedisService.java` 27행)
- **채팅 세션 키**: `miriart:chat:session:{sessionId}`  
  - `sessionId`는 `AiProxyService.chat()`에서 결정: `chatRequest.getSessionKey()`가 있으면 그 값, 없으면 `UUID.randomUUID().toString()`.

```74:77: MiriArt/miriart-be/src/main/java/com/miriart/api/global/redis/RedisService.java
    // AI Chat 세션 (TTL 72시간)
    public void saveChatSession(String sessionId, String data) {
        redisTemplate.opsForValue().set(
                PREFIX + "chat:session:" + sessionId, data, 72, TimeUnit.HOURS);
```

### 2.2 Value JSON 구조

- **형식**: 배열 JSON. 각 요소는 `Map<String, String>` (role, text).
- **역할**: `"user"` | `"model"`.
- **저장 로직** (`AiProxyService.updateSessionHistory`, 144–173행):
  1. `redisService.getChatSession(sessionId)`로 기존 JSON 조회.
  2. 없으면 빈 리스트, 있으면 `objectMapper.readValue(existing, List<Map.class>)`로 파싱.
  3. `{"role":"user","text": request.getMessage()}` 추가.
  4. `{"role":"model","text": response.getText()}` 추가.
  5. `redisService.updateChatSession(sessionId, objectMapper.writeValueAsString(history))`로 저장.

예시:

```json
[
  {"role":"user","text":"첫 질문"},
  {"role":"model","text":"첫 답변"},
  {"role":"user","text":"두 번째 질문"},
  {"role":"model","text":"두 번째 답변"}
]
```

### 2.3 TTL 설정 위치

| 메서드 | 파일:행 | TTL |
|--------|---------|-----|
| saveChatSession | RedisService.java:74–76 | 72시간 |
| updateChatSession | RedisService.java:84–87 | 72시간 (갱신 시 리셋) |

```84:87: MiriArt/miriart-be/src/main/java/com/miriart/api/global/redis/RedisService.java
    public void updateChatSession(String sessionId, String data) {
        // TTL 리셋하며 업데이트
        redisTemplate.opsForValue().set(
                PREFIX + "chat:session:" + sessionId, data, 72, TimeUnit.HOURS);
```

- **getChatSession**에는 TTL 설정 없음(조회만).
- AiProxyService는 **saveChatSession을 직접 호출하지 않고**, 항상 **getChatSession → updateChatSession** 경로만 사용 (기존 히스토리 로드 후 append 후 update). 따라서 실제 TTL은 **updateChatSession**에서만 72시간으로 설정/리셋됨.

---

## 3. 상세 2: PlanType별 월 사용량 제한

### 3.1 체크 위치 (분석 경로)

- **호출 경로**: `AnalysisService.startAnalysis()` → `analysisFailHandler.savePending(userId, ...)` → **AnalysisFailHandler.checkCreditLimit(user, userId)**.
- **파일/라인**: `AnalysisFailHandler.java` 46–61행 (savePending), 95–105행 (checkCreditLimit).

```95:105: MiriArt/miriart-be/src/main/java/com/miriart/api/domain/analysis/service/AnalysisFailHandler.java
    private void checkCreditLimit(User user, Long userId) {
        if (!user.isNeedsProfile()) {
            String billingYearMonth = LocalDate.now().format(DateTimeFormatter.ofPattern("yyyy-MM"));
            long usedThisMonth = usageLogRepository.countByUserIdAndBillingYearMonth(userId, billingYearMonth);
            int monthlyLimit = user.getPlanType().getMonthlyLimit();
            if (usedThisMonth >= monthlyLimit) {
                log.warn("분석 크레딧 한도 초과 - userId: {}, used: {}, limit: {}", userId, usedThisMonth, monthlyLimit);
                throw new BusinessException(ErrorCode.CREDIT_LIMIT_EXCEEDED);
            }
        }
    }
```

- **PlanType 한도**: `PlanType.java` — FREE(5), BASIC(10), PREMIUM(99999).
- **적용 조건**: `!user.isNeedsProfile()`일 때만 한도 적용. 온보딩 전(`needsProfile=true`)은 체험으로 한도 미적용.

### 3.2 사용량 조회 (플랜 API용)

- **메서드**: `AnalysisService.getUsedThisMonth(Long userId)` (132–134행).
- **구현**: `usageLogRepository.countByUserIdAndBillingYearMonth(userId, currentBillingMonth())`.
- **사용처**: `UserController.getPlan()` → `analysisService.getUsedThisMonth(userId)` → `userService.getPlanInfo(userId, usedThisMonth)`.

### 3.3 Chat 경로에 동일 제한 적용 여부

- **Chat 경로**: `AiChatController.chat()` → `ChatSessionService.chat()` → `AiProxyService.chat()`.
- **코드 검색 결과**: Chat 경로에서는 `checkCreditLimit`, `getUsedThisMonth`, `CREDIT_LIMIT_EXCEEDED`, `monthlyLimit` 호출이 **전혀 없음**.
- **결론**: PlanType 기반 월 사용량 제한은 **분석(analyze) 경로에만** 적용되어 있고, **Chat 경로에는 동일 제한이 적용되지 않음**.  
  ErrorCode 주석에도 `CREDIT_LIMIT_EXCEEDED`는 "이번 달 **분석** 한도"이며, `PLAN_UPGRADE_REQUIRED`는 Phase 2 / Chat 제한용 예약 코드로 되어 있음.

---

## 4. 상세 3: InternalChatRequest 생성 시 modelType

### 4.1 설정 위치와 값

| 단계 | 파일:위치 | 설정 방식 |
|------|-----------|-----------|
| 1. 요청 DTO 기본값 | ChatRequest.java:25 | `private String modelType = "CHAT_PRO";` |
| 2. InternalChatRequest 빌드 | AiProxyService.java:93–99 | `.modelType(chatRequest.getModelType())` |

```93:99: MiriArt/miriart-be/src/main/java/com/miriart/api/domain/ai/service/AiProxyService.java
        InternalChatRequest internalRequest = InternalChatRequest.builder()
                .modelType(chatRequest.getModelType())
                .message(chatRequest.getMessage())
                ...
```

- **결과**: FE가 `modelType`을 보내지 않으면 **"CHAT_PRO"**가 그대로 사용되고, FE가 값을 보내면 그 값이 InternalChatRequest.modelType으로 전달됨.

### 4.2 DB 세션과의 일관성

- **ChatSession 엔티티**: `modelType` 필드 기본값 `"CHAT_PRO"` (ChatSession.java:48). Builder 생성자에서도 `modelType == null`이면 `"CHAT_PRO"` (64행).
- **ChatSessionService.getOrCreateByAnalysis**: 분석 기반 세션 생성 시 `.modelType("CHAT_PRO")` 명시 (100행).
- **ChatSessionKeyResolver.createNewSession**: Builder에 modelType 미지정 → 엔티티 필드 기본값 "CHAT_PRO" 사용.

정리하면, **InternalChatRequest.modelType**은 **ChatRequest.modelType**에서 오며, 기본값은 **"CHAT_PRO"**이고, Chat 세션 엔티티/생성 로직과도 동일한 기본값을 사용함.

---

## 5. ErrorCode 매핑 표 (대상 클래스·연관 코드)

| ErrorCode | HTTP | 코드 문자열 | 사용처 (파일/맥락) |
|-----------|------|-------------|---------------------|
| DUPLICATE_NICKNAME | CONFLICT | M002 | UserService.updateProfile |
| FILE_EMPTY | BAD_REQUEST | F001 | AnalysisService.startAnalysis |
| INVALID_FILE_TYPE | BAD_REQUEST | F004 | AnalysisService.startAnalysis |
| ANALYSIS_NOT_FOUND | NOT_FOUND | AN003 | AnalysisService.getAnalysis, AnalysisFailHandler.complete, ChatSessionService, ChatSessionKeyResolver |
| AI_ANALYSIS_FAILED | BAD_GATEWAY | AN001 | AiProxyService.analyze, AnalysisService.startAnalysis |
| AI_ANALYSIS_TIMEOUT | GATEWAY_TIMEOUT | AN002 | AiProxyService.analyze |
| AI_ANALYSIS_RATE_LIMITED | TOO_MANY_REQUESTS | AN004 | AiErrorMapper (429) |
| CREDIT_LIMIT_EXCEEDED | PAYMENT_REQUIRED | CR001 | AnalysisFailHandler.checkCreditLimit |
| AI_CHAT_FAILED | BAD_GATEWAY | AI001 | AiProxyService.chat |
| AI_CHAT_TIMEOUT | GATEWAY_TIMEOUT | AI002 | AiProxyService.chat |
| AI_SERVICE_AUTH_FAILED | BAD_GATEWAY | AI003 | AiErrorMapper (401/403) |
| AI_CHAT_RATE_LIMITED | TOO_MANY_REQUESTS | AI004 | AiErrorMapper (429, chat) |
| CHAT_SESSION_NOT_FOUND | NOT_FOUND | CS001 | ChatSessionService.getBySessionKey |
| IMAGE_URL_GENERATION_FAILED | BAD_GATEWAY | F005 | AiErrorMapper (502+GCS_ERROR) |
| INVALID_INPUT_VALUE | BAD_REQUEST | C001 | AiErrorMapper (400+VALIDATION_ERROR) |

---

## 6. Redis 키/값/TTL 요약표

| 용도 | 키 패턴 | Value 형식 | TTL 설정 위치 |
|------|---------|------------|----------------|
| AI 채팅 세션 히스토리 | `miriart:chat:session:{sessionId}` | JSON 배열 `[{"role":"user"\|"model","text":"..."}, ...]` | saveChatSession: 72시간, updateChatSession: 72시간(리셋) |
| OAuth2 코드 | `miriart:oauth2:code:{code}` | payload 문자열 | 60초 |
| 리프레시 토큰 | `miriart:refresh:{userId}` | token 문자열 | 7일 |

---

*문서 끝.*
