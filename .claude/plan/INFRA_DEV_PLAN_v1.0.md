# INFRA_DEV 실행 플랜 v1.0

> **역할**: MiriArt GCP 인프라 전담. Cloud Run, Cloud Build, IAM, GCS, Logging/Monitoring을 SSOT(v1.2)와 일치하게 정리하고, miriart-ai 배포/운영 품질을 보장한다.
> **기준 문서**: SSOT v1.2, Dev Spec v1.0, API_CONTRACT v1.0
> **작성일**: 2026-03-09
> **현황 기준**: GCP 실시간 조회 완료 (gcloud CLI)

---

## 0. 현황 감사 결과 (As-Is vs To-Be 갭 분석)

### miriart-ai Cloud Run

| 항목 | 현재값 (GCP 실측) | 목표값 (Dev Spec) | 갭 |
|------|-------------------|-------------------|-----|
| invoker-iam-disabled | **true (IAM 우회)** | false (IAM 체크) | **CRITICAL** |
| min-instances | 0 (미설정) | 1 | cold start 502 발생 |
| max-instances | 20 | 20 | OK |
| concurrency | 80 (기본값) | 10 | 과다 — AI I/O bound 서비스에 부적합 |
| cpu-boost | enabled | enabled | OK |
| cpu-throttling | 기본 (throttled) | 기본 유지 | OK |
| image tag | `:latest` | `:$COMMIT_SHA` | 버전 추적 불가 |
| ingress | `all` | `all` (BE도 public에서 호출) | OK (내부전용은 IAM으로 보호) |

### miriart-be Cloud Run

| 항목 | 현재값 (GCP 실측) | SSOT 기대 | 갭 |
|------|-------------------|-----------|-----|
| invoker-iam-disabled | **true (IAM 우회)** | false | **CRITICAL — BE도 동일 이슈** |
| memory | 512Mi | 1Gi (SSOT §2) | **부족 — Java Spring Boot에 512Mi** |
| max-instances | 2 | 미명시 (TODO-007) | 검토 필요 |
| concurrency | 80 | 미명시 | OK for now |
| timeout | 300s | 미명시 | OK (AI 120s보다 여유) |
| cpu-throttling | false | — | OK (always-on CPU) |
| FASTAPI_INTERNAL_URL | `https://miriart-ai-svc-946560105497...` | AI Cloud Run URL | **URL 불일치 의심 — `-svc-` 접미 확인 필요** |
| GCS_BUCKET_NAME | `miriart-uploads` | `miriart-bucket` | **버킷명 불일치** |
| image tag | `:latest` | `:$COMMIT_SHA` 권장 | 추적 불가 |

### GCS

| 항목 | 현재 상태 | 비고 |
|------|-----------|------|
| miriart-bucket | 존재, 비공개 (uniform bucket IAM) | OK |
| miriart-uploads | **404 — 존재하지 않음** | BE env에서 참조 중이나 버킷 없음 |
| public access | `public_access_prevention: inherited` | 명시적 enforce 권장 |

### IAM / Service Accounts

| SA | 현재 역할 | 필요 추가 | 비고 |
|----|-----------|-----------|------|
| miriart-ai-runner | aiplatform.user, storage.objectAdmin | **iam.serviceAccountTokenCreator** (Signed URL용) | Phase 2 대비 |
| miriart-be-runner | cloudsql.client, secretmanager.secretAccessor, storage.objectAdmin, run.invoker | — | OK |
| miriart-cloudbuild | run.admin, iam.serviceAccountUser, artifactregistry.writer, storage.objectAdmin | — | OK |

### Cloud Build / 트리거

| 항목 | 현재 상태 | 목표 |
|------|-----------|------|
| 트리거 | **없음 (전역/리전 모두)** | main 브랜치 push 자동 트리거 |
| 최근 빌드 | 4건 SUCCESS (수동) | 자동화 |
| cloudbuild.yaml | 단일 태그 ($COMMIT_SHA) | 듀얼 태그 ($COMMIT_SHA + latest) |

### 관측성

