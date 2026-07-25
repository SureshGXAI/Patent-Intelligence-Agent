"""Shared HTTP helper for live source clients.

Adds retry with exponential backoff, honouring Retry-After on 429/503, a small
connection-error retry, and a typed error so callers can distinguish auth
failures (which should surface a re-credential prompt) from transient ones.

NOTE: exercised only in live mode. It cannot be smoke-tested inside the offline
sandbox (target hosts are network-blocked), so it is written to the documented
contracts and must be validated against the live services before shipping.
"""
from __future__ import annotations

import time
from typing import Optional

import requests

from ..config import settings


class SourceError(RuntimeError):
    def __init__(self, message: str, *, status: Optional[int] = None,
                 kind: str = "transient"):
        super().__init__(message)
        self.status = status
        self.kind = kind          # "auth" | "client" | "transient"


def request(method: str, url: str, *, max_retries: int = 3,
            backoff: float = 0.5, **kwargs) -> requests.Response:
    kwargs.setdefault("timeout", settings.http_timeout)
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.request(method, url, **kwargs)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == max_retries:
                raise SourceError(f"connection failed: {exc}", kind="transient")
            time.sleep(backoff * (2 ** attempt))
            continue

        if resp.status_code in (429, 500, 502, 503, 504):
            if attempt == max_retries:
                raise SourceError(f"{resp.status_code} after retries",
                                  status=resp.status_code, kind="transient")
            wait = float(resp.headers.get("Retry-After", backoff * (2 ** attempt)))
            time.sleep(wait)
            continue

        if resp.status_code in (401, 403):
            raise SourceError(f"authentication failed ({resp.status_code})",
                              status=resp.status_code, kind="auth")
        if 400 <= resp.status_code < 500:
            raise SourceError(f"client error {resp.status_code}: {resp.text[:200]}",
                              status=resp.status_code, kind="client")
        return resp
    raise SourceError(f"request failed: {last_exc}", kind="transient")


def get(url: str, **kwargs) -> requests.Response:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs) -> requests.Response:
    return request("POST", url, **kwargs)
