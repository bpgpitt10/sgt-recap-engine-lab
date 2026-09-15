from __future__ import annotations

import os
import time
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

TRANSIENT_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
DEFAULT_DELAYS_SECONDS = (5, 15, 45, 120, 240)


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    value = headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, min(float(value), 300.0))
    except (TypeError, ValueError):
        return None


def is_transient_openai_error(exc: Exception) -> bool:
    if isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError)):
        return True
    if isinstance(exc, APIStatusError):
        return int(getattr(exc, "status_code", 0) or 0) in TRANSIENT_STATUS_CODES
    return False


def create_response_with_retry(
    client: Any,
    *,
    model: str,
    max_attempts: int | None = None,
    **request_kwargs: Any,
):
    """Call Responses API with explicit retries for transient provider failures.

    Validation retries belong in the caller. This helper only retries transport,
    throttling, timeout, and transient 5xx failures so one provider hiccup does
    not kill an otherwise-valid tournament build.
    """
    configured_attempts = max_attempts or int(os.environ.get("OPENAI_TRANSIENT_ATTEMPTS", "6"))
    configured_attempts = max(1, configured_attempts)
    last_error: Exception | None = None

    for attempt in range(1, configured_attempts + 1):
        try:
            return client.responses.create(model=model, **request_kwargs)
        except Exception as exc:  # preserve SDK exception details in workflow logs
            last_error = exc
            transient = is_transient_openai_error(exc)
            if not transient or attempt >= configured_attempts:
                raise

            retry_after = _retry_after_seconds(exc)
            fallback_delay = DEFAULT_DELAYS_SECONDS[min(attempt - 1, len(DEFAULT_DELAYS_SECONDS) - 1)]
            delay = retry_after if retry_after is not None else fallback_delay
            print(
                f"Transient OpenAI failure for {model} on API attempt {attempt}/{configured_attempts}: "
                f"{type(exc).__name__}: {exc}. Retrying in {delay:g}s."
            )
            time.sleep(delay)

    raise RuntimeError(f"OpenAI retry loop exited unexpectedly: {last_error}")


def model_candidates(primary_model: str) -> list[str]:
    """Primary model followed by an optional emergency fallback model."""
    fallback = os.environ.get("OPENAI_FALLBACK_MODEL", "").strip()
    candidates = [primary_model]
    if fallback and fallback not in candidates:
        candidates.append(fallback)
    return candidates
