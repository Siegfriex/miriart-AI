# GCS Signed URL 인프라 실행 보고서 — 2026-03-10

> **기준 지침**: CTO Signed URL 실행 지침 (§3~§4)
> **실행 주체**: INFRA_DEV 에이전트 (Claude Code)
> **환경**: WSL Ubuntu-24.04, gcloud CLI, 프로젝트 `miriarts`

---

## 1. 실행 요약

| 구분 | 항목 | 상태 |
|------|------|------|
| §4.1 SA·권한 설정 | BE SA tokenCreator 부여 | ✅ 완료 |
| §4.3 CORS 설정 | GCS 버킷 CORS 적용 | ✅ 완료 |
| §3 AI 코드 검증 | 경로/에러/구조 확인 | ✅ 변경 불필요 확인 |
| §4.2 정책/TTL/경로 | SSOT §3.4 반영 | ✅ 완료 |
| §4.4 관측성 | BE 코드 구현 후 메트릭 생성 예정 | ⏸️ 대기 |
| SSOT 갱신 | miriarts_infra.md, Runbook 업데이트 | ✅ 완료 |

---

## 2. §4.1 SA·권한 설정 (A안 채택)

### 2.1 실행 전 BE SA 권한 (실측)

```
gcloud projects get-iam-policy miriarts \
  --flatten="bindings[].members" \
  --filter="bindings.members:miriart-be-runner@miriarts.iam.gserviceaccount.com" \
  --format="table(bindings.role)"

ROLE
roles/cloudsql.client
roles/run.invoker
roles/secretmanager.secretAccessor
roles/storage.objectAdmin
```

```
gcloud iam service-accounts get-iam-policy \
  miriart-be-runner@miriarts.iam.gserviceaccount.com --project=miriarts

etag: ACAB    ← 바인딩 없음 (tokenCreator 미부여)
```

> **V4 Signed URL에는 `iam.serviceAccounts.signBlob` 권한이 필요하며, 이는 `roles/iam.serviceAccountTokenCreator`에 포함.**
> BE SA에 이 역할이 없어 Signed URL 생성 불가 상태였음.

### 2.2 실행

```bash
gcloud iam service-accounts add-iam-policy-binding \
  miriart-be-runner@miriarts.iam.gserviceaccount.com \
  --project=miriarts \
  --member="serviceAccount:miriart-be-runner@miriarts.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

### 2.3 검증

```
gcloud iam service-accounts get-iam-policy \
  miriart-be-runner@miriarts.iam.gserviceaccount.com --project=miriarts

bindings:
- members:
  - serviceAccount:miriart-be-runner@miriarts.iam.gserviceaccount.com
  role: roles/iam.serviceAccountTokenCreator
etag: BwZMpBjGsBY=
version: 1
```

| 항목 | Before | After |
|------|--------|-------|
| `roles/iam.serviceAccountTokenCreator` | ❌ 없음 | ✅ **자기 자신에게 바인딩** |

> **자기 자신 바인딩**: BE SA가 자신의 signBlob만 호출 가능. 다른 SA 토큰 생성 불가. 보안 범위 최소화.

### 2.4 조직 정책 충돌 확인

| 조직 정책 | 결과 |
|-----------|------|
| `iam.allowedPolicyMemberDomains` | ❌ 충돌 없음. SA는 프로젝트 내부 멤버 |
| `storage.publicAccessPrevention` | ❌ 충돌 없음. Signed URL ≠ public access |

---

## 3. §4.3 CORS 설정

### 3.1 실행 전 상태

```
gcloud storage buckets describe gs://miriart-bucket --format="yaml(cors_config)"

(출력 없음 — CORS 미설정)
```

### 3.2 실행

```bash
# /tmp/cors.json
[
  {
    "origin": ["https://miriart.app", "http://localhost:3000"],
    "method": ["GET"],
    "responseHeader": ["Content-Type", "Content-Length"],
    "maxAgeSeconds": 3600
  }
]

gcloud storage buckets update gs://miriart-bucket --cors-file=/tmp/cors.json
```

### 3.3 검증

```
gcloud storage buckets describe gs://miriart-bucket --format="yaml(cors_config)"

