# MiriArt-AI 인프라 런북 v1

> **대상 서비스**: miriart-ai (FastAPI, Cloud Run)
> **작성일**: 2026-03-10
> **최종 갱신**: 2026-03-10
> **SSOT 참조**: `SSOT/miriarts_infra.md`

---

## 1. 서비스 개요

| 항목 | 값 |
|------|-----|
| Cloud Run 서비스명 | `miriart-ai` |
| 리전 | `asia-northeast3` (서울) |
| 프로젝트 | `miriarts` |
| URL | `https://miriart-ai-gzjczkus6q-du.a.run.app` |
| SA | `miriart-ai-runner@miriarts.iam.gserviceaccount.com` |
| CPU/Memory | 1 vCPU / 1Gi |
| Timeout | 120s |
| Concurrency | 10 |
| Min/Max Instances | 1 / 20 |
| IAM | `invoker-iam-check` 활성 (외부 403) |

---

## 2. 배포 절차 (수동 Cloud Build)

### 2.1 사전 조건

```bash
# gcloud 인증 확인
gcloud auth list
gcloud config set project miriarts
```

### 2.2 빌드 & 배포

```bash
cd /path/to/miriart-ai

# Cloud Build로 빌드+배포 (cloudbuild.yaml 사용)
gcloud builds submit --config=cloudbuild.yaml \
  --project=miriarts \
  --region=asia-northeast3
```

`cloudbuild.yaml`이 수행하는 작업:
1. Docker 이미지 빌드 (듀얼 태그: `$COMMIT_SHA` + `latest`)
2. Artifact Registry 푸시 (`asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai`)
3. Cloud Run 배포 (min=1, max=20, concurrency=10, IAM 보호)

### 2.3 배포 검증

```bash
# 최신 리비전 확인
gcloud run services describe miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --format="value(status.latestReadyRevisionName)"

# 외부 접근 차단 확인 (403이어야 정상)
curl -s -o /dev/null -w "%{http_code}" \
  https://miriart-ai-gzjczkus6q-du.a.run.app/health

# BE SA 토큰으로 내부 접근 확인 (prod에서는 Cloud Run SA 자동 발급)
# 로컬 테스트 시:
# gcloud auth print-identity-token \
#   --impersonate-service-account=miriart-be-runner@miriarts.iam.gserviceaccount.com \
#   --audiences=https://miriart-ai-gzjczkus6q-du.a.run.app
```

---

## 3. 롤백 절차

### 3.1 이전 리비전으로 트래픽 전환

```bash
# 현재 리비전 목록 확인
gcloud run revisions list --service=miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --format="table(REVISION,ACTIVE,LAST_DEPLOYED_AT)" --limit=5

# 이전 리비전으로 100% 트래픽 전환
gcloud run services update-traffic miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --to-revisions=<PREVIOUS_REVISION>=100
```

### 3.2 이미지 태그로 재배포

```bash
# 특정 커밋 SHA 이미지로 재배포
gcloud run deploy miriart-ai \
  --image=asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:<COMMIT_SHA> \
  --region=asia-northeast3 --project=miriarts
```

### 3.3 롤백 후 검증

```bash
# 헬스 체크 (외부 → 403 확인)
curl -s -o /dev/null -w "%{http_code}" \
  https://miriart-ai-gzjczkus6q-du.a.run.app/health

# 서비스 Ready 상태 확인
gcloud run services describe miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --format="value(status.conditions[0].status)"
```

---

## 4. 장애 대응 (Incident Response)

### 4.1 3단계 대응 프로세스

#### Step 1: 탐지 & 확인 (< 5분)

```bash
# 1. 서비스 상태 확인
gcloud run services describe miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --format="yaml(status.conditions)"

# 2. 최근 에러 로그 확인
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-ai"
   AND severity>=ERROR' \
  --project=miriarts --limit=20 \
  --format="table(timestamp,severity,textPayload)"

# 3. 5xx 비율 확인
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-ai"
   AND httpRequest.status>=500' \
  --project=miriarts --limit=10 \
  --format="table(timestamp,httpRequest.status,httpRequest.requestUrl)"
```

#### Step 2: 원인 분류

