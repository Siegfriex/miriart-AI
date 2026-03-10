# GCS Signed URL 인프라 제안서 — 2026-03-10

> **목적**: BE(Java)가 GCS v4 Signed URL 기반 이미지 전달을 구현하기 위한 인프라/보안/정책 준비
> **대상 버킷**: `miriart-bucket` (asia-northeast3)
> **실행 주체**: INFRA_DEV 에이전트

---

## 1. GCS/SA 권한 검토 (Signed URL 전제 확인)

### 1.1 현재 SA 권한 상태 (실측)

#### miriart-be-runner (BE 실행 SA)

| 권한 | 범위 | 용도 |
|------|------|------|
| `roles/storage.objectAdmin` | 프로젝트 + 버킷 | GCS 읽기/쓰기/삭제 |
| `roles/cloudsql.client` | 프로젝트 | Cloud SQL 접속 |
| `roles/run.invoker` | 프로젝트 | AI Cloud Run 호출 |
| `roles/secretmanager.secretAccessor` | 프로젝트 | Secret Manager 읽기 |
| `roles/iam.serviceAccountTokenCreator` | **없음** | ❌ signBlob 불가 |

#### miriart-ai-runner (AI 실행 SA)

| 권한 | 범위 | 용도 |
|------|------|------|
| `roles/storage.objectAdmin` | 프로젝트 + 버킷 | GCS 읽기/쓰기 |
| `roles/aiplatform.user` | 프로젝트 | Vertex AI |
| `roles/aiplatform.expressUser` | 프로젝트 | Vertex AI Express |
| `roles/iam.serviceAccountTokenCreator` | **자기 자신** | ✅ signBlob 가능 |

### 1.2 V4 Signed URL 생성에 필요한 최소 권한

GCS V4 Signed URL 생성 시 SA는 `signBlob` API를 호출해야 합니다.

| 필요 권한 | 포함 역할 | 설명 |
|-----------|-----------|------|
| `iam.serviceAccounts.signBlob` | `roles/iam.serviceAccountTokenCreator` | URL 서명 생성 |
| `storage.objects.get` | `roles/storage.objectViewer` 이상 | 오브젝트 읽기 (URL 대상) |

> **현재 BE SA 상태**: `storage.objectAdmin`은 있지만, `serviceAccountTokenCreator`가 **없어서** Signed URL 생성 불가.

### 1.3 구성 제안 (A안 vs B안)

#### A안: BE SA에 직접 tokenCreator 부여 (권장)

```bash
gcloud iam service-accounts add-iam-policy-binding \
  miriart-be-runner@miriarts.iam.gserviceaccount.com \
  --project=miriarts \
  --member="serviceAccount:miriart-be-runner@miriarts.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

| 항목 | 평가 |
|------|------|
| 복잡도 | **낮음** — gcloud 1줄 |
| 지연 | **없음** — 직접 서명 |
| 보안 | BE SA가 자신의 토큰만 서명 (자기 자신에게만 바인딩) |
| 코드 변경 | Java `Storage.signUrl()` 표준 패턴 |
| 운영 | SA 1개 관리 |

**BE Java 코드 패턴 (A안)**:
```java
// Cloud Run에서 SA 자동 주입 — 별도 credential 로딩 불필요
Storage storage = StorageOptions.getDefaultInstance().getService();

BlobInfo blobInfo = BlobInfo.newBuilder("miriart-bucket", objectPath).build();
URL signedUrl = storage.signUrl(blobInfo, 15, TimeUnit.MINUTES,
    Storage.SignUrlOption.withV4Signature());
```

#### B안: 별도 image-signer SA + BE impersonate

```bash
# 1. 전용 SA 생성
gcloud iam service-accounts create miriart-image-signer \
  --project=miriarts \
  --display-name="Image Signed URL Signer"

# 2. GCS objectViewer 부여 (최소 권한)
gcloud storage buckets add-iam-policy-binding gs://miriart-bucket \
  --member="serviceAccount:miriart-image-signer@miriarts.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"

