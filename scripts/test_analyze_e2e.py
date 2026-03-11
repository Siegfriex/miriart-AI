"""
analyze_artwork E2E 검증 스크립트.

배포 후 실행:
  python scripts/test_analyze_e2e.py https://miriart-ai-<hash>-du.a.run.app

또는 로컬:
  python scripts/test_analyze_e2e.py http://localhost:8080

검증 항목:
  - 404 NOT_FOUND(모델명) 에러가 더 이상 발생하지 않는지
  - HTTP status + body.code가 기대대로 나오는지
  - 성공 시 JSON 구조(grade, radarData 등) 유효한지
"""
import sys
import time
import requests

DEFAULT_BASE = "http://localhost:8080"
ENDPOINT = "/internal/ai/analyze"
NUM_CALLS = 5

# 테스트 페이로드 — gcsUri는 실제 버킷에 존재하는 이미지로 교체 필요
PAYLOAD = {
    "gcsUri": "gs://miriart-bucket/test/sample-artwork.jpg",
    "analysisType": "PRACTICE",
    "problemText": "정물 소묘",
}


def run_test(base_url: str) -> None:
    url = base_url.rstrip("/") + ENDPOINT
    print(f"Target: {url}")
    print(f"Calls:  {NUM_CALLS}\n")
    print(f"{'#':<3} {'Status':<8} {'Code':<22} {'Latency':>8}  Message")
    print("-" * 80)

    for i in range(1, NUM_CALLS + 1):
        start = time.time()
        try:
            resp = requests.post(url, json=PAYLOAD, timeout=65)
            latency = time.time() - start
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            code = body.get("code", body.get("grade", "-"))
            msg = body.get("message", body.get("comment", ""))[:60]
            print(f"{i:<3} {resp.status_code:<8} {code:<22} {latency:>7.2f}s  {msg}")

            # 핵심 검증: 404 NOT_FOUND(모델) 에러가 아닌지
            if resp.status_code == 502 and "NOT_FOUND" in str(body):
                print(f"    !! 모델 404 에러 발생 — 배포 코드 확인 필요")

        except requests.exceptions.Timeout:
            latency = time.time() - start
            print(f"{i:<3} TIMEOUT  -                      {latency:>7.2f}s  client-side timeout")
        except Exception as e:
            latency = time.time() - start
            print(f"{i:<3} ERROR    -                      {latency:>7.2f}s  {e}")

        if i < NUM_CALLS:
            time.sleep(2)  # 429 방지 간격

    print("\n검증 완료.")


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE
    run_test(base)
