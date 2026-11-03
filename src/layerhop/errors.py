from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:  # pragma: no cover
    from .types import ProviderError, RouteSuggestion

MAX_ROUTE_SUGGESTIONS = 4
_DIGITS = re.compile(r"^\d{1,78}$")
_KINDS = ("dst_token", "src_token", "via_hub")


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_leg(x: Any) -> bool:
    if not isinstance(x, dict):
        return False
    amount, dst_amount = x.get("amount"), x.get("dstAmount")
    return (
        _is_int(x.get("srcChain")) and _is_int(x.get("dstChain"))
        and isinstance(x.get("srcToken"), str) and isinstance(x.get("dstToken"), str)
        and isinstance(amount, str) and bool(_DIGITS.match(amount)) and amount != "0"
        and (dst_amount is None or (isinstance(dst_amount, str) and bool(_DIGITS.match(dst_amount))))
    )


def parse_route_suggestions(details: Any) -> "List[RouteSuggestion]":
    """``details["suggestions"]`` of an error, validated: malformed entries (and ``via_hub`` entries
    without a valid ``hub`` and two ``steps``) are dropped, at most 4 are kept; anything else gives ``[]``."""
    raw = details.get("suggestions") if isinstance(details, dict) else None
    if not isinstance(raw, list):
        return []
    out: List[Any] = []
    for s in raw:
        if not _is_leg(s) or s.get("kind") not in _KINDS or not isinstance(s.get("message"), str):
            continue
        if s["kind"] == "via_hub":
            steps, hub = s.get("steps"), s.get("hub")
            if not isinstance(steps, list) or len(steps) != 2 or not all(_is_leg(l) for l in steps):
                continue
            if not (isinstance(hub, dict) and _is_int(hub.get("chainId")) and isinstance(hub.get("token"), str)
                    and isinstance(hub.get("symbol"), str) and _is_int(hub.get("decimals"))):
                continue
        out.append(s)
        if len(out) >= MAX_ROUTE_SUGGESTIONS:
            break
    return out


class LayerHopApiError(Exception):
    """A non-2xx API response. ``code`` is a stable error code, e.g. ``QUOTE_EXPIRED``.

    ``details`` is the raw ``error.details`` object when the API sent one (``None`` otherwise): read
    it with :meth:`suggestions` (``NO_ROUTE``), :meth:`provider_errors` and the ``min_amount*``
    properties (``AMOUNT_TOO_SMALL``).

    See https://docs.layerhop.com/errors/<code> for causes and fixes.
    """

    def __init__(
        self, code: str, message: str, status: int, request_id: Optional[str] = None, docs_url: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.request_id = request_id
        self.docs_url = docs_url
        self.details = details

    def suggestions(self) -> "List[RouteSuggestion]":
        """Alternative routes that quoted (``NO_ROUTE``, or ``UNSUPPORTED_CHAIN`` into e.g. Blast), best first."""
        return parse_route_suggestions(self.details)

    def provider_errors(self) -> "List[ProviderError]":
        """Why each provider returned no quote (``details.errors``)."""
        raw = (self.details or {}).get("errors")
        if not isinstance(raw, list):
            return []
        out: List[Any] = [e for e in raw if isinstance(e, dict) and isinstance(e.get("provider"), str)
                          and isinstance(e.get("code"), str) and isinstance(e.get("message"), str)]
        return out

    @property
    def min_amount(self) -> Optional[str]:
        """``AMOUNT_TOO_SMALL``: the smallest input known to quote, base units of ``srcToken``."""
        v = (self.details or {}).get("minAmount")
        return v if isinstance(v, str) and _DIGITS.match(v) else None

    @property
    def min_amount_usd(self) -> Optional[float]:
        """``AMOUNT_TOO_SMALL``: ``min_amount`` in USD, when the token has a price."""
        v = (self.details or {}).get("minAmountUsd")
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    @property
    def min_amount_approx(self) -> Optional[bool]:
        """``AMOUNT_TOO_SMALL``: ``True`` when found by probing larger amounts (the true minimum is at most this)."""
        v = (self.details or {}).get("minAmountApprox")
        return v if isinstance(v, bool) else None

    def __repr__(self) -> str:
        return f"LayerHopApiError(code={self.code!r}, status={self.status}, message={self.message!r}, request_id={self.request_id!r})"

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class WebhookSignatureError(Exception):
    """Raised by :func:`layerhop.construct_webhook_event` when a signature does not verify."""
