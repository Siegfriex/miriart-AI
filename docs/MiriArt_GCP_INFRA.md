# MiriArt GCP 인프라 명세서 v1.2

> **작성일**: 2026-02-22 | **최종 업데이트**: 2026-02-22 (v1.2 - BE 배포 완료)
> **GCP 프로젝트명**: miriart | **GCP 프로젝트 ID**: `miriarts`
> **리전**: asia-northeast3 (서울)
> **세팅 상태**: ✅ 인프라 완료 | ✅ BE 실제 배포 완료 | ⏳ 카카오 OAuth 미등록 | ✅ FE URL 등록 완료

---

## 1. 활성화된 API 목록

| API 이름 | 서비스 ID | 용도 | 상태 |
|----------|-----------|------|------|
| Cloud Run API | `run.googleapis.com` | BE/AI 서비스 배포 | ✅ |
| Cloud Build API | `cloudbuild.googleapis.com` | CI/CD 파이프라인 | ✅ |
| Artifact Registry API | `artifactregistry.googleapis.com` | Docker 이미지 저장 | ✅ |
| Cloud Storage API | `storage.googleapis.com` | 이미지 파일 저장 | ✅ |
| Vertex AI API | `aiplatform.googleapis.com` | Gemini Vision, Chat | ✅ |
| Cloud SQL Admin API | `sqladmin.googleapis.com` | MySQL (Cloud SQL) | ✅ |
| Secret Manager API | `secretmanager.googleapis.com` | 환경변수/시크릿 관리 | ✅ |
| IAM API | `iam.googleapis.com` | 서비스 계정 관리 | ✅ |
| Cloud Resource Manager API | `cloudresourcemanager.googleapis.com` | 프로젝트 정책 | ✅ |
| Compute Engine API | `compute.googleapis.com` | VPC 네트워크 | ✅ |
| Service Networking API | `servicenetworking.googleapis.com` | Private IP (Cloud SQL) | ✅ |
| Redis (Memorystore) API | `redis.googleapis.com` | Memorystore for Redis | ✅ |

**Phase C5 추가 예정**: Firebase Cloud Messaging API (`fcm.googleapis.com`)

---

## 2. 서비스 계정 목록

| 계정 ID | 이메일 | 용도 | 상태 |
|---------|--------|------|------|
| `miriart-ai-runner` | `miriart-ai-runner@miriarts.iam.gserviceaccount.com` | FastAPI AI Cloud Run 런타임 | ✅ |
| `miriart-be-runner` | `miriart-be-runner@miriarts.iam.gserviceaccount.com` | Java BE Cloud Run 런타임 | ✅ |
| `miriart-cloudbuild` | `miriart-cloudbuild@miriarts.iam.gserviceaccount.com` | CI/CD 파이프라인 | ✅ |
| `miriart-local-dev` | `miriart-local-dev@miriarts.iam.gserviceaccount.com` | 로컬 개발용 (키파일 발급) | ✅ |

### IAM 바인딩 상세

| 서비스 계정 | 역할 | 용도 |
|-------------|------|------|
| `miriart-ai-runner` | `roles/aiplatform.user` | Gemini API 호출 |
| `miriart-ai-runner` | `roles/storage.objectAdmin` | GCS 읽기/쓰기 |
| `miriart-be-runner` | `roles/storage.objectAdmin` | GCS 이미지 업로드 |
| `miriart-be-runner` | `roles/run.invoker` | AI Cloud Run 내부 호출 |
| `miriart-be-runner` | `roles/cloudsql.client` | Cloud SQL 연결 |
| `miriart-be-runner` | `roles/secretmanager.secretAccessor` | Secret Manager 읽기 |
| `miriart-cloudbuild` | `roles/run.admin` | Cloud Run 배포 |
| `miriart-cloudbuild` | `roles/iam.serviceAccountUser` | 서비스 계정 위임 |
| `miriart-cloudbuild` | `roles/artifactregistry.writer` | 이미지 푸시 |
| `miriart-cloudbuild` | `roles/storage.objectAdmin` | Build 캐시 접근 |
| `miriart-local-dev` | `roles/aiplatform.user` | 로컬 Gemini 테스트 |
| `miriart-local-dev` | `roles/storage.objectAdmin` | 로컬 GCS 테스트 |

### 2.1 로컬 개발용 서비스 계정 키 가져오기 (miriart-ai)