| 증상 | 가능 원인 | 확인 방법 | 해결 액션 예시 |
|------|-----------|-----------|---------------|
| 502 Bad Gateway | Cold start 실패, 컨테이너 크래시 | 인스턴스 로그 확인, startup probe 상태 | §3 롤백, 메모리/타임아웃 조정 |
| 504 Timeout | Gemini API 응답 지연 (>120s) | Vertex AI 로그, request latency 확인 | 대기 또는 fallback 메시지 |
| 500 Internal | 코드 에러, 의존성 실패 | 에러 스택트레이스 확인 | §3 롤백 |
| 403 전면 | IAM 설정 변경, SA 권한 해제 | IAM policy 확인 | SA 역할 재부여 |
| 연속 크래시 | OOM, 환경변수 누락 | 리비전 로그, describe로 env 확인 | 메모리 증설, env 수정 |
| 404 I001 | 잘못된 analysisId / 권한 없음 | BE 로그 / DB `analyses.id` 조회 | FE 링크 로직 수정 |
| 502 F005 | gcsUri 이상 / GCS 권한 / prefix 미스 | BE `signed_url_error` 로그, `gcloud storage objects describe gs://miriart-bucket/{path}` | DB 정제, SA 재검증 |
| 브라우저 403 (GCS) | Signed URL 만료(15분) 또는 미발급 | curl 직접 호출로 URL 만료 확인, BE 로그에서 `signed_url_generated` 검색 | TTL 검토, BE 로직 확인 |
| 브라우저 CORS 에러 | GCS CORS 미설정 또는 origin 불일치 | 브라우저 콘솔 CORS 에러, `gcloud storage buckets describe gs://miriart-bucket --format=yaml(cors_config)` | CORS origin 수정 |
| Signed URL 생성 실패 | BE SA tokenCreator 권한 누락 | `gcloud iam service-accounts get-iam-policy miriart-be-runner@miriarts.iam.gserviceaccount.com --project=miriarts` | tokenCreator 역할 재부여 |
| 이미지 404 | GCS 오브젝트 경로 불일치 | `gcloud storage ls gs://miriart-bucket/{path}` | 경로 prefix 확인, SSOT §3.4 대조 |

#### Step 3: 조치

- **코드 문제**: §3 롤백 절차 수행
- **인프라 문제**: 아래 체크리스트 확인 후 수정
- **외부 의존성(Vertex AI)**: 대기 또는 fallback 메시지 처리

### 4.3 이미지 로딩 실패 시 디버깅 절차

> **목표**: FE에서 이미지가 표시되지 않을 때, 원인을 **15분 이내** 특정하고 해결한다.
> 15분 초과 시 CTO 에스컬레이트.

#### Step 1: 증상 파악 (~2분)

FE 에러코드 또는 브라우저 네트워크 탭에서 증상을 확인한다.

| FE 증상 | 가능한 원인 카테고리 |
|---------|---------------------|
| `I001` (404) | analysisId 불일치 / 권한 없음 → Step 2 |
| `F005` (502) | BE Signed URL 생성 실패 → Step 2 |
| 브라우저 403 (이미지 요청) | Signed URL 만료 또는 미발급 → Step 3 |
| 브라우저 CORS 에러 | GCS CORS 설정 문제 → Step 5 |
| 이미지 깨짐 / 404 (GCS) | 오브젝트 미존재 → Step 3 |

#### Step 2: Signed URL 문제 판별 (~3분)

BE 로그에서 `signed_url_error` 또는 `signed_url_generated`를 검색한다.

```bash
# 최근 Signed URL 에러 로그 확인
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-be"
   AND jsonPayload.message="signed_url_error"' \
  --project=miriarts --limit=10 \
  --format="table(timestamp,jsonPayload.analysisId,jsonPayload.objectPath,jsonPayload.errorCode,jsonPayload.errorDetail)"

# 성공 로그 확인 (발급이 되고 있는지)
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-be"
   AND jsonPayload.message="signed_url_generated"' \
  --project=miriarts --limit=5 \
  --format="table(timestamp,jsonPayload.analysisId,jsonPayload.objectPath)"
```

- **에러 로그 있음**: `errorCode`, `errorDetail` 확인 → Step 3 또는 Step 4
- **성공 로그도 에러 로그도 없음**: BE 엔드포인트 자체가 호출되지 않음 → FE 라우팅 확인

#### Step 3: GCS 오브젝트 존재 확인 (~2분)

```bash
# 특정 오브젝트 존재 및 메타 확인
gcloud storage objects describe gs://miriart-bucket/{objectPath}

# prefix 기준 목록 확인
gcloud storage ls gs://miriart-bucket/{prefix}/ --limit=5
```

- **오브젝트 없음 (NotFound)**: DB의 `gcs_uri`가 실제 GCS와 불일치. DB 정제 또는 AI 재업로드 필요.
- **오브젝트 있음**: Step 4 (권한 문제)