cors_config:
- maxAgeSeconds: 3600
  method:
  - GET
  origin:
  - https://miriart.app
  - http://localhost:3000
  responseHeader:
  - Content-Type
  - Content-Length
```

| 항목 | Before | After |
|------|--------|-------|
| CORS | 미설정 | ✅ GET, origin 2개, maxAge 3600s |

---

## 4. §3 AI 코드 검증 (실코드 라인 인용)

### 4.1 GCS 업로드 — `upload_bytes` 반환값 확인

> **파일**: `app/services/gcs_service.py:51-60`

```python
    def upload_bytes(
        self,
        blob_path: str,
        data: bytes,
        content_type: str = "image/jpeg",
    ) -> str:
        """bytes를 GCS에 업로드 후 공개 URL 반환. image_edit_service에서 사용."""
        blob = self._bucket.blob(blob_path)
        blob.upload_from_string(data, content_type=content_type)
        return f"https://storage.googleapis.com/{self._bucket_name}/{blob_path}"
```

**분석**:
- `:60` — `https://storage.googleapis.com/{bucket}/{path}` 형태 URL 반환.
- 이 URL은 **버킷이 비공개이므로 외부에서 403**. FE 직접 사용 불가.
- **정책 준수**: 이 URL은 BE가 `image_url` 필드로 받아 **내부 식별/메타용**으로만 사용. FE에는 Signed URL로 변환하여 전달.

### 4.2 이미지 편집 경로 패턴

> **파일**: `app/services/image_edit_service.py:62-68`

```python
    image_url: str | None = None
    if edited_image_bytes:
        blob_path = f"edited/{uuid.uuid4()}.jpg"
        try:
            image_url = gcs.upload_bytes(blob_path, edited_image_bytes, content_type=edited_mime)
        except Exception as e:
            raise GCSError(f"GCS 업로드 실패: {e}")
```

**분석**:
- `:64` — 경로 패턴: `edited/{uuid}.jpg`. 날짜 세그먼트 없음.
- 제안서 규칙(`edited/{date}/{uuid}_{filename}`)과 차이 있으나, **현재 코드 기준으로 SSOT에 기록** 완료 (`miriarts_infra.md:305`).
- BE의 Signed URL prefix 검증은 `edited/` prefix까지만 체크하면 양쪽 패턴 모두 커버.

### 4.3 응답 스키마 — `image_url` Optional 유지

> **파일**: `app/schemas/image_edit.py:23-29`

```python
class InternalImageEditResponse(BaseModel):
    """이미지 편집 응답. AI 코멘트 텍스트와 GCS에 저장된 결과 이미지 URL."""

    model_config = _CAMEL

    text: str
    image_url: Optional[str] = None
```

**분석**:
- `:29` — `image_url: Optional[str] = None`. 이미지 편집 실패 시 `None` 반환 가능.
- JSON 구조 깨지지 않음 (Pydantic serialize → `"imageUrl": null`).
- **정책 준수**: camelCase 직렬화(`_CAMEL`) 적용. BE ↔ AI 계약 유지.

### 4.4 에러 코드 — GCS 실패 시 502 GCS_ERROR 유지

> **파일**: `app/core/exceptions.py:39-43`

```python
class GCSError(MiriArtAIError):
    """GCS 다운로드/업로드 실패. BE에서 F003(GCS 오류)로 매핑."""

    def __init__(self, message: str):
        super().__init__(message, error_code="GCS_ERROR")
```

> **파일**: `app/core/error_handler.py:31`

```python
    GCSError: (502, "GCS_ERROR"),
```

**분석**:
- GCS 관련 실패 → HTTP 502 + `"code": "GCS_ERROR"` 응답.
- BE는 이를 `F003` ErrorCode로 매핑 (API_CONTRACT §9).
- **정책 준수**: 에러 코드 일관성 유지 확인.

### 4.5 AI generate_signed_url (참고 — 현재 미사용)

> **파일**: `app/services/gcs_service.py:32-49`

