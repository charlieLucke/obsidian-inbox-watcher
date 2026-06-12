"""Bounded Retry-Policy für transiente Remote-Fehler (HTTP + Gemini).

Gemeinsam genutzt von extractors (_http_get) und note_builder
(_generate_note_json) — eine Definition davon, was "transient" heißt.
"""

from __future__ import annotations

import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def _is_transient(exc: BaseException) -> bool:
    """Return True for errors worth retrying (network blips, 429, HTTP 5xx)."""
    if isinstance(exc, requests.exceptions.Timeout | requests.exceptions.ConnectionError):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        resp = exc.response
        return resp is not None and (resp.status_code == 429 or 500 <= resp.status_code < 600)
    from google.genai import errors as genai_errors

    if isinstance(exc, genai_errors.APIError):
        code = exc.code
        return code == 429 or 500 <= code < 600
    return False


# Bounded exponential backoff for transient remote failures; permanent errors
# (bad JSON, empty text, programming errors) fall through immediately.
retryable = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, max=30),
    retry=retry_if_exception(_is_transient),
    reraise=True,
)