| 항목 | 현재 상태 |
|------|-----------|
| Log-based metrics | **없음** |
| Monitoring dashboards | **없음** |
| Alert policies | **없음** |
| 구조화 로깅 | 미적용 (BE_DEV 영역) |

### 네트워크

| 항목 | 현재 상태 | 비고 |
|------|-----------|------|
| VPC connector | miriart-connector, READY, e2-micro, 10.8.0.0/28 | OK |
| Cloud SQL | miriart-mysql, db-f1-micro, Private IP 10.99.0.3 | OK (소형) |
| Redis | miriart-redis, BASIC, 10.15.105.203:6379, Redis 7.0 | OK |

---

## 1. 실행 플랜

### Phase 0: 긴급 보안 (즉시, Day 1)

#### TASK-A1: miriart-ai IAM 체크 활성화

**위험도**: P0 CRITICAL
**현황**: `invoker-iam-disabled: true` → 외부에서 인증 없이 AI API 호출 가능

```bash
# Step 1: IAM 체크 재활성화
gcloud run services update miriart-ai \
  --region=asia-northeast3 \
  --project=miriarts \
  --invoker-iam-check

# Step 2: BE SA에 Invoker 권한 확인 (이미 있으나 재확인)
gcloud run services add-iam-policy-binding miriart-ai \
  --region=asia-northeast3 \
  --project=miriarts \
  --member="serviceAccount:miriart-be-runner@miriarts.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

**검증**:
```bash
# 외부 직접 호출 → 403
curl -s -o /dev/null -w "%{http_code}" \
  https://miriart-ai-946560105497.asia-northeast3.run.app/health
# 기대: 403

# BE SA identity token으로 호출 → 200
# (impersonate 권한 필요 시 CTO 계정으로)
```

**SSOT 갱신**: §4.3 서비스계정 & IAM에 invoker-iam-check 활성화 기록

---

#### TASK-A2: miriart-be IAM 체크 활성화

**위험도**: P0 CRITICAL
**현황**: BE도 `invoker-iam-disabled: true` — BE는 FE에서 직접 호출하므로 `allUsers` Invoker가 필요할 수 있음

**판단 기준**:
- BE는 FE(브라우저)에서 직접 호출 → IAM identity token 발급 불가
- 따라서 BE는 `--allow-unauthenticated`가 맞고, 인증은 Spring Security JWT로 처리
- 하지만 현재 `--no-allow-unauthenticated` + `invoker-iam-disabled: true`는 모순 상태

**조치 옵션** (CTO 확인 필요):
- **옵션 A**: BE를 `--allow-unauthenticated`로 전환 (FE 브라우저 호출 허용, 앱 레벨 JWT 보호)
- **옵션 B**: IAM 체크 활성화 + `allUsers` Invoker 추가 (실질적으로 옵션 A와 동일)
- **옵션 C**: 현행 유지하되 `invoker-iam-disabled` annotation만 제거 (위험)

**권장**: 옵션 A — BE는 public 서비스, 인증은 Spring Security가 담당

```bash
# 옵션 A 실행 시
gcloud run services update miriart-be \
  --region=asia-northeast3 \
  --project=miriarts \
  --allow-unauthenticated \
  --invoker-iam-check
```

**⚠️ CTO 승인 후 실행**

---

### Phase 1: Cloud Run 리소스 스펙 정렬 (Day 1-2)

#### TASK-D1: miriart-ai 리소스/스케일 최적화

**현황 vs 목표**:

| 파라미터 | 현재 | 목표 | 변경 |
|---------|------|------|------|
| min-instances | 0 | 1 | ✅ |
| concurrency | 80 | 10 | ✅ |
| 나머지 | OK | OK | — |

```bash
gcloud run services update miriart-ai \
  --region=asia-northeast3 \
  --project=miriarts \
  --min-instances=1 \
  --concurrency=10 \
  --cpu-boost