```python
    def generate_signed_url(
        self, blob_path: str, expiration_minutes: int = 60
    ) -> str:
        """Phase 2용. miriart-ai-runner SA로 v4 signed URL 생성."""
        source_creds, _ = default()
        signing_creds = impersonated_credentials.Credentials(
            source_credentials=source_creds,
            target_principal=f"miriart-ai-runner@{self._project_id}.iam.gserviceaccount.com",
            target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        blob = self._bucket.blob(blob_path)
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=expiration_minutes),
            method="GET",
            credentials=signing_creds,
        )
        return url
```

**분석**:
- AI SA(`miriart-ai-runner`) impersonate 방식으로 Signed URL 생성.
- **현재 미사용**. Signed URL 생성은 BE(Java)에서 `miriart-be-runner` SA로 수행하므로, AI 쪽 이 메서드는 호출되지 않음.
- 코드 제거 불필요 — 향후 AI에서 직접 Signed URL이 필요한 경우 재활용 가능.

### 4.6 GCS 설정 — 버킷/프로젝트 설정값

> **파일**: `app/core/config.py:21-24`

```python
    gcp_project_id: str = "miriart-dev"
    gcp_region: str = "asia-northeast3"
    gcs_bucket_name: str = "miriart-bucket"
    google_application_credentials: str = ""
```

> **파일**: `cloudbuild.yaml:40`

```yaml
      - '--set-env-vars=GCP_PROJECT_ID=miriarts,GCP_REGION=asia-northeast3,GCS_BUCKET_NAME=miriart-bucket'
```

**분석**:
- 로컬 기본값: `gcp_project_id=miriart-dev`, `gcs_bucket_name=miriart-bucket`.
- Cloud Run: 환경변수로 `GCP_PROJECT_ID=miriarts` 오버라이드 (`:40`).
- 버킷명은 dev/prod 모두 `miriart-bucket`으로 동일.

### 4.7 AI 진입점 — 내부 전용 확인

> **파일**: `app/main.py:44`

```python
app.include_router(ai.router, prefix="/internal/ai", tags=["AI Internal"])
```

> **파일**: `app/main.py:33-39`

```python
app = FastAPI(
    title="MiriArt AI Service",
    version="1.0.0",
    description="MiriArt 내부 AI 서비스 (Java BE → FastAPI). FE 직접 접근 불가.",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)
```

**분석**:
- `:44` — 모든 AI 엔드포인트는 `/internal/ai/*` prefix. BE만 호출.
- `:37-38` — Swagger/ReDoc 비활성화 (내부 서비스이므로).
- Cloud Run IAM(`invoker-iam-check`)으로 외부 접근 403 차단 (`:37-38` of `cloudbuild.yaml`).

---

## 5. §4.2 정책/TTL/경로 — SSOT 반영 결과

### SSOT에 반영된 내용

> **파일**: `SSOT/miriarts_infra.md:279-308` (§3.4 이미지 전달 정책)

| 항목 | SSOT 기록 값 | 근거 |
|------|-------------|------|
| 전달 방식 | GCS V4 Signed URL (BE에서만 생성) | CTO 지침 §4.1 |
| BE 엔드포인트 | `GET /api/images/{id}/url` | CTO 지침 §4 |
| 서명 SA | `miriart-be-runner` | A안 채택 |
| 유효기간 | 15분 | CTO 지침 §4.2 |
| 허용 Method | GET | CTO 지침 §4.2 |
| 허용 경로 prefix | `artworks/`, `edited/`, `analyses/` | CTO 지침 §4.2 |
| CORS | GET, origin 2개 | CTO 지침 §4.3 |

### GCS 경로 패턴 — 코드 vs 규칙 대조

| 규칙 (§4.2) | 실코드 | 파일:라인 | 일치 |
|-------------|--------|-----------|------|
| `artworks/{date}/{uuid}_{filename}` | `artworks/2026-03-03/aa8ac12c-..._IMG_6728.jpeg` | GCS 실측 | ✅ |
| `edited/{date}/{uuid}_{filename}` | `edited/{uuid}.jpg` | `image_edit_service.py:64` | ⚠️ date 세그먼트 없음 |
| `analyses/**` | (향후) | — | — |

