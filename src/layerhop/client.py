"""Sync and async LayerHop clients (httpx).

The SDK never holds private keys: it returns unsigned transactions that your own wallet library
signs and broadcasts.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Union
from urllib.parse import quote as _urlquote

import httpx

from .errors import LayerHopApiError
from .types import (
    FINAL_STATES,
    BuiltTx,
    Chain,
    CheckoutQuoteResponse,
    CheckoutSession,
    CheckoutSessionsPage,
    CheckoutStatus,
    FeeChannel,
    OrdersPage,
    OrderStatus,
    QuoteResponse,
    ReportSubmittedResponse,
    SimulateResponse,
    Token,
)

DEFAULT_BASE_URL = "https://api.layerhop.com"
DEFAULT_TIMEOUT = 30.0
__version__ = "0.2.0"


def _seg(v: str) -> str:
    return _urlquote(str(v), safe="")


class _Base:
    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        channel: FeeChannel = "api",
        integrator: Optional[str] = None,
        integrator_fee_bps: Optional[int] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key
        self.channel = channel
        self.integrator = integrator
        self.integrator_fee_bps = integrator_fee_bps
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        h = {"accept": "application/json", "user-agent": f"layerhop-python/{__version__}"}
        if self.api_key:
            h["x-api-key"] = self.api_key
        return h

    def _url(self, path: str) -> str:
        return f"{self.base_url}/v1{path}"

    def _quote_params(
        self, src_chain: Union[str, int], src_token: str, amount: str, dst_chain: Union[str, int],
        dst_token: str, sender: str, recipient: str, slippage_bps: int,
    ) -> Dict[str, str]:
        if not isinstance(amount, str):
            raise TypeError("amount must be an integer string in base units (e.g. '100000000')")
        q = {
            "srcChain": str(src_chain), "srcToken": src_token, "amount": amount,
            "dstChain": str(dst_chain), "dstToken": dst_token, "sender": sender, "recipient": recipient,
            "slippageBps": str(slippage_bps), "channel": self.channel,
        }
        if self.integrator:
            q["integrator"] = self.integrator
        if self.integrator_fee_bps is not None:
            q["integratorFeeBps"] = str(self.integrator_fee_bps)
        return q

    @staticmethod
    def _orders_params(address: Optional[str], status: Optional[str], cursor: Optional[str], limit: Optional[int]) -> Dict[str, str]:
        p: Dict[str, str] = {}
        if address:
            p["address"] = address
        if status:
            p["status"] = status
        if cursor:
            p["cursor"] = cursor
        if limit is not None:
            p["limit"] = str(limit)
        return p

    @staticmethod
    def _checkout_create_body(
        amount: str, settle_chain: Union[str, int], settle_token: str, recipient: str,
        merchant_name: Optional[str], description: Optional[str], reference: Optional[str],
        metadata: Optional[Dict[str, str]], success_url: Optional[str], cancel_url: Optional[str],
        expires_in_minutes: Optional[int],
    ) -> Dict[str, Any]:
        if not isinstance(amount, str):
            raise TypeError("amount must be an integer string in base units (e.g. '49000000')")
        b: Dict[str, Any] = {
            "amount": amount, "settleChain": str(settle_chain), "settleToken": settle_token, "recipient": recipient,
        }
        for k, v in (("merchantName", merchant_name), ("description", description), ("reference", reference),
                     ("metadata", metadata), ("successUrl", success_url), ("cancelUrl", cancel_url),
                     ("expiresInMinutes", expires_in_minutes)):
            if v is not None:
                b[k] = v
        return b

    @staticmethod
    def _checkout_quote_body(src_chain: Union[str, int], src_token: str, sender: str, slippage_bps: Optional[int]) -> Dict[str, Any]:
        b: Dict[str, Any] = {"srcChain": str(src_chain), "srcToken": src_token, "sender": sender}
        if slippage_bps is not None:
            b["slippageBps"] = slippage_bps
        return b

    @staticmethod
    def _handle(res: httpx.Response) -> Any:
        try:
            body = res.json()
        except ValueError:
            body = {}
        if res.is_success:
            return body
        err = body.get("error") if isinstance(body, dict) else None
        if not isinstance(err, dict):
            err = {}
        raise LayerHopApiError(
            code=str(err.get("code") or "INTERNAL"),
            message=str(err.get("message") or res.reason_phrase or f"HTTP {res.status_code}"),
            status=res.status_code,
            request_id=err.get("requestId") or res.headers.get("x-request-id"),
            docs_url=err.get("docsUrl"),
        )


class Checkout:
    """Checkout ("pay with any token"), as ``LayerHop.checkout``.

    ``create``, ``list`` and ``expire`` need an API key; ``get`` and ``quote`` are public (the
    payer's side). Pay a quote with ``build_tx`` + ``report_submitted`` as usual.
    """

    def __init__(self, client: "LayerHop") -> None:
        self._c = client

    def create(
        self, amount: str, settle_chain: Union[str, int], settle_token: str, recipient: str, *,
        merchant_name: Optional[str] = None, description: Optional[str] = None, reference: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None, success_url: Optional[str] = None,
        cancel_url: Optional[str] = None, expires_in_minutes: Optional[int] = None,
    ) -> CheckoutSession:
        """Create a session for ``amount`` (base units of the settlement token). Send the payer to ``url``."""
        return self._c._call("POST", "/checkout/sessions", json=_Base._checkout_create_body(
            amount, settle_chain, settle_token, recipient, merchant_name, description, reference, metadata,
            success_url, cancel_url, expires_in_minutes))

    def get(self, id: str) -> CheckoutSession:
        """Public. Without the owner's API key, ``reference`` and ``metadata`` are omitted."""
        return self._c._call("GET", f"/checkout/sessions/{_seg(id)}")

    def list(
        self, *, status: Optional[CheckoutStatus] = None, cursor: Optional[str] = None, limit: Optional[int] = None,
    ) -> CheckoutSessionsPage:
        """Your sessions of the key's mode (live or test), newest first. Pass ``nextCursor`` to page."""
        return self._c._call("GET", "/checkout/sessions", params=_Base._orders_params(None, status, cursor, limit))

    def expire(self, id: str) -> CheckoutSession:
        """Cancel an ``open`` session so it can no longer be paid."""
        return self._c._call("POST", f"/checkout/sessions/{_seg(id)}/expire", json={})

    def quote(
        self, id: str, src_chain: Union[str, int], src_token: str, *, sender: str, slippage_bps: Optional[int] = None,
    ) -> CheckoutQuoteResponse:
        """Public. Price paying the session with ``src_token`` on ``src_chain`` from ``sender``."""
        return self._c._call("POST", f"/checkout/sessions/{_seg(id)}/quote",
                             json=_Base._checkout_quote_body(src_chain, src_token, sender, slippage_bps))


class AsyncCheckout:
    """Checkout ("pay with any token"), as ``AsyncLayerHop.checkout``. Same methods as :class:`Checkout`."""

    def __init__(self, client: "AsyncLayerHop") -> None:
        self._c = client

    async def create(
        self, amount: str, settle_chain: Union[str, int], settle_token: str, recipient: str, *,
        merchant_name: Optional[str] = None, description: Optional[str] = None, reference: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None, success_url: Optional[str] = None,
        cancel_url: Optional[str] = None, expires_in_minutes: Optional[int] = None,
    ) -> CheckoutSession:
        return await self._c._call("POST", "/checkout/sessions", json=_Base._checkout_create_body(
            amount, settle_chain, settle_token, recipient, merchant_name, description, reference, metadata,
            success_url, cancel_url, expires_in_minutes))

    async def get(self, id: str) -> CheckoutSession:
        return await self._c._call("GET", f"/checkout/sessions/{_seg(id)}")

    async def list(
        self, *, status: Optional[CheckoutStatus] = None, cursor: Optional[str] = None, limit: Optional[int] = None,
    ) -> CheckoutSessionsPage:
        return await self._c._call("GET", "/checkout/sessions", params=_Base._orders_params(None, status, cursor, limit))

    async def expire(self, id: str) -> CheckoutSession:
        return await self._c._call("POST", f"/checkout/sessions/{_seg(id)}/expire", json={})

    async def quote(
        self, id: str, src_chain: Union[str, int], src_token: str, *, sender: str, slippage_bps: Optional[int] = None,
    ) -> CheckoutQuoteResponse:
        return await self._c._call("POST", f"/checkout/sessions/{_seg(id)}/quote",
                                   json=_Base._checkout_quote_body(src_chain, src_token, sender, slippage_bps))


class LayerHop(_Base):
    """Synchronous client.

    >>> lh = LayerHop(api_key="lh_live_...")
    >>> q = lh.quote("base", "USDC", "100000000", "solana", "SOL", sender="0x...", recipient="9WzD...")
    """

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        channel: FeeChannel = "api",
        integrator: Optional[str] = None,
        integrator_fee_bps: Optional[int] = None,
        timeout: float = DEFAULT_TIMEOUT,
        http_client: Optional[httpx.Client] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        super().__init__(base_url=base_url, api_key=api_key, channel=channel, integrator=integrator,
                         integrator_fee_bps=integrator_fee_bps, timeout=timeout)
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout, transport=transport)
        self.checkout = Checkout(self)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "LayerHop":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _call(self, method: str, path: str, *, params: Optional[Dict[str, str]] = None, json: Any = None) -> Any:
        res = self._client.request(method, self._url(path), params=params, json=json, headers=self._headers())
        return self._handle(res)

    def health(self) -> Dict[str, Any]:
        return self._call("GET", "/health")

    def chains(self) -> List[Chain]:
        return self._call("GET", "/chains")["chains"]

    def tokens(self, chain: Union[str, int]) -> List[Token]:
        return self._call("GET", "/tokens", params={"chain": str(chain)})["tokens"]

    def quote(
        self, src_chain: Union[str, int], src_token: str, amount: str, dst_chain: Union[str, int], dst_token: str,
        *, sender: str, recipient: str, slippage_bps: int = 50,
    ) -> QuoteResponse:
        """Ask every provider; ``best`` is the highest output for the user. ``amount`` is base units."""
        return self._call("GET", "/quote", params=self._quote_params(
            src_chain, src_token, amount, dst_chain, dst_token, sender, recipient, slippage_bps))

    def build_tx(self, quote_id: str) -> BuiltTx:
        """The unsigned transaction for a quote. EVM txs may carry an ``approval`` to send first."""
        return self._call("POST", "/orders", json={"quoteId": quote_id})["tx"]

    def submit(self, quote_id: str, signed_transaction: str) -> str:
        """For SvmTx with ``submitViaApi``: send the wallet-signed tx (base64). Returns the signature."""
        return self._call("POST", "/orders/submit", json={"quoteId": quote_id, "signedTransaction": signed_transaction})["txHash"]

    def report_submitted(self, quote_id: str, tx_hash: str) -> ReportSubmittedResponse:
        """Tell LayerHop you broadcast the tx, so it tracks the order (and fires webhooks). Idempotent."""
        return self._call("POST", f"/orders/{_seg(quote_id)}/submitted", json={"txHash": tx_hash})

    def simulate(self, quote_id: str) -> SimulateResponse:
        """Build and dry-run the tx without recording an order."""
        return self._call("POST", "/simulate", json={"quoteId": quote_id})

    def status(self, provider: str, id: str) -> OrderStatus:
        return self._call("GET", f"/orders/{_seg(provider)}/{_seg(id)}")

    def list_orders(
        self, *, address: Optional[str] = None, status: Optional[str] = None,
        cursor: Optional[str] = None, limit: Optional[int] = None,
    ) -> OrdersPage:
        """Orders by sender or recipient address, newest first. Pass ``nextCursor`` to page."""
        return self._call("GET", "/orders", params=self._orders_params(address, status, cursor, limit))

    def watch(self, provider: str, id: str, *, interval: float = 3.0, timeout: float = 1800.0) -> Iterator[OrderStatus]:
        """Poll until the order is final (filled/refunded/failed), yielding each state change."""
        end = time.monotonic() + timeout
        last = None
        while time.monotonic() < end:
            s = self.status(provider, id)
            if s["state"] != last:
                last = s["state"]
                yield s
            if s["state"] in FINAL_STATES:
                return
            time.sleep(interval)