```

**검증**:
```bash
gcloud run services describe miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --format="yaml(spec.template.spec.containerConcurrency,spec.template.metadata.annotations)"
```

**비용 영향**: min-instances=1 → idle 시 ~$35/월 (1vCPU+1Gi, request-based billing)

---

#### TASK-D2: miriart-be 리소스 점검 및 조정

**현황 발견사항**:
- memory: 512Mi → Java Spring Boot에 부족 (OOM 위험)
- max-instances: 2 → DAU 100 기준 충분하나 확장성 부족
- FASTAPI_INTERNAL_URL에 `-svc-` 포함 → 실제 AI URL과 불일치 가능

```bash
# Step 1: BE 메모리 증설
gcloud run services update miriart-be \
  --region=asia-northeast3 \
  --project=miriarts \
  --memory=1Gi

# Step 2: FASTAPI_INTERNAL_URL 확인 및 수정
# 현재: https://miriart-ai-svc-946560105497.asia-northeast3.run.app
# 실제 AI URL: https://miriart-ai-946560105497.asia-northeast3.run.app
# → '-svc-' 유무 확인 필요
```

**⚠️ BE 환경변수 변경은 서비스 재기동 발생 — 트래픽 없는 시간에 실행**

---

#### TASK-H1: GCS 버킷 불일치 해결

**현황**:
- miriart-be env: `GCS_BUCKET_NAME=miriart-uploads` → **버킷 404 (존재하지 않음)**
- miriart-ai env: `GCS_BUCKET_NAME=miriart-bucket` → 정상 존재
- SSOT: `miriart-bucket`이 정식 버킷

**조치 옵션** (CTO 확인 필요):
- **옵션 A**: BE의 `GCS_BUCKET_NAME`을 `miriart-bucket`으로 변경
- **옵션 B**: `miriart-uploads` 버킷 신규 생성 (BE/AI 버킷 분리)

**권장**: 옵션 A (SSOT 기준 `miriart-bucket` 통일)

```bash
# 옵션 A
gcloud run services update miriart-be \
  --region=asia-northeast3 \
  --project=miriarts \
  --update-env-vars=GCS_BUCKET_NAME=miriart-bucket
```

---

### Phase 2: 배포 파이프라인 정비 (Day 2-3)

#### TASK-D3: .dockerignore 생성

```
# .dockerignore
docs/
SSOT/
.cursor/
.claude/
.git/
.gitignore
*.md
!requirements.txt
__pycache__/
.env
.env.*
*.pyc
.pytest_cache/
tests/
cloudbuild.yaml
package-lock.json
```

**효과**: Docker context 크기 감소, 빌드 속도 개선, 이미지 경량화

---

#### TASK-D4: cloudbuild.yaml 개선

**변경 내역**:
1. 듀얼 태그 ($COMMIT_SHA + latest)
2. Cloud Run deploy에 모든 리소스/보안 파라미터 명시
3. logging 옵션 추가

```yaml
# cloudbuild.yaml (최종안)
steps:
  # 1. Docker build (2 tags)
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '-t'
      - 'asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:$COMMIT_SHA'
      - '-t'
      - 'asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:latest'
      - '.'

  # 2. Push all tags
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'push'
      - '--all-tags'
      - 'asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai'

  # 3. Deploy to Cloud Run
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: gcloud
    args:
      - 'run'
      - 'deploy'
      - 'miriart-ai'
      - '--image=asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:$COMMIT_SHA'
      - '--region=asia-northeast3'
      - '--platform=managed'
      - '--port=8080'
      - '--cpu=1'
      - '--memory=1Gi'
      - '--timeout=120'
      - '--min-instances=1'
      - '--max-instances=20'
      - '--concurrency=10'
      - '--cpu-boost'
      - '--no-allow-unauthenticated'
      - '--invoker-iam-check'
      - '--service-account=miriart-ai-runner@miriarts.iam.gserviceaccount.com'
      - '--set-env-vars=GCP_PROJECT_ID=miriarts,GCP_REGION=asia-northeast3,GCS_BUCKET_NAME=miriart-bucket'

images:
  - 'asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:$COMMIT_SHA'
  - 'asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:latest'

options:
  logging: CLOUD_LOGGING_ONLY
```

---

#### TASK-D5: Cloud Build 트리거 생성

**전제**: miriart-ai GitHub 레포가 Cloud Build에 연결되어 있어야 함

```bash
# GitHub 레포 연결 확인
gcloud builds repositories list --project=miriarts --region=asia-northeast3

