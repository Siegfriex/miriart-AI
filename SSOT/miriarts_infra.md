# MiriArt 인프라 SSOT v1.2

> **목적**: MiriArt GCP 인프라/배포/운영 관련 **단일 참조 문서(Single Source of Truth, SSOT)**.  
> **규칙**: 실제 시크릿 값은 기재하지 않음. 환경변수/Secret 이름·용도·흐름만 기술. 코드·설정·문서에서 확인되지 않은 내용은 **(추론)**으로 표기.

---

## 운영 요약 (Operations Summary)

*이 섹션만 읽어도 신규 온콜이 대략 그림을 잡을 수 있도록 요약함.*

- **사용자 요청 플로우**: FE(Vite/React) → BE(Spring Boot, Cloud Run) → AI(FastAPI, Cloud Run) → GCS/Vertex AI. FE는 `VITE_API_BASE_URL`로 BE만 호출하고, BE는 `FASTAPI_INTERNAL_URL`로 AI의 `/internal/ai/analyze`, `/internal/ai/chat`, `/internal/ai/edit-image` 등 호출. (전체 엔드포인트: docs/miriart-ai-codebase-snapshot.md §2.1)
- **주요 GCP 리소스**: Cloud Run 2개(miriart-be, miriart-ai), Cloud SQL(MySQL miriart-mysql), Memorystore Redis(miriart-redis), GCS(miriart-bucket, miriart-build-cache), Secret Manager(DB/JWT/OAuth 등), Artifact Registry(miriart-images), Vertex AI(Gemini).
- **인프라 TODO Top 3**: (1) BE 자동 배포/CI 부재 — Gradle+Dockerfile+gcloud 기반 수동/스크립트 배포, 중기에는 Cloud Build로 이식 예정 (TODO-004). (2) 카카오 OAuth Secret 미등록 (TODO-001). (3) 관측성 부족 — 알람·대시보드 미구축 (TODO-006).
- **장애 시 먼저 확인할 위치**: (1) BE 헬스 `GET /actuator/health` (인증 불필요). (2) AI 헬스 `GET /health`. (3) Cloud Logging에서 서비스별 로그(miriart-be, miriart-ai) 및 GlobalExceptionHandler/스택 로그.

---

## 0. 개요 (Overview)

**목적**: 서비스 정의·GCP 기본 정보·문서 역할을 한눈에 파악할 수 있게 함.

### 서비스 한 줄 정의

**MiriArt(미리미대)** — Vision AI 작품 평가 + 입시 빅데이터 + 수험생 간 Q&A 커뮤니티를 결합한, 미대 입시 수험생 전용 AI 코칭 앱.  
*소스: docs/MiriArt_PRD_v2.md:14–16*

### GCP 프로젝트·리전·환경

| 항목 | 값 | 소스(파일/라인) |
|------|-----|------------------|
| GCP 프로젝트 ID | `miriarts` | docs/MiriArt_GCP_INFRA.md:4–5 |
| GCP 프로젝트명 | miriart | 동일 |
| 주요 리전 | asia-northeast3 (서울) | 동일 |
| 현재 환경 | prod(Cloud Run BE 배포 완료, AI는 문서상 placeholder), 로컬 dev(application-dev.yml) | docs/MiriArt_GCP_INFRA.md §4, §12 |

### 이 문서의 목적

