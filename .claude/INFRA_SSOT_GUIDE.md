# MiriArt 인프라·SSOT 에이전트 지침

에이전트가 인프라/배포/환경설정 관련 작업을 할 때 참고할 규칙과 문서 위치를 정리한다.

---

## 1. 참조 문서 (우선순위)

| 용도 | 문서 경로 | 비고 |
|------|-----------|------|
| **인프라 SSOT** | `docs/SSOT/miriarts_infra.md` | GCP 리소스, 구성, 배포, TODO의 단일 참조. 변경 전·배포 전에 반드시 맞출 기준선. §5.3 BE Docker 빌드·Actuator 참고. |
| **스키마 SSOT** | `docs/mysql_erd_v1.md` | **실제 DB(MySQL) 테이블·컬럼·인덱스**의 단일 참조. 역추출 기준. 정합성 점검은 §4. ERD_v2는 설계/Phase 확장용. |
| **세션 리셋/첫 인지** | 본 GUIDE + `docs/SSOT/miriarts_infra.md` §운영 요약·§1 | 레포 구조·BE/AI·Cloud Run·시크릿은 SSOT 앞단·§1 참고. *(선택)* `docs/IDE_에이전트_올인원_프롬프트_v2_요약.md` 있으면 추가 참고. |
| **SSOT 초안 재생성** | SSOT 변경 규칙(§하단) + “MiriArt 인프라 SSOT 문서 초안 생성” 프롬프트 | 새 SSOT 초안이 필요할 때 사용. |
| **GCP 인프라 명세** | `docs/MiriArt_GCP_INFRA.md` | API, 서비스 계정, 버킷, Secret 목록 등 상세. |
| **BE Cloud Run 배포** | `miriart-be/scripts/cloudrun-redeploy.ps1` + `docs/SSOT/miriarts_infra.md` §5.2 | 배포 명령·옵션의 현재 기준. *(레포에 있으면)* `docs/MiriArt_BE_CloudRun_CloudSQL_FIX.md` 참고. |
| **BE 부팅·동작 보고서** | *(해당 파일 없음 시)* miriarts_infra.md §6.1·§5 | dev/prod 기동·health는 SSOT §6·§5 참고. miriart-be/docs/ 에 BE_*_boot_ok_report.md 있으면 추가 참고. |
| **BE API·health 분석/패치** | miriart-be/docs/ 내 해당 파일 있으면 참고 | 없으면 SSOT·GCP_INFRA 기준으로 점검. |
| **BE 재배포 스크립트** | `miriart-be/scripts/cloudrun-redeploy.ps1` | PowerShell: Cloud Build submit → gcloud run deploy. 로컬 Docker는 gradlew CRLF 처리 필요(Dockerfile 참고). |

---

## 2. 작성·수정 시 규칙