class AsyncLayerHop(_Base):
    """Asynchronous client with the same methods as :class:`LayerHop` (``await``-able)."""

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        channel: FeeChannel = "api",
        integrator: Optional[str] = None,
        integrator_fee_bps: Optional[int] = None,
        timeout: float = DEFAULT_TIMEOUT,
        http_client: Optional[httpx.AsyncClient] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        super().__init__(base_url=base_url, api_key=api_key, channel=channel, integrator=integrator,
                         integrator_fee_bps=integrator_fee_bps, timeout=timeout)
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=timeout, transport=transport)
        self.checkout = AsyncCheckout(self)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "AsyncLayerHop":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def _call(self, method: str, path: str, *, params: Optional[Dict[str, str]] = None, json: Any = None) -> Any:
        res = await self._client.request(method, self._url(path), params=params, json=json, headers=self._headers())
        return self._handle(res)

    async def health(self) -> Dict[str, Any]:
        return await self._call("GET", "/health")

    async def chains(self) -> List[Chain]:
        return (await self._call("GET", "/chains"))["chains"]

    async def tokens(self, chain: Union[str, int]) -> List[Token]:
        return (await self._call("GET", "/tokens", params={"chain": str(chain)}))["tokens"]

    async def quote(
        self, src_chain: Union[str, int], src_token: str, amount: str, dst_chain: Union[str, int], dst_token: str,
        *, sender: str, recipient: str, slippage_bps: int = 50,
    ) -> QuoteResponse:
        return await self._call("GET", "/quote", params=self._quote_params(
            src_chain, src_token, amount, dst_chain, dst_token, sender, recipient, slippage_bps))

    async def build_tx(self, quote_id: str) -> BuiltTx:
        return (await self._call("POST", "/orders", json={"quoteId": quote_id}))["tx"]

    async def submit(self, quote_id: str, signed_transaction: str) -> str:
        return (await self._call("POST", "/orders/submit", json={"quoteId": quote_id, "signedTransaction": signed_transaction}))["txHash"]

    async def report_submitted(self, quote_id: str, tx_hash: str) -> ReportSubmittedResponse:
        return await self._call("POST", f"/orders/{_seg(quote_id)}/submitted", json={"txHash": tx_hash})

    async def simulate(self, quote_id: str) -> SimulateResponse:
        return await self._call("POST", "/simulate", json={"quoteId": quote_id})

    async def status(self, provider: str, id: str) -> OrderStatus:
        return await self._call("GET", f"/orders/{_seg(provider)}/{_seg(id)}")

    async def list_orders(
        self, *, address: Optional[str] = None, status: Optional[str] = None,
        cursor: Optional[str] = None, limit: Optional[int] = None,
    ) -> OrdersPage:
        return await self._call("GET", "/orders", params=self._orders_params(address, status, cursor, limit))

    async def watch(self, provider: str, id: str, *, interval: float = 3.0, timeout: float = 1800.0) -> AsyncIterator[OrderStatus]:
        end = time.monotonic() + timeout
        last = None
        while time.monotonic() < end:
            s = await self.status(provider, id)
            if s["state"] != last:
                last = s["state"]
                yield s
            if s["state"] in FINAL_STATES:
                return
            await asyncio.sleep(interval)
