# MiriArt AI 인프라·SSOT 에이전트 지침

에이전트가 인프라/배포/환경설정 관련 작업을 할 때 참고할 규칙과 문서 위치.

---

## 1. 참조 문서 (우선순위)

| 용도 | 문서 경로 | 비고 |
|------|-----------|------|
| **AI SSOT 5개** | `SSOT/miriart-ai-infra.md`, `miriart-ai-api.md`, `miriart-ai-flows.md`, `miriart-ai-runbook.md`, `miriart-ai-changelog.md` | 유일 참조는 app/ 코드. 문서는 코드를 따른다. |
| **문서 정본** | [miriart_docs](https://github.com/Siegfriex/miriart_docs) 레포 (`miriart_docs/ai/`) | `SSOT/`는 로컬 작업 사본. |
| **GCP 인프라 명세** | `SSOT/miriart-ai-infra.md` §2 | Cloud Run, SA, Secret, 환경변수 목록. |
| **세션 리셋/첫 인지** | 본 GUIDE + `SSOT/miriart-ai-infra.md` §0–§3 | AI 서비스 코드 메타·배포·로깅 파악. |

---

## 2. 작성·수정 시 규칙

- **시크릿**: 환경변수/Secret 이름·용도·흐름만 기술. 실제 값은 절대 기재하지 않는다.
- **근거**: 코드·설정·문서에서 확인된 내용만 서술한다. 확인되지 않으면 **(추론)**으로 명시한다.
- **소스 표기**: 주장·표 항목에는 가능한 한 **소스(파일:라인)** 또는 `§섹션`을 붙인다.

---

## 3. 변경 시 동기화

- **Cloud Run / 환경변수 / 배포 설정** 변경 → `SSOT/miriart-ai-infra.md` §0, §2 갱신.
- **엔드포인트·스키마** 변경 → `miriart-ai-api.md` §1·§2 갱신.
- **에러 코드** 변경 → `miriart-ai-api.md` §3, `miriart-ai-flows.md` 해당 E 갱신.
- **CI/CD** 변경 → `miriart-ai-infra.md` §5 갱신.
- **모든 변경** → `miriart-ai-changelog.md` 이력 추가.

---

## 4. 배포 상태 요약

- **AI (miriart-ai)**: Cloud Build → Artifact Registry → Cloud Run 자동 배포 (`cloudbuild.yaml`).
- 배포 명령: `gcloud builds submit --config=cloudbuild.yaml --project=miriarts --region=asia-northeast3`

---

## 5. 에이전트 변경 시 SSOT 자동 업데이트

인프라·배포·환경설정에 영향을 주는 코드·설정·문서를 수정한 경우:

### 5-1. SSOT 본문 갱신

| 수정한 대상 | 갱신할 SSOT 문서·섹션 |
|-------------|----------------------|
| app/ 코드 심볼·라인 변경 | `miriart-ai-infra.md` §0.1 |
| 엔드포인트·스키마 추가/변경 | `miriart-ai-infra.md` §0.1, `miriart-ai-api.md` §1·§2 |
| 에러 코드 추가/변경 | `miriart-ai-api.md` §3, `miriart-ai-flows.md` 해당 플로우 E |
| `config.py`, `cloudbuild.yaml`, `Dockerfile` | `miriart-ai-infra.md` §0.2, §2 |
| 로깅 이벤트 변경 | `miriart-ai-infra.md` §3 |
| 실행·배포·디버깅 절차 | `miriart-ai-runbook.md` 해당 섹션 |

### 5-2. 변경 이력 기록 (필수)

`SSOT/miriart-ai-changelog.md` 파일 맨 위(최신이 위)에 추가:

```markdown
### YYYY-MM-DD | 에이전트
- miriart-ai-infra.md §X: 변경 내용 요약.
- miriart-ai-changelog.md 이력 추가.
```

### 5-3. 트리거 조건

아래를 **직접 수정**했을 때만 SSOT·CHANGELOG 반영:

- `app/**/config.py`, `cloudbuild.yaml`, `Dockerfile` 편집
- `SSOT/*.md` 편집
- Secret/환경변수 목록 변경, 인프라 점검 결과 반영

**트리거하지 않는 경우**: 인프라와 무관한 비인증 로직만 수정한 경우.

---

*이 지침은 miriart-ai SSOT 5개 문서의 변경 규칙을 요약한 것이다.*
