"""
JSON 구조화 로깅 설정. Cloud Logging 등에서 파싱하기 쉬운 stdout JSON 출력.

- root logger: timestamp, severity, name, message
- uvicorn.access: WARNING 이상만 출력 (요청 로그 노이즈 감소)
"""
import logging
import sys

from pythonjsonlogger import jsonlogger


def setup_logging() -> None:
    """앱 시작 시 1회 호출. root logger에 JSON handler 부착."""
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "severity"},
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = [handler]
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
