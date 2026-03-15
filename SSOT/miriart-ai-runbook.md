# miriart-ai 운영 런북 (SSOT)

> **대상**: miriart-ai (FastAPI, Cloud Run)  
> **목적**: 로컬 실행·배포·로그 조회·디버깅 절차. 값의 출처는 [miriart-ai-infra.md](miriart-ai-infra.md) §0·§2 또는 코드 인용.

---

## §1. 로컬 실행

### 1.1 사전 조건

- Python 3.11+
- GCP SA 키 파일 (로컬 개발용)
- `.env` 파일

### 1.2 환경변수

필수 env: 소스 `app/core/config.py` (Settings).  
참조: [miriart-ai-infra.md](miriart-ai-infra.md) §2.1.

**.env 예시**:
```env
GCP_PROJECT_ID=miriarts
GCP_REGION=asia-northeast3
GCS_BUCKET_NAME=miriart-bucket
GOOGLE_APPLICATION_CREDENTIALS=/path/to/miriart-local-dev-key.json
```

### 1.3 실행

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# 또는
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 1.4 로컬 테스트

```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/internal/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"modelType": "FAST", "message": "석고 데생 팁을 알려주세요"}'

curl -X POST http://localhost:8000/internal/ai/analyze \
  -H "Content-Type: application/json" \
  -d '{"gcsUri": "gs://miriart-bucket/artworks/2026-03-03/test.jpeg", "analysisType": "basic"}'
```

로컬에서는 IAM 체크 없음. GCS/Vertex 인증은 `GOOGLE_APPLICATION_CREDENTIALS` 사용.

### 1.5 BE 연동 URL

로컬: BE의 `FASTAPI_INTERNAL_URL=http://localhost:8000`.  
Prod: BE가 Cloud Run에 배포된 miriart-ai 서비스 URL 사용. BE `application.yml`의 `FASTAPI_INTERNAL_URL` 환경변수로 설정.

---

## §2. Docker 로컬 빌드 / 실행

```bash
docker build -t miriart-ai:local .

docker run -p 8080:8080 \
  -e GCP_PROJECT_ID=miriarts \
  -e GCP_REGION=asia-northeast3 \
  -e GCS_BUCKET_NAME=miriart-bucket \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/key.json \
  -v /path/to/miriart-local-dev-key.json:/app/key.json:ro \
  miriart-ai:local

curl http://localhost:8080/health
```

소스: `Dockerfile:10,12` (EXPOSE 8080, CMD uvicorn).

---

## §3. Cloud Run Prod 배포 / 롤백

### 3.1 현재 상태 확인

```bash
gcloud run services describe miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --format="value(status.latestReadyRevisionName)"

gcloud run revisions list --service=miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --format="table(REVISION,ACTIVE,LAST_DEPLOYED_AT)" --limit=5

gcloud run services describe miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --format="yaml(spec.template.spec.containers[0].env)"
```

### 3.2 배포

소스: `cloudbuild.yaml`.

```bash
cd /path/to/miriart-ai
gcloud builds submit --config=cloudbuild.yaml \
  --project=miriarts \
  --region=asia-northeast3
```

cloudbuild.yaml이 수행하는 작업: Docker 이미지 빌드(듀얼 태그), Artifact Registry 푸시, Cloud Run 배포 (port 8080, timeout 120, env 등 — cloudbuild.yaml:29,32,40,41).

### 3.3 롤백

```bash
gcloud run services update-traffic miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --to-revisions=<PREVIOUS_REVISION>=100

# 또는 특정 이미지로 재배포
gcloud run deploy miriart-ai \
  --image=asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:<COMMIT_SHA> \
  --region=asia-northeast3 --project=miriarts
```

### 3.4 배포 검증

```bash
# 외부 접근 차단 확인 (403이어야 정상)
curl -s -o /dev/null -w "%{http_code}" https://miriart-ai-...run.app/health

# 서비스 Ready
gcloud run services describe miriart-ai \
  --region=asia-northeast3 --project=miriarts \
  --format="value(status.conditions[0].status)"

# 에러 로그 확인
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-ai"
   AND severity>=ERROR' \
  --project=miriarts --limit=10 \
  --format="table(timestamp,severity,jsonPayload.message)"
```

