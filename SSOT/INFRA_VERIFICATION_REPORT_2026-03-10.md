# 인프라 최종 검증 리포트 — 2026-03-10

> **대상**: INFRA-T1 ~ T4 검증 결과
> **실행 주체**: INFRA_DEV 에이전트 (Claude Code)

---

## INFRA-T1: E2E 스모크 캡처

### 서비스 상태 확인

| 서비스 | URL | Health Check | 기대값 | 실측 |
|--------|-----|-------------|--------|------|
| miriart-ai | `https://miriart-ai-gzjczkus6q-du.a.run.app` | `/health` (외부) | 403 | **403** ✅ |
| miriart-be | `https://miriart-be-gzjczkus6q-du.a.run.app` | `/actuator/health` | 200 | **200** ✅ |
| miriart-be (alt) | `https://miriart-be-946560105497.asia-northeast3.run.app` | `/actuator/health` | 200 | **200** ✅ |

### Cloud Run 상태

| 서비스 | Ready | Latest Revision | 비고 |
|--------|-------|-----------------|------|
| miriart-ai | `True` (02:34 UTC) | `miriart-ai-00003-85b` | min=1, concurrency=10, IAM 보호 |
| miriart-be | `True` (03:45 UTC) | `miriart-be-00032-jnx` | 1Gi memory, DRS 완화 |

### 오늘 로그 요약 (2026-03-10)

**miriart-ai 로그**:

| 시각 (UTC) | Status | URL | 비고 |
|------------|--------|-----|------|
| 02:34:14~17 | 403 | `/`, `/favicon.ico` | IAM 차단 (정상) |
| 03:43:22 | **200** | `/health` | 내부 호출 성공 (SA 인증) |
| 04:19:15 | 403 | `/health` | 외부 curl 검증 (정상) |

**miriart-be 에러 로그**:

| 시각 (UTC) | Status | URL | 비고 |
|------------|--------|-----|------|
| 03:22:38 | 403 | `/actuator/health` | TASK-A2 IAM 테스트 중 발생 (이후 롤백) |

### E2E 트래픽

오늘 FE→BE→AI 실제 E2E 트래픽(analyze/chat/QA)은 **기록 없음**. 프로덕션 사용자 호출이 없는 상태.

> **권장**: FE에서 실제 분석/채팅 1회씩 수행 후 로그 재확인 필요. CLI에서 E2E를 직접 트리거하려면 JWT 토큰이 필요하며, 이는 BE 로그인 API를 통해 발급받아야 함.

---

## INFRA-T2: 관측성 파이프라인 검증

### 메트릭 존재 확인

| 메트릭 | 상태 |
|--------|------|
| `miriart-ai-5xx-errors` | ✅ 존재 |
| `miriart-ai-502-gateway` | ✅ 존재 |
| `miriart-ai-504-timeout` | ✅ 존재 |
| `miriart-be-5xx-errors` | ✅ 존재 |

### Alert Policy 확인

| 항목 | 상태 |
|------|------|
| `miriart-ai 5xx Spike` | ✅ Enabled |
| Policy ID | `8942907770327332678` |
| 알림 채널 | CTO Email 연결 |

### 5xx 에러 발생 현황

오늘 AI/BE 모두 **5xx 에러 0건**. 알림 트리거 조건(5분간 5건 초과) 미달.

### 의도적 5xx 테스트 — 제한사항

| 테스트 | 가능 여부 | 이유 |
|--------|-----------|------|
| AI에 직접 잘못된 요청 | ❌ | IAM 보호로 외부 접근 403 |
| BE를 통한 AI 에러 유발 | ❌ | JWT 인증 필요 |
| BE 직접 5xx 유발 | ⚠️ | 존재하지 않는 엔드포인트 → 404(5xx 아님) |

> **결론**: 관측성 인프라(메트릭, 알림, 대시보드) 구성은 정상. 실제 5xx 발생 시 파이프라인 작동 여부는 E2E 트래픽 발생 후 검증 필요. 알림 이메일 수신 테스트는 실제 5xx 발생 시점에 확인.

---

## INFRA-T3: imageUrl 접근성 검증 + 정책 제안

### 현재 상태

```
테스트 URL:
https://storage.googleapis.com/miriart-bucket/artworks/2026-03-03/aa8ac12c-..._IMG_6728.jpeg

결과: 403 Forbidden
```

### GCS 버킷 IAM 정책

