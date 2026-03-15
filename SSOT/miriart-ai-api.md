# miriart-ai API 계약 (SSOT)

> **대상**: miriart-ai (FastAPI) — `/internal/ai/*` 엔드포인트  
> **원칙**: 유일 참조는 코드. 스키마·에러 정의는 app/ 파일:행 인용.  
> **타임아웃·리트라이**: 참조 [miriart-ai-infra.md](miriart-ai-infra.md) §0.1 또는 app/core/gemini_client.py:21,23,26,90.

---

## §1. 엔드포인트 인벤토리

참조: [miriart-ai-infra.md](miriart-ai-infra.md) §0.1 (app/routers/ai.py 테이블).

| # | Method | Path | Handler | 시작행 | 끝행 | Request Schema | Response Schema | Service |
|---|--------|------|---------|--------|------|----------------|-----------------|---------|
| 1 | POST | /internal/ai/analyze | analyze | 49 | 57 | InternalAnalyzeRequest | InternalAnalyzeResponse | analyze_service.analyze_artwork() |
| 2 | POST | /internal/ai/chat | chat | 60 | 68 | InternalChatRequest | InternalChatResponse | chat_service.chat() |
| 3 | POST | /internal/ai/edit-image | edit_image | 71 | 79 | InternalImageEditRequest | InternalImageEditResponse | image_edit_service.edit_image() |
| 4 | POST | /internal/ai/summarize-answers | api_summarize_answers | 82 | 91 | SummarizeAnswersRequest | SummarizeAnswersResponse | qa_service.summarize_answers() |
| 5 | POST | /internal/ai/draft-from-question | api_draft_from_question | 94 | 107 | DraftFromQuestionRequest | DraftFromQuestionResponse | qa_service.draft_from_question() |
| 6 | GET | /internal/ai/status | status | 24 | 46 | — | JSON (상태) | — |
| 7 | GET | /health | health | app/main.py:47-50 | — | {"status": "ok"} | — |

모든 `/internal/ai/*` 엔드포인트는 Cloud Run IAM 보호. BE SA(`miriart-be-runner`)만 호출 가능.

---

## §2. 스키마 정의

정의 SSOT는 코드. 아래 행 범위는 [miriart-ai-infra.md](miriart-ai-infra.md) §0.1과 동일.

### 2.1 작품 분석 (analyze)

소스: `app/schemas/analyze.py:14-21` (InternalAnalyzeRequest), `:24-33` (RadarData), `:36-45` (UniversityPrediction), `:48-58` (InternalAnalyzeResponse). 참조 [miriart-ai-infra.md](miriart-ai-infra.md) §0.1.

**InternalAnalyzeRequest**

| 필드 | 타입 | Required | JSON Key |
|------|------|----------|----------|
| gcs_uri | str | ✅ | gcsUri |
| analysis_type | str | ✅ | analysisType ("basic" \| "major") |
| problem_text | Optional[str] | ❌ | problemText |

**RadarData** (0–100): density, form, completion, relevance, thinking.

**UniversityPrediction**: university, major, line, probability, similar_accepted_count.

**InternalAnalyzeResponse**: grade, total_score, radar_data, fix_scope, comment, university_predictions.

직렬화: Pydantic alias_generator=to_camel, populate_by_name=True.

### 2.2 AI 채팅 (chat)

소스: `app/schemas/chat.py:14-20` (HistoryItem), `:23-31` (UniversityPrediction), `:33-46` (StickyContext), `:49-60` (InternalChatRequest), `:63-70` (InternalChatResponse).

**HistoryItem**: role ("user" \| "model"), parts.

**UniversityPrediction** (chat용 — analyze.py의 동명 클래스와 필드 상이): name (str), type (Literal["TOP","HIGH","MID","LOW","SAFE"]), probability (float).

**StickyContext**: grade, score, fix_scope, radar_data (Optional[Dict]), university_predictions (Optional[List[UniversityPrediction]]), analysis_comment (Optional[str]), target_major (Optional[str]), target_university (Optional[str]), summary_text (Optional[str]).

**InternalChatRequest**: model_type, message, session_id, sticky_context, image_base64, image_mime_type, history.

**InternalChatResponse**: text, grounding_urls, quick_replies.

### 2.3 이미지 편집 (edit-image)

소스: `app/schemas/image_edit.py:14-20` (InternalImageEditRequest), `:23-29` (InternalImageEditResponse). 참조 [miriart-ai-infra.md](miriart-ai-infra.md) §0.1.

**InternalImageEditRequest**: image_base64, prompt.

**InternalImageEditResponse**: text, image_url (Optional).

### 2.4 QA 답변 요약 (summarize-answers)

소스: `app/schemas/qa.py:14-20` (SummarizeAnswersRequest), `:23-29` (SummarizeAnswersResponse).

**SummarizeAnswersRequest**: question (1–2000자), answers (1–20개).

**SummarizeAnswersResponse**: summary, supplement.

### 2.5 QA 답변 초안 (draft-from-question)

소스: `app/schemas/qa.py:32-39` (DraftFromQuestionRequest), `:42-47` (DraftFromQuestionResponse).

**DraftFromQuestionRequest**: title (1–200자), content (1–5000자), image_base64 (Optional).

**DraftFromQuestionResponse**: draft.

---

## §3. 에러 응답

### 3.1 body 형식

소스: `app/core/error_handler.py:55-56` (MiriArtAIError 응답), `:69-82` (RequestValidationError 응답).