# 3. 자기 자신에 tokenCreator
gcloud iam service-accounts add-iam-policy-binding \
  miriart-image-signer@miriarts.iam.gserviceaccount.com \
  --project=miriarts \
  --member="serviceAccount:miriart-image-signer@miriarts.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"

# 4. BE SA가 impersonate 할 수 있도록
gcloud iam service-accounts add-iam-policy-binding \
  miriart-image-signer@miriarts.iam.gserviceaccount.com \
  --project=miriarts \
  --member="serviceAccount:miriart-be-runner@miriarts.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

| 항목 | 평가 |
|------|------|
| 복잡도 | **높음** — SA 3개 관리, impersonate 체인 |
| 지연 | impersonate 토큰 발급 ~50ms 추가 |
| 보안 | 최소 권한 원칙 강화 (signer SA는 objectViewer만) |
| 코드 변경 | impersonate credential 로딩 + signUrl |
| 운영 | SA 추가 관리, 디버깅 복잡 |

**BE Java 코드 패턴 (B안)**:
```java
// impersonate credential
GoogleCredentials impersonated = ImpersonatedCredentials.create(
    GoogleCredentials.getApplicationDefault(),
    "miriart-image-signer@miriarts.iam.gserviceaccount.com",
    null, List.of("https://www.googleapis.com/auth/cloud-platform"), 3600);

Storage storage = StorageOptions.newBuilder()
    .setCredentials(impersonated).build().getService();

URL signedUrl = storage.signUrl(blobInfo, 15, TimeUnit.MINUTES,
    Storage.SignUrlOption.withV4Signature());
```

### 1.4 권장: A안

| 근거 | 설명 |
|------|------|
| 현재 BE SA가 이미 `objectAdmin` | objectAdmin은 읽기/쓰기/삭제 모두 가능. 별도 signer SA를 만들어 objectViewer로 제한해도, BE SA 자체가 이미 full access. 실질적 보안 차이 없음. |
| 운영 복잡도 | SA 1개 vs 3개 관리. 장애 시 디버깅 단순. |
| 코드 복잡도 | 표준 패턴 1줄 vs impersonate 체인. |
| 자기 자신 바인딩 | tokenCreator를 자기 자신에게만 부여하므로 다른 SA의 토큰을 생성할 수 없음. |

> B안은 BE SA의 GCS 권한을 `objectViewer`로 낮출 수 있는 경우에만 의미가 있음. 현재 BE가 이미지 업로드(objectAdmin)도 담당하므로 권한 축소 불가.

### 1.5 조직 정책 충돌 평가

| 조직 정책 | 영향 |
|-----------|------|
| `iam.allowedPolicyMemberDomains` | ❌ 충돌 없음. SA는 프로젝트 내부 멤버이므로 `allUsers` 차단과 무관. |
| `storage.publicAccessPrevention` | ❌ 충돌 없음. Signed URL은 public access가 아닌 SA 서명 기반. 버킷 public 설정 불필요. |
| `storage.uniformBucketLevelAccess` | ❌ 충돌 없음. Uniform IAM + Signed URL은 공존 가능. ACL 불필요. |

---

## 2. 정책/TTL/경로 규칙 제안

### 2.1 Signed URL 정책 표 (SSOT 반영용)

| 항목 | 값 | 근거 |
|------|-----|------|
| **유효기간** | **15분** | V4 최대 7일이지만, 이미지 조회는 즉시성 요구. 15분이면 FE 렌더링+재시도 충분. 유출 시 영향 최소화. |
| **dev/prod 구분** | **불필요** | 동일 버킷·동일 정책. dev에서 길게 줄 이유 없음. |
| **허용 HTTP Method** | **GET** | 읽기 전용. PUT/DELETE는 BE SDK 직접 사용. |
| **서명 SA** | `miriart-be-runner` | A안 기준. |
| **허용 경로 prefix** | 아래 표 참조 | BE 코드에서 경로 검증 후 서명. |

### 2.2 허용 경로 규칙

