from __future__ import annotations

from typing import Optional


class LayerHopApiError(Exception):
    """A non-2xx API response. ``code`` is a stable error code, e.g. ``QUOTE_EXPIRED``.

    See https://docs.layerhop.com/errors/<code> for causes and fixes.
    """

    def __init__(self, code: str, message: str, status: int, request_id: Optional[str] = None, docs_url: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.request_id = request_id
        self.docs_url = docs_url

    def __repr__(self) -> str:
        return f"LayerHopApiError(code={self.code!r}, status={self.status}, message={self.message!r}, request_id={self.request_id!r})"

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class WebhookSignatureError(Exception):
    """Raised by :func:`layerhop.construct_webhook_event` when a signature does not verify."""
