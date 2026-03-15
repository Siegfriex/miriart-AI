# miriart-ai Docker 빌드·배포 프롬프트

아래 프롬프트를 복사해서 Claude/Cursor 챗에 붙여넣으면 Docker 빌드·배포 작업을 요청할 수 있습니다.

---

## 1) 로컬 Docker 빌드

```
miriart-ai를 Docker로 빌드해줘.

- Python (FastAPI), Dockerfile 있음. 루트는 miriart-ai/ (이 레포 루트).
- 이미지 이름: miriart-ai:latest
- 빌드 명령어 알려주고, 로컬 실행 docker run 예시도 줘.
```

---

## 2) 프로덕션 배포용 이미지 빌드

```
miriart-ai 프로덕션 배포용 Docker 이미지를 빌드해줘.

- multi-stage 빌드 유지, 불필요한 파일 제외
- 태그 규칙: miriart-ai:latest, miriart-ai:{git-sha}
- Artifact Registry(asia-northeast3-docker.pkg.dev/miriarts/...) 푸시용 명령어 예시
```

---

## 3) Cloud Build 배포

```
miriart-ai를 Cloud Build로 배포해줘.

- cloudbuild.yaml 사용
- project: miriarts, region: asia-northeast3
- 배포 명령: gcloud builds submit --config=cloudbuild.yaml --project=miriarts --region=asia-northeast3
- 배포 후 Cloud Run 서비스 상태 확인 방법도 알려줘.
```

---

## 4) CI/CD 설계

```
miriart-ai의 CI/CD 파이프라인을 Cloud Build 기반으로 설계해줘.

- Docker 이미지 빌드 → Artifact Registry 푸시 → Cloud Run 배포 순서
- 시크릿(API 키 등)은 Secret Manager 사용, Dockerfile에 넣지 않기
- cloudbuild.yaml 단계별 설명
```

---

## 빠른 참조: 수동 빌드·실행 명령어

```bash
# Docker 빌드 (이 레포 루트에서)
docker build -t miriart-ai:latest .

# 로컬 실행 (환경변수는 Secret Manager 또는 .env 파일로)
docker run -p 8000:8000 miriart-ai:latest

# Cloud Build 배포
gcloud builds submit --config=cloudbuild.yaml --project=miriarts --region=asia-northeast3

# Cloud Run 상태 확인
gcloud run services describe miriart-ai --region=asia-northeast3 --project=miriarts
```
