# Signed URL 대시보드 스펙

> **작성일**: 2026-03-10
> **SSOT 참조**: `SSOT/miriarts_infra.md` §3.4, `SSOT/RUNBOOK_AI_INFRA_v1.md` §5.2
> **목적**: GCS Signed URL 관련 메트릭 정의, 대시보드 위젯 스펙, 알람 임계값, BE 로그 출력 규격을 한곳에 정리
>
> **대시보드**: [MiriArt - BE Signed URL](https://console.cloud.google.com/monitoring/dashboards/builder/707df634-a515-4226-9e73-edf7f9e9db91?project=miriarts) (ID: `707df634-a515-4226-9e73-edf7f9e9db91`)
> **알람 정책**: `Signed URL Errors Spike` (Policy ID: `10494294328358958245`)

---

## §1 메트릭 정의

| 메트릭 ID | 설명 | Log Filter | Value Type |
|-----------|------|-----------|------------|
| `miriart-be-signed-url-count` | Signed URL 발급 성공 수 | `resource.type="cloud_run_revision" AND resource.labels.service_name="miriart-be" AND jsonPayload.message="signed_url_generated"` | INT64 (counter) |
| `miriart-be-signed-url-errors` | Signed URL 발급 실패 수 | `resource.type="cloud_run_revision" AND resource.labels.service_name="miriart-be" AND jsonPayload.message="signed_url_error"` | INT64 (counter) |

**검증 명령어**:
```bash
gcloud logging metrics list --project=miriarts --filter="name:miriart-be-signed-url"
```

---

## §2 대시보드 위젯 스펙

대시보드 이름: **MiriArt Signed URL Monitoring**
기존 대시보드 `MiriArt-AI BE/AI Overview`에 패널 추가 또는 별도 대시보드 생성.

### 위젯 1: Signed URL 발급 수 (1분 평균)

| 항목 | 값 |
|------|-----|
| 차트 타입 | Line Chart |
| 메트릭 | `logging.googleapis.com/user/miriart-be-signed-url-count` |
| Aligner | `ALIGN_RATE` (1분 간격) |
| 시간 범위 | 1시간 |
| 집계 | 없음 (단일 서비스) |
| 제목 | "Signed URL 발급 수 (1분 평균)" |

### 위젯 2: Signed URL 실패 수

| 항목 | 값 |
|------|-----|
| 차트 타입 | Line Chart |
| 메트릭 | `logging.googleapis.com/user/miriart-be-signed-url-errors` |
| Aligner | `ALIGN_SUM` (1분 간격) |
| 시간 범위 | 1시간 |
| 집계 | 없음 (단일 서비스) |
| 제목 | "Signed URL 실패 수" |

### 위젯 3: Top objectPath (최근 1시간)

| 항목 | 값 |
|------|-----|
| 타입 | Logs Explorer 쿼리 (대시보드 내 로그 패널 또는 저장된 쿼리) |
| 제목 | "Top objectPath (최근 1시간)" |

**Logs Explorer 쿼리**:
```
resource.type="cloud_run_revision"
resource.labels.service_name="miriart-be"
jsonPayload.message="signed_url_generated"
-- Logs Explorer에서 아래 필드로 GROUP BY:
-- jsonPayload.analysisId, jsonPayload.objectPath
```

> Logs Explorer는 SQL-style GROUP BY를 직접 지원하지 않으므로, **Log Analytics**(BigQuery 연동) 사용 시 아래 쿼리 활용:
```sql
SELECT
  JSON_VALUE(json_payload, '$.analysisId') AS analysis_id,
  JSON_VALUE(json_payload, '$.objectPath') AS object_path,
  COUNT(*) AS cnt
FROM `miriarts.global._Default._AllLogs`
WHERE
  resource.type = 'cloud_run_revision'
  AND resource.labels.service_name = 'miriart-be'
  AND JSON_VALUE(json_payload, '$.message') = 'signed_url_generated'
  AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
GROUP BY analysis_id, object_path
ORDER BY cnt DESC
LIMIT 20
```

---

## §3 알람 임계값

| 항목 | 값 |
|------|-----|
| 알람 이름 | `miriart-be-signed-url-error-alert` |
| 조건 | `miriart-be-signed-url-errors > 0` (5분 지속) |
| Aligner | `ALIGN_SUM`, 5분 윈도우 |
| Comparison | `COMPARISON_GT`, threshold `0` |
| Duration | 300s (5분) |
| 알림 대상 | CTO Email (`6siegfriex@argo.ai.kr`) |
| 자동 해소 | 조건 미충족 시 자동 close |

**생성 참고** (gcloud CLI):
```bash
# Alert Policy는 JSON 파일로 정의 후 생성하는 것을 권장
# 상세: https://cloud.google.com/monitoring/alerts/policies-in-json
gcloud alpha monitoring policies create --policy-from-file=signed-url-alert-policy.json --project=miriarts
```

---

## §4 BE 로그 출력 규격 (BE 개발자 참조용)

BE에서 Signed URL 생성 시 아래 JSON 구조로 로그를 출력해야 메트릭 필터가 정상 동작한다.

### 성공 로그 (`signed_url_generated`)

```json
{
  "severity": "INFO",
  "message": "signed_url_generated",
  "analysisId": 12345,
  "objectPath": "artworks/2026-03-03/aa8ac12c-...jpeg",
  "ttl": 900,
  "timestamp": "2026-03-10T12:00:00Z"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `message` | string | **필수** | 고정값 `"signed_url_generated"`. 메트릭 필터 키. |
| `analysisId` | long | 필수 | 대상 분석 ID |
| `objectPath` | string | 필수 | GCS 오브젝트 경로 (prefix 포함, 예: `artworks/...`) |
| `ttl` | int | 권장 | Signed URL 유효기간(초). 기본 900 |

### 실패 로그 (`signed_url_error`)

```json
{
  "severity": "ERROR",
  "message": "signed_url_error",
  "analysisId": 12345,
  "objectPath": "artworks/2026-03-03/aa8ac12c-...jpeg",
  "errorCode": "F005",
  "errorDetail": "Object not found in GCS",
  "timestamp": "2026-03-10T12:00:00Z"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `message` | string | **필수** | 고정값 `"signed_url_error"`. 메트릭 필터 키. |
| `analysisId` | long | 필수 | 대상 분석 ID |
| `objectPath` | string | 필수 | 요청된 GCS 오브젝트 경로 |
| `errorCode` | string | 필수 | BE ErrorCode (예: `F005`) |
| `errorDetail` | string | 권장 | 에러 상세 메시지 |

### BE 구현 가이드라인

- **로깅 프레임워크**: Spring Boot의 구조화 로그 출력 (Logback JSON encoder 권장) 또는 `ObjectMapper`로 JSON 직렬화 후 `log.info()`/`log.error()`.
- **Cloud Run 자동 수집**: Cloud Run의 stdout JSON 로그는 Cloud Logging `jsonPayload`로 자동 파싱됨. 별도 SDK 불필요.
- **메트릭 필터 매칭**: `jsonPayload.message` 필드가 정확히 `"signed_url_generated"` 또는 `"signed_url_error"`여야 함. 오타·대소문자 주의.

---

*문서 끝 — 2026-03-10, INFRA_DEV 에이전트*
