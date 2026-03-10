# Signed URL 파이프라인 Go-Live 리포트

> **작성일**: 2026-03-10
> **작성자**: INFRA_DEV 에이전트
> **목적**: GCS Signed URL 파이프라인이 인프라/AI 인프라 관점에서 **운영 가능한 상태**인지를 CTO가 한 번에 판단할 수 있도록 정리

---

## 1. 메트릭 / 대시보드 / 알람 생성 내역

### 1.1 Log-based Metrics

| 메트릭 ID | Log Filter | 상태 |
|-----------|-----------|------|
| `miriart-be-signed-url-count` | `resource.type="cloud_run_revision" AND resource.labels.service_name="miriart-be" AND jsonPayload.message="signed_url_generated"` | ✅ 생성 완료 |
| `miriart-be-signed-url-errors` | `resource.type="cloud_run_revision" AND resource.labels.service_name="miriart-be" AND jsonPayload.message="signed_url_error"` | ✅ 생성 완료 |

> 기존 이름(`miriart-be-signed-url-issued`, `miriart-be-signed-url-error`)은 삭제하고 지침 기준 이름으로 재생성 완료.

### 1.2 대시보드

| 이름 | ID | 위젯 | URL |
|------|-----|------|-----|
| MiriArt - BE Signed URL | `707df634-a515-4226-9e73-edf7f9e9db91` | (1) Signed URL 발급 수 (1분 평균, ALIGN_RATE) (2) Signed URL 실패 수 (ALIGN_SUM) (3) Top objectPath (Logs Explorer 참조 텍스트) | [콘솔 링크](https://console.cloud.google.com/monitoring/dashboards/builder/707df634-a515-4226-9e73-edf7f9e9db91?project=miriarts) |

> 기존 `MiriArt-AI BE/AI Overview` (ID: `000813b5-103e-48d7-8966-15022037129a`)는 그대로 유지.

### 1.3 알람 정책

| 이름 | 조건 | 알림 채널 | Policy ID |
|------|------|-----------|-----------|
| Signed URL Errors Spike | `miriart-be-signed-url-errors > 0` (5분 지속, ALIGN_SUM 300s) | CTO Email (`6siegfriex@argo.ai.kr`) — 채널 ID `4993565277249380040` | `10494294328358958245` |

> 기존 `miriart-ai 5xx Spike` (ID: `8942907770327332678`)와 동일한 알림 채널 사용.

---

## 2. BE/FE 배포 버전 및 상태

### 2.1 BE (miriart-be)

| 항목 | 값 | 상태 |
|------|-----|------|
| 최신 리비전 | `miriart-be-00032-jnx` | ✅ Running |
| `GCS_BUCKET_NAME` 환경변수 | `miriart-bucket` | ✅ 정상 |
| `SPRING_PROFILES_ACTIVE` | `prod` | ✅ |
| `FASTAPI_INTERNAL_URL` | `https://miriart-ai-gzjczkus6q-du.a.run.app` | ✅ |
| Signed URL 엔드포인트 (`/api/images/{id}/url`) | **BE 코드 구현 완료, 배포 대기** | ⏳ |
| Signed URL 로그 출력 (`signed_url_generated`/`signed_url_error`) | **BE 코드 추가 예정** | ⏳ |

> **참고**: 현재 리비전(00032)에는 아직 Signed URL 엔드포인트가 포함되지 않음. BE팀에서 다음 배포에 포함 예정. 배포 후 Runbook §8 체크리스트를 순서대로 실행할 것.

### 2.2 FE

| 항목 | 상태 |
|------|------|
| `SignedImage` 컴포넌트 도입 | **FE 구현 완료, 배포 대기** |
| `/api/images/{analysisId}/url` 호출 전환 | ⏳ (BE 배포 후 동시 또는 직후 배포) |
| `F005`/`I001` 에러 핸들링 UX | ⏳ |

> FE는 BE Signed URL 엔드포인트 배포 후 연동 배포 예정. 배포 시 버전/커밋 해시를 CHANGELOG_infra.md에 기록할 것.

### 2.3 AI (miriart-ai)

| 항목 | 값 | 상태 |
|------|-----|------|
| 최신 리비전 | `miriart-ai-00003-85b` | ✅ Running |
| `GCS_BUCKET_NAME` | `miriart-bucket` | ✅ |
| `GCP_PROJECT_ID` | `miriarts` | ✅ |
| 외부 /health 접근 | 403 (IAM 보호 정상) | ✅ |
| `edited/` prefix 사용 | `image_edit_service.py:64` — `f"edited/{uuid.uuid4()}.jpg"` | ✅ SSOT §3.4 일치 |
| Signed URL 관련 코드 변경 | 불필요 (BE에서만 생성) | ✅ |

---

## 3. 인프라 체크리스트 (Runbook §8 기준)

### 배포 전 체크

| 항목 | 담당 | 상태 |
|------|------|------|
| CORS 설정 (`miriart-bucket`) | 인프라 | ✅ origin: `https://miriart.app`, `http://localhost:3000`, method: GET, maxAge: 3600 |
| SA tokenCreator (`miriart-be-runner`) | 인프라 | ✅ `roles/iam.serviceAccountTokenCreator` 자기 자신 바인딩 확인 |
| 메트릭 생성 | 인프라 | ✅ `miriart-be-signed-url-count`, `miriart-be-signed-url-errors` |
| 대시보드 생성 | 인프라 | ✅ `MiriArt - BE Signed URL` (3위젯) |
| 알람 정책 | 인프라 | ✅ `Signed URL Errors Spike` |
| SSOT 문서 업데이트 | 인프라 | ✅ miriarts_infra.md, RUNBOOK, DASHBOARD_SPEC, CHANGELOG |
| BE 엔드포인트 구현 | BE | ⏳ 구현 완료, 배포 대기 |
| BE 로그 출력 규격 | BE | ⏳ DASHBOARD_SPEC §4 참조하여 구현 예정 |
| FE SignedImage 컴포넌트 | FE | ⏳ 구현 완료, 배포 대기 |

### 배포 직후 (~10분) — BE/FE 배포 후 실행

| 항목 | 확인 방법 | 상태 |
|------|-----------|------|
| `signed_url_generated` 로그 확인 | `gcloud logging read` (Runbook §4.3 Step 2) | ⏳ BE 배포 후 |
| `signed_url_error` 비정상 다발 여부 | 동일 | ⏳ |
| FE 이미지 렌더링 | 브라우저 네트워크 탭 | ⏳ |
| CORS 에러 없음 | 브라우저 콘솔 | ⏳ |
| 메트릭 수집 시작 | Monitoring → Metrics Explorer | ⏳ |

### 배포 1일 후 — 스냅샷 기록

| 항목 | 상태 |
|------|------|
| error/count 비율 확인 (목표: < 1%) | ⏳ |
| 대시보드 파형 정상 확인 | ⏳ |
| 알림 테스트 (의도적 에러 → 수신 확인) | ⏳ |

---

## 4. 배포 직후~1일차 모니터링 플로우

### T0~T+2시간 (BE/FE 배포 직후)

1. QA 세션: 분석 업로드 → 결과 상세 → 홈 최신 목록 → 아카이브 → 채팅방 헤더
2. 확인 항목:
   - GCS 403/404 없음
   - FE 이미지 깨짐 없음
   - BE F005/I001 과도 발생 없음
3. 대시보드 확인:
   - `miriart-be-signed-url-count` > 0 (트래픽 발생 확인)
   - `miriart-be-signed-url-errors` = 0

### T0~T+24시간

1. `Signed URL Errors Spike` 알람 발생 여부 모니터링
2. 발생 시: Runbook §4.3 "이미지 로딩 실패 디버깅 절차" 5단계 실행
3. 절차 수행 중 부족한 부분이 발견되면 Runbook 즉시 보완

### 1일차 스냅샷 (T+24시간)

> **BE/FE 배포 후 아래 항목을 채워 CHANGELOG_infra.md에 기록**

```
- Signed URL count 총량: ___건
- Signed URL error 총량: ___건
- 에러율: ___%
- 대표 로그 샘플: (signed_url_generated 1건, signed_url_error 0~1건)
- 이슈 발생: 없음 / (상세 기록)
```

---

## 5. 발생 이슈 및 대응

| # | 이슈 | 원인 | 대응 | 상태 |
|---|------|------|------|------|
| — | (BE/FE 배포 전이므로 운영 이슈 없음) | — | — | — |

---

## 6. 남은 TODO

| ID | 항목 | 담당 | 우선순위 | 설명 |
|----|------|------|----------|------|
| SU-1 | BE Signed URL 엔드포인트 배포 | BE | **High** | `/api/images/{id}/url` + JSON 로그 출력 포함 다음 BE 배포에 반영 |
| SU-2 | FE SignedImage 배포 | FE | **High** | BE 배포 후 동시 또는 직후 배포 |
| SU-3 | 배포 직후 체크리스트 실행 | 인프라 | **High** | 본 리포트 §3 "배포 직후" 섹션 + Runbook §8 |
| SU-4 | 1일차 스냅샷 기록 | 인프라 | Medium | 본 리포트 §4 "1일차 스냅샷" 템플릿 작성 → CHANGELOG 기록 |
| SU-5 | FE 이미지 캐싱 모니터링 | FE/인프라 | Low | Signed URL 기반 브라우저 캐시 적중률 확인. Cache-Control 헤더 튜닝 여부 판단 |
| SU-6 | Log Analytics (BigQuery) Top objectPath 쿼리 활성화 | 인프라 | Low | DASHBOARD_SPEC §2 위젯3의 SQL 쿼리를 Log Analytics에서 실행 가능하도록 연동 |
| SU-7 | 알림 테스트 실행 | 인프라 | Medium | 배포 1일 후 의도적 에러 발생 → `Signed URL Errors Spike` 알람 수신 확인 |

---

## 7. 결론

**인프라 관점에서 Signed URL 파이프라인은 "운영 준비 완료(Ready for Go-Live)" 상태이다.**

완료된 항목:
- ✅ SA tokenCreator 권한 부여
- ✅ GCS CORS 설정 적용
- ✅ Log-based Metrics 2개 생성 (지침 기준 이름)
- ✅ Monitoring 대시보드 생성 (3위젯)
- ✅ Alert Policy 생성 (`errors > 0` 5분 지속 → CTO 알림)
- ✅ SSOT 문서 전체 동기화 (miriarts_infra.md, RUNBOOK, DASHBOARD_SPEC, CHANGELOG)
- ✅ 디버깅 절차 정형화 (Runbook §4.3 — 5단계, 15분 에스컬레이션)
- ✅ 배포 체크리스트 정형화 (Runbook §8 — 배포 전/직후/1일 후)
- ✅ AI 코드 경로 검증 (`edited/{uuid}.jpg` → SSOT §3.4 일치)
- ✅ AI Cloud Run 상태 정상 (IAM 403 외부 차단, GCS_BUCKET_NAME=miriart-bucket)

**다음 단계**: BE/FE 배포 후 Runbook §8 체크리스트 및 본 리포트 §3~§4 모니터링 플로우 실행.

---

*리포트 끝 — 2026-03-10, INFRA_DEV 에이전트*