- **시크릿**: 실제 값은 절대 기재하지 않는다. 환경변수/Secret **이름·용도·어디서 쓰이는지 흐름**만 기술한다.
- **근거**: 코드·설정·문서에서 확인된 내용만 서술한다. 확인되지 않으면 **(추론)**으로 명시한다. 가설을 사실처럼 쓰지 않는다.
- **소스 표기**: 주장이나 표 항목에는 가능한 한 **소스(파일:라인)** 또는 `§섹션`을 붙여, 해당 코드/문서를 바로 열 수 있게 한다.
- **검색 범위**: 인프라/설정 요약을 할 때는 **레포 전체 코드·설정·docs/*.md**를 대상으로 하되, 시크릿 값은 출력하지 않는다.

---

## 3. 변경 시 동기화 (Change Policy 요약)

- **Cloud Run / Cloud SQL / Redis / Secret Manager / Artifact Registry / 서비스 계정** 변경 시 → **배포 전에** `docs/SSOT/miriarts_infra.md` 해당 섹션(§2, §3, §4, §5)을 먼저 수정한다.
- **DB 스키마/엔티티** 변경 시 → **스키마 SSOT** `docs/mysql_erd_v1.md`를 기준으로 한다. DDL/역추출 변경 후 해당 문서 §1·§2·§4(정합성 점검) 갱신. 설계 문서 `docs/MiriArt_ERD_v2.md`와 불일치 시 조율(ERD_v2는 설계·미구현 테이블 포함).
- **새 GCP 리소스** 추가 시 → §2(리소스 카탈로그)와 §3(환경변수·Secret 맵)을 함께 갱신한다.
- **CI/CD 파이프라인** 변경 시 → §5(배포 & CI/CD)와 §7(개방 이슈/TODO) 상태를 함께 갱신한다.
- **공개 엔드포인트·인증·CORS** 변경 시 → §4(네트워크 & 보안)를 갱신한다.

---

## 4. 배포 상태 요약 (현재)

- **AI (miriart-ai)**: Cloud Build → Artifact Registry → Cloud Run 자동 배포 (`miriart-ai/cloudbuild.yaml`).
- **BE (miriart-be)**: Gradle + Dockerfile + docker push(또는 Cloud Build submit) + gcloud run deploy. **스크립트** `miriart-be/scripts/cloudrun-redeploy.ps1`. Docker 빌드 시 gradlew CRLF·build/libs 경로는 Dockerfile·SSOT §5.3 참고.
- **FE**: Vercel Git push 기반 빌드/배포. FE 배포 설정의 SSOT는 Vercel 프로젝트.

---

## 5. 에이전트 변경 시 SSOT 자동 업데이트

에이전트(인프라/BE/FE/디자인 등)가 **인프라·배포·환경설정에 영향을 주는** 코드·설정·문서를 수정한 경우, 다음 두 가지를 수행한다.

### 5-1. SSOT 본문 갱신

수정 내용에 맞춰 `docs/SSOT/miriarts_infra.md` 의 해당 섹션을 **즉시** 수정한다.

| 수정한 대상 | 갱신할 SSOT 섹션 |
|-------------|------------------|
| Cloud Run / Cloud SQL / Redis / GCS / Secret / 서비스 계정 | §2 리소스 카탈로그, §3 환경변수·Secret 맵 |
| application*.yml, config.py, 환경변수, 배포 스크립트 | §3 구성·설정, §5.2 배포 파라미터 |
| SecurityConfig, CORS, permitAll, 인증 경로 | §4.2 인증/인가·CORS |
| cloudbuild.yaml, Dockerfile, 배포 절차 | §5 배포 & CI/CD |
| TODO 완료·추가·변경 | §7 개방 이슈/TODO |
| 새 리소스·엔드포인트·헬스 | §2, §3, §6.1 |

### 5-2. 변경 이력 기록 (필수)

`docs/SSOT/CHANGELOG_infra.md` **파일 맨 위(최신이 위)** 에 아래 형식으로 한 줄 이상 추가한다.

- **날짜**: YYYY-MM-DD
- **에이전트 롤**: 인프라 에이전트 / BE 전문 에이전트 / FE 전문 에이전트 / FE(디자인) 에이전트 / 기타(간단히 명시)
- **구체적 수정 내역**: 무엇을 바꿨는지(파일·섹션·요약). 시크릿 값은 기재하지 않음.

예시:
```markdown
### 2026-03-02 | 인프라 에이전트
- miriarts_infra.md §4.2: GET /api/answers/** 컨트롤러 미구현(Phase C1) 명시. §3.1 JWT 만료 라인 32-33으로 수정.
- CHANGELOG_infra.md 초안 추가.
```

### 5-3. 트리거 조건

다음과 같은 작업을 **직접 수정**했을 때만 SSOT·CHANGELOG 반영을 수행한다.

- `miriart-be/**/application*.yml`, `miriart-ai/**/config.py`, `**/cloudbuild*.yaml`, `**/Dockerfile` 편집
- `docs/SSOT/*.md`, `docs/MiriArt_GCP_INFRA.md` 편집
- SecurityConfig, 배포 스크립트(cloudrun-redeploy.ps1 등), Secret/환경변수 목록 변경
- 인프라 점검·재점검 결과를 SSOT에 반영하는 경우

**트리거하지 않는 경우**: 인프라와 무관한 FE 페이지·BE 비인증 로직만 수정한 경우 등. (해당 에이전트가 “인프라 문서도 갱신했다”고 판단하면 그때만 CHANGELOG에 기록.)

---

*이 지침은 `docs/SSOT/miriarts_infra.md`의 변경 규칙 및 기존 에이전트용 프롬프트를 요약한 것이다.*

docker build -t asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-be:latest .


docker push asia-northeast3-docker.pkg.dev/miriarts/miriart-images/miriart-be:latest

gcloud run deploy miriart-be   --image=$IMAGE_BE   --region=$REGION   --platform=managed   --no-allow-unauthenticated   --service-account=$SA_BE   --port=8080   --memory=1Gi   --add-cloudsql-instances=$INSTANCE   --vpc-connector=miriart-connector   --vpc-egress=private-ranges-only   --set-secrets=DB_URL=miriart-db-url:latest,DB_USERNAME=miriart-db-username:latest,DB_PASSWORD=miriart-db-password:latest,REDIS_HOST=miriart-redis-host:latest,JWT_ACCESS_SECRET=miriart-jwt-access-secret:latest,JWT_REFRESH_SECRET=miriart-jwt-refresh-secret:latest,GOOGLE_CLIENT_ID=miriart-google-client-id:latest,GOOGLE_CLIENT_SECRET=miriart-google-client-secret:latest,KAKAO_CLIENT_ID=miriart-kakao-client-id:latest,KAKAO_CLIENT_SECRET=miriart-kakao-client-secret:latest,FRONTEND_OAUTH_SUCCESS_URL=miriart-frontend-oauth-url:latest   --set-env-vars="SPRING_PROFILES_ACTIVE=prod,FASTAPI_INTERNAL_URL=https://miriart-ai-946560105497.asia-northeast3.run.app,GCS_BUCKET_NAME=miriart-bucket"   --project=$PROJECT_ID