miriart-ai 로컬 실행 시 Vertex AI·GCS 인증에 **`miriart-local-dev`** 키 파일을 사용한다.  
`.env`의 `GOOGLE_APPLICATION_CREDENTIALS`가 해당 JSON 경로를 가리키면 된다. (참고: `.env.example`, 본 문서 §9.2, §11.)

**방법 A — gcloud CLI (WSL 권장)**

```bash
# 프로젝트 설정
export PROJECT_ID=miriarts

# 키 파일 생성 (현 디렉터리에 service-account.json으로 저장)
gcloud iam service-accounts keys create ./service-account.json \
  --iam-account=miriart-local-dev@${PROJECT_ID}.iam.gserviceaccount.com \
  --project=${PROJECT_ID}
```

생성 후 프로젝트 루트에 `service-account.json`이 있으면 `.env`에 `GOOGLE_APPLICATION_CREDENTIALS=./service-account.json` 로 지정.

**방법 B — GCP 콘솔**

1. [GCP 콘솔](https://console.cloud.google.com/) → **IAM 및 관리자** → **서비스 계정**
2. 프로젝트 `miriarts` 선택 후 **miriart-local-dev** 클릭
3. **키** 탭 → **키 추가** → **새 키 만들기** → **JSON** 선택 후 만들기
4. 다운로드된 JSON을 프로젝트 루트에 복사 후 `service-account.json` 등으로 두고 `.env`에 경로 설정

**주의**: 키 파일은 `.gitignore`에 포함됨(`service-account*.json`). Git에 커밋하지 말 것.

---

## 3. GCS 버킷

| 버킷명 | 용도 | 접근 정책 | 상태 |
|--------|------|-----------|------|
| `miriart-bucket` | 작품/편집/프로필 이미지 | 비공개 (서비스 계정만) | ✅ |
| `miriart-build-cache` | Cloud Build 캐시 | Cloud Build만 | ✅ |

**`miriart-bucket` 폴더 구조**:
```
miriart-bucket/
├── artworks/{userId}/{YYYY-MM-DD}/{uuid}_{filename}   ← 작품 원본
├── edited/{uuid}.jpg                                   ← AI 편집 결과
├── community/{postId}/{uuid}_{filename}               ← 커뮤니티 첨부 (Phase C)
└── profiles/{userId}/avatar.jpg                       ← 프로필 이미지 (Phase 2)
```

---

## 4. Cloud Run 서비스

| 서비스명 | URL | 인증 | 서비스 계정 | 상태 |
|----------|-----|------|-------------|------|
| `miriart-ai` | `https://miriart-ai-946560105497.asia-northeast3.run.app` | 비공개 (내부 전용) | `miriart-ai-runner` | ✅ placeholder |
| `miriart-be` | `https://miriart-be-946560105497.asia-northeast3.run.app` | JWT 검증 | `miriart-be-runner` | ✅ **실제 배포 완료** (rev: miriart-be-00013-l6j) |

**miriart-be 최신 배포 정보:**
- 이미지: `asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-be:latest`
- 리비전: `miriart-be-00013-l6j`
- `ddl-auto: validate` (DB 스키마 생성 완료, 운영 고정)
- VPC 커넥터: `miriart-connector` (Redis 접근용)
- Cloud SQL 연결: `miriarts:asia-northeast3:miriart-mysql` (Socket Factory)

---

## 5. Cloud SQL (MySQL 8.0)

| 항목 | 값 |
|------|-----|
| 인스턴스명 | `miriart-mysql` |
| 데이터베이스명 | `miriart_prod` |
| 사용자 | `miriart` |
| Private IP | `10.99.0.3` (인스턴스 네트워크) |
| 포트 | `3306` |
| 리전 | `asia-northeast3` |
| **Cloud Run BE 연결 방식** | **Socket Factory** (Unix 소켓). `--add-cloudsql-instances=miriarts:asia-northeast3:miriart-mysql`. JDBC URL은 Secret `miriart-db-url`에 소켓 방식으로 저장. Private IP 직결 아님. |
| charset | `utf8mb4` / `utf8mb4_unicode_ci` |
| JDBC URL (참고) | BE는 `DB_URL`(Secret) 사용. 소켓 방식 예: `jdbc:mysql:///miriart_prod?cloudSqlInstance=miriarts:asia-northeast3:miriart-mysql&socketFactory=...` (실제 값은 Secret Manager). 인스턴스 자체는 VPC 피어링으로 Private IP 보유. |

---

## 6. Memorystore Redis

| 항목 | 값 |
|------|-----|
| 인스턴스명 | `miriart-redis` |
| 버전 | Redis 7.0 |
| Private IP | `10.15.105.203` |
| 포트 | `6379` |
| 메모리 | 1GB |
| 리전 | `asia-northeast3` |

---

## 7. Artifact Registry

| 저장소명 | 형식 | 리전 | 상태 |
|----------|------|------|------|
| `miriart-images` | Docker | `asia-northeast3` | ✅ |

이미지 경로 규칙:
```
asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:latest
asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-be:latest
```

---

## 8. Secret Manager 시크릿 현황

| 시크릿 ID | 용도 | 사용 서비스 | 등록 상태 |
|-----------|------|------------|-----------|
| `miriart-jwt-access-secret` | JWT Access Token 서명 키 | miriart-be | ✅ 등록 완료 (오염 없음 검증) |
| `miriart-jwt-refresh-secret` | JWT Refresh Token 서명 키 | miriart-be | ✅ 등록 완료 (오염 없음 검증) |
| `miriart-db-url` | MySQL JDBC URL (소켓 방식) | miriart-be | ✅ 등록 완료 (소켓 URL 검증) |
| `miriart-db-username` | MySQL 사용자명 | miriart-be | ✅ 등록 완료 |
| `miriart-db-password` | MySQL 비밀번호 | miriart-be | ✅ 등록 완료 (오염 없음 검증) |
| `miriart-redis-host` | Redis 호스트 IP | miriart-be | ✅ 등록 완료 (`10.15.105.203`) |
| `miriart-google-client-id` | 구글 OAuth2 Client ID | miriart-be | ✅ 등록 완료 |
| `miriart-google-client-secret` | 구글 OAuth2 Secret | miriart-be | ✅ 등록 완료 |
| `miriart-frontend-oauth-url` | OAuth 성공 후 FE 리다이렉트 URL (도메인만, 경로 없음) | miriart-be | ✅ 등록 완료. 코드가 baseUrl + "/auth/callback?code=" 를 사용하므로 Secret 값은 `https://miri-art.vercel.app` 형태(도메인만). |
| `miriart-kakao-client-id` | 카카오 OAuth2 Client ID | miriart-be | ⏳ 미등록 (placeholder) |
| `miriart-kakao-client-secret` | 카카오 OAuth2 Secret | miriart-be | ⏳ 미등록 (placeholder) |

---

## 9. 환경변수 전체 매핑

### 9.1 Java BE (Spring Boot) — `application-dev.yml` 기준

| Spring Boot 환경변수 | Secret Manager ID | 로컬 기본값 | 비고 |
|----------------------|-------------------|-------------|------|
| `DB_URL` | `miriart-db-url` | `jdbc:mysql://localhost:3306/miriart_dev` | |
| `DB_USERNAME` | `miriart-db-username` | `root` | |
| `DB_PASSWORD` | `miriart-db-password` | `password` | |
| `REDIS_HOST` | `miriart-redis-host` | `localhost` | |
| `GOOGLE_CLIENT_ID` | `miriart-google-client-id` | `dev-google-id` | ✅ |
| `GOOGLE_CLIENT_SECRET` | `miriart-google-client-secret` | `dev-google-secret` | ✅ |
| `KAKAO_CLIENT_ID` | `miriart-kakao-client-id` | `dev-kakao-id` | ⏳ |
| `KAKAO_CLIENT_SECRET` | `miriart-kakao-client-secret` | `dev-kakao-secret` | ⏳ |
| `JWT_ACCESS_SECRET` | `miriart-jwt-access-secret` | (Base64 로컬값) | ✅ |
| `JWT_REFRESH_SECRET` | `miriart-jwt-refresh-secret` | (Base64 로컬값) | ✅ |
| `FRONTEND_OAUTH_SUCCESS_URL` | `miriart-frontend-oauth-url` | `http://localhost:5173` | ⏳ |
| `FASTAPI_INTERNAL_URL` | (Secret 없음, Cloud Run 환경변수) | `http://localhost:8000` | Cloud Run URL |
| `GCS_BUCKET_NAME` | (Secret 없음, 고정값) | `miriart-bucket` | |

### 9.2 FastAPI AI — `.env` 기준

| 환경변수 | 값 | 비고 |
|----------|-----|------|
| `GCP_PROJECT_ID` | `miriarts` | |
| `GCP_REGION` | `asia-northeast3` | |
| `GCS_BUCKET_NAME` | `miriart-bucket` | |
| `GOOGLE_APPLICATION_CREDENTIALS` | `./service-account-dev.json` | 로컬 전용, Cloud Run 불필요 |

---

## 10. OAuth 2.0 설정

### Google OAuth
| 항목 | 값 |
|------|-----|
| Client ID | `YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com` (GCP 콘솔에서 발급) |
| 승인된 JavaScript 원본 | `https://miri-art.vercel.app`, `http://localhost:5173` |
| 승인된 리다이렉트 URI (로컬) | `http://localhost:8080/login/oauth2/code/google` |
| 승인된 리다이렉트 URI (운영) | `https://miriart-be-946560105497.asia-northeast3.run.app/login/oauth2/code/google` ← 배포 후 추가 필요 |

### Kakao OAuth
| 항목 | 값 |
|------|-----|
| 상태 | ⏳ 미발급 |
| 리다이렉트 URI | `http://localhost:8080/login/oauth2/code/kakao` (로컬) |

---

## 11. 로컬 개발 환경 설정

### miriart-ai `.env`
```env
GCP_PROJECT_ID=miriarts
GCP_REGION=asia-northeast3
GCS_BUCKET_NAME=miriart-bucket
GOOGLE_APPLICATION_CREDENTIALS=./service-account-dev.json
```

### miriart-be `.env` (로컬 오버라이드용)
```env
# DB
DB_URL=jdbc:mysql://localhost:3306/miriart_dev
DB_USERNAME=root
DB_PASSWORD=password

# Redis
REDIS_HOST=localhost

# Google OAuth (.env에 실제값 입력, 이 파일은 Git 커밋 금지)
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-your-secret

# Kakao OAuth (미발급)
KAKAO_CLIENT_ID=
KAKAO_CLIENT_SECRET=

# JWT (openssl rand -base64 64 또는 Secret Manager 값으로 .env에 입력)
JWT_ACCESS_SECRET=your-base64-access-secret
JWT_REFRESH_SECRET=your-base64-refresh-secret

# FE 리다이렉트
FRONTEND_OAUTH_SUCCESS_URL=http://localhost:5173

# FastAPI AI 서비스
FASTAPI_INTERNAL_URL=http://localhost:8000

# GCS
GCS_BUCKET_NAME=miriart-bucket
```

### .gitignore 필수 항목
```gitignore
# GCP 서비스 계정 키
service-account-dev.json
service-account*.json

# 환경변수
.env
.env.local
*.env.local

# Google OAuth 다운로드 파일
client_secret_*.json
```

---

## 12. 잔여 TODO

| 항목 | 우선순위 | 비고 |
|------|----------|------|
| ⏳ 카카오 OAuth 발급 → Secret Manager 등록 | High | 카카오 개발자 콘솔 (`miriart-kakao-client-id`, `miriart-kakao-client-secret`) |
| ⏳ Google OAuth 운영 리다이렉트 URI 추가 | Medium | `https://miriart-be-946560105497.asia-northeast3.run.app/login/oauth2/code/google` |
| ⏳ FastAPI AI 실제 이미지 빌드 + Cloud Run 배포 | High | `miriart-ai` Dockerfile 사용, 현재 placeholder |
| ⏳ cloudbuild.yaml CI/CD 파이프라인 작성 | Medium | AI/BE 자동 배포 (miriart-ai에 cloudbuild.yaml 존재, BE 미작성) |

**완료된 항목 (2026-02-22):**
- ✅ Java BE 실제 이미지 빌드 + Cloud Run 배포 완료 (rev: miriart-be-00013-l6j)
- ✅ FE OAuth 성공 URL Secret 등록 완료 (`https://miri-art.vercel.app/auth/callback`)
- ✅ DB 스키마 생성 완료 (`miriart_prod` 내 9개 테이블: users, analyses, analysis_usage_logs, posts, personas, comments, answers, likes, reputation_ledger)
- ✅ Secret Manager 전수 검증 완료 (오염 없음)