# 트리거 생성 (GitHub 2nd gen)
gcloud builds triggers create github \
  --project=miriarts \
  --region=asia-northeast3 \
  --name="miriart-ai-main-deploy" \
  --repository="projects/miriarts/locations/asia-northeast3/connections/YOUR_CONNECTION/repositories/miriart-ai" \
  --branch-pattern="^main$" \
  --build-config="cloudbuild.yaml" \
  --description="miriart-ai: main push → build → deploy to Cloud Run"
```

**⚠️ GitHub 연결(connection) 이름은 CTO 확인 필요**. 기존 연결이 없으면 GCP 콘솔에서 GitHub App 설치 → 연결 생성 선행.

**롤백 전략**:
```bash
# 이전 리비전으로 트래픽 전환 (즉시 롤백)
gcloud run services update-traffic miriart-ai \
  --region=asia-northeast3 \
  --to-revisions=PREVIOUS_REVISION=100

# 특정 COMMIT_SHA 이미지로 재배포
gcloud run deploy miriart-ai \
  --image=asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:COMMIT_SHA \
  --region=asia-northeast3
```

---

### Phase 3: GCS / IAM 보강 (Day 3-4)

#### TASK-C1: GCS 버킷 보안 강화

```bash
# public access prevention 명시적 enforce
gcloud storage buckets update gs://miriart-bucket \
  --public-access-prevention

# 현재 버킷 내 public ACL 확인
gcloud storage buckets get-iam-policy gs://miriart-bucket
```

**주의**: public access prevention 적용 시 기존에 public URL로 이미지 제공하는 경로가 깨질 수 있음.
**Phase 1**: 현행 유지 (비공개 버킷 + SA objectAdmin)
**Phase 2**: Signed URL 전환 후 enforce

---

#### TASK-C2: miriart-ai-runner SA 역할 추가 (Signed URL 준비)

```bash
# Phase 2 Signed URL을 위한 serviceAccountTokenCreator 추가
gcloud iam service-accounts add-iam-policy-binding \
  miriart-ai-runner@miriarts.iam.gserviceaccount.com \
  --project=miriarts \
  --member="serviceAccount:miriart-ai-runner@miriarts.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

**검증**:
```bash
gcloud iam service-accounts get-iam-policy \
  miriart-ai-runner@miriarts.iam.gserviceaccount.com --project=miriarts
```

---

### Phase 4: 관측성 기초 세팅 (Day 4-5)

#### TASK-E1: Log-based Metrics 생성

```bash
# Metric 1: 5xx 에러 카운트 (AI)
gcloud logging metrics create miriart-ai-5xx-errors \
  --project=miriarts \
  --description="miriart-ai 5xx error count" \
  --log-filter='resource.type="cloud_run_revision"
resource.labels.service_name="miriart-ai"
httpRequest.status>=500'

# Metric 2: 502 Bad Gateway (AI cold start 지표)
gcloud logging metrics create miriart-ai-502-gateway \
  --project=miriarts \
  --description="miriart-ai 502 Bad Gateway count" \
  --log-filter='resource.type="cloud_run_revision"
resource.labels.service_name="miriart-ai"
httpRequest.status=502'

# Metric 3: 504 Timeout (AI)
gcloud logging metrics create miriart-ai-504-timeout \
  --project=miriarts \
  --description="miriart-ai 504 Gateway Timeout count" \
  --log-filter='resource.type="cloud_run_revision"
resource.labels.service_name="miriart-ai"
httpRequest.status=504'

# Metric 4: BE 5xx 에러 카운트
gcloud logging metrics create miriart-be-5xx-errors \
  --project=miriarts \
  --description="miriart-be 5xx error count" \
  --log-filter='resource.type="cloud_run_revision"
resource.labels.service_name="miriart-be"
httpRequest.status>=500'
```

**BE_DEV가 구조화 로깅 적용 후 추가할 메트릭**:
```
# 향후: gemini_call_error, gemini_call_timeout 패턴 매칭
# (BE_DEV가 logging_config.py + python-json-logger 적용 후)
gcloud logging metrics create miriart-ai-gemini-timeout \
  --log-filter='resource.type="cloud_run_revision"
resource.labels.service_name="miriart-ai"
jsonPayload.message="gemini_call_timeout"'

gcloud logging metrics create miriart-ai-gemini-error \
  --log-filter='resource.type="cloud_run_revision"
resource.labels.service_name="miriart-ai"
jsonPayload.message="gemini_call_error"'
```