#### Step 4: SA/권한 확인 (~3분)

```bash
# BE SA의 tokenCreator 권한 확인
gcloud iam service-accounts get-iam-policy \
  miriart-be-runner@miriarts.iam.gserviceaccount.com \
  --project=miriarts

# 버킷 IAM 정책에서 objectAdmin 확인
gcloud storage buckets get-iam-policy gs://miriart-bucket --project=miriarts

# BE SA에 필요한 역할:
# - roles/iam.serviceAccountTokenCreator (자기 자신에 대해)
# - roles/storage.objectAdmin (버킷에 대해)
```

- **tokenCreator 없음**: `gcloud iam service-accounts add-iam-policy-binding` 으로 복구
- **objectAdmin 없음**: 버킷 IAM 수정

#### Step 5: CORS 확인 (~2분)

```bash
# GCS 버킷 CORS 설정 확인
gcloud storage buckets describe gs://miriart-bucket \
  --format="yaml(cors_config)"
```

- 기대값: origin에 `https://miriart.app`, `http://localhost:3000` 포함, method에 `GET` 포함
- **CORS 미설정/불일치**: `gcloud storage buckets update` 로 CORS 재적용

**에스컬레이션 기준**: 위 5단계를 모두 수행해도 원인 미특정, 또는 전체 소요 15분 초과 시 **CTO 에스컬레이트**.

---

### 4.2 주요 체크 포인트

```bash
# 환경변수 확인
gcloud run services describe miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --format="yaml(spec.template.spec.containers[0].env)"

# SA 권한 확인
gcloud projects get-iam-policy miriarts \
  --flatten="bindings[].members" \
  --filter="bindings.members:miriart-ai-runner@miriarts.iam.gserviceaccount.com" \
  --format="table(bindings.role)"

# Invoker 바인딩 확인 (BE SA가 있어야 함)
gcloud run services get-iam-policy miriart-ai \
  --region=asia-northeast3 --project=miriarts
```

---

## 5. 관측성 (Observability)

### 5.1 대시보드

| 대시보드 | ID | 용도 |
|----------|-----|------|
| MiriArt-AI BE/AI Overview | `000813b5-103e-48d7-8966-15022037129a` | AI/BE 전체 Request, Latency, 5xx, Instance |
| MiriArt - BE Signed URL | `707df634-a515-4226-9e73-edf7f9e9db91` | Signed URL 발급 수, 실패 수, Top objectPath |

