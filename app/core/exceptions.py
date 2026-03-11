"""
MiriArt AI 서비스 공통 예외 계층. BE ErrorCode 매핑 의도는 docstring에 명시.

- API_CONTRACT 9 / Dev Spec C1: AI error_code → BE ErrorCode (AN002, AI002, AN001, AI001, F003, C001)
"""
from typing import Optional


class MiriArtAIError(Exception):
    """MiriArt AI 서비스 공통 베이스 예외. message와 error_code로 BE가 HTTP/ErrorCode 매핑."""

    def __init__(self, message: str, error_code: str = "UNKNOWN"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class LLMTimeoutError(MiriArtAIError):
    """Gemini 호출 타임아웃. BE에서 AN002(분석 타임아웃) / AI002(채팅 타임아웃)로 매핑."""

    def __init__(self, message: str):
        super().__init__(message, error_code="LLM_TIMEOUT")


class LLMRateLimitError(MiriArtAIError):
    """Gemini 429 RESOURCE_EXHAUSTED. BE/FE에서 재시도 유도용 429 반환."""

    def __init__(self, message: str):
        super().__init__(message, error_code="LLM_RATE_LIMITED")


class LLMServiceError(MiriArtAIError):
    """Gemini 5xx 또는 SDK 에러. BE에서 AN001(분석 실패) / AI001(채팅 실패)로 매핑."""

    def __init__(self, message: str):
        super().__init__(message, error_code="LLM_SERVICE_ERROR")


class LLMParsingError(MiriArtAIError):
    """Gemini 응답 JSON 파싱 실패. BE에서 AN001 / AI001로 매핑."""

    def __init__(self, message: str):
        super().__init__(message, error_code="LLM_PARSING_ERROR")


class GCSError(MiriArtAIError):
    """GCS 다운로드/업로드 실패. BE에서 F003(GCS 오류)로 매핑."""

    def __init__(self, message: str):
        super().__init__(message, error_code="GCS_ERROR")


class ValidationError(MiriArtAIError):
    """입력 검증 실패. BE에서 C001로 매핑."""

    def __init__(self, message: str):
        super().__init__(message, error_code="VALIDATION_ERROR")