| 경로 패턴 | 용도 | 생성 주체 |
|-----------|------|-----------|
| `artworks/{date}/{uuid}_{filename}` | 원본 업로드 이미지 | BE (업로드 시) |
| `edited/{date}/{uuid}_{filename}` | AI 이미지 편집 결과 | AI (edit-image 응답) |
| `analyses/{date}/{uuid}_*.{ext}` | 분석 결과 이미지 (향후) | AI |

> **BE 코드에서의 경로 검증**: `objectPath`가 위 prefix 중 하나로 시작하는지 검증 후에만 Signed URL 생성. 임의 경로에 대한 서명 방지.

### 2.3 이미지 크기/해상도 참고

| 항목 | 값 | 비고 |
|------|-----|------|
| GCS 단일 오브젝트 최대 | 5 TiB | GCS 한도, 실질적 제약 아님 |
| 현재 샘플 이미지 크기 | ~165 KB | `artworks/2026-03-03/...IMG_6728.jpeg` 실측 |
| 권장 업로드 제한 (BE) | **10 MB** | Spring Boot `multipart.max-file-size` 설정 권장 |
| 권장 해상도 가이드 | 4096×4096 px 이하 | Gemini Vision API 입력 권장 범위 |

---

## 3. 보안 관점 체크리스트

### 3.1 원칙 대비표

| 항목 | 현재 상태 | Signed URL 도입 후 원칙 |
|------|-----------|------------------------|
| **Public access** | 버킷 public 차단, `allUsers` 바인딩 없음 | ✅ **계속 금지**. Signed URL은 public access를 필요로 하지 않음. |
| **Uniform IAM** | `uniformBucketLevelAccess: true` | ✅ **유지**. ACL 사용 금지. |
| **SA 키 파일** | 없음 (Cloud Run 자동 SA) | ✅ **계속 금지**. 키 파일 다운로드 하지 않음. |
| **CORS** | 미설정 | ⚠️ **설정 필요** (아래 §3.3) |

### 3.2 Signed URL 유출 시 영향 범위

| 시나리오 | 영향 | 통제 |
|----------|------|------|
| URL 유출 (15분 내) | 해당 오브젝트 **읽기만** 가능 | GET만 서명, 15분 TTL |
| URL 유출 (15분 후) | 접근 불가 (403 SignatureDoesNotMatch) | 자동 만료 |
| URL로 쓰기/삭제 시도 | 실패 (Method Not Allowed) | GET만 서명 |
| 대량 URL 수집 | 각각 독립 서명, 일괄 무효화 불가 | 짧은 TTL + 경로 제한으로 완화 |

> **핵심**: Signed URL은 "시한부 읽기 토큰"으로 동작. 유출 시 최악의 경우 15분간 해당 이미지 1개가 노출되며, 쓰기/삭제 권한은 없음.

### 3.3 CORS 설정 (필수)

FE가 Signed URL로 GCS에 직접 `GET` 요청하려면 버킷에 CORS 설정이 필요합니다.

```json
[
  {
    "origin": ["https://miriart.vercel.app", "http://localhost:5173"],
    "method": ["GET"],
    "responseHeader": ["Content-Type", "Content-Length"],
    "maxAgeSeconds": 3600
  }
]
```

```bash
# cors.json 파일 생성 후:
gcloud storage buckets update gs://miriart-bucket --cors-file=cors.json
```

> **prod 도메인이 확정되면 origin 업데이트 필요.** `"*"`는 사용하지 않음.

### 3.4 로그 & 모니터링

#### GCS 접근 로그 기록 방식

| 로그 종류 | Signed URL 기록 여부 | 위치 |
|-----------|---------------------|------|
| Cloud Audit Log (Data Access) | ✅ 기록됨 (`storage.objects.get`) | Cloud Logging |
| GCS Usage Log (legacy) | ✅ 기록됨 | 별도 버킷 설정 시 |
| Cloud Run 로그 | BE의 URL 생성 요청만 기록 | Cloud Logging |

> **주의**: Data Access Audit Log는 기본적으로 **비활성**입니다. 활성화하면 GCS read마다 로그가 쌓여 비용이 발생합니다.

#### 활성화 방법 (선택적):

