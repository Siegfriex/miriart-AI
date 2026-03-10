# Docker 빌드·런·푸시 / GCP 풀 앤 디플로이 — 실행 프롬프트

> 아래 블록을 복사해 에이전트·동료에게 주거나, 터미널에서 순서대로 실행할 때 참고하세요.

---

## 1. 에이전트/사람에게 줄 프롬프트 (한글)

```
MiriArt 백엔드(miriart-be)를 다음 순서로 진행해줘.

1) Docker 빌드
   - 경로: miriart-be 루트 (Dockerfile 있는 곳)
   - 이미지 태그: asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-be:latest
   - 명령: docker build -t <위 태그> .

2) (선택) 로컬에서 컨테이너 실행
   - 포트 8080 노출, 필요하면 -e DB_URL=... 등 환경변수 넘겨서 동작 확인

3) GCP Artifact Registry 푸시
   - 사전: gcloud auth configure-docker asia-northeast3-docker.pkg.dev --quiet
   - 명령: docker push asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-be:latest

4) GCP에서 “풀 앤 디플로이”
   - 방법 A: GCP 콘솔 → Cloud Run → 서비스 miriart-be 선택 → “새 리비전 배포” / “이미지 수정” → 동일 이미지(위 태그) 선택 후 배포
   - 방법 B: gcloud CLI로 배포 (프로젝트 miriarts, 리전 asia-northeast3, 서비스명 miriart-be, --image=위 태그). Cloud SQL·VPC·시크릿 옵션은 기존 서비스 설정 유지하거나 docs/MiriArt_BE_CloudRun_CloudSQL_FIX.md §4 참고해서 deploy 명령 작성

요약: 빌드 → (선택) 로컬 run → 푸시 → GCP 콘솔 또는 gcloud로 해당 이미지로 재배포.
```

---

## 2. 로컬에서 복붙용 명령어 (PowerShell)

### 2-1. Docker 빌드 + 푸시 (로컬 Docker 사용)

```powershell
cd H:\MiriArt\miriart-be

$IMAGE = "asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-be:latest"

# 빌드
docker build -t $IMAGE .

# 레지스트리 인증 (최초 1회)
gcloud auth configure-docker asia-northeast3-docker.pkg.dev --quiet

# 푸시
docker push $IMAGE
```

### 2-2. (선택) 로컬에서 컨테이너 실행 테스트

```powershell
docker run --rm -p 8080:8080 `
  -e SPRING_PROFILES_ACTIVE=dev `
  -e DB_URL="jdbc:mysql://host.docker.internal:3306/miriart_dev?..." `
  asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-be:latest
```

- 로컬 DB/Redis가 있다면 `-e` 로 URL 등 넘겨서 확인.

### 2-3. GCP에서 풀 앤 디플로이 (gcloud)

이미지를 푸시한 뒤, **같은 이미지**로 Cloud Run만 재배포:

```powershell
$PROJECT_ID = "miriarts"
$REGION = "asia-northeast3"
$IMAGE = "asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-be:latest"
$SA = "miriart-be-runner@miriarts.iam.gserviceaccount.com"
$INSTANCE = "miriarts:asia-northeast3:miriart-mysql"

gcloud run deploy miriart-be `
  --image=$IMAGE `
  --region=$REGION `
  --platform=managed `
  --no-allow-unauthenticated `
  --service-account=$SA `
  --port=8080 `
  --memory=1Gi `
  --add-cloudsql-instances=$INSTANCE `
  --vpc-connector=miriart-connector `
  --vpc-egress=private-ranges-only `
  --set-secrets=DB_URL=miriart-db-url:latest,DB_USERNAME=miriart-db-username:latest,DB_PASSWORD=miriart-db-password:latest,REDIS_HOST=miriart-redis-host:latest,JWT_ACCESS_SECRET=miriart-jwt-access-secret:latest,JWT_REFRESH_SECRET=miriart-jwt-refresh-secret:latest,GOOGLE_CLIENT_ID=miriart-google-client-id:latest,GOOGLE_CLIENT_SECRET=miriart-google-client-secret:latest,KAKAO_CLIENT_ID=miriart-kakao-client-id:latest,KAKAO_CLIENT_SECRET=miriart-kakao-client-secret:latest,FRONTEND_OAUTH_SUCCESS_URL=miriart-frontend-oauth-url:latest `
  --set-env-vars="SPRING_PROFILES_ACTIVE=prod,FASTAPI_INTERNAL_URL=https://miriart-ai-946560105497.asia-northeast3.run.app,GCS_BUCKET_NAME=miriart-bucket" `
  --project=$PROJECT_ID
```

---

## 3. GCP 콘솔에서 “풀 앤 디플로이” 하는 방법

1. **콘솔**  
   [Cloud Run](https://console.cloud.google.com/run?project=miriarts) → 리전 **asia-northeast3 (서울)** 선택.

2. **서비스 선택**  
   `miriart-be` 클릭.

3. **새 리비전 배포**  
   상단 **“새 리비전 배포”** (또는 “수정” 후 컨테이너 이미지 변경).

4. **컨테이너 이미지**  
   - “컨테이너 이미지 URL”에  
     `asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-be:latest`  
     입력 또는 “이미지 선택”에서 Artifact Registry 해당 이미지 선택.
   - 이미지를 방금 푸시했다면 **같은 태그**로 선택하면 최신 이미지가 풀되어 배포됨.

5. **나머지 설정**  
   기존과 동일하게 두고(Cloud SQL, VPC, 시크릿, 메모리 등) **“배포”** 클릭.

- **요약**: 푸시한 이미지 = `.../miriart-be:latest` → 콘솔에서 해당 이미지로 새 리비전 배포 = “풀 앤 디플로이”.

---

## 4. 한 번에 하기 (빌드·푸시·배포)

로컬 Docker 없이 **GCP Cloud Build로 빌드·푸시 후 배포**하려면:

```powershell
cd H:\MiriArt\miriart-be
.\scripts\cloudrun-redeploy.ps1
```

- `gcloud builds submit`으로 이미지 빌드·푸시 후, 이어서 `gcloud run deploy` 실행.
- 전제: `gcloud` 로그인, 프로젝트 `miriarts`, VPC 커넥터 `miriart-connector` 및 시크릿 존재.