| 바인딩 | 역할 |
|--------|------|
| `miriart-ai-runner` SA | `roles/storage.objectAdmin` |
| `miriart-be-runner` SA | `roles/storage.objectAdmin` |
| `projectEditor/Owner` | `roles/storage.legacyBucketOwner` |
| `projectViewer` | `roles/storage.legacyBucketReader` |
| **allUsers** | **없음** (공개 접근 불가) |

### 버킷 설정

| 항목 | 값 |
|------|-----|
| Uniform Bucket-Level Access | `true` |
| Public Access Prevention | `inherited` (조직 정책에 따름) |

### 영향 분석

AI 서비스가 이미지 분석/편집 결과로 반환하는 `imageUrl`이 `gs://` 또는 `https://storage.googleapis.com/...` 형태인 경우, **FE에서 직접 접근 불가** (403).

### 정책 제안

#### Option A: Phase 1 — BE 프록시 (즉시 적용 가능)

```
FE → BE /api/images/{id} → BE가 SA 인증으로 GCS 다운로드 → FE에 바이너리 응답
```

- **장점**: 추가 인프라 변경 없음, 보안 유지
- **단점**: BE 트래픽 증가, 대용량 이미지 시 BE 메모리 압박

#### Option B: Phase 2 — Signed URL (권장, SA 준비 완료)

```
FE → BE /api/images/{id}/url → BE가 SA로 Signed URL 생성 (유효 15분) → FE가 직접 GCS 접근
```

- **장점**: BE 부하 최소화, 대용량 이미지 처리 가능
- **단점**: BE 코드 수정 필요
- **준비 상태**: `miriart-ai-runner` SA에 `serviceAccountTokenCreator` 역할 이미 부여 (TASK-C2 완료)

#### 권장안

**Phase 1(현재)**: BE 프록시 방식으로 최소 구현 → **Phase 2(릴리즈 전)**: Signed URL로 전환.

BE 코드에서 AI 응답의 `imageUrl`을 그대로 FE에 전달하지 않고, BE가 프록시하거나 Signed URL로 변환해서 전달해야 함.

---

## INFRA-T4: Runbook v1

**생성 완료**: `SSOT/RUNBOOK_AI_INFRA_v1.md`

| 섹션 | 내용 |
|------|------|
| §1 서비스 개요 | Cloud Run 스펙, URL, SA 정보 |
| §2 배포 절차 | Cloud Build 수동 빌드+배포, 검증 명령어 |
| §3 롤백 절차 | 리비전 트래픽 전환, 이미지 태그 재배포 |
| §4 장애 대응 | 3단계 프로세스 (탐지→분류→조치), 증상별 원인 표 |
| §5 관측성 | 대시보드, 메트릭, 알림 정책 참조 |
| §6 운영 명령어 | 스케일링, 환경변수, 로그 스트리밍 |
| §7 알려진 제약사항 | GCS 403, BE IAM, CI/CD 트리거, SA impersonate |

---

## 종합 판정

| 항목 | 상태 | 판정 |
|------|------|------|
| AI Cloud Run | Ready, IAM 보호, min=1 | ✅ 정상 |
| BE Cloud Run | Ready, 200, 1Gi | ✅ 정상 |
| BE→AI 연결 (FASTAPI_INTERNAL_URL) | 올바른 URL 설정 | ✅ 정상 |
| GCS 버킷 통일 | `miriart-bucket` | ✅ 정상 |
| 관측성 인프라 | 메트릭 4개, 대시보드, 알림 | ✅ 구성 완료 |
| GCS imageUrl 접근 | 403 (공개 불가) | ⚠️ Phase 1/2 결정 필요 |
| E2E 트래픽 검증 | 미실행 (FE 트래픽 없음) | ⚠️ FE 테스트 필요 |
| 5xx 알림 이메일 검증 | 미검증 (5xx 0건) | ⚠️ 실트래픽 후 확인 |

### 배포 차단 이슈 (Blocker)

**없음**. 인프라는 배포 가능 상태. 다만 아래 3건은 릴리즈 전 확인 필요:

1. **GCS imageUrl**: FE에서 이미지 표시 방식 결정 (BE 프록시 vs Signed URL)
2. **E2E 체인**: FE→BE→AI 실제 호출 1회 이상 성공 확인
3. **BE IAM (TODO-009)**: 릴리즈 전 조직 태그 예외 적용

---

*검증 완료. 2026-03-10, INFRA_DEV 에이전트.*