> **영향 없음**: BE의 Signed URL prefix 검증은 `edited/`까지만 체크하면 양쪽 패턴 모두 커버됨.

---

## 6. GCS 버킷 최종 상태 (실측)

### 6.1 버킷 설정

```
gcloud storage buckets describe gs://miriart-bucket

location: ASIA-NORTHEAST3
uniform_bucket_level_access: true
public_access_prevention: inherited
```

### 6.2 버킷 IAM 정책

```
gcloud storage buckets get-iam-policy gs://miriart-bucket

bindings:
- members:
  - projectEditor:miriarts
  - projectOwner:miriarts
  role: roles/storage.legacyBucketOwner
- members:
  - projectViewer:miriarts
  role: roles/storage.legacyBucketReader
- members:
  - projectEditor:miriarts
  - projectOwner:miriarts
  role: roles/storage.legacyObjectOwner
- members:
  - projectViewer:miriarts
  role: roles/storage.legacyObjectReader
- members:
  - serviceAccount:miriart-ai-runner@miriarts.iam.gserviceaccount.com
  - serviceAccount:miriart-be-runner@miriarts.iam.gserviceaccount.com
  role: roles/storage.objectAdmin
```

> **allUsers 바인딩 없음** — 공개 접근 차단 유지.

### 6.3 imageUrl 접근 테스트

```
curl -s -o /dev/null -w "%{http_code}" \
  "https://storage.googleapis.com/miriart-bucket/artworks/2026-03-03/aa8ac12c-0d06-4525-9342-982d4c8b43df_IMG_6728.jpeg"

→ 403  ✅ (정상 — 비공개)
```

### 6.4 샘플 오브젝트

```
gcloud storage objects describe \
  gs://miriart-bucket/artworks/2026-03-03/aa8ac12c-..._IMG_6728.jpeg

size: 165773  (≈162 KB)
```

---

## 7. SA 최종 상태 (실측)

### miriart-be-runner

```
# 프로젝트 레벨 역할
gcloud projects get-iam-policy miriarts --filter="...miriart-be-runner..."

roles/cloudsql.client
roles/run.invoker
roles/secretmanager.secretAccessor
roles/storage.objectAdmin

# SA 레벨 바인딩 (자기 자신)
gcloud iam service-accounts get-iam-policy miriart-be-runner@...

bindings:
- members:
  - serviceAccount:miriart-be-runner@miriarts.iam.gserviceaccount.com
  role: roles/iam.serviceAccountTokenCreator    ← 신규 (이번 실행)
```

### miriart-ai-runner

```
# 프로젝트 레벨 역할
roles/aiplatform.expressUser
roles/aiplatform.user
roles/storage.objectAdmin

# SA 레벨 바인딩 (자기 자신)
bindings:
- members:
  - serviceAccount:miriart-ai-runner@miriarts.iam.gserviceaccount.com
  role: roles/iam.serviceAccountTokenCreator    ← 기존 (TASK-C2)
```

> SSOT `miriarts_infra.md:397-398` (§4.3)에 양쪽 SA 모두 반영 완료.

---

## 8. SSOT/Runbook 갱신 내역

| 문서 | 섹션 | 변경 내용 | 라인 |
|------|------|-----------|------|
| `miriarts_infra.md` | §3.4 (신규) | 이미지 전달 정책: Signed URL 방식, TTL 15분, 경로 prefix, CORS, 원칙 3개 | `:279-308` |
| `miriarts_infra.md` | §2 GCS 버킷 | CORS 설정 반영, Signed URL §3.4 참조 추가 | `:146` |
| `miriarts_infra.md` | §4.3 SA | `miriart-be-runner`에 `roles/iam.serviceAccountTokenCreator` 추가 | `:397` |
| `RUNBOOK_AI_INFRA_v1.md` | §4 Step 2 | Signed URL 관련 장애 증상 4건 추가 (이미지 403, CORS, 서명 실패, 404) | 증상 표 |
| `RUNBOOK_AI_INFRA_v1.md` | §6 | GCS Signed URL 디버깅 명령어 블록 추가 | 운영 명령어 |
| `RUNBOOK_AI_INFRA_v1.md` | §7 | GCS imageUrl 항목 상태 갱신: "인프라 준비 완료, BE 코드 구현 대기" | 제약사항 |
| `CHANGELOG_infra.md` | 최신 항목 | 전체 실행 내역 5줄 기록 | 최상단 |