---

#### TASK-E2: Alert Policy 생성

```bash
# 5분간 5xx 에러 5건 이상 시 알림
gcloud monitoring policies create \
  --project=miriarts \
  --display-name="miriart-ai 5xx Spike" \
  --condition-display-name="5xx errors > 5 in 5min" \
  --condition-filter='metric.type="logging.googleapis.com/user/miriart-ai-5xx-errors" AND resource.type="cloud_run_revision"' \
  --condition-threshold-value=5 \
  --condition-threshold-duration=300s \
  --condition-threshold-comparison=COMPARISON_GT \
  --notification-channels=CHANNEL_ID \
  --combiner=OR
```

**⚠️ notification-channels(이메일/Slack) 사전 생성 필요**:
```bash
# 이메일 알림 채널 생성
gcloud monitoring channels create \
  --project=miriarts \
  --display-name="CTO Email" \
  --type=email \
  --channel-labels=email_address=6siegfriex@argo.ai.kr
```

---

#### TASK-E3: Monitoring Dashboard (콘솔에서 생성 권장)

대시보드 구성안:

| 패널 | 메트릭 | 차트 |
|------|--------|------|
| AI Request Count | run.googleapis.com/request_count (miriart-ai) | 시계열 |
| AI Latency p50/p95/p99 | run.googleapis.com/request_latencies (miriart-ai) | 히트맵 |
| AI 5xx Rate | user/miriart-ai-5xx-errors | 시계열 |
| AI Instance Count | run.googleapis.com/container/instance_count (miriart-ai) | 시계열 |
| BE Request Count | run.googleapis.com/request_count (miriart-be) | 시계열 |
| BE Latency p95 | run.googleapis.com/request_latencies (miriart-be) | 히트맵 |
| BE 5xx Rate | user/miriart-be-5xx-errors | 시계열 |

---

## 2. 운영 Runbook (AI 전용)

### 장애 대응 3단계

**1단계: Health Check**
```bash
# AI 서비스 상태
curl -s -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  https://miriart-ai-946560105497.asia-northeast3.run.app/health

# BE 서비스 상태
curl -s https://miriart-be-946560105497.asia-northeast3.run.app/actuator/health
```

**2단계: 로그 확인**
```bash
# AI 최근 에러 로그
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="miriart-ai" AND severity>=ERROR' \
  --project=miriarts --limit=20 --freshness=1h --format=json

# BE → AI 호출 로그 (status, error_code 패턴)
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="miriart-ai" AND httpRequest.requestUrl:"/internal/ai/"' \
  --project=miriarts --limit=20 --freshness=1h \
  --format="table(timestamp,httpRequest.status,httpRequest.latency,httpRequest.requestUrl)"
```

**3단계: Vertex AI / IAM / GCS 점검**
```bash
# Vertex AI 할당량 확인
gcloud services list --project=miriarts --filter="config.name:aiplatform"

# AI SA 권한 확인
gcloud projects get-iam-policy miriarts \
  --flatten="bindings[].members" \
  --filter="bindings.members:miriart-ai-runner" \
  --format="table(bindings.role)"

# GCS 접근 테스트
gcloud storage ls gs://miriart-bucket/ --project=miriarts | head -5
```

### 롤백 절차

```bash
# 1. 현재 리비전 확인
gcloud run revisions list --service=miriart-ai \
  --region=asia-northeast3 --project=miriarts

# 2. 이전 리비전으로 100% 트래픽 전환
gcloud run services update-traffic miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --to-revisions=PREVIOUS_REVISION_NAME=100

# 3. 복구 확인
curl -s -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  https://miriart-ai-946560105497.asia-northeast3.run.app/health
```

---

## 3. SSOT 갱신 항목 (작업 완료 후)

