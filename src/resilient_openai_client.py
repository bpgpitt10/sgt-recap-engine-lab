from __future__ import annotations

import os
from typing import Any

from openai import OpenAI as SDKOpenAI

from openai_resilience import create_response_with_retry, model_candidates


class _ResponsesProxy:
    def __init__(self, client: SDKOpenAI):
        self._client = client

    def create(self, *, model: str, **kwargs: Any):
        last_error: Exception | None = None
        candidates = model_candidates(model)
        for index, candidate in enumerate(candidates):
            try:
                if index:
                    print(f"Primary OpenAI model {model} exhausted transient retries; trying emergency fallback {candidate}.")
                return create_response_with_retry(self._client, model=candidate, **kwargs)
            except Exception as exc:
                last_error = exc
                if index + 1 >= len(candidates):
                    raise
                print(
                    f"OpenAI model {candidate} failed after retry policy: "
                    f"{type(exc).__name__}: {exc}"
                )
        raise RuntimeError(f"No OpenAI model candidate completed the request: {last_error}")


class ResilientOpenAI:
    """Drop-in subset of OpenAI used by the recap writers.

    The SDK's hidden retries are disabled so GitHub logs show exactly what the
    publisher is doing. Explicit retry/backoff lives in openai_resilience.py.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        kwargs.setdefault("max_retries", 0)
        kwargs.setdefault("timeout", float(os.environ.get("OPENAI_REQUEST_TIMEOUT_SECONDS", "120")))
        self._client = SDKOpenAI(*args, **kwargs)
        self.responses = _ResponsesProxy(self._client)
