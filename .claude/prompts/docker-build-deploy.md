# Docker 빌드 및 배포 프롬프트

아래 프롬프트를 복사해서 Cursor/챗에 붙여넣으면, Docker 빌드·배포 작업을 요청할 수 있습니다.

---

## 1) 전체 서비스 Docker 빌드

```
이 프로젝트를 Docker로 빌드해줘.

- miriart-be: Spring Boot (Gradle, Java 17), Dockerfile 있음. 루트는 miriart-be/
- server: Node.js, Dockerfile 있음. 루트는 server/
- miriart-ai: Python (FastAPI), Dockerfile 있음. 루트는 miriart-ai/

각 서비스별로:
1. 해당 디렉터리에서 Docker 이미지 빌드 (이미지 이름은 서비스명 기반으로, 예: miriart-be, miriart-server, miriart-ai)
2. 빌드에 필요한 명령어나 스크립트를 알려주거나 작성해줘
3. 필요하면 docker-compose.yml로 한 번에 빌드/실행할 수 있게 해줘
```

---

## 2) 특정 서비스만 빌드·실행

```
[miriart-be / server / miriart-ai] 서비스를 Docker로 빌드하고 로컬에서 실행해줘.

- 이미지 이름과 컨테이너 이름 규칙 제안
- 포트 매핑 (각각 8080 등)
- 필요한 환경 변수(application-prod, .env 등) 반영 방법
- 실행용 docker run 예시 또는 docker-compose 서비스 정의
```

---

## 3) 프로덕션 배포용 이미지 빌드

```
프로덕션 배포용 Docker 이미지를 빌드해줘.

- [miriart-be / server / miriart-ai] 기준으로
- multi-stage 빌드 유지, 불필요한 파일 제외
- 태그 규칙: 이미지이름:latest, 이미지이름:버전(또는 git sha)
- 레지스트리 푸시용 명령어 예시 (예: Docker Hub, GCR, ECR) 알려줘
```

---

## 4) docker-compose로 로컬/스테이징 실행

```
docker-compose로 로컬(또는 스테이징) 환경을 구성해줘.

- miriart-be, server, miriart-ai를 각각 서비스로 정의
- 내부 통신용 네트워크, 포트 노출
- 환경별 설정(application-dev, .env) 적용 방법
- 한 번에 빌드 후 실행하는 방법 설명
```

---

## 5) CI/CD에서 Docker 빌드·배포 (요약 요청)

```
CI/CD 파이프라인에서 이 프로젝트를 Docker로 빌드하고 배포하는 단계를 설계해줘.

- GitHub Actions / GitLab CI / Jenkins 등 (원하는 것 지정)
- Docker 이미지 빌드 → 레지스트리 푸시 → 배포(Cloud Run, ECS, Kubernetes 등) 순서
- 시크릿(API 키, DB 비밀번호)은 환경 변수나 Secret Manager 사용, Dockerfile에 넣지 않기
```

---

## 빠른 참조: 수동 빌드 명령어

```bash
# miriart-be (프로젝트 루트가 MiriArt일 때)
docker build -t miriart-be:latest ./miriart-be

# server
docker build -t miriart-server:latest ./server

# miriart-ai
docker build -t miriart-ai:latest ./miriart-ai
```

실행 예시 (포트만 맞추면 됨):

```bash
docker run -p 8080:8080 -e SPRING_PROFILES_ACTIVE=prod miriart-be:latest
docker run -p 8081:8080 miriart-server:latest
docker run -p 8082:8080 miriart-ai:latest
```