---

## §4. 로그 조회

로그 이벤트·필드 정의: [miriart-ai-infra.md](miriart-ai-infra.md) §3.1.  
소스: `app/core/logging_config.py`, `app/core/error_handler.py`, `app/core/gemini_client.py`.

```bash
# 전체 AI 서비스 로그 (최근 20건)
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-ai"' \
  --project=miriarts --limit=20 \
  --format="table(timestamp,severity,jsonPayload.message)"

# Gemini 호출 에러만
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-ai"
   AND jsonPayload.message="gemini_call_error"' \
  --project=miriarts --limit=10 \
  --format="table(timestamp,jsonPayload.purpose,jsonPayload.model,jsonPayload.error)"

# Gemini 타임아웃만
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-ai"
   AND jsonPayload.message="gemini_call_timeout"' \
  --project=miriarts --limit=10 \
  --format="table(timestamp,jsonPayload.purpose,jsonPayload.model,jsonPayload.timeout_s)"

# 미처리 예외
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-ai"
   AND jsonPayload.message="unhandled_exception"' \
  --project=miriarts --limit=5 \
  --format="table(timestamp,jsonPayload.error,jsonPayload.traceback)"

# request_id 추적
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="miriart-ai"
   AND jsonPayload.request_id="abc123def456"' \
  --project=miriarts --limit=20
```

---

## §5. Gemini 클라이언트 요약 (확인 위치)

타임아웃·리트라이·모델 상수: [miriart-ai-infra.md](miriart-ai-infra.md) §0.1, [miriart-ai-flows.md](miriart-ai-flows.md) 마지막 표.

| 확인 항목 | 소스 |
|-----------|------|
| 클라이언트 초기화·싱글톤 | app/core/gemini_client.py:32-59 |
| 모델 상수 (FLASH, PRO, FLASH_LITE) | app/core/gemini_client.py:62-67 |
| 타임아웃·리트라이 상수 | app/core/gemini_client.py:21-26, 42, 44, 90 |
| 이미지 편집 timeout_override | app/core/gemini_client.py:26, app/services/image_edit_service.py:44 |
| 429 → LLMRateLimitError | app/core/gemini_client.py:184-194, app/core/error_handler.py:30 |

---

## §6. 디버깅 체크리스트

| 순서 | 확인 | 명령어/위치 |
|------|------|------------|
| 1 | Cloud Run 서비스 상태 | `gcloud run services describe miriart-ai --region=asia-northeast3 --project=miriarts` |
| 2 | 최근 에러 로그 | §4 "Gemini 호출 에러만" 쿼리 |
| 3 | 리비전/인스턴스 | `gcloud run revisions list --service=miriart-ai --region=asia-northeast3 --project=miriarts --limit=3` |
| 4 | 환경변수 | `gcloud run services describe ... --format="yaml(spec.template.spec.containers[0].env)"` |
| 5 | GCS 버킷 접근 | `gcloud storage ls gs://miriart-bucket/ --limit=3` |

---

## §7. 주의사항 / 알려진 제한

| # | 항목 | 상태 | 확인 위치 |
|---|------|------|-----------|
| 1 | generate_signed_url() in gcs_service | 미사용 | app/services/gcs_service.py (Phase 2 준비. BE에서 Signed URL 생성) |
| 2 | upload_bytes() 반환값 | 공개 URL 형태 | 버킷 비공개이므로 BE가 Signed URL로 변환 후 FE 제공 |
| 3 | Chat sessionId | AI에서 미사용 | BE Redis에서 세션/히스토리 관리, history로 전달 |
| 4 | quick_replies | 3개 하드코딩 | 동적 생성 미구현 |
| 5 | Swagger/ReDoc | prod 비활성 | main.py (docs_url=None, redoc_url=None) |
| 6 | stub.py | 미사용 | 라우터에서 참조 없음 |

---

*문서 끝. 절차·명령어는 이 문서, 값·라인은 miriart-ai-infra.md §0·§2 또는 코드 인용.*
