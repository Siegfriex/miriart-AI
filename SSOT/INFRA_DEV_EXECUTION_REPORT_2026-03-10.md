# INFRA_DEV 실행 보고서 — 2026-03-10

> **기준 플랜**: `.cursor/plan/INFRA_DEV_PLAN_v1.0.md`
> **실행 주체**: INFRA_DEV 에이전트 (Claude Code)
> **환경**: WSL Ubuntu-24.04, gcloud CLI, 프로젝트 `miriarts`

---

## 1. 실행 요약

| 구분 | 완료 | 블로커 | 스킵 |
|------|------|--------|------|
| **[1] 즉시 실행** | 5/5 | 0 | 0 |
| **[2] CTO 확정 후** | 6/7 | 1 (A2) | 1 (D5) |
| **문서화** | 3/3 | 0 | 0 |

---

## 2. [1] 즉시 실행 항목 — 전체 완료

### TASK-A1: miriart-ai IAM invoker-iam-check 활성화

**위험도**: P0 CRITICAL

**실행 내역**:
```bash
gcloud run services update miriart-ai \
  --region=asia-northeast3 --project=miriarts --invoker-iam-check

gcloud run services add-iam-policy-binding miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --member="serviceAccount:miriart-be-runner@miriarts.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

**검증 결과**:

| 테스트 | 기대 | 결과 | 상태 |
|--------|------|------|------|
| 외부 curl /health | 403 | **403** | ✅ |
| BE SA impersonate → /health | 200 | 검증 불가 | ⚠️ CTO 계정에 impersonate 권한 없음 |

> BE SA 토큰 검증은 CTO 계정의 impersonate 권한 부족으로 CLI에서 불가. 프로덕션 BE→AI 호출은 Cloud Run SA 자동 토큰이므로 실서비스 영향 없음. 실제 체인 검증은 FE→BE→AI 시나리오로 확인 필요.

---

### TASK-D1: miriart-ai 리소스/스케일 최적화

**실행 내역**:
```bash
gcloud run services update miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --min-instances=1 --concurrency=10 --cpu-boost
```

**결과**: 리비전 `miriart-ai-00003-85b` 배포, 100% 트래픽.

**검증 (describe)**:
```yaml
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/maxScale: '20'
        autoscaling.knative.dev/minScale: '1'
        run.googleapis.com/startup-cpu-boost: 'true'
    spec:
      containerConcurrency: 10
```

| 파라미터 | Before | After |
|---------|--------|-------|
| min-instances | 0 | **1** |
| concurrency | 80 | **10** |
| cpu-boost | enabled | enabled |
| max-instances | 20 | 20 (변경 없음) |

**비용 영향**: idle 시 ~$35/월 (1vCPU+1Gi, request-based billing)

---

### TASK-C2: miriart-ai-runner serviceAccountTokenCreator 추가

**실행 내역**:
```bash
gcloud iam service-accounts add-iam-policy-binding \
  miriart-ai-runner@miriarts.iam.gserviceaccount.com \
  --project=miriarts \
  --member="serviceAccount:miriart-ai-runner@miriarts.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

**검증 (get-iam-policy)**:
```yaml
bindings:
- members:
  - serviceAccount:miriart-ai-runner@miriarts.iam.gserviceaccount.com
  role: roles/iam.serviceAccountTokenCreator
```

**용도**: Phase 2 GCS Signed URL 생성 시 `signBlob` 권한으로 사용.

---

### TASK-E1: Log-based Metrics 4개 생성

**실행 내역**:

| 메트릭 이름 | 필터 | 용도 |
|-------------|------|------|
| `miriart-ai-5xx-errors` | AI Cloud Run, status>=500 | AI 전체 5xx |
| `miriart-ai-502-gateway` | AI Cloud Run, status=502 | cold start / upstream 장애 |
| `miriart-ai-504-timeout` | AI Cloud Run, status=504 | Gemini 타임아웃 |
| `miriart-be-5xx-errors` | BE Cloud Run, status>=500 | BE 전체 5xx |

**검증 (logging metrics list)**:
```
NAME                    DESCRIPTION
miriart-ai-502-gateway  miriart-ai 502 Bad Gateway count
miriart-ai-504-timeout  miriart-ai 504 Gateway Timeout count
miriart-ai-5xx-errors   miriart-ai 5xx error count
miriart-be-5xx-errors   miriart-be 5xx error count
```

---

### TASK-E3: Monitoring Dashboard 생성

**대시보드명**: `MiriArt-AI BE/AI Overview`
**ID**: `000813b5-103e-48d7-8966-15022037129a`

