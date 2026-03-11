# miriart-ai 배포 상태 & 운영 튜닝 리포트

> **작성일**: 2026-03-10
> **대상 리비전**: `miriart-ai-00004-gfx`

---

## 1. Cloud Run miriart-ai 상태

| 항목 | 값 |
|------|---|
| latestReadyRevisionName | `miriart-ai-00004-gfx` |
| traffic | 100% → `miriart-ai-00004-gfx` |
| image | `asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-ai:21f0023` |
| serviceAccountName | `miriart-ai-runner@miriarts.iam.gserviceaccount.com` |
| timeoutSeconds | 120 |
| containerConcurrency | 10 |
| CPU / Memory | 1 vCPU / 1Gi |

**환경변수**:
```
GCP_PROJECT_ID  = miriarts
GCP_REGION      = asia-northeast3
GCS_BUCKET_NAME = miriart-bucket
```

---

## 2. image_edit timeout 튜닝

**현재값**: `timeout_override_s=55` (`image_edit_service.py:44`)

**이번 배포에서 수정 여부**: **아니오 — 다음 릴리스로 미룸**

**이유**:

1. image_edit 엔드포인트는 BE에서 아직 호출되지 않음 (현재 BE는 `/analyze`와 `/chat`만 호출 중)
2. BE 리비전 `miriart-be-00036-6vb`의 OIDC 토큰 문제가 아직 미해결 — BE 배포가 우선
3. 현재 리비전 `00004-gfx`는 `/health` + `/chat` + `/analyze` E2E 검증 완료 상태이므로, 안정 리비전으로 고정하는 것이 맞음
4. timeout 수정은 코드 변경 + 재빌드 + 새 리비전 배포가 필요 — 현재 안정 상태를 깨뜨릴 이유 없음

**다음 릴리스 시 적용할 내용**:

```python
# image_edit_service.py:44 — 변경 전
timeout_override_s=55,

# image_edit_service.py:44 — 변경 후
timeout_override_s=25,    # BE WebClient 30s 내 수렴
```

```bash
# 재배포 커맨드 (다음 릴리스 시)
COMMIT_SHA=$(git rev-parse --short HEAD)
gcloud builds submit . \
  --project=miriarts \
  --config=cloudbuild.yaml \
  --substitutions=COMMIT_SHA=$COMMIT_SHA
```

---

## 3. 수동 I/O 체크

### GET `/health`

```
HTTP 200 | 1.054s (네트워크 포함)
```

```json
{"status": "ok"}
```

### POST `/internal/ai/chat`

```bash
curl -X POST -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d '{"modelType":"FAST","message":"크로키 연습 팁 하나만 알려줘"}' \
  https://miriart-ai-946560105497.asia-northeast3.run.app/internal/ai/chat
```

```
HTTP 200 | 10.201s
```

```json
{
  "text": "크로키는 '움직임'을 그리는 거예요! 완벽한 형태보다 인체의 흐름(gesture)과 에너지를 선으로 따라가 보세요. 짧은 시간 안에 핵심적인 동세를 포착하는 연습이 중요해요. 과감하게 선을 긋는 것이 실력 향상에 큰 도움이 될 거예요! 꾸준히 연습하면 분명 늘 거예요. 응원합니다!",
  "groundingUrls": [],
  "quickReplies": [
    "이 부분을 더 자세히 알려주세요",
    "연습 방법을 추천해주세요",
    "비슷한 대학은 어디가 있나요?"
  ]
}
```

---

## 4. 로그 패턴

최근 30분 내 구조화 로그:

### gemini_call_success 예시

```
2026-03-10T08:11:59.159 [INFO]
  message: gemini_call_success
  purpose: chat
  model: gemini-2.5-flash
  latency_s: 18.81
  output_len: 125
```

### handled_error 예시

```
2026-03-10T08:13:08.440 [WARNING]
  message: handled_error
  error_code: GCS_ERROR
  status: 502
  path: /internal/ai/analyze
```

### http_request 예시 (정상)

```
2026-03-10T08:11:59.159 [INFO]
  message: http_request
  request_id: 00883054-264
  path: /internal/ai/chat
  status: 200
  latency_s: 18.811
```

### http_request 예시 (에러)

```
2026-03-10T08:13:08.440 [INFO]
  message: http_request
  request_id: 59e9f4ad-fb9
  path: /internal/ai/analyze
  status: 502
  latency_s: 0.103
```

### http_request 예시 (validation)

```
2026-03-10T08:14:08.180 [INFO]
  message: http_request
  request_id: 793d54c4-57a
  path: /internal/ai/analyze
  status: 400
  latency_s: 0.001
```

---

## 5. 판정

| 항목 | 상태 |
|------|------|
| 리비전 고정 | ✅ `00004-gfx` 100% 트래픽 |
| /health | ✅ 200 |
| /chat E2E (Gemini) | ✅ 200, 10.2s |
| /analyze GCS_ERROR 분기 | ✅ 502 정상 매핑 |
| /analyze VALIDATION_ERROR 분기 | ✅ 400 정상 매핑 |
| gemini_call_success 로그 | ✅ 확인 |
| handled_error 로그 | ✅ 확인 |
| http_request + request_id | ✅ 확인 |
| image_edit timeout | ⏳ 다음 릴리스에서 55→25 변경 예정 |

**miriart-ai prod 배포 상태: 정상. 리비전 `00004-gfx` 고정 운영.**
