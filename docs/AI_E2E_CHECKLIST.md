# MiriArt-AI Prod E2E 체크리스트

Cloud Run에 배포된 miriart-ai 서비스에 대해 **BE 또는 인프라**가 수동으로 호출·검증할 때 사용하는 curl/httpie 예제와 기대 응답 형식이다.  
인증: Cloud Run은 `--no-allow-unauthenticated` 기준이면 **Bearer SA 토큰** 필요. 로컬/테스트용으로는 인증 생략 가능한 환경에서만 예제 사용.

---

## 기본 정보

| 항목 | 값 |
|------|-----|
| **Base URL (prod)** | `https://miriart-ai-{hash}-asia-northeast3.run.app` (실제 URL은 Cloud Run 콘솔 또는 `gcloud run services describe miriart-ai --region=asia-northeast3` 확인) |
| **Content-Type** | `application/json` |
| **인증 (prod)** | `Authorization: Bearer $(gcloud auth print-identity-token --impersonate-service-account=miriart-be-runner@miriarts.iam.gserviceaccount.com)` |

---

## 1. Health

**목적**: 서비스 기동·로드밸런서 검사.

```bash
# curl
curl -s -o /dev/null -w "%{http_code}" "https://<CLOUD_RUN_URL>/health"

# httpie
http GET "https://<CLOUD_RUN_URL>/health"
```

**기대 응답**

- **HTTP**: 200 (인증 없이 호출 가능한 경로는 200; IAM 체크 시에는 인증 필요 시 403)
- **Body**: `{"status":"ok"}`

---

## 2. Analyze (작품 분석)

**POST** `/internal/ai/analyze`

**요청 (camelCase)**  
- `gcsUri`: GCS 이미지 URI (예: `gs://miriart-bucket/...`)  
- `analysisType`: `basic` \| `major`  
- `problemText`: (선택) 문제/맥락 텍스트  

```bash
# curl
curl -s -X POST "https://<CLOUD_RUN_URL>/internal/ai/analyze" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token --impersonate-service-account=miriart-be-runner@miriarts.iam.gserviceaccount.com)" \
  -d '{"gcsUri":"gs://miriart-bucket/path/to/image.jpg","analysisType":"major","problemText":""}'

# httpie
http POST "https://<CLOUD_RUN_URL>/internal/ai/analyze" \
  Authorization:"Bearer $(gcloud auth print-identity-token --impersonate-service-account=miriart-be-runner@miriarts.iam.gserviceaccount.com)" \
  gcsUri=gs://miriart-bucket/path/to/image.jpg analysisType=major
```

**기대 응답 (200)**

```json
{
  "grade": "B",
  "totalScore": 82,
  "radarData": {
    "density": 85,
    "form": 80,
    "completion": 78,
    "relevance": 88,
    "thinking": 79
  },
  "fixScope": "DetailTuning",
  "comment": "...",
  "universityPredictions": []
}
```

**에러 예**  
- 502 + `{"code":"GCS_ERROR","message":"..."}`: GCS 다운로드 실패  
- 502 + `{"code":"LLM_SERVICE_ERROR","message":"..."}` 또는 `LLM_PARSING_ERROR`: Gemini/파싱 실패  
- 504 + `{"code":"LLM_TIMEOUT","message":"..."}`: 타임아웃  

---

## 3. Chat (AI 멘토 채팅)

**POST** `/internal/ai/chat`

**요청 (camelCase)**  
- `message`: 사용자 메시지 (필수)  
- `modelType`: `CHAT_PRO` \| `FAST` \| `THINKING` \| `SEARCH` \| `IMAGE_EDIT`  
- `sessionId`, `stickyContext`, `imageBase64`, `imageMimeType`, `history`: 선택  

```bash
# curl (최소)
curl -s -X POST "https://<CLOUD_RUN_URL>/internal/ai/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"message":"밀도를 높이는 방법을 알려주세요","modelType":"FAST"}'

# httpie
http POST "https://<CLOUD_RUN_URL>/internal/ai/chat" \
  Authorization:"Bearer <TOKEN>" \
  message="밀도를 높이는 방법을 알려주세요" modelType=FAST
```

**기대 응답 (200)**

```json
{
  "text": "밀도를 높이려면 오브젝트 간격을 20% 줄이고...",
  "groundingUrls": [],
  "quickReplies": ["이 부분을 더 자세히 알려주세요", "연습 방법을 추천해주세요", "비슷한 대학은 어디가 있나요?"]
}
```

**에러 예**  
- 400 + `{"code":"VALIDATION_ERROR","message":"..."}`: 잘못된 body(예: 잘못된 imageBase64)  
- 502 / 504: LLM_SERVICE_ERROR, LLM_TIMEOUT  

---

## 4. QA — Summarize answers (답변 요약)

**POST** `/internal/ai/summarize-answers`