- **콘솔**: [GCP Monitoring Dashboards](https://console.cloud.google.com/monitoring/dashboards?project=miriarts)
- **Signed URL 대시보드 직접 링크**: [MiriArt - BE Signed URL](https://console.cloud.google.com/monitoring/dashboards/builder/707df634-a515-4226-9e73-edf7f9e9db91?project=miriarts)

### 5.2 Log-based Metrics

| 메트릭 | 필터 | 용도 |
|--------|------|------|
| `miriart-ai-5xx-errors` | AI status>=500 | AI 전체 5xx |
| `miriart-ai-502-gateway` | AI status=502 | Cold start / upstream 장애 |
| `miriart-ai-504-timeout` | AI status=504 | Gemini 타임아웃 |
| `miriart-be-5xx-errors` | BE status>=500 | BE 전체 5xx |
| `miriart-be-signed-url-count` | BE `signed_url_generated` | Signed URL 발급 성공 |
| `miriart-be-signed-url-errors` | BE `signed_url_error` | Signed URL 발급 실패 |

### 5.3 Alert Policies

| 이름 | 조건 | 알림 | Policy ID |
|------|------|------|-----------|
| `miriart-ai 5xx Spike` | 5분간 5xx > 5건 | CTO Email (`6siegfriex@argo.ai.kr`) | `8942907770327332678` |
| `Signed URL Errors Spike` | `miriart-be-signed-url-errors > 0` 5분 지속 | CTO Email (동일) | `10494294328358958245` |

### 5.4 관측성 검증 명령어

```bash
# 메트릭 목록 확인
gcloud logging metrics list --project=miriarts

# 알림 정책 확인
gcloud alpha monitoring policies list --project=miriarts

# 대시보드 확인
gcloud monitoring dashboards list --project=miriarts
```

---

## 6. 주요 운영 명령어 모음

### 스케일링 조정

```bash
gcloud run services update miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --min-instances=<N> --max-instances=<N> --concurrency=<N>
```

### 환경변수 업데이트

```bash
gcloud run services update miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --update-env-vars=KEY=VALUE
```

### 로그 실시간 스트리밍

```bash
gcloud logging tail \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-ai"' \
  --project=miriarts
```

### 인스턴스 수 확인

```bash
gcloud run services describe miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --format="yaml(spec.template.metadata.annotations)"
```

### GCS Signed URL 디버깅

```bash
# CORS 설정 확인
gcloud storage buckets describe gs://miriart-bucket \
  --format="yaml(cors_config)"

# 오브젝트 존재 확인
gcloud storage ls gs://miriart-bucket/{path}

# BE SA 서명 권한 확인
gcloud iam service-accounts get-iam-policy \
  miriart-be-runner@miriarts.iam.gserviceaccount.com --project=miriarts

# 버킷 IAM 정책 확인
gcloud storage buckets get-iam-policy gs://miriart-bucket --project=miriarts
```

---

## 7. 알려진 제약사항

| # | 항목 | 상태 | 해결 계획 |
|---|------|------|-----------|
| 1 | GCS imageUrl 403 (공개 접근 불가) | **인프라 준비 완료** | BE SA tokenCreator 부여 완료, CORS 설정 완료. BE 코드 구현 대기. |
| 2 | BE IAM (TODO-009) | DRS 완화 유지 | 릴리즈 전 조직 태그 예외 적용 |
| 3 | CI/CD 트리거 미설정 (TASK-D5) | 스킵 | 수동 `gcloud builds submit` 사용 |
| 4 | BE SA impersonate 테스트 불가 | 정상 동작 | prod에서 Cloud Run SA 자동 토큰으로 작동 |

---

## 8. Signed URL 관련 변경 배포 체크리스트

> **적용 시점**: BE가 GCS Signed URL 기반 이미지 전달(`/api/images/{id}/url`)을 배포할 때.

### 배포 전

| 담당 | 체크 항목 |
|------|-----------|
| **BE** | `/api/images/{id}/url` 엔드포인트 구현 완료 |
| **BE** | `GcsSignedUrlService` (또는 동등 서비스)에서 `signed_url_generated` / `signed_url_error` JSON 로그 출력 (`SSOT/DASHBOARD_SIGNED_URL_SPEC.md` §4 규격 준수) |
| **BE** | ErrorCode `F005` (Signed URL 생성 실패) 매핑 완료 |
| **BE** | 허용 prefix 목록 (`artworks/`, `edited/`, `analyses/`) 검증 로직 포함 |
| **FE** | `SignedImage` 컴포넌트 (또는 동등) 구현, 기존 `imageUrl` 직접 사용 → Signed URL 전환 |
| **FE** | `F005` / `I001` 에러 핸들링 UI 구현 |
| **인프라** | CORS 설정 확인: `gcloud storage buckets describe gs://miriart-bucket --format=yaml(cors_config)` |
| **인프라** | SA tokenCreator 확인: `gcloud iam service-accounts get-iam-policy miriart-be-runner@miriarts.iam.gserviceaccount.com` |
| **인프라** | 메트릭 존재 확인: `gcloud logging metrics list --project=miriarts --filter="name:miriart-be-signed-url"` |

### 배포 직후 (~10분)

| 담당 | 체크 항목 |
|------|-----------|
| **BE** | BE 로그에서 `signed_url_generated` 출력 확인 (`gcloud logging read` §4.3 Step 2 참조) |
| **BE** | `signed_url_error` 이 비정상적으로 다수 발생하지 않는지 확인 |
| **FE** | 브라우저에서 이미지 렌더링 정상 확인 (artworks, edited 이미지 각 1건 이상) |
| **FE** | 브라우저 콘솔에 CORS 에러 없는지 확인 |
| **인프라** | 메트릭 카운트 수집 시작 확인: Cloud Monitoring → Metrics Explorer → `miriart-be-signed-url-count` 데이터 포인트 존재 |

### 배포 1일 후

| 담당 | 체크 항목 |
|------|-----------|
| **BE** | `signed_url_errors` / `signed_url_count` 비율 확인 (에러율 < 1% 목표) |
| **FE** | 이미지 캐싱 동작 확인 (동일 이미지 재요청 시 브라우저 캐시 히트) |
| **인프라** | 대시보드 파형 정상 확인 (DASHBOARD_SIGNED_URL_SPEC §2 위젯 3개에 데이터 표시) |
| **인프라** | 알림 테스트: 의도적으로 잘못된 경로로 Signed URL 요청 → `signed_url_error` 발생 → 알림 수신 확인 → 테스트 데이터 정리 |

---

*Runbook v1 — 2026-03-10, INFRA_DEV 에이전트*