```json
{
  "code": "LLM_TIMEOUT",
  "message": "Gemini 응답 시간 초과 (55s)"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| code | str | 머신 리더블 에러 코드 |
| message | str | 사람 리더블 에러 메시지 |
| errors | array (400만) | VALIDATION_ERROR 시 필드별 검증 실패 — 각 요소 {"field": str, "message": str} |

### 3.2 에러 코드 전체 목록

소스: ERROR_MAP `app/core/error_handler.py:28-35`.

| code | HTTP | 예외 클래스 |
|------|------|------------|
| LLM_TIMEOUT | 504 | LLMTimeoutError |
| LLM_RATE_LIMITED | 429 | LLMRateLimitError |
| LLM_SERVICE_ERROR | 502 | LLMServiceError |
| LLM_PARSING_ERROR | 502 | LLMParsingError |
| GCS_ERROR | 502 | GCSError |
| VALIDATION_ERROR | 400 | ValidationError / RequestValidationError |
| INTERNAL_ERROR | 500 | Exception (미처리) |

---

## §4. GCS 스토리지 IO·상태

### 4.1 GcsService 메서드 인벤토리

소스: `app/services/gcs_service.py:30-70`

| 메서드 | 사용처 | 동작 | 예외 |
|--------|--------|------|------|
| download_as_bytes(gcs_uri) | analyze_service | GCS → bytes | caller가 GCSError raise |
| upload_bytes(blob_path, data, content_type) | image_edit_service | bytes → GCS 업로드, URL 반환 | GCSError |
| generate_signed_url(...) | 미사용 (Phase 2 준비) | V4 Signed URL | — |

### 4.2 GCS 경로 규칙

| 경로 패턴 | 용도 | 생성 주체 |
|-----------|------|-----------|
| artworks/{date}/{uuid}_{filename} | 원본 업로드 이미지 | BE |
| edited/{uuid}.jpg | AI 이미지 편집 결과 | AI (image_edit_service) |

### 4.3 Stateless

AI 서비스는 DB/Redis 없음. 세션·히스토리는 BE가 Redis에서 관리 후 요청에 history로 전달. get_settings()·get_genai_client() 싱글톤만 사용.

---

## §5. DB 스키마 정합 (GCP Cloud SQL 실 DB 기준, 2026-03-15)

> AI 서비스는 Stateless (DB/Redis 없음). 아래는 BE가 DB에 저장하는 값과 AI 스키마 필드의 대응.

### 5.1 InternalAnalyzeResponse → analyses 테이블

| AI 응답 필드 | DB 컬럼 | DB 타입 | 비고 |
|-------------|---------|---------|------|
| grade | analyses.grade | ENUM('A','B','C','D','F') | |
| total_score | analyses.total_score | DECIMAL(5,2) | |
| radar_data | analyses.scores | JSON | `{"density":85,"form":80,...}` |
| fix_scope | analyses.fix_scope | ENUM('DetailTuning','StructureRebuild') | |
| comment | analyses.comment | TEXT | |
| university_predictions | analyses.university_predictions | JSON | `[{"university":"...","major":"...","line":"HIGH","probability":68,"similarAcceptedCount":14}]` |

기타 analyses 컬럼: id(PK BIGINT), user_id(FK→users), gcs_url(TEXT), image_url(TEXT), analysis_type(VARCHAR(50)), problem_text(VARCHAR(500)), status(ENUM PENDING/COMPLETED/FAILED), completed_at(DATETIME(6)), created_at/updated_at(DATETIME(6)).

인덱스: idx_status(status), idx_user_created(user_id,created_at), idx_user_grade(user_id,grade).

### 5.2 StickyContext — BE 조립 기준

BE가 analyses 테이블 + FE 입력으로 StickyContext를 구성하여 AI chat 요청에 전달:
- grade, score(=total_score), fix_scope, radar_data(=scores JSON) → analyses 테이블
- university_predictions → analyses.university_predictions JSON (chat.py UniversityPrediction는 name/type/probability로 변환됨 — analyze.py 버전과 필드 상이)
- analysis_comment(=comment) → analyses.comment
- target_major, target_university, summary_text → FE에서 전달 (DB 미저장)

### 5.3 chat_sessions 테이블 (운영 중)

| 컬럼 | 타입 | 기본값 | 비고 |
|------|------|--------|------|
| id | BIGINT PK | auto_increment | |
| user_id | BIGINT FK→users | | |
| analysis_id | BIGINT FK→analyses | NULL | 연결된 분석 (없으면 일반 채팅) |
| session_key | VARCHAR(36) UNIQUE | | UUID |
| model_type | VARCHAR(20) | 'CHAT_PRO' | CHAT_PRO/FAST/THINKING/SEARCH/IMAGE_EDIT |
| title | VARCHAR(100) | '새 채팅' | |
| last_message | TEXT | NULL | |
| message_count | INT | 0 | |
| created_at | DATETIME(6) | | |
| updated_at | DATETIME(6) | | |

인덱스: UNI(session_key), idx_cs_session_key, idx_cs_user_analysis(user_id,analysis_id), idx_cs_user_updated(user_id,updated_at).

### 5.4 analysis_usage_logs 테이블

| 컬럼 | 타입 | 비고 |
|------|------|------|
| id | BIGINT PK | |
| analysis_id | BIGINT NULL | |
| billing_year_month | VARCHAR(7) | 'YYYY-MM' |
| created_at | DATETIME(6) | |
| user_id | BIGINT FK→users | |

인덱스: idx_user_month(user_id, billing_year_month).

### 5.5 전체 DB 테이블 목록 (12개, flyway_schema_history 제외 11개)

users, analyses, analysis_usage_logs, chat_sessions, posts, answers, comments, likes, personas, reputation_ledger, reports. 전체 MySQL 8.x, InnoDB, utf8mb4_unicode_ci.

---

*문서 끝. 유일 참조는 코드. 스키마·에러 변경 시 해당 app/schemas/*, app/core/error_handler.py 라인과 동기화. DB 정합은 §5 참조.*