**요청 (camelCase)**  
- `question`: 질문 문자열 (필수)  
- `answers`: 답변 문자열 배열 (필수, 1~20개)  

```bash
# curl
curl -s -X POST "https://<CLOUD_RUN_URL>/internal/ai/summarize-answers" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"question":"석고 데생 톤 처리 방법은?","answers":["답변1 내용","답변2 내용"]}'

# httpie
http POST "https://<CLOUD_RUN_URL>/internal/ai/summarize-answers" \
  Authorization:"Bearer <TOKEN>" \
  question="석고 데생 톤 처리 방법은?" answers:='["답변1","답변2"]'
```

**기대 응답 (200)**

```json
{
  "summary": "3줄 이내 요약 텍스트",
  "supplement": "추가 조언 1~2줄"
}
```

**에러 예**  
- 400: VALIDATION_ERROR (question/answers 누락·형식 오류)  
- 502: LLM_SERVICE_ERROR, LLM_PARSING_ERROR  

---

## 5. QA — Draft from question (질문 기반 초안)

**POST** `/internal/ai/draft-from-question`

**요청 (camelCase)**  
- `title`: 제목 (필수)  
- `content`: 내용 (필수)  
- `imageBase64`: (선택) base64 이미지  

```bash
# curl (텍스트만)
curl -s -X POST "https://<CLOUD_RUN_URL>/internal/ai/draft-from-question" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"title":"톤 처리 질문","content":"밝은 부분 톤을 어떻게 맞추나요?"}'

# httpie
http POST "https://<CLOUD_RUN_URL>/internal/ai/draft-from-question" \
  Authorization:"Bearer <TOKEN>" \
  title="톤 처리 질문" content="밝은 부분 톤을 어떻게 맞추나요?"
```

**기대 응답 (200)**

```json
{
  "draft": "AI가 생성한 답변 초안 텍스트 (200자 이내)"
}
```

**에러 예**  
- 400 + `{"code":"VALIDATION_ERROR","message":"..."}`: 잘못된 imageBase64 등  
- 502: LLM_SERVICE_ERROR, LLM_PARSING_ERROR  

---

## 6. Image edit (이미지 편집)

**POST** `/internal/ai/edit-image`

**요청 (camelCase)**  
- `imageBase64`: base64 인코딩 이미지 (필수)  
- `prompt`: 편집 지시 (필수)  

```bash
# curl (실제 base64는 길어지므로 변수 사용 권장)
IMAGE_B64="<base64-string>"
curl -s -X POST "https://<CLOUD_RUN_URL>/internal/ai/edit-image" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d "{\"imageBase64\":\"$IMAGE_B64\",\"prompt\":\"레트로 필터 적용\"}"

# httpie
http POST "https://<CLOUD_RUN_URL>/internal/ai/edit-image" \
  Authorization:"Bearer <TOKEN>" \
  imageBase64=@image.b64 prompt="레트로 필터 적용"
```

**기대 응답 (200)**

```json
{
  "text": "이미지 편집이 완료됐습니다.",
  "imageUrl": "https://storage.googleapis.com/miriart-bucket/edited/xxx.jpg"
}
```

`imageUrl`이 없을 수 있음(모델이 이미지 미반환 시).  
**에러 예**  
- 400: VALIDATION_ERROR (base64 디코딩 실패 등)  
- 502: GCS_ERROR(업로드 실패), LLM_SERVICE_ERROR  

---

## 7. 공통 에러 응답 형식

모든 4xx/5xx는 JSON:

```json
{
  "code": "ERROR_CODE",
  "message": "사람이 읽을 수 있는 메시지"
}
```

요청 검증 실패(400)일 때만 `errors` 배열 추가:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Request validation failed",
  "errors": [
    { "field": "question", "message": "..." }
  ]
}
```

**에러 코드**: `LLM_TIMEOUT`, `LLM_SERVICE_ERROR`, `LLM_PARSING_ERROR`, `GCS_ERROR`, `VALIDATION_ERROR`, `INTERNAL_ERROR`.  
상세 매핑은 [AI_LOGS_AND_ERROR_CODES.md](AI_LOGS_AND_ERROR_CODES.md) 참고.

---

## 8. E2E 체크 순서 제안

1. `GET /health` → 200  
2. `POST /internal/ai/chat` (최소 payload) → 200 + `text`  
3. `POST /internal/ai/summarize-answers` (최소 payload) → 200 + `summary`, `supplement`  
4. `POST /internal/ai/draft-from-question` (title, content만) → 200 + `draft`  
5. `POST /internal/ai/analyze` (실제 GCS URI) → 200 + `grade`, `radarData` 등  
6. `POST /internal/ai/edit-image` (실제 base64 + prompt) → 200 + `text`, `imageUrl`(선택)  

에러 케이스: 잘못된 base64로 chat 또는 draft-from-question → 400; 존재하지 않는 gcsUri로 analyze → 502.