---

## 9. AI 코드 변경 판정

| 판정 항목 | 결과 | 근거 (파일:라인) |
|-----------|------|-----------------|
| `upload_bytes` 반환값 변경 | **불필요** | `gcs_service.py:60` — URL은 BE 내부 식별용. Signed URL은 BE에서 생성. |
| `image_url` 스키마 변경 | **불필요** | `image_edit.py:29` — `Optional[str]` 유지. BE가 이 값으로 objectPath를 추출하여 Signed URL 생성. |
| 에러 코드 변경 | **불필요** | `exceptions.py:43`, `error_handler.py:31` — GCSError → 502 GCS_ERROR 유지. |
| 경로 패턴 변경 | **불필요 (현시점)** | `image_edit_service.py:64` — `edited/{uuid}.jpg`. prefix `edited/`가 정책 범위 내. |
| `generate_signed_url` 메서드 | **불필요 (미사용 유지)** | `gcs_service.py:32-49` — BE에서 서명하므로 AI 미사용. 제거 불필요. |
| CORS 미들웨어 추가 | **불필요** | `main.py:44` — AI는 내부 전용(`/internal/ai/*`). FE 직접 접근 없음. |

**결론: AI(FastAPI) 코드 변경 0건. 현재 구조 그대로 유지.**

---

## 10. BE(Java) 구현 시 인프라 전달 사항

인프라 측 준비는 모두 완료. BE 개발자에게 전달할 내용:

### 10.1 Java 코드 패턴 (A안 — 직접 서명)

```java
// Cloud Run에서 SA 자동 주입 — 별도 credential 불필요
Storage storage = StorageOptions.getDefaultInstance().getService();

BlobInfo blobInfo = BlobInfo.newBuilder("miriart-bucket", objectPath).build();
URL signedUrl = storage.signUrl(blobInfo, 15, TimeUnit.MINUTES,
    Storage.SignUrlOption.withV4Signature());
```

### 10.2 objectPath 추출

AI 응답의 `imageUrl` 예시:
```
https://storage.googleapis.com/miriart-bucket/edited/a1b2c3d4-...jpg
```

BE에서 objectPath 추출:
```java
String objectPath = imageUrl.replace(
    "https://storage.googleapis.com/miriart-bucket/", "");
// → "edited/a1b2c3d4-...jpg"
```

### 10.3 prefix 검증 (필수)

```java
List<String> ALLOWED_PREFIXES = List.of("artworks/", "edited/", "analyses/");

boolean valid = ALLOWED_PREFIXES.stream().anyMatch(objectPath::startsWith);
if (!valid) throw new InvalidImagePathException(objectPath);
```

### 10.4 의존성

```gradle
implementation 'com.google.cloud:google-cloud-storage:2.x.x'
```

> BE에 이미 `google-cloud-storage` 의존성이 있다면 추가 불필요.

---

## 11. §4.4 관측성 — 대기 항목

BE 코드에서 구조화 로그 출력 후 실행할 gcloud 명령어:

```bash
# Signed URL 생성 카운트
gcloud logging metrics create miriart-be-signed-url-count \
  --project=miriarts \
  --description="Signed URL generation count" \
  --log-filter='resource.type="cloud_run_revision" AND resource.labels.service_name="miriart-be" AND jsonPayload.message="signed_url_generated"'

# Signed URL 생성 에러
gcloud logging metrics create miriart-be-signed-url-errors \
  --project=miriarts \
  --description="Signed URL generation errors" \
  --log-filter='resource.type="cloud_run_revision" AND resource.labels.service_name="miriart-be" AND jsonPayload.message="signed_url_error"'
```

> BE에서 `{"message":"signed_url_generated","path":"...","ttl":900}` 형태 로그를 출력해야 메트릭이 수집됨.

---

*보고 완료. 2026-03-10, INFRA_DEV 에이전트.*
