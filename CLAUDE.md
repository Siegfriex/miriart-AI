# MiriArt AI Service (FastAPI)

> Cloud Run 배포 FastAPI AI 서비스. BE(Java)에서 `/internal/ai/*` 호출.

## 핵심 경로

| 경로 | 용도 |
|------|------|
| `app/` | FastAPI 소스 (routers, schemas, services, core) |
| `SSOT/` | AI 서비스 SSOT 문서 5개 (로컬 사본, 정본: miriart_docs) |
| `cloudbuild.yaml` | Cloud Build → Artifact Registry → Cloud Run 배포 |
| `requirements.txt` | Python 의존성 (google-genai, fastapi, pydantic 등) |

## 규칙

- **코드가 SSOT**: 문서는 코드를 따른다. 코드 변경 시 SSOT 문서 즉시 갱신.
- **문서 정본**: [miriart_docs](https://github.com/Siegfriex/miriart_docs) 레포. `SSOT/`는 로컬 사본.
- **시크릿 금지**: 환경변수 이름·흐름만 기술. 실제 값 절대 미기재.
- **WSL 전용**: 모든 실행·배포 명령은 WSL Ubuntu에서만.
- **Python venv**: `source .venv/bin/activate` 후 pip/python 사용.

## 실행

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 배포

```bash
gcloud builds submit --config=cloudbuild.yaml --project=miriarts --region=asia-northeast3
```

## 참조

- 상세 룰: `.claude/rules/`
- SSOT 가이드: `.claude/INFRA_SSOT_GUIDE.md`
- AI 문서 정본: `miriart_docs/ai/`