이 문서는 **MiriArt 인프라/배포/운영 관련 단일 참조 문서(SSOT)** 로, 레포의 코드·설정·docs/*.md 를 기준으로 GCP 리소스, 구성, 환경변수·시크릿, 네트워크·보안, 배포·CI/CD, 운영·관측성, 개방 이슈를 한곳에 정리한다.

---

## 1. 논리 아키텍처 (Logical Architecture)

**목적**: 서비스 구성과 요청 플로우를 코드/설정 기준으로 정리해, 트래픽 경로와 비활성 컴포넌트를 구분할 수 있게 함.

### 1.1 서비스 목록

| 이름 | 역할 | 주요 책임 | 사용 스택 | 비고 |
|------|------|------------|------------|------|
| **miriart-be** | 백엔드 API | 인증(OAuth2/JWT), 커뮤니티(게시글·Q&A), AI 프록시(FastAPI 호출), GCS 업로드, 분석·채팅 API | Java 17, Spring Boot 3.4.2 | *소스: miriart-be/build.gradle:3, 11–13* |
| **miriart-ai** | AI 전용 서비스 | Vertex AI(Gemini) Vision/Chat 연동, GCS 읽기/쓰기, 작품 분석·AI 채팅·이미지 편집 | Python 3.11, FastAPI 0.115.8 | *소스: miriart-ai/Dockerfile:1, requirements.txt* |
| **server** | Node API 서버 | Gemini SDK 직접 호출(채팅·분석·이미지 편집 라우트). Cloud Run 배포용 Dockerfile 존재 | Node 20, Express 4.x | **(현재 비활성 / future use)** FE/BE와 HTTP 연동 없음 (추론). *소스: server/package.json, server/Dockerfile* |
| **프론트엔드** | 클라이언트 | 인증·분석·채팅·커뮤니티 UI. BE API만 호출(VITE_API_BASE_URL) | Node ≥18, React 19.2.4, Vite 6, Tailwind 4 | *소스: 루트 package.json* |

### 1.2 요청 플로우 다이어그램 (텍스트)

```
[프론트엔드 (Vite/React)]
    │ Base URL: import.meta.env.VITE_API_BASE_URL. dev 미설정 시 'http://localhost:8080', prod 미설정 시 ''(빈 문자열) → Vercel 등 prod 빌드 시 반드시 환경변수 설정 필요.
    │ 소스: src/shared/config/api.ts:8-12, miriartApi.ts, Login.tsx
    ▼
[miriart-be (Spring Boot, Cloud Run)]
    │ Base URL: miriart.fastapi.internal-url → FASTAPI_INTERNAL_URL (기본값 http://localhost:8000)
    │ 소스: WebClientConfig.java:33, 42–44, AiProxyService.java:58–59, 97–98
    │ 호출 path: POST /internal/ai/analyze, POST /internal/ai/chat, POST /internal/ai/edit-image 등 (전체: docs/miriart-ai-codebase-snapshot.md)
    ▼
[miriart-ai (FastAPI, Cloud Run)]  — prefix /internal/ai (miriart-ai/app/main.py:34)
    └→ Vertex AI, GCS

[server (Node/Express)]  — (현재 비활성 / future use) 위 플로우에 미연동 (추론)
```

---

## 2. GCP 리소스 카탈로그 (Resource Catalog)

**목적**: 운영자가 GCP 콘솔과 비교할 기준 목록. 레포/문서에서 확인 가능한 값만 기재. 확실하지 않으면 (추론) 표기.

### Cloud Run 서비스

| 서비스명 | 리전 | 런타임 | 메모리/CPU | 타임아웃 | 동시성/min·max | 서비스 계정 | Ingress/IAM | 소스(파일/라인) |
|----------|------|--------|------------|----------|----------------|-------------|-------------|------------------|
| miriart-be | asia-northeast3 | Java 17 (Eclipse Temurin) | **1Gi** (2026-03-10 증설, 기존 512Mi) | 300s | 문서에 미기재 | miriart-be-runner@miriarts.iam.gserviceaccount.com | --no-allow-unauthenticated, **invoker-iam-disabled 유지** (조직 정책 allUsers 차단으로 IAM 체크 불가) | miriart-be/scripts/cloudrun-redeploy.ps1:18-31, GCP 실측 2026-03-10 |
| miriart-ai | asia-northeast3 | Python 3.11, uvicorn | 1Gi, 1 CPU | 120s | concurrency=10, min=1, max=20 | miriart-ai-runner@miriarts.iam.gserviceaccount.com | --no-allow-unauthenticated, **invoker-iam-check 활성**, cpu-boost | miriart-ai/cloudbuild.yaml:17–33, GCP 실측 2026-03-10 |
| server | (레포 내 배포 정의 없음) | Node 20 | Dockerfile만 존재 | — | — | — | **(현재 비활성 / future use)** (추론) | server/Dockerfile |

프론트엔드는 GCP Cloud Run이 아닌 **Vercel**에 배포되며, FE 배포 설정의 SSOT는 Vercel 프로젝트 설정이다. *소스: README.md:82–100, 157 (Vercel 배포·연결), docs/SSOT/miriarts_central.md:223 (Vercel SPA 배포).*

### Cloud SQL (MySQL)

| 항목 | 값 | 소스(파일/라인) |
|------|-----|------------------|
| 인스턴스명 | miriart-mysql | docs/MiriArt_GCP_INFRA.md §5 |
| 리전 | asia-northeast3 | 동일 |
| 연결 방식 | Cloud Run → **Socket Factory**(Unix 소켓). 인스턴스는 Private IP(10.99.0.3) 존재 | docs/MiriArt_BE_CloudRun_CloudSQL_FIX.md:4–9, miriart-be/build.gradle:56–57 |
| 주 DB 이름 | miriart_prod (prod), miriart_dev (dev) | docs/MiriArt_GCP_INFRA.md §5, miriart-be/src/main/resources/application-dev.yml:3 |
| 문자셋 | utf8mb4 / utf8mb4_unicode_ci | docs/MiriArt_GCP_INFRA.md §5 |
| **실제 스키마 SSOT** | **`docs/mysql_erd_v1.md`** | 테이블·컬럼·인덱스는 해당 문서(역추출·§4 정합성 점검) 기준. 스키마 변경 시 해당 문서 재추출 또는 §4 갱신. 설계/Phase 확장은 `docs/MiriArt_ERD_v2.md`. *Cursor 규칙: .cursor/rules/infra-ssot.mdc, INFRA_SSOT_GUIDE.md* |
| Cloud Shell 접속(공개 IP) | 공개 IP 활성화 시에만 가능. **승인된 네트워크**에 Cloud Shell egress IP를 `x.x.x.x/32` 형식으로 추가. 해당 IP는 세션마다 다를 수 있으므로 **환경변수로 두지 않음** — 접속 전 `curl -s ifconfig.me` 로 확인 후 GCP 콘솔(SQL → 인스턴스 → 연결 → 승인된 네트워크)에서 추가. | 운영 확인 2026-03-02 |

#### Cloud Shell에서 MySQL 접속 절차

*전제: 인스턴스에 공개 IP가 활성화되어 있고, 승인된 네트워크에 현재 Cloud Shell egress IP가 등록되어 있어야 함. IP는 환경변수로 관리하지 않음.*

1. **변수 설정** (Cloud Shell bash)
   ```bash
   export PROJECT_ID="miriarts"
   export REGION="asia-northeast3"
   export INSTANCE_NAME="miriart-mysql"
   export INSTANCE_CONNECTION="$PROJECT_ID:$REGION:$INSTANCE_NAME"
   export DB_NAME="miriart_prod"
   export DB_USER="miriart"
   ```

2. **Cloud SQL Proxy 백그라운드 실행**
   ```bash
   cloud-sql-proxy $INSTANCE_CONNECTION --port=3306 &
   ```
   (Proxy가 준비될 때까지 1~2초 대기 권장.)

3. **DB 비밀번호 로드** (Secret Manager — 실제 값은 문서에 기재하지 않음)
   ```bash
   export DB_PASSWORD=$(gcloud secrets versions access latest --secret=miriart-db-password --project=$PROJECT_ID)
   ```

4. **mysql 클라이언트 접속**
   ```bash
   mysql -h 127.0.0.1 -P 3306 -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME"
   ```
   접속 후 DB 선택이 필요하면 `USE miriart_prod;` 실행. (`gcloud sql connect` 의 `--database` 플래그는 MySQL 인스턴스에서 지원되지 않음 — PostgreSQL/SQL Server 전용.)

### Memorystore Redis

| 항목 | 값 | 소스(파일/라인) |
|------|-----|------------------|
| 인스턴스명 | miriart-redis | docs/MiriArt_GCP_INFRA.md §6 |
| 리전 | asia-northeast3 | 동일 |
| 메모리/버전 | 1GB, Redis 7.0 | 동일 |
| 접속 방식 | Private IP (10.15.105.203), 포트 6379. Cloud Run → **VPC 커넥터** miriart-connector 필요 | docs/MiriArt_GCP_INFRA.md §6, docs/MiriArt_BE_CloudRun_CloudSQL_FIX.md §3, §6 |

### GCS 버킷

| 버킷명 | 용도 | 공개/비공개 | 소스(파일/라인) |
|--------|------|-------------|------------------|
| miriart-bucket | 작품(artworks), 편집(edited), 프로필(profiles), 커뮤니티(community) 이미지 | 비공개 (서비스 계정만). CORS: GET, origin `https://miriart.app` + `http://localhost:3000` (2026-03-10 설정). Signed URL §3.4 참조 | docs/MiriArt_GCP_INFRA.md §3 |
| miriart-build-cache | Cloud Build 캐시 | Cloud Build만 | 동일 |

### Secret Manager (주요 Secret ID)

| Secret ID | 용도 | 매핑(서비스 → env) | 소스(파일/라인) |
|-----------|------|---------------------|------------------|
| miriart-db-url | MySQL JDBC URL (소켓 방식) | miriart-be → DB_URL | docs/MiriArt_GCP_INFRA.md §8, application-prod.yml:12 |
| miriart-db-username | MySQL 사용자명 | miriart-be → DB_USERNAME | 동일 |
| miriart-db-password | MySQL 비밀번호 | miriart-be → DB_PASSWORD | 동일 |
| miriart-redis-host | Redis 호스트 IP | miriart-be → REDIS_HOST | 동일 |
| miriart-jwt-access-secret | JWT Access 서명 키 | miriart-be → JWT_ACCESS_SECRET | 동일, application-prod.yml:51, JwtProperties.java |
| miriart-jwt-refresh-secret | JWT Refresh 서명 키 | miriart-be → JWT_REFRESH_SECRET | 동일 |
| miriart-google-client-id | 구글 OAuth2 Client ID | miriart-be → GOOGLE_CLIENT_ID | 동일 |
| miriart-google-client-secret | 구글 OAuth2 Secret | miriart-be → GOOGLE_CLIENT_SECRET | 동일 |
| miriart-frontend-oauth-url | OAuth 성공 후 FE 리다이렉트 URL | miriart-be → FRONTEND_OAUTH_SUCCESS_URL | 동일 |
| miriart-kakao-client-id | 카카오 OAuth2 Client ID | miriart-be → KAKAO_CLIENT_ID (문서상 미등록) | 동일 |
| miriart-kakao-client-secret | 카카오 OAuth2 Secret | miriart-be → KAKAO_CLIENT_SECRET (문서상 미등록) | 동일 |

*시크릿 값은 기재하지 않음.*

### 기타 GCP 서비스

| 서비스 | 용도 | 비고 | 소스(파일/라인) |
|--------|------|------|------------------|
| Artifact Registry | Docker 이미지 저장소 `miriart-images`, 리전 asia-northeast3 | | docs/MiriArt_GCP_INFRA.md §7 |
| Vertex AI | Gemini Vision/Chat (miriart-ai) | | docs/MiriArt_GCP_INFRA.md §1, miriart-ai/app/core/gemini_client.py |
| Cloud Build | CI/CD (miriart-ai용 cloudbuild.yaml) | | docs/MiriArt_GCP_INFRA.md §1, §2 |
| FCM (Firebase Cloud Messaging) | Phase C5 추가 예정 | | docs/MiriArt_GCP_INFRA.md §1 |

---

## 3. 구성·설정 (Configuration & Environment)

**목적**: 환경별(dev/prod) 설정 차이와 환경변수·Secret 매핑을 한곳에서 관리·참조할 수 있게 함.

### 3.1 환경별 설정 (dev vs prod)

#### BE 기준

*소스: miriart-be/src/main/resources/application.yml, application-dev.yml, application-prod.yml*

| 구분 | dev | prod |
|------|-----|------|
| DB 연결 | localhost:3306/miriart_dev, username/password 고정 (application-dev.yml:3–5) | DB_URL, DB_USERNAME, DB_PASSWORD(Secret 주입), Socket Factory JDBC URL (application-prod.yml:12–14) |
| Redis | host localhost, port 6379 (application-dev.yml:24) | REDIS_HOST(Secret), port 6379, Memorystore + VPC 커넥터 (application-prod.yml:32–33) |
| OAuth redirect URL | {baseUrl}/login/oauth2/code/{registrationId}, baseUrl=로컬 BE | 동일 템플릿, baseUrl=Cloud Run BE URL (문서) |
| FE OAuth 성공 URL | FRONTEND_OAUTH_SUCCESS_URL 기본값 http://localhost:5173 (application.yml:17) | Secret miriart-frontend-oauth-url (문서) |
| JWT 시크릿/만료 | access/refresh 플레이스홀더 기본값 (application-dev.yml:56–57). 만료 900000/604800000 ms (application.yml:32–33 miriart.jwt.access-expiration-ms, refresh-expiration-ms) | JWT_ACCESS_SECRET, JWT_REFRESH_SECRET 필수(Secret). 만료 동일 |
| 파일 저장 | MockFileStorageService 사용 가능 | GcsFileStorageService, miriart.gcs.bucket (application.yml:24) |
| JPA ddl-auto, show-sql, 로그 | ddl-auto none, show-sql true, com.miriart.api DEBUG (application-dev.yml) | ddl-auto validate, show-sql false, root INFO (application-prod.yml:23–24, 55–56) |

#### FastAPI / server / FE

| 서비스 | dev / prod 차이 | 소스(파일/라인) |
|--------|------------------|------------------|
| FastAPI | config 기본값 gcp_project_id `miriart-dev`, gcp_region `asia-northeast3`, gemini_location `global`(Gemini API 호출 리전, GCP_REGION과 분리), gcs_bucket_name `miriart-bucket`. 로컬: .env·GOOGLE_APPLICATION_CREDENTIALS. Cloud Run: --set-env-vars GCP_PROJECT_ID=miriarts 등. Gemini 호출은 gemini_location 사용 (config.py:26, gemini_client.py:32). | miriart-ai/app/core/config.py:22–26, miriart-ai/cloudbuild.yaml:40 |
| server | **(현재 비활성 / future use)** 레포 내 dev/prod 전용 설정 없음. PORT, ALLOWED_ORIGIN, GEMINI_API_KEY 환경변수 (추론) | server/index.ts:19, 24 |
| FE | VITE_API_BASE_URL: dev 미설정 시 http://localhost:8080, prod 미설정 시 ''(빈 문자열). Vercel 등 prod에서는 반드시 BE URL로 설정 필요. | src/shared/config/api.ts:8-12 |

### 3.2 환경변수·Secret 맵 (SSOT 표)

*실제 값은 기재하지 않음. 이름·용도·흐름만.*

| 이름 | Secret Manager ID | 사용 서비스 | 용도 | 로드 위치 | 소스(파일/라인) |
|------|-------------------|-------------|------|-----------|------------------|
| DB_URL | miriart-db-url | miriart-be | Cloud SQL JDBC URL (소켓) | application-prod.yml → spring.datasource.url, 배포 시 --set-secrets | application-prod.yml:12 |
| DB_USERNAME | miriart-db-username | miriart-be | MySQL 사용자명 | application-prod.yml | 동일 |
| DB_PASSWORD | miriart-db-password | miriart-be | MySQL 비밀번호 | application-prod.yml | 동일 |
| REDIS_HOST | miriart-redis-host | miriart-be | Redis 호스트 IP | application-prod.yml → spring.data.redis.host | application-prod.yml:32 |
| JWT_ACCESS_SECRET | miriart-jwt-access-secret | miriart-be | JWT Access 서명 키 | application-prod.yml → miriart.jwt.secret.access | application-prod.yml:51, JwtProperties.java |
| JWT_REFRESH_SECRET | miriart-jwt-refresh-secret | miriart-be | JWT Refresh 서명 키 | application-prod.yml → miriart.jwt.secret.refresh | 동일 |
| GOOGLE_CLIENT_ID | miriart-google-client-id | miriart-be | 구글 OAuth2 Client ID | application-dev/prod.yml | application-dev.yml:43, application-prod.yml:44 |
| GOOGLE_CLIENT_SECRET | miriart-google-client-secret | miriart-be | 구글 OAuth2 Secret | 동일 | 동일 |
| KAKAO_CLIENT_ID | miriart-kakao-client-id | miriart-be | 카카오 OAuth2 Client ID | application-dev.yml (문서상 Secret 미등록) | application-dev.yml:35 |
| KAKAO_CLIENT_SECRET | miriart-kakao-client-secret | miriart-be | 카카오 OAuth2 Secret | 동일 | 동일 |
| FRONTEND_OAUTH_SUCCESS_URL | miriart-frontend-oauth-url | miriart-be | OAuth 성공 후 FE 리다이렉트 URL | application.yml → miriart.frontend.oauth-success-url | application.yml:17 |
| FASTAPI_INTERNAL_URL | (없음) | miriart-be | FastAPI AI Base URL. **Prod 확정값**: `https://miriart-ai-gzjczkus6q-du.a.run.app` (2026-03-10 수정, 기존 `-svc-` URL 404이었음) | application.yml → miriart.fastapi.internal-url, 배포 시 --set-env-vars | application.yml:19, WebClientConfig.java:33 |
| GCS_BUCKET_NAME | (없음) | miriart-be | GCS 버킷명 | application.yml → miriart.gcs.bucket | application.yml:24 |
| GCP_PROJECT_ID | (없음) | miriart-ai | Vertex/GCS 프로젝트 ID. 기본값 `miriart-dev`, Prod `miriarts` (cloudbuild) | config.py → gcp_project_id, cloudbuild --set-env-vars | miriart-ai/app/core/config.py:22 |
| GCP_REGION | (없음) | miriart-ai | Cloud Run/설정 리전 | config.py → gcp_region | config.py:23 |
| GEMINI_LOCATION | (없음) | miriart-ai | Gemini API 호출 리전 (Cloud Run 리전과 분리) | config.py → gemini_location, 기본값 `global`, cloudbuild 미설정 시 기본값 | config.py:26, gemini_client.py:32 |
| GCS_BUCKET_NAME | (없음) | miriart-ai | GCS 버킷명 | config.py → gcs_bucket_name | config.py:24 |
| GOOGLE_APPLICATION_CREDENTIALS | (없음) | miriart-ai | 로컬 인증 JSON 경로 | config.py. Cloud Run 불필요 | config.py:25 |
| VITE_API_BASE_URL | (없음) | FE | BE API Base URL | import.meta.env (Vite), 빌드 시 주입 | src/shared/api/miriartApi.ts |
| PORT, ALLOWED_ORIGIN, GEMINI_API_KEY | — | server | 서버 포트, CORS origin, Gemini API 키 | process.env (server) | server/index.ts:19, 24, 55 |

### 3.3 로그인 기준 확정값 (Prod 검증용)

*아래 값은 로그인 플로우가 동작하는 prod 환경 기준으로, 수동 확인 후 갱신한다. 시크릿 실제 값은 기재하지 않음.*

#### Google OAuth redirect URI (수동 확인)

| 항목 | 확정값/기대값 | 확인 방법 |
|------|----------------|-----------|
| Google 콘솔 승인된 리다이렉트 URI | `https://miriart-be-946560105497.asia-northeast3.run.app/login/oauth2/code/google` (BE Cloud Run URL과 정확히 일치) | GCP 콘솔 → APIs & Services → 사용자 인증 정보 → OAuth 2.0 클라이언트 ID → 해당 클라이언트 → "승인된 리다이렉트 URI" 목록에 위 URI 존재 여부 확인. |
| BE baseUrl | Cloud Run 서비스 URL(https, trailing slash 없음). `forward-headers-strategy: framework`로 X-Forwarded-Proto/Host 반영 (application-prod.yml:4). | — |

#### FRONTEND_OAUTH_SUCCESS_URL (Secret 형식)

| 항목 | 확정값/기대값 | 확인 방법 |
|------|----------------|-----------|
| Secret `miriart-frontend-oauth-url` 형식 | **도메인만** (경로 없음). 예: `https://miri-art.vercel.app` | BE 코드가 `frontendOauthSuccessUrl + "/auth/callback?code=" + code` 를 사용하므로(OAuth2LoginSuccessHandler.java:54), Secret 값에 경로를 넣으면 리다이렉트 URL이 중복됨. **확인:** `gcloud secrets versions access latest --secret=miriart-frontend-oauth-url --project=miriarts` 실행 후 값이 경로 없이 FE 도메인만인지 확인. (실제 값은 문서에 기재하지 않음.) |

#### Prod 수동 시나리오 체크리스트

| 순서 | 단계 | 확인 내용 |
|------|------|-----------|
| 0 | 사전 | 로그아웃 또는 시크릿/비로그인 브라우저에서 진행. (기존 세션 있으면 /auth/login에서 바로 /onboarding 등으로 리다이렉트됨.) |
| 1 | /auth/login | `https://miri-art.vercel.app/auth/login` 접속 → "Google로 시작하기" 클릭 |
| 2 | Google → BE | Google 로그인 후 `https://miriart-be-946560105497.asia-northeast3.run.app/login/oauth2/code/google?code=...` 로 리다이렉트되는지 확인 |
| 3 | BE → FE callback | BE가 `FRONTEND_OAUTH_SUCCESS_URL + "/auth/callback?code=" + UUID` 로 리다이렉트 → `https://miri-art.vercel.app/auth/callback?code=...` 도달 |
| 4 | /api/auth/token | FE가 POST /api/auth/token 호출 → 200 + Access Token(body) + Set-Cookie(refreshToken) |
| 5 | /api/users/me | FE가 GET /api/users/me (Authorization: Bearer) → 200, 프로필 응답 |
| 6 | 최종 | /onboarding 또는 /app/home 진입 |

#### Refresh 쿠키 (코드 기준 확정값)

*소스: OAuth2TokenExchangeService.java:70-77, AuthController.java:86-91, application-prod.yml:45*

| 속성 | prod 확정값 | 비고 |
|------|-------------|------|
| 이름 | refreshToken | |
| httpOnly | true | |
| Secure | true | |
| SameSite | None | prod: miriart.auth.cookie-same-site: None (application-prod.yml:45). cross-site(Vercel↔Cloud Run) 전송 허용. |
| Path | /api/auth/refresh | |
| Max-Age | 604800 (7일) | |
| Domain | **미설정** | ResponseCookie에 domain 미지정 → 브라우저가 Set-Cookie를 받은 호스트(BE 도메인) 기준으로 저장. FE 도메인이 아닌 BE 도메인에만 쿠키 존재. |

*수동 확인 권장:* 로그인 성공 후 브라우저 DevTools → Application → Cookies → `https://miriart-be-946560105497.asia-northeast3.run.app` 에서 refreshToken 항목의 SameSite=None, Secure, Path=/api/auth/refresh 확인. (Domain 미설정이면 호스트와 동일한 도메인만 표시됨.)

---

### 3.4 이미지 전달 정책 (GCS Signed URL)

> **2026-03-10 신규**. 버킷 `miriart-bucket`은 비공개이며, 이미지 URL 직접 접근 시 403이 **정상**이다.

| 항목 | 값 |
|------|-----|
| 전달 방식 | GCS V4 Signed URL (BE에서만 생성) |
| BE 엔드포인트 | `GET /api/images/{id}/url` |
| 서명 SA | `miriart-be-runner@miriarts.iam.gserviceaccount.com` |
| 유효기간 | 15분 (dev/prod 동일) |
| 허용 Method | GET (읽기 전용) |
| 허용 경로 prefix | `artworks/`, `edited/`, `analyses/` |
| CORS origin | `https://miriart.app`, `http://localhost:3000` |
| CORS method | GET |
| CORS maxAge | 3600s |

**원칙**:
- FE는 이미지 조회 시 반드시 BE(`/api/images/{id}/url`)를 통해 Signed URL을 발급받아 접근.
- AI(`GcsService.upload_bytes`)가 반환하는 `https://storage.googleapis.com/...` URL은 BE 내부 식별/메타용. FE에 직접 전달하지 않음.
- SA 키 파일 다운로드 금지. Cloud Run 자동 SA만 사용.

**GCS 경로 패턴 (현재 코드 기준)**:

| 경로 패턴 | 용도 | 생성 주체 | 소스 |
|-----------|------|-----------|------|
| `artworks/{date}/{uuid}_{filename}` | 원본 업로드 이미지 | BE | — |
| `edited/{uuid}.jpg` | AI 이미지 편집 결과 | AI | `image_edit_service.py:64` |
| `analyses/**` (향후) | 분석 결과 이미지 | AI | — |

**GCS 경로 prefix 변경 프로세스**:
1. AI/BE가 새 prefix를 도입할 경우, **코드 PR 전에** 이 SSOT §3.4 경로 표를 먼저 수정.
2. BE의 Signed URL prefix 검증 허용 목록에 새 prefix 추가.
3. PR 템플릿 체크: "☐ SSOT/miriarts_infra.md §3.4 경로 prefix 갱신 여부 확인"

---

## 4. 네트워크 & 보안 (Networking & Security)

**목적**: 네트워크 경로·인증/인가·CORS·서비스 계정을 정리해, 변경 시 기준선으로 사용할 수 있게 함.

### 4.1 네트워크 토폴로지 요약

| 경로 | 방식 | 소스(파일/라인) |
|------|------|------------------|
| Cloud Run (BE) → Cloud SQL | **Socket Factory** / 인스턴스 연결(Unix 소켓). --add-cloudsql-instances=miriarts:asia-northeast3:miriart-mysql. Private IP 직결 아님 | docs/MiriArt_BE_CloudRun_CloudSQL_FIX.md:4–9, miriart-be/build.gradle:56–57 |
| Cloud Run (BE) → Redis | **VPC 커넥터** miriart-connector, **Private IP** (10.15.105.203). --vpc-egress=private-ranges-only | docs/MiriArt_BE_CloudRun_CloudSQL_FIX.md §3, §6 |
| Cloud Run (BE) → miriart-ai | HTTPS, FASTAPI_INTERNAL_URL. miriart-ai는 --no-allow-unauthenticated → IAM(roles/run.invoker) 호출 | docs/MiriArt_GCP_INFRA.md §2, §4 |
| miriart-ai | **인터넷 직접 노출 없음**(내부 전용). BE만 호출 | miriart-ai/cloudbuild.yaml:26 |

### 4.2 인증/인가 & CORS

#### Spring Security (miriart-be)

*소스: miriart-be/src/main/java/com/miriart/api/global/config/SecurityConfig.java:52–66*

| URL 패턴 | 접근 | 소스(파일/라인) |
|----------|------|------------------|
| /api/auth/** | permitAll | SecurityConfig.java:55 |
| /oauth2/**, /login/oauth2/** | permitAll | :56 |
| GET /api/posts/**, GET /api/answers/** | permitAll | :57–58. **GET /api/answers/** 는 컨트롤러 미구현(Phase C1). 구현 전까지 해당 경로 요청 시 404. |
| /swagger-ui/**, /v3/api-docs/** | permitAll | :59 |
| /actuator/health | permitAll | :60 |
| 그 외 | authenticated() (JWT) | :62 |

#### CORS

| 서비스 | 설정 | FE 도메인 연관 | 소스(파일/라인) |
|--------|------|----------------|------------------|
| miriart-be | SecurityConfig에서 CORS 설정. allowedOrigins: `http://localhost:5173`, `https://miri-art.vercel.app`. allowCredentials: true. allowedMethods: GET, POST, PUT, PATCH, DELETE, OPTIONS. allowedHeaders: * | FE prod: https://miri-art.vercel.app, dev: http://localhost:5173. **allowedOrigins에 없는 FE 도메인으로 배포 시 CORS 차단 발생** → 새 도메인 사용 시 SecurityConfig 갱신 필요. | SecurityConfig.java:83-96 |
| miriart-ai | CORS 미들웨어 없음. BE만 호출 | — | miriart-ai/app/main.py |
| server | **(현재 비활성 / future use)** origin: ALLOWED_ORIGIN \|\| '*', methods: GET, POST, OPTIONS, allowedHeaders: Content-Type, Authorization | ALLOWED_ORIGIN으로 제한 가능 | server/index.ts:23–27 |

### 4.2.1 조직 정책 & Cloud Run IAM 현황 (2026-03-10 확인)

**조직 정책 `iam.allowedPolicyMemberDomains`가 활성 상태**이며, `allUsers` / `allAuthenticatedUsers` IAM 바인딩이 프로젝트 `miriarts` 전체에서 차단되어 있다.

이로 인해 Cloud Run 서비스에 `--allow-unauthenticated`(= `allUsers` Invoker)를 설정할 수 없다.

#### 현재 상태 (DRS 완화 상태)

| 서비스 | invoker-iam-check | invoker-iam-disabled | allUsers Invoker | 외부 접근 | 비고 |
|--------|-------------------|----------------------|------------------|-----------|------|
| **miriart-ai** | **활성** | false | ❌ (BE SA만) | 403 (정상) | BE→AI는 SA 토큰 자동 발급으로 정상 동작 |
| **miriart-be** | 비활성 | **true (완화)** | ❌ (조직 차단) | 200 (완화) | FE(브라우저)→BE 호출을 위해 IAM 우회 유지. 앱 레벨 인증은 Spring Security JWT가 담당 |

**⚠️ miriart-be의 `invoker-iam-disabled: true`는 보안 완화 상태이다.** BE는 FE(브라우저)에서 직접 호출하는 public 서비스이므로, 조직 정책이 `allUsers` 바인딩을 차단하는 한 이 완화가 불가피하다. 앱 레벨에서 Spring Security가 JWT·OAuth2로 인증/인가를 처리하므로, 비인증 요청은 Spring이 거부한다.

#### 릴리즈 전 보안 강화 계획 (TODO-009)

조직 정책 예외를 태그 기반으로 적용하여 `invoker-iam-disabled` 완화를 해소한다.

**Step 1: 조직 태그 생성**

| 항목 | 값 |
|------|-----|
| 태그 키 | `sa-api-key-policy` |
| 설명 | 서비스 계정 API Key 생성 허용 정책 (조직 기본: 차단) |
| 태그 값 | `enforced` (기본 차단) / `exempt` (예외 허용) |

**Step 2: 조직 정책 조건부 적용**
- 조직 루트: `iam.allowedPolicyMemberDomains` = `enforced` (기본)
- `miriarts` 프로젝트에 태그 `sa-api-key-policy=exempt` 부착
- 조건부 정책: 해당 태그가 있는 프로젝트만 `allUsers` 바인딩 허용

**Step 3: BE IAM 정상화**
```bash
gcloud run services update miriart-be \
  --region=asia-northeast3 --project=miriarts \
  --allow-unauthenticated --invoker-iam-check
```

**실행 시점**: v1 릴리즈 직전 보안 점검 시. 조직 관리자 권한 필요.

---

### 4.3 서비스 계정 & IAM

*소스: docs/MiriArt_GCP_INFRA.md §2. 구체 리소스 정책은 문서 범위 내.*

| 서비스 계정 | 용도 | 역할 (문서 기준) |
|-------------|------|-------------------|
| miriart-be-runner | BE Cloud Run 런타임 | roles/storage.objectAdmin, roles/run.invoker, roles/cloudsql.client, roles/secretmanager.secretAccessor, **roles/iam.serviceAccountTokenCreator** (GCS Signed URL 서명, 2026-03-10 추가) |
| miriart-ai-runner | AI Cloud Run 런타임 | roles/aiplatform.user, roles/storage.objectAdmin, **roles/iam.serviceAccountTokenCreator** (Signed URL 준비, 2026-03-10 추가) |
| miriart-cloudbuild | CI/CD 파이프라인 | roles/run.admin, roles/iam.serviceAccountUser, roles/artifactregistry.writer, roles/storage.objectAdmin |
| miriart-local-dev | 로컬 개발(키파일) | roles/aiplatform.user, roles/storage.objectAdmin |

### 4.4 API 구현 현황(검증됨)

*코드·설정 기준으로 확인된 API·데이터·에러 정책만 기재. FSD/PRD 상세는 각 문서 참고.*  
*예외 코드(ErrorCode)·전역 핸들러(I-P-O-E)·CORS·엔드포인트 일람: **docs/MiriArt_API_CONTRACT.md §9(ErrorCode), §10(코드 기준 검증), §8(FastAPI Internal 프로덕션 명세)**.*

#### 구현된 엔드포인트(인증 필요)

| 경로 | 용도 | 비고 |
|------|------|------|
| GET /api/users/me | 내 프로필 조회 | UserProfileResponse에 needsProfile, role, planType 포함. BE는 값 노출만, 분기는 FE. *소스: UserController.java:36–40, UserProfileResponse.java* |
| PATCH /api/users/me/profile | 온보딩 프로필 완성 | 닉네임 중복 시 M002. 완료 시 needsProfile=false. *소스: UserController.java:42–46, UserService.java:47–60* |
| GET /api/users/me/plan | 플랜·월 한도·사용량·잔여 | PlanType(FREE/BASIC/PREMIUM) monthlyLimit, AnalysisService.getUsedThisMonth 연동. *소스: UserController.java:48–52, PlanType.java, UserService.java:66–81* |
| POST /api/analyses | 작품 분석 시작 | 202 + analysisId. needsProfile=true일 때만 월 한도 체크, 초과 시 CR001(402). FREE=5회/월. *소스: AnalysisController.java, AnalysisService.java (PlanType.FREE=5)* |
| GET /api/analyses, GET /api/analyses/{id} | 분석 목록·단건 | 본인만. 없으면 AN003(404). *소스: AnalysisController.java:57–69* |
| POST /api/chat | AI 멘토 채팅 | FastAPI /internal/ai/chat 호출, Redis 세션 갱신. *소스: AiChatController.java:37–42, AiProxyService.java:97–98* |

#### 유저·플랜·크레딧(검증됨)

- **needsProfile**: User 엔티티 `needs_profile`(boolean), completeProfile() 시 false. API 차단 로직 없음. *소스: User.java:61–62, 84*
- **PlanType**: FREE(5), BASIC(10), PREMIUM(99999) 회/월. P1: 온보딩 완료(needsProfile=false) 시 분석 한도 체크 스킵. *소스: PlanType.java, AnalysisService.java*
- **analysis_usage_logs**: 테이블 존재. user_id, analysis_id, billing_year_month(YYYY-MM), created_at. 월별 집계·CR001 체크에 사용. *소스: AnalysisUsageLog.java, AnalysisUsageLogRepository.java*

#### Redis AI 채팅 세션

| 항목 | 값 | 소스(파일/라인) |
|------|-----|------------------|
| 키 패턴 | `miriart:chat:session:{sessionId}` | RedisService.java:76, 80, 85 |
| value | JSON 배열 [{"role":"user"\|"model","text":"..."}, ...] | AiProxyService.java:137–155 |
| TTL | 72시간 | RedisService.java:77, 86 |

MySQL `chat_sessions` / `chat_messages` 테이블·엔티티는 **없음**. 채팅 영속화는 Redis만 사용.

#### 미구현(코드 검색 기준)

- **성적/입시 전용 API**: `/api/theory`, `/api/universities`, `/api/line` 컨트롤러·전용 서비스 없음. grade·universityPredictions는 분석·유저 도메인 필드로만 사용. → §7 TODO-008.

#### 전역 에러 정책(참조용)

- **BusinessException** → GlobalExceptionHandler → ErrorCode 기반 HTTP status·code·message. *소스: GlobalExceptionHandler.java:35–40, ErrorCode.java*
- **DataAccessException / DB 커넥션 실패** 전용 핸들러 없음 → Exception 핸들러로 500 + C003. *소스: GlobalExceptionHandler.java:99–104*

---

## 5. 배포 & CI/CD (Deployment & CI/CD)

**목적**: 서비스별 배포 방식과 Cloud Run 배포 파라미터를 SSOT로 두어, 배포 전에 반드시 맞출 기준선으로 사용함.

### 5.1 배포 파이프라인 현황

| 서비스 | 배포 방식 | 상태 | 소스(파일/라인) |
|--------|-----------|------|------------------|
| miriart-ai | Cloud Build + Cloud Run 자동 배포 (cloudbuild.yaml 기반). Docker 빌드 → Artifact Registry 푸시 → gcloud run deploy | OK (자동 배포) | miriart-ai/cloudbuild.yaml 전체 |
| miriart-be | Gradle + Dockerfile + docker push(또는 Cloud Build submit) + gcloud run deploy. **스크립트**: `miriart-be/scripts/cloudrun-redeploy.ps1` (PowerShell, Cloud Build submit → deploy). 로컬 Docker 빌드 시 gradlew CRLF 처리·JAR 경로는 Dockerfile 참고 (§5.3). | 수동/스크립트 배포. 중기: Cloud Build 이식 예정 (TODO-004). | miriart-be/scripts/cloudrun-redeploy.ps1, miriart-be/Dockerfile |
| Frontend | Vercel 프로젝트를 통한 Git push 기반 자동 빌드/배포 (추론) | OK (FE 배포 SSOT는 Vercel 설정) | README.md:82–100, 157, docs/SSOT/miriarts_central.md:223 |
| server | Dockerfile만 존재. 배포 파이프라인/Cloud Run 정의 없음 | **(현재 비활성 / future use)** | server/Dockerfile |

### 5.2 Cloud Run 배포 파라미터 SSOT

#### miriart-be (문서 기준)

*소스: miriart-be/scripts/cloudrun-redeploy.ps1:18-31, docs/MiriArt_GCP_INFRA.md §4*

현재는 아래 파라미터를 **gcloud run deploy** 명령으로 로컬 스크립트/수동 배포 시 사용한다. (Cloud Build 파이프라인은 아직 없음, TODO-004.)

| 항목 | 값/설명 | 소스(파일/라인) |
|------|----------|------------------|
| 이미지 | asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-be:latest | cloudrun-redeploy.ps1:8 |
| 포트 | 8080 | :71 |
| 메모리 | 1Gi | :72 |
| CPU, 타임아웃, 동시성, min/max 인스턴스 | 문서에 미기재 → Cloud Run 기본값 (미흡 → TODO-007) | — |
| --add-cloudsql-instances | miriarts:asia-northeast3:miriart-mysql | :72 |
| --vpc-connector | miriart-connector | :73 |
| --vpc-egress | private-ranges-only | :74 |
| --no-allow-unauthenticated | 사용 | :69 |
| --set-secrets | DB_URL, DB_USERNAME, DB_PASSWORD, REDIS_HOST, JWT_ACCESS_SECRET, JWT_REFRESH_SECRET, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, KAKAO_CLIENT_ID, KAKAO_CLIENT_SECRET, FRONTEND_OAUTH_SUCCESS_URL (각 :latest) | :75 |
| --set-env-vars | SPRING_PROFILES_ACTIVE=prod, FASTAPI_INTERNAL_URL=(miriart-ai Cloud Run URL), GCS_BUCKET_NAME=miriart-bucket | cloudrun-redeploy.ps1:30 |

#### 5.3 BE Docker 빌드·Actuator (참고)

| 항목 | 내용 | 소스(파일/라인) |
|------|------|------------------|
| **gradlew CRLF** | Windows에서 체크 아웃 시 gradlew가 CRLF이면 Linux 컨테이너에서 `./gradlew: not found`. Dockerfile에서 `sed -i 's/\r$//' gradlew` 후 chmod 사용. | miriart-be/Dockerfile:9–10 |
| **JAR 경로** | Gradle 기본 출력은 `build/libs/*.jar`. Dockerfile COPY는 `--from=builder /app/build/libs/*.jar`. | miriart-be/Dockerfile:26, build.gradle |
| **Actuator health** | Cloud Run에서 `/actuator/health` 500 시 NoResourceFoundException 가능. application-prod.yml에 `management.endpoints.web.exposure.include: health` 명시. | miriart-be/src/main/resources/application-prod.yml:53–60 |
| **분석·패치 문서** | GET /api/posts 500(컨트롤러 없음 → PostController 추가), Cloud Run health 500(Actuator 노출·경로) 원인·해결은 miriart-be/docs 내 분석 문서 참고. | miriart-be/docs/GET_api_posts_500_분석_패치.md, CloudRun_health_500_분석_패치.md |

#### miriart-ai (cloudbuild.yaml 기준)

*소스: miriart-ai/cloudbuild.yaml:17–33*

| 항목 | 값 | 소스(파일/라인) |
|------|-----|------------------|
| 이미지 | asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:$COMMIT_SHA | cloudbuild.yaml:23 |
| 포트 | 8080 | :28 |
| 메모리/CPU | 1Gi, 1 | :29–30 |
| 타임아웃 | 120 | :31 |
| 동시성, min/max 인스턴스 | 미기재 | — |
| --set-env-vars | GCP_PROJECT_ID=miriarts, GCP_REGION=asia-northeast3, GCS_BUCKET_NAME=miriart-bucket (선택: GEMINI_LOCATION=global) | :40 |
| --set-secrets | 없음 | — |

---

## 6. 운영 & 관측성 (Operations & Observability)

**목적**: 헬스체크·로그·모니터링 현황을 정리해, 장애 시 확인 위치와 관측성 갭을 파악할 수 있게 함.

### 6.1 헬스체크 & 상태 확인

| 서비스 | 엔드포인트 | 인증 | 비고 | 소스(파일/라인) |
|--------|-------------|------|------|------------------|
| miriart-be | GET /actuator/health | permitAll | Spring Boot Actuator. **prod**: application-prod.yml에 management.endpoints.web.exposure.include: health 명시. 로드밸런서/배포 검사용. | SecurityConfig.java:60, application-prod.yml:53–60, build.gradle:65 |
| miriart-ai | GET /health | 없음 | 응답 {"status": "ok"} | miriart-ai/app/main.py:37–41 |
| server | **(현재 비활성 / future use)** GET /health | 없음 | 응답 { status, timestamp } | server/index.ts:34–36 |

### 6.2 로그 & 모니터링 현황

| 항목 | 내용 | 소스(파일/라인) |
|------|------|------------------|
| Cloud Logging / Monitoring / Trace | 전용 설정·SDK 없음. Spring Cloud GCP는 storage만 사용. **(추론: 기본 로그 수준만 사용)** | miriart-be/build.gradle |
| BE 예외 로깅 | GlobalExceptionHandler: 예외 유형별 log.error. 미처리 예외는 `log.error("Unhandled Exception: ", e)` (스택 포함). request/response body·헤더 직접 로깅 없음 | miriart-be/.../GlobalExceptionHandler.java:36–102, AiProxyService.java:71, 110 |
| AI/server | FastAPI lifespan 경고, server console.error. body/헤더 로깅 없음 | miriart-ai/app/main.py:24, server/index.ts:46–48 |
| Log-based Metrics | miriart-ai-5xx-errors, miriart-ai-502-gateway, miriart-ai-504-timeout, miriart-be-5xx-errors, **miriart-be-signed-url-count**, **miriart-be-signed-url-errors** (2026-03-10 생성) | GCP Logging > Log-based Metrics |
| Monitoring Dashboard | (1) "MiriArt-AI BE/AI Overview" — AI/BE Request Count, Latency, 5xx Rate, Instance Count 7패널. (2) **"MiriArt - BE Signed URL"** — Signed URL 발급/에러/Top objectPath 3위젯 (2026-03-10 생성) | GCP Monitoring > Dashboards |
| Alert Policy | (1) "miriart-ai 5xx Spike": 5분간 5xx > 5건 시 CTO 이메일 알림. (2) **"Signed URL Errors Spike"**: `signed_url_errors > 0` 5분 지속 시 CTO 알림 (2026-03-10 생성) | GCP Monitoring > Alerting |
| 알람/대시보드 | 대시보드·메트릭·알림 기초 구축 완료. Signed URL 전용 대시보드·알람 추가 완료. TODO-006 완료. | — |

---

## 7. 개방 이슈 / TODO (Open Issues / TODO)

**목적**: 인프라 관련 미완료 항목을 ID와 함께 정리해, 체크리스트·우선순위 정렬에 사용함.

*소스: docs/MiriArt_GCP_INFRA.md §12 및 관련 문서.*

| ID | 항목 | 중요도 | 설명 |
|----|------|--------|------|
| TODO-001 | 카카오 OAuth Secret 미등록 | High | 카카오 개발자 콘솔 발급 후 miriart-kakao-client-id, miriart-kakao-client-secret Secret Manager 등록 |
| TODO-002 | Google OAuth 운영 리다이렉트 URI 추가 | Medium | BE Cloud Run URL `https://miriart-be-946560105497.asia-northeast3.run.app/login/oauth2/code/google` 를 Google 콘솔 승인된 리다이렉트 URI에 추가. **검증:** §3.3 로그인 기준 확정값의 수동 확인 체크리스트 참고. |
| TODO-003 | miriart-ai 실제 이미지 빌드 + Cloud Run 배포 | High | 문서상 placeholder. Dockerfile·cloudbuild.yaml 있으나 실제 배포 완료 여부 문서 외 확인 필요 |
| TODO-004 | BE용 CI/CD 파이프라인 | Medium | 현재는 Gradle + Dockerfile + docker push + gcloud run deploy를 사용하는 로컬 스크립트 기반 수동 배포. 중기 목표는 이 절차를 그대로 Cloud Build 파이프라인으로 옮겨 main→prod 자동 배포를 구성하는 것. |
| TODO-005 | FCM API | Low | Phase C5 추가 예정 (fcm.googleapis.com) |
| TODO-006 | 관측성(알람·대시보드) 미구축 | Medium | Cloud Monitoring 알람/대시보드 없음. 기본 로그만 사용. 별도 설계 필요 |
| TODO-007 | BE Cloud Run 신뢰성 파라미터 미명시 | Medium | 타임아웃, 동시성, min/max 인스턴스가 문서·배포 스크립트에 명시되어 있지 않음. Cloud Run 기본값 의존 |
| TODO-008 | 성적/입시 전용 API 미구현 | Low | /api/theory, /api/universities, /api/line 컨트롤러·전용 서비스 없음. 분석·유저 도메인 필드(grade, universityPredictions)로만 노출. §4.4 |
| TODO-009 | BE Cloud Run IAM 정상화 (invoker-iam-disabled 해소) | **High** | 조직 정책 `iam.allowedPolicyMemberDomains`가 `allUsers` 바인딩 차단 → BE `invoker-iam-disabled: true` 완화 유지 중. **릴리즈 전 보안 점검 시** 조직 태그(`sa-api-key-policy=exempt`) 기반 예외 적용 후 `--allow-unauthenticated --invoker-iam-check` 전환. 상세: §4.2.1 |

---

## 변경 규칙 (Change Policy)

**목적**: SSOT 문서를 “변경 전에 반드시 맞춰야 하는 기준선”으로 유지하기 위한 최소 규칙 초안.

- **Cloud Run / Cloud SQL / Redis / Secret Manager / Artifact Registry / 서비스 계정**에 변경이 발생하면, **배포 전에** 이 SSOT 문서의 해당 섹션(§2 리소스 카탈로그, §3 구성·설정, §4 네트워크·보안, §5 배포 파라미터)을 우선 수정한다.
- **DB 스키마/테이블·엔티티** 변경 시: **스키마 SSOT** `docs/mysql_erd_v1.md`를 기준으로 한다. DDL 적용·역추출 후 해당 문서 §1·§2·§4(무결성·정합성 점검)를 갱신한다. 설계 문서 `docs/MiriArt_ERD_v2.md`와 불일치하면 조율(ERD_v2는 설계·미구현 테이블 포함). *Cursor 규칙: `.cursor/rules/infra-ssot.mdc`, `.cursor/INFRA_SSOT_GUIDE.md` §3.*
- **새로운 GCP 리소스**가 추가되면, §2(리소스 카탈로그)와 §3(환경변수·Secret 맵)을 함께 업데이트한다.
- **CI/CD 파이프라인** 변경 시 §5(배포 & CI/CD)와 §7(개방 이슈/TODO) 상태를 함께 갱신한다.
- **공개 엔드포인트·인증·CORS** 변경 시 §4(네트워크 & 보안)를 갱신한다.
- **에이전트가 인프라 관련 수정을 한 경우**: SSOT 해당 섹션 갱신 후 `docs/SSOT/CHANGELOG_infra.md`에 **날짜·에이전트 롤·구체적 수정 내역**을 기록한다. 상세: `.cursor/INFRA_SSOT_GUIDE.md` §5.

---

## SRE/DevOps 체크리스트

**목적**: 배포·신뢰성·관측성·보안·데이터 관점의 현재 상태를 한눈에 보고, 미흡/미구현 항목을 §7 TODO와 연결함.

### 배포 (CI/CD)

| 항목 | 현재 상태 | 참고 섹션 / TODO |
|------|-----------|-------------------|
| miriart-be 자동 배포 | 수동 배포(로컬 스크립트로 표준화됨). 단기 목표는 표준화된 수동 배포 유지, 중기 목표는 Cloud Build 자동화 (TODO-004) | §5.1. Gradle+Dockerfile+gcloud 기반 수동/스크립트 배포 → **TODO-004** |
| miriart-ai 자동 배포 | OK | §5.1. cloudbuild.yaml 기반 |
| FE (Vercel 배포) | OK (Vercel 파이프라인에 의해 자동 배포) | FE 배포 세부 설정은 Vercel 프로젝트가 SSOT이며, 이 인프라 문서는 개요만 제공. README.md, docs/SSOT/miriarts_central.md |
| server 배포 파이프라인 | (현재 비활성 / future use) | §5.1. Dockerfile만 존재 |
| 롤백 전략 문서/절차 | 미흡 | §5. 문서에 롤백 절차 없음. BE 수동 배포 의존 → **TODO-004** 연관 |

### 신뢰성

| 항목 | 현재 상태 | 참고 섹션 / TODO |
|------|-----------|-------------------|
| BE Cloud Run min/max 인스턴스 | 미흡 | §5.2. 문서에 미기재 → **TODO-007** |
| BE Cloud Run 동시성·타임아웃 | 미흡 | §5.2. 문서에 미기재 → **TODO-007** |
| AI Cloud Run 동시성·min/max | 미흡 | §5.2. cloudbuild에 동시성·min/max 없음. 타임아웃 120s만 명시 |

### 관측성

| 항목 | 현재 상태 | 참고 섹션 / TODO |
|------|-----------|-------------------|
| 헬스체크 엔드포인트 | OK | §6.1. BE /actuator/health, AI /health |
| 로그 레벨·구조 | OK (기본 수준) | §6.2. GlobalExceptionHandler 등 앱 로그 존재. 전용 구조화 로그/트레이스 미설정 |
| 알람/대시보드 | 미구현 | §6.2. Cloud Monitoring 알람/대시보드 없음 → **TODO-006** |

### 보안

| 항목 | 현재 상태 | 참고 섹션 / TODO |
|------|-----------|-------------------|
| 시크릿 관리 방식 | OK | §2, §3.2. Secret Manager 사용, BE는 --set-secrets 주입. 카카오 미등록 → **TODO-001** |
| 서비스 계정 권한 | OK (문서 기준) | §4.3. 역할 문서화됨 |
| 공개 엔드포인트 보호 | OK (BE/AI) | §4.2. BE는 JWT·permitAll 구분, AI는 --no-allow-unauthenticated. CORS는 SecurityConfig에서 설정 (§4.2) |

### 데이터

| 항목 | 현재 상태 | 참고 섹션 / TODO |
|------|-----------|-------------------|
| DB 백업/복구 전략 | 미문서화 | 레포/문서에 Cloud SQL 백업·복구 절차 없음. (문서에 있으면 §2·§3에 반영 권장) |
| DB 스키마 변경 정책 | OK (문서 반영됨) | §3.1. prod ddl-auto: validate. 스키마 변경 시 수동 DDL/Flyway 등 문서화 권장 |

---

**문서 끝.**  
*(실제 시크릿 값은 전부 미기재. 이름·용도·흐름만 기술.)*