```bash
# 프로젝트 전체가 아닌 버킷 단위로는 불가 — 프로젝트 audit config 수정 필요
gcloud projects get-iam-policy miriarts --format=json > /tmp/policy.json
# auditConfigs 섹션에 storage.googleapis.com DATA_READ 추가
# → 비용 주의: 이미지 조회량에 비례하여 로그 비용 발생
```

**권장**: 초기에는 Data Access Log 비활성 유지. 이상 징후 감지는 BE 측 Signed URL 생성 로그(요청 수/경로)로 대체.

---

## 4. 관측성/알림 보완 제안

### 4.1 BE 측 Signed URL 메트릭 (권장)

BE 코드에서 Signed URL 생성 시 로그를 남기고, log-based metric으로 추적:

```
# 구조화 로그 예시 (BE에서 출력)
{"severity":"INFO","message":"signed_url_generated","path":"artworks/2026-03-03/...","ttl":900}
```

| 메트릭 | 필터 | 용도 |
|--------|------|------|
| `miriart-be-signed-url-count` | `jsonPayload.message="signed_url_generated"` | URL 생성 빈도 |
| `miriart-be-signed-url-errors` | `jsonPayload.message="signed_url_error"` | 서명 실패 (권한 등) |

```bash
# 메트릭 생성 (BE 코드에서 구조화 로그 출력 후)
gcloud logging metrics create miriart-be-signed-url-count \
  --project=miriarts \
  --description="Signed URL generation count" \
  --log-filter='resource.type="cloud_run_revision" AND resource.labels.service_name="miriart-be" AND jsonPayload.message="signed_url_generated"'

gcloud logging metrics create miriart-be-signed-url-errors \
  --project=miriarts \
  --description="Signed URL generation errors" \
  --log-filter='resource.type="cloud_run_revision" AND resource.labels.service_name="miriart-be" AND jsonPayload.message="signed_url_error"'
```

### 4.2 GCS 4xx 모니터링 (선택)

GCS 내장 메트릭 `storage.googleapis.com/api/request_count`를 대시보드에 추가:

```
metric.type = "storage.googleapis.com/api/request_count"
resource.labels.bucket_name = "miriart-bucket"
metric.labels.response_code >= 400
```

> 기존 대시보드 `MiriArt-AI BE/AI Overview`에 패널 추가 가능.

### 4.3 비정상 패턴 탐지 (향후)

| 패턴 | 탐지 방법 | 우선순위 |
|------|-----------|----------|
| 동일 IP 과도 요청 | Data Access Log + Cloud Armor (FE→BE 구간) | 낮음 (Phase 3) |
| 단시간 대량 URL 생성 | BE 로그 기반 rate alert (5분 내 100건 초과) | 중간 |
| 만료된 URL 재사용 시도 | GCS 403 spike | 낮음 |

> 초기 릴리즈에서는 §4.1의 BE 로그 기반 메트릭 2개로 충분. Data Access Log 기반 탐지는 트래픽 규모 확인 후 판단.

---

## 5. SSOT/Runbook 업데이트 초안

### 5.1 miriarts_infra.md 추가 초안

#### §3.3 이미지 전달 정책 (신규 섹션)

