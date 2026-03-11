"""
Google GenAI(Vertex AI) 클라이언트 및 공통 LLM 호출 래퍼.

- vertexai SDK 제거, google-genai SDK 사용 (Vertex AI 백엔드).
- GCS 관련 함수는 app.services.gcs_service로 이전.
"""
import asyncio
import logging
import time
from typing import Any, List, Optional

from google import genai
from google.genai import types

from app.core.config import get_settings
from app.core.exceptions import LLMRateLimitError, LLMServiceError, LLMTimeoutError

logger = logging.getLogger(__name__)

# [DEBUG] SDK 내부 HTTP 호출 추적 — 배포 후 로그 확인 완료 시 제거
logging.getLogger("google.genai").setLevel(logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.DEBUG)

_client: Optional[genai.Client] = None


def get_genai_client() -> genai.Client:
    """GenAI Client 싱글턴. vertexai=True로 Vertex AI 백엔드 사용."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.gcp_region,
            http_options=types.HttpOptions(
                timeout=55 * 1000,  # 55s (BE 60s - 5s margin)
                retry_options=types.HttpRetryOptions(
                    attempts=2,  # 429 등 일시적 에러 시 1회 재시도. AFC 비활성화로 호출 수 제어됨
                    initial_delay=1.0,
                    max_delay=8.0,
                    exp_base=2.0,
                    jitter=0.5,
                    http_status_codes=[429, 500, 502, 503, 504],
                ),
            ),
        )
        logger.info(
            "GenAI client initialized (project=%s, region=%s)",
            settings.gcp_project_id,
            settings.gcp_region,
        )
    return _client


class GeminiModel:
    """Gemini 모델 ID 상수."""

    FLASH = "gemini-3-flash"
    PRO = "gemini-3.1-pro-preview"
    FLASH_LITE = "gemini-3.1-flash-lite-preview"


async def call_gemini(
    model: str,
    contents: Any,
    *,
    system_instruction: Optional[str] = None,
    purpose: str = "unknown",
    timeout_override_s: Optional[int] = None,
    temperature: float = 0.7,
    max_output_tokens: int = 4096,
    response_mime_type: Optional[str] = None,
    return_response: bool = False,
) -> Any:
    """
    모든 Gemini 호출의 단일 진입점.
    - asyncio.wait_for로 Python-level timeout 보장
    - 에러를 LLMTimeoutError / LLMServiceError로 분류
    - 구조화 로그 출력
    - return_response=True 시 raw response 객체 반환 (image-edit 등에서 사용)
    """
    client = get_genai_client()
    effective_timeout = timeout_override_s or 55

    config = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        system_instruction=system_instruction,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    if response_mime_type:
        config.response_mime_type = response_mime_type

    # [DEBUG] 호출 직전 상태 로그 — H1~H6 가설 검증용
    content_types = []
    if isinstance(contents, list):
        for c in contents:
            ctype = type(c).__name__
            if hasattr(c, "mime_type"):
                ctype += f"({c.mime_type})"
            content_types.append(ctype)
    logger.info(
        "gemini_call_start",
        extra={
            "purpose": purpose,
            "model": model,
            "effective_timeout_s": effective_timeout,
            "content_parts": content_types,
            "has_image": any("image" in str(c) for c in content_types),
            "response_mime_type": response_mime_type,
            "afc_disabled": True,
            "sdk_attempts": 2,
            "sdk_timeout_ms": 55000,
        },
    )

    start = time.monotonic()
    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=contents,
                config=config,
            ),
            timeout=effective_timeout,
        )
        latency = time.monotonic() - start
        if return_response:
            logger.info(
                "gemini_call_success",
                extra={
                    "purpose": purpose,
                    "model": model,
                    "latency_s": round(latency, 2),
                    "output_len": 0,
                },
            )
            return response
        text = (response.text or "").strip() if hasattr(response, "text") else ""
        if not text and hasattr(response, "candidates") and response.candidates:
            cand = response.candidates[0]
            if hasattr(cand, "content") and cand.content and hasattr(cand.content, "parts"):
                for part in cand.content.parts:
                    if hasattr(part, "text") and part.text:
                        text = part.text.strip()
                        break
        logger.info(
            "gemini_call_success",
            extra={
                "purpose": purpose,
                "model": model,
                "latency_s": round(latency, 2),
                "output_len": len(text),
            },
        )
        return text

    except asyncio.TimeoutError:
        latency = time.monotonic() - start
        logger.warning(
            "gemini_call_timeout",
            extra={
                "purpose": purpose,
                "model": model,
                "timeout_s": effective_timeout,
                "latency_s": round(latency, 2),
            },
        )
        raise LLMTimeoutError(
            f"Gemini '{purpose}' timed out after {effective_timeout}s"
        )

    except Exception as e:
        latency = time.monotonic() - start
        err_str = str(e)
        is_429 = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
        if is_429:
            logger.warning(
                "gemini_call_rate_limited",
                extra={
                    "purpose": purpose,
                    "model": model,
                    "latency_s": round(latency, 2),
                },
            )
            raise LLMRateLimitError(
                f"Gemini rate limit (429). Please try again in a moment."
            )
        logger.error(
            "gemini_call_error",
            extra={
                "purpose": purpose,
                "model": model,
                "error": err_str[:500],
                "error_type": type(e).__name__,
                "latency_s": round(latency, 2),
            },
            exc_info=True,
        )
        raise LLMServiceError(
            f"Gemini '{purpose}' failed: {type(e).__name__}: {e}"
        )