| 섹션 | 갱신 내용 |
|------|-----------|
| §2 Cloud Run 서비스 | AI: min-instances=1, concurrency=10, invoker-iam-check 활성 |
| §2 Cloud Run 서비스 | BE: memory 1Gi, invoker-iam 상태 갱신, GCS_BUCKET_NAME 수정 |
| §4.3 서비스 계정 | miriart-ai-runner에 iam.serviceAccountTokenCreator 추가 |
| §5.1 배포 파이프라인 | Cloud Build 트리거 생성, 듀얼 태그 전략 |
| §5.2 배포 파라미터 | AI: 전체 파라미터 확정 (concurrency, min/max 등) |
| §6.2 로그 & 모니터링 | log-based metrics, alert policy, dashboard 추가 |
| §7 TODO | TODO-003(AI배포) 완료, TODO-006(관측성) 부분완료, TODO-007(BE파라미터) 진행중 |
| CHANGELOG_infra.md | 날짜, INFRA_DEV 롤, 구체적 수정 내역 기록 |

---

## 4. 실행 순서 체크리스트

### Phase 0: 긴급 보안 (Day 1)
- [ ] TASK-A1: miriart-ai `--invoker-iam-check` 활성화
- [ ] TASK-A1: 검증 — 외부 403, BE SA 200
- [ ] TASK-A2: miriart-be IAM 정책 결정 (CTO 승인 필요)

### Phase 1: 리소스 스펙 (Day 1-2)
- [ ] TASK-D1: miriart-ai min-instances=1, concurrency=10
- [ ] TASK-D2: miriart-be memory 1Gi 증설
- [ ] TASK-D2: FASTAPI_INTERNAL_URL `-svc-` 확인/수정
- [ ] TASK-H1: GCS 버킷명 통일 결정 (CTO 확인)

### Phase 2: 배포 파이프라인 (Day 2-3)
- [ ] TASK-D3: `.dockerignore` 생성 + 커밋
- [ ] TASK-D4: `cloudbuild.yaml` 최종안 교체 + 커밋
- [ ] TASK-D5: Cloud Build 트리거 생성 (GitHub 연결 확인)
- [ ] TASK-D5: 트리거 테스트 빌드 실행

### Phase 3: GCS/IAM (Day 3-4)
- [ ] TASK-C1: GCS 버킷 보안 검토 (Phase 1: 현행 유지)
- [ ] TASK-C2: miriart-ai-runner serviceAccountTokenCreator 추가

### Phase 4: 관측성 (Day 4-5)
- [ ] TASK-E1: log-based metrics 4개 생성
- [ ] TASK-E2: 알림 채널 생성 + alert policy 생성
- [ ] TASK-E3: monitoring dashboard 생성

### 완료 후
- [ ] SSOT v1.2 갱신 (§2, §4, §5, §6, §7)
- [ ] CHANGELOG_infra.md 기록

---

## 5. CTO 확인 필요 사항 (Blockers)

| # | 항목 | 배경 | 옵션 |
|---|------|------|------|
| 1 | **TASK-A2**: miriart-be IAM 정책 | BE는 FE에서 직접 호출 — `invoker-iam-disabled: true` 해제 시 FE 호출 차단 가능 | A: `--allow-unauthenticated` 전환 / B: IAM 체크 + allUsers Invoker |
| 2 | **TASK-H1**: GCS 버킷명 | BE에 `miriart-uploads`(404) 설정, AI에 `miriart-bucket` | A: BE를 `miriart-bucket`으로 통일 / B: 신규 버킷 생성 |
| 3 | **TASK-D2**: FASTAPI_INTERNAL_URL | BE env에 `-svc-` 포함 URL — 실제 AI URL과 다를 수 있음 | 실제 호출 성공 여부 확인 필요 |
| 4 | **TASK-D5**: GitHub 연결 | Cloud Build GitHub App 연결이 필요 — 기존 연결 유무 확인 | GCP 콘솔에서 연결 생성 |
| 5 | **TASK-E2**: 알림 수신처 | 이메일? Slack? | 알림 채널 결정 |

---

*이 플랜은 GCP 실시간 조회 결과를 기반으로 작성됨. 실행 시 각 단계 검증 후 다음 단계 진행.*