```markdown
### 3.3 이미지 전달 정책 (GCS Signed URL)

| 항목 | 값 |
|------|-----|
| 전달 방식 | GCS V4 Signed URL |
| 생성 엔드포인트 | BE `GET /api/images/{id}/url` |
| 서명 SA | `miriart-be-runner@miriarts.iam.gserviceaccount.com` |
| 유효기간 | 15분 |
| 허용 Method | GET (읽기 전용) |
| 허용 경로 | `artworks/**`, `edited/**`, `analyses/**` |
| CORS origin | `https://miriart.vercel.app`, `http://localhost:5173` |

**원칙**:
- 버킷은 public이 아니며, `https://storage.googleapis.com/miriart-bucket/...` 직접 접근 시 403이 **정상**.
- 이미지 조회는 반드시 BE를 통해 Signed URL을 발급받아 접근.
- SA 키 파일 다운로드 금지. Cloud Run 자동 SA만 사용.
```

#### §4.3 SA 업데이트

```markdown
| SA | 역할 추가 | 용도 |
|----|-----------|------|
| miriart-be-runner | `roles/iam.serviceAccountTokenCreator` (자기 자신) | GCS V4 Signed URL 서명 |
```

### 5.2 RUNBOOK_AI_INFRA_v1.md 추가 초안

#### §4.2 증상별 원인 표에 추가

```markdown
| 증상 | 가능 원인 | 확인 방법 |
|------|-----------|-----------|
| FE 이미지 403 (GCS) | Signed URL 만료 또는 미발급 | BE 로그에서 signed_url_generated 확인, URL TTL 검증 |
| FE 이미지 403 (CORS) | CORS 미설정 또는 origin 불일치 | 브라우저 콘솔 CORS 에러, `gcloud storage buckets describe --format=yaml(cors)` |
| Signed URL 생성 실패 | BE SA tokenCreator 권한 누락 | `gcloud iam service-accounts get-iam-policy miriart-be-runner@...` |
| 이미지 404 | GCS 오브젝트 경로 불일치 | `gcloud storage ls gs://miriart-bucket/{path}` |
```

#### §6 운영 명령어에 추가

```markdown
### GCS Signed URL 디버깅

# CORS 설정 확인
gcloud storage buckets describe gs://miriart-bucket \
  --format="yaml(cors_config)"

# 오브젝트 존재 확인
gcloud storage ls gs://miriart-bucket/{path}

# BE SA 서명 권한 확인
gcloud iam service-accounts get-iam-policy \
  miriart-be-runner@miriarts.iam.gserviceaccount.com --project=miriarts

# Signed URL 수동 생성 테스트 (impersonate)
gcloud storage sign-url \
  gs://miriart-bucket/artworks/2026-03-03/test.jpeg \
  --private-key-file=- --duration=15m
```

---

## 6. 실행 작업 목록 (gcloud)

### 즉시 실행 가능 (CTO 승인 후)

| # | 작업 | 명령어 | 비고 |
|---|------|--------|------|
| 1 | **BE SA tokenCreator 부여** | `gcloud iam service-accounts add-iam-policy-binding miriart-be-runner@miriarts.iam.gserviceaccount.com --project=miriarts --member="serviceAccount:miriart-be-runner@miriarts.iam.gserviceaccount.com" --role="roles/iam.serviceAccountTokenCreator"` | A안 핵심 |
| 2 | **CORS 설정** | `gcloud storage buckets update gs://miriart-bucket --cors-file=cors.json` | FE 직접 GCS 접근 용 |
| 3 | **Signed URL 메트릭 생성** | 위 §4.1 참조 | BE 로그 출력 후 |

### BE 코드 구현 후 실행

| # | 작업 | 명령어 |
|---|------|--------|
| 4 | Signed URL 메트릭 생성 | BE에서 구조화 로그 출력 확인 후 §4.1 명령어 실행 |
| 5 | 대시보드 패널 추가 | GCS request_count 패널 추가 (선택) |

### 실행 불필요 (현재 상태로 충분)

| 항목 | 이유 |
|------|------|
| Data Access Audit Log 활성화 | 비용 우려, BE 로그로 대체 |
| 별도 image-signer SA 생성 (B안) | A안 채택 시 불필요 |
| Public access 변경 | Signed URL은 public 불필요 |

---

## 7. 요약 의사결정 매트릭스

| 결정 항목 | 권장안 | 대안 | CTO 결정 필요 |
|-----------|--------|------|---------------|
| SA 구성 | **A안** (BE SA 직접) | B안 (별도 signer SA) | ✅ |
| Signed URL TTL | **15분** | 1시간 | |
| CORS origin | FE prod URL + localhost | `*` (비권장) | ✅ FE URL 확정 시 |
| Data Access Log | **비활성 유지** | 활성화 (비용 증가) | |
| BE 엔드포인트 | `GET /api/images/{id}/url` | `GET /api/images/{id}` (프록시) | |

---

*제안서 작성 완료. 2026-03-10, INFRA_DEV 에이전트.*