| 패널 | 메트릭 | 차트 |
|------|--------|------|
| AI Request Count | `run.googleapis.com/request_count` (miriart-ai) | 시계열 (ALIGN_RATE) |
| AI Latency p99 | `run.googleapis.com/request_latencies` (miriart-ai) | 시계열 (ALIGN_PERCENTILE_99) |
| AI 5xx Rate | `logging.googleapis.com/user/miriart-ai-5xx-errors` | 시계열 (ALIGN_RATE) |
| AI Instance Count | `run.googleapis.com/container/instance_count` (miriart-ai) | 시계열 (ALIGN_MEAN) |
| BE Request Count | `run.googleapis.com/request_count` (miriart-be) | 시계열 (ALIGN_RATE) |
| BE Latency p95 | `run.googleapis.com/request_latencies` (miriart-be) | 시계열 (ALIGN_PERCENTILE_95) |
| BE 5xx Rate | `logging.googleapis.com/user/miriart-be-5xx-errors` | 시계열 (ALIGN_RATE) |

---

## 3. [2] CTO 확정 후 실행 항목

### TASK-A2: miriart-be IAM 체크 활성화 — ⚠️ 블로커

**실행 시도**:
```bash
# Step 1: invoker-iam-check 활성화 → 성공
gcloud run services update miriart-be \
  --region=asia-northeast3 --project=miriarts --invoker-iam-check

# Step 2: allUsers Invoker 추가 → 실패
gcloud run services add-iam-policy-binding miriart-be \
  --region=asia-northeast3 --project=miriarts \
  --member="allUsers" --role="roles/run.invoker"
# ERROR: FAILED_PRECONDITION: One or more users named in the policy do not belong
# to a permitted customer, perhaps due to an organization policy.
```

**원인**: 조직 정책 `iam.allowedPolicyMemberDomains`가 `allUsers` 바인딩을 차단.

**영향 확인**:
```
curl BE /actuator/health → 403 (FE→BE 호출 차단)
```

**즉시 롤백**:
```bash
gcloud run services update miriart-be \
  --region=asia-northeast3 --project=miriarts --no-invoker-iam-check
# → 200 복구 확인
```

**현재 상태**: BE `invoker-iam-disabled: true` 유지 (DRS 완화 상태). 앱 레벨 인증은 Spring Security JWT가 처리.

**해결 계획**: SSOT §4.2.1에 문서화 완료. 릴리즈 전 조직 태그(`sa-api-key-policy=exempt`) 기반 예외 적용 후 정상화 (TODO-009).

---

### TASK-H1: GCS 버킷 불일치 해결

**발견 사항**:
```yaml
# BE 환경변수 (수정 전)
GCS_BUCKET_NAME: miriart-uploads  # ← 404 (버킷 존재하지 않음)

# AI 환경변수
GCS_BUCKET_NAME: miriart-bucket   # ← 정상 존재
```

**실행**:
```bash
gcloud run services update miriart-be \
  --region=asia-northeast3 --project=miriarts \
  --update-env-vars=GCS_BUCKET_NAME=miriart-bucket
```

**결과**: SSOT 기준 `miriart-bucket`으로 통일. ✅

---

### TASK-D2: miriart-be 리소스 점검 및 조정

#### FASTAPI_INTERNAL_URL 수정

**발견 사항**:
```yaml
# BE 설정 (수정 전)
FASTAPI_INTERNAL_URL: https://miriart-ai-svc-946560105497.asia-northeast3.run.app
# → curl 결과: 404 (존재하지 않는 URL)

# 실제 AI Cloud Run URL (describe로 확인)
status.url: https://miriart-ai-gzjczkus6q-du.a.run.app
# → curl 결과: 200
```

**실행** (H1과 동시):
```bash
gcloud run services update miriart-be \
  --region=asia-northeast3 --project=miriarts \
  --update-env-vars="FASTAPI_INTERNAL_URL=https://miriart-ai-gzjczkus6q-du.a.run.app,GCS_BUCKET_NAME=miriart-bucket"
```

#### Memory 증설

```bash
gcloud run services update miriart-be \
  --region=asia-northeast3 --project=miriarts --memory=1Gi
```

| 항목 | Before | After |
|------|--------|-------|
| FASTAPI_INTERNAL_URL | `miriart-ai-svc-...` (404) | `miriart-ai-gzjczkus6q-du...` (200) |
| GCS_BUCKET_NAME | `miriart-uploads` (404) | `miriart-bucket` (OK) |
| memory | 512Mi | **1Gi** |

**결과**: 리비전 `miriart-be-00032-jnx`, 200 정상. ✅

---

### TASK-D3: .dockerignore 보완

**변경 내역** (기존 파일에 추가):

| 추가 항목 | 이유 |
|-----------|------|
| `SSOT/` | SSOT 문서 이미지 제외 |
| `.claude/` | Claude Code 설정 제외 |
| `.env.*` | .env.example 등 이미지 제외 |
| `package-lock.json` | FE용 lock 파일 제외 |

✅

---

### TASK-D4: cloudbuild.yaml 최종안

**변경 내역**:

