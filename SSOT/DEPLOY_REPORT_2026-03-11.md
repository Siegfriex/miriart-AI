# 배포 보고서 — miriart-ai 리비전 00012-k5b

**일시**: 2026-03-11
**배포 방식**: `gcloud run deploy --source`
**활성 리비전**: `miriart-ai-00012-k5b` (트래픽 100%)

---

## 1. 변경 파일 및 코드라인 인용

### 1-1. `app/core/config.py` — gemini_location 필드 추가

**변경**: L23~25 신규 추가

```python
# app/core/config.py:23-25
gemini_location: str = "global"
```

| 항목 | 이전 (리비전 00011) | 이후 (리비전 00012) |
|------|-------------------|-------------------|
| 필드 존재 여부 | 없음 | `gemini_location: str = "global"` |
| env override | 불가 | `GEMINI_LOCATION=global` |

**왜 변경했는가**: GenAI Client 생성 시 `gcp_region`(Cloud Run 배포 리전)과 Gemini API 호출 리전을 분리하기 위해. `asia-northeast3`에서는 쿼터가 낮고 일부 모델이 미지원이므로, Gemini 전용 location을 `global`로 분리.

---

### 1-2. `app/core/gemini_client.py` — 4개 라인 변경

#### (a) DEBUG 로그 제거 — 구 L20~22 삭제

```python
# 삭제됨 (이전 코드):
# logging.getLogger("google.genai").setLevel(logging.DEBUG)
# logging.getLogger("httpx").setLevel(logging.DEBUG)
```

**왜**: 진단 완료 후 불필요한 노이즈. prod에서 httpx DEBUG 로그가 Cloud Logging 비용/가독성을 악화.

---

#### (b) location 파라미터 변경 — L32

```python
# app/core/gemini_client.py:32
location=settings.gemini_location,  # Cloud Run 리전(gcp_region)과 분리
```

| 이전 | 이후 |
|------|------|
| `location=settings.gcp_region` → `"asia-northeast3"` | `location=settings.gemini_location` → `"global"` |

**왜**: `asia-northeast3`에서 `gemini-2.5-flash` 호출 시 429(RESOURCE_EXHAUSTED) 3건 + timeout 6건 발생. `global` 엔드포인트는 Google이 자동으로 가용 리전으로 라우팅하여 쿼터·지연 문제를 완화.

---

#### (c) retry attempts 2→3 — L36

```python
# app/core/gemini_client.py:36
attempts=3,  # 429 등 일시적 에러 시 2회 재시도 (SDK 55s 내에서 완료)
```

| 이전 | 이후 |
|------|------|
| `attempts=2` (1회 재시도) | `attempts=3` (2회 재시도) |

**왜**: 429/5xx 일시적 에러에 대한 내성 강화. SDK `http_options.timeout=55s`가 전체 시도를 감싸므로, attempts=3이어도 총 대기 시간은 55초를 초과하지 않음. BE WebClient timeout(65s)과의 관계도 안전.

**최악 시나리오 수치**:
```
SDK 55s 타임아웃 내에서:
  시도1 → 실패 → backoff ~1s
  시도2 → 실패 → backoff ~2s
  시도3 → 실패
총합 ≤ 55s < BE 65s < Cloud Run 120s
```

---

#### (d) 초기화 로그 메시지 보강 — L46~49

```python
# app/core/gemini_client.py:46-49
logger.info(
    "GenAI client initialized (project=%s, gemini_location=%s, cloud_run_region=%s)",
    settings.gcp_project_id,
    settings.gemini_location,
    settings.gcp_region,
)
```

| 이전 | 이후 |
|------|------|
| `"project=%s, region=%s"` (인자 2개) | `"project=%s, gemini_location=%s, cloud_run_region=%s"` (인자 3개) |

**왜**: 배포 직후 Cloud Logging에서 어떤 location으로 초기화되었는지 즉시 확인하기 위해.

---

#### (e) 로그 내 sdk_attempts 반영 — L111

```python
# app/core/gemini_client.py:111
"sdk_attempts": 3,
```

| 이전 | 이후 |
|------|------|
| `"sdk_attempts": 2` | `"sdk_attempts": 3` |

**왜**: `gemini_call_start` 로그에 실제 retry 설정값을 정확히 기록하여, 로그만으로 현재 설정을 확인 가능하게.

---

### 1-3. `cloudbuild.yaml` — GEMINI_LOCATION env 추가 — L40

```yaml
# cloudbuild.yaml:40
- '--set-env-vars=GCP_PROJECT_ID=miriarts,GCP_REGION=asia-northeast3,GCS_BUCKET_NAME=miriart-bucket,GEMINI_LOCATION=global'
```

| 이전 | 이후 |
|------|------|
| `GCP_PROJECT_ID,GCP_REGION,GCS_BUCKET_NAME` (3개) | `+ GEMINI_LOCATION=global` (4개) |

**왜**: Cloud Build 트리거 배포 시에도 `GEMINI_LOCATION=global`이 주입되도록. 이전에는 누락되어 config.py 기본값(`"global"`)에만 의존했으나, 명시적 선언이 운영 안정성에 필수.

---

## 2. 변경하지 않은 파일 (확인만 수행)

| 파일 | 확인 내용 | 결과 |
|------|----------|------|
| `app/core/exceptions.py` | LLMRateLimitError→429, LLMTimeoutError→504 매핑 | 정상 (L25~29) |
| `app/core/error_handler.py` | ERROR_MAP에서 HTTP status/body.code 매핑 | 정상 (L28~34) |
| `app/services/analyze_service.py` | `model=GeminiModel.FLASH`, `timeout_override_s` 미지정→55s | 정상 (L110~118) |
| `app/services/chat_service.py` | MODEL_MAP 매핑, GeminiModel.FLASH/PRO 사용 | 정상 (L19~24) |

---

## 3. Cloud Run 배포 설정 비교

| 항목 | 이전 리비전 (00011) | 현재 리비전 (00012) | cloudbuild.yaml 기준 |
|------|-------------------|-------------------|---------------------|
| Image repo | `cloud-run-source-deploy` | `cloud-run-source-deploy` | `miriart-images` |
| Memory | 512Mi | **1Gi** | 1Gi |
| min-instances | 0 | **1** | 1 |
| max-instances | 3 | **20** | 20 |
| concurrency | 기본(80) | **10** | 10 |
| timeout | 기본(300s) | **120s** | 120s |
| CPU boost | O | O | O |
| GCP_PROJECT_ID | miriarts | miriarts | miriarts |
| GCP_REGION | asia-northeast3 | asia-northeast3 | asia-northeast3 |
| GCS_BUCKET_NAME | 미설정 | **miriart-bucket** | miriart-bucket |
| GEMINI_LOCATION | **미설정** | **global** | global |

---

## 4. 해소된 장애 원인 요약

7일간 에러 로그(25건) 기준:

| 에러 | 건수 | 원인 | 해소 코드라인 |
|------|------|------|-------------|
| 404 NOT_FOUND (`gemini-3-flash`) | 10건 | 커밋 `b547868`에서 모델명 실험적 변경 후 미롤백 배포 | `gemini_client.py:57` — `FLASH = "gemini-2.5-flash"` |
| 429 RESOURCE_EXHAUSTED | 3건 | `asia-northeast3` 리전의 낮은 RPM 쿼터 | `gemini_client.py:32` — `location=settings.gemini_location` → `"global"` |
| Timeout (28~55s) | 6건 | `asia-northeast3` 리전 응답 지연 + retry 부족 | `gemini_client.py:32` (location) + `gemini_client.py:36` (attempts=3) |
| TypeError (NoneType) | 1건 | 404 후 빈 응답 파싱 시도 — 모델 수정으로 간접 해소 | `gemini_client.py:57` |

---

## 5. 자바 BE 정합성 매트릭스

| 계약 항목 | BE 기대값 | FastAPI 현재값 | 코드 위치 | 정합 |
|----------|----------|--------------|----------|------|
| 모델 | gemini-2.5-flash | `GeminiModel.FLASH` | `gemini_client.py:57` | O |
| 모델 | gemini-2.5-pro | `GeminiModel.PRO` | `gemini_client.py:58` | O |
| location | global | `settings.gemini_location` | `config.py:25` + `gemini_client.py:32` | O |
| FastAPI timeout | 55s | `effective_timeout=55` | `gemini_client.py:82` | O |
| BE timeout | 65s | — | BE 측 WebClient | O (55 < 65) |
| Cloud Run timeout | 120s | `--timeout=120` | `cloudbuild.yaml:32` | O (65 < 120) |
| 429 응답 | HTTP 429 + `LLM_RATE_LIMITED` | `LLMRateLimitError` | `error_handler.py:30` + `gemini_client.py:186` | O |
| 504 응답 | HTTP 504 + `LLM_TIMEOUT` | `LLMTimeoutError` | `error_handler.py:29` + `gemini_client.py:169` | O |
| 502 응답 | HTTP 502 + `LLM_SERVICE_ERROR` | `LLMServiceError` | `error_handler.py:31` + `gemini_client.py:200` | O |

---

## 6. 배포 후 검증 체크리스트

- [ ] Cloud Logging에서 `"GenAI client initialized"` 로그 확인 → `gemini_location=global` 표시되는지
- [ ] `/internal/ai/analyze` 호출 → `gemini_call_start` 로그에 `model=gemini-2.5-flash` 확인
- [ ] analyze_artwork 최소 1회 성공 (`gemini_call_success`, `purpose=analyze_artwork`)
- [ ] 404 NOT_FOUND (`gemini-3-flash`) 에러 재발하지 않는지
- [ ] 429 발생 시 HTTP 429 + `code=LLM_RATE_LIMITED`로 BE에 전달되는지