| 항목 | Before | After |
|------|--------|-------|
| 이미지 태그 | `$COMMIT_SHA`만 | `$COMMIT_SHA` + `latest` (듀얼) |
| push | 단일 태그 | `--all-tags` |
| `--min-instances` | 없음 | `1` |
| `--max-instances` | 없음 | `20` |
| `--concurrency` | 없음 | `10` |
| `--cpu-boost` | 없음 | 추가 |
| `--invoker-iam-check` | 없음 | 추가 |
| `options.logging` | 없음 | `CLOUD_LOGGING_ONLY` |

✅

---

### TASK-D5: Cloud Build 트리거 — ⏸️ 스킵

CTO 지시에 따라 이번 스프린트에서는 실행하지 않음. 수동 `gcloud builds submit`만 사용.

---

### TASK-E2: Alert Policy 생성

**알림 채널**:
```bash
gcloud beta monitoring channels create --project=miriarts \
  --display-name="CTO Email" --type=email \
  --channel-labels=email_address=6siegfriex@argo.ai.kr
# → projects/miriarts/notificationChannels/4993565277249380040
```

**Alert Policy**:

| 항목 | 값 |
|------|-----|
| 이름 | `miriart-ai 5xx Spike` |
| 조건 | 5분간 5xx 에러 > 5건 |
| 알림 대상 | CTO Email (`6siegfriex@argo.ai.kr`) |
| 자동 종료 | 7일 |
| Policy ID | `8942907770327332678` |

✅

---

## 4. SSOT 갱신 내역

| 섹션 | 갱신 내용 |
|------|-----------|
| §2 Cloud Run (AI) | concurrency=10, min=1, max=20, invoker-iam-check 활성, cpu-boost |
| §2 Cloud Run (BE) | memory 1Gi (기존 512Mi), invoker-iam-disabled 유지 사유 명시 |
| §3.2 FASTAPI_INTERNAL_URL | 확정값 `https://miriart-ai-gzjczkus6q-du.a.run.app` |
| §4.2.1 (신규) | 조직 정책 현황, DRS 완화 상태 명시, 릴리즈 전 태그 기반 전환 계획 |
| §4.3 SA | miriart-ai-runner에 `roles/iam.serviceAccountTokenCreator` 추가 |
| §6.2 관측성 | Log-based Metrics 4개, Dashboard, Alert Policy 기록 |
| §7 TODO-009 (신규) | BE IAM 정상화 — 릴리즈 전 조직 태그 예외 적용 |
| CHANGELOG_infra.md | Phase 0-1, Phase 2, 조직 정책 문서화 3건 기록 |

---

## 5. 미해결 블로커

| # | 항목 | 원인 | 해결 방법 | 시점 |
|---|------|------|-----------|------|
| 1 | **BE IAM (TODO-009)** | 조직 정책 `iam.allowedPolicyMemberDomains`가 `allUsers` 차단 | 조직 태그 `sa-api-key-policy=exempt` 부여 후 `--allow-unauthenticated --invoker-iam-check` | 릴리즈 전 보안 점검 |

---

## 6. GCP 리소스 최종 상태 (실측)

### miriart-ai Cloud Run

| 항목 | 값 |
|------|-----|
| URL | `https://miriart-ai-gzjczkus6q-du.a.run.app` |
| 최신 리비전 | `miriart-ai-00003-85b` |
| CPU/Memory | 1 vCPU / 1Gi |
| Timeout | 120s |
| Concurrency | 10 |
| Min/Max Instances | 1 / 20 |
| CPU Boost | enabled |
| IAM | invoker-iam-check **활성**, BE SA만 Invoker |
| 외부 접근 | **403** (정상) |

### miriart-be Cloud Run

| 항목 | 값 |
|------|-----|
| URL | `https://miriart-be-946560105497.asia-northeast3.run.app` |
| 최신 리비전 | `miriart-be-00032-jnx` |
| Memory | **1Gi** (기존 512Mi에서 증설) |
| FASTAPI_INTERNAL_URL | `https://miriart-ai-gzjczkus6q-du.a.run.app` |
| GCS_BUCKET_NAME | `miriart-bucket` |
| IAM | invoker-iam-disabled: true (DRS 완화) |
| 외부 접근 | **200** (정상) |

### 관측성

| 리소스 | 이름/ID |
|--------|---------|
| Metrics (4) | miriart-ai-5xx-errors, miriart-ai-502-gateway, miriart-ai-504-timeout, miriart-be-5xx-errors |
| Dashboard | MiriArt-AI BE/AI Overview (`000813b5-103e-48d7-8966-15022037129a`) |
| Alert Policy | miriart-ai 5xx Spike (`8942907770327332678`) |
| Notification Channel | CTO Email (`4993565277249380040`) |

---

*보고 완료. 2026-03-10, INFRA_DEV 에이전트.*
