"""Sync and async LayerHop clients (httpx).

The SDK never holds private keys: it returns unsigned transactions that your own wallet library
signs and broadcasts.
"""

from __future__ import annotations

import asyncio
import json as _json
import time
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Union
from urllib.parse import quote as _urlquote

import httpx

from .errors import LayerHopApiError
from .types import (
    FINAL_STATES,
    BuiltTx,
    Chain,
    CheckoutProduct,
    CheckoutProductsPage,
    CheckoutQuoteResponse,
    CheckoutSession,
    CheckoutSessionsPage,
    CheckoutStatus,
    FeeChannel,
    Invoice,
    InvoiceLineItem,
    InvoicePayResponse,
    InvoicesPage,
    InvoiceStatus,
    Order,
    OrdersPage,
    OrderStatus,
    PublicInvoice,
    QuoteResponse,
    Refund,
    RefundCreateResponse,
    ReportSubmittedResponse,
    SimulateResponse,
    StatusResponse,
    Token,
    TriggerWebhookResponse,
    WebhookEvent,
    WebhookEventType,
)

DEFAULT_BASE_URL = "https://api.layerhop.com"
DEFAULT_TIMEOUT = 30.0
__version__ = "0.5.1"


def _seg(v: str) -> str:
    return _urlquote(str(v), safe="")


class _Unset:
    """Marks an omitted argument of ``products.update`` (``None`` sends ``null`` to clear a field)."""

    def __repr__(self) -> str:
        return "UNSET"


_UNSET: Any = _Unset()


class _SseParser:
    """Incremental Server-Sent Events parser, fed one line (without its terminator) at a time.

    ``feed`` returns the joined ``data`` of a completed frame whose name is ``event``, else ``None``.
    Comment lines (``:``) are skipped; frames of other names (``ready``) are ignored.
    """

    def __init__(self, event: str) -> None:
        self.event = event
        self._name = "message"
        self._data: List[str] = []

    def feed(self, line: str) -> Optional[str]:
        line = line.rstrip("\r")
        if line == "":
            name, data = self._name, self._data
            self._name, self._data = "message", []
            return "\n".join(data) if name == self.event and data else None
        if line.startswith("event:"):
            self._name = line[6:].strip()
        elif line.startswith("data:"):
            v = line[5:]
            self._data.append(v[1:] if v.startswith(" ") else v)
        return None


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
        stream_timeout: Optional[float] = None,
    ) -> None:
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key
        self.channel = channel
        self.integrator = integrator
        self.integrator_fee_bps = integrator_fee_bps
        self.timeout = timeout
        self.stream_timeout = stream_timeout

    def _stream_headers(self) -> Dict[str, str]:
        return {**self._headers(), "accept": "text/event-stream"}

    def _stream_timeout_config(self) -> httpx.Timeout:
        # Streams are long-lived and only send a ping every 15 s: no read timeout by default.
        return httpx.Timeout(self.timeout, read=self.stream_timeout)

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
    def _product_body(fields: Dict[str, Any], *, skip: Any) -> Dict[str, Any]:
        """camelCase JSON body from snake_case arguments, leaving out values that are ``skip``."""
        amount = fields.get("amount", skip)
        if amount is not skip and not isinstance(amount, str):
            raise TypeError("amount must be an integer string in base units (e.g. '49000000')")
        names = {
            "name": "name", "description": "description", "merchant_name": "merchantName", "amount": "amount",
            "settle_chain": "settleChain", "settle_token": "settleToken", "recipient": "recipient",
            "success_url": "successUrl", "cancel_url": "cancelUrl", "expires_in_minutes": "expiresInMinutes",
            "allowed_origins": "allowedOrigins", "active": "active",
        }
        b: Dict[str, Any] = {}
        for k, key in names.items():
            v = fields.get(k, skip)
            if v is skip:
                continue
            b[key] = str(v) if k == "settle_chain" and v is not None else v
        return b

    @staticmethod
    def _product_list_params(active: Optional[bool], cursor: Optional[str], limit: Optional[int]) -> Dict[str, str]:
        p: Dict[str, str] = {}
        if active is not None:
            p["active"] = "true" if active else "false"
        if cursor:
            p["cursor"] = cursor
        if limit is not None:
            p["limit"] = str(limit)
        return p

    @staticmethod
    def _product_session_body(reference: Optional[str], metadata: Optional[Dict[str, str]]) -> Dict[str, Any]:
        b: Dict[str, Any] = {}
        if reference is not None:
            b["reference"] = reference
        if metadata is not None:
            b["metadata"] = metadata
        return b

    @staticmethod
    def _checkout_quote_body(src_chain: Union[str, int], src_token: str, sender: str, slippage_bps: Optional[int]) -> Dict[str, Any]:
        b: Dict[str, Any] = {"srcChain": str(src_chain), "srcToken": src_token, "sender": sender}
        if slippage_bps is not None:
            b["slippageBps"] = slippage_bps
        return b

    @staticmethod
    def _invoice_body(fields: Dict[str, Any], *, skip: Any) -> Dict[str, Any]:
        """camelCase invoice body from snake_case arguments, leaving out values that are ``skip``."""
        items = fields.get("line_items", skip)
        if items is not skip and items is not None:
            for li in items:
                if not isinstance(li.get("unitAmount"), str):
                    raise TypeError("unitAmount must be an integer string in base units (e.g. '49000000')")
        names = {
            "customer_email": "customerEmail", "customer_name": "customerName", "merchant_name": "merchantName",
            "memo": "memo", "line_items": "lineItems", "settle_chain": "settleChain", "settle_token": "settleToken",
            "recipient": "recipient", "due_at": "dueAt", "send": "send",
        }
        b: Dict[str, Any] = {}
        for k, key in names.items():
            v = fields.get(k, skip)
            if v is skip:
                continue
            b[key] = str(v) if k == "settle_chain" and v is not None else v
        return b

    @staticmethod
    def _refund_body(amount: Optional[str], reason: Optional[str], from_: Optional[str], to: Optional[str]) -> Dict[str, Any]:
        if amount is not None and not isinstance(amount, str):
            raise TypeError("amount must be an integer string in base units (e.g. '10000000')")
        b: Dict[str, Any] = {}
        for k, v in (("amount", amount), ("reason", reason), ("from", from_), ("to", to)):
            if v is not None:
                b[k] = v
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


class CheckoutProducts:
    """Products, as ``LayerHop.checkout.products``: a fixed price for payment buttons,
    ``layerhop.com/buy/{id}`` links and store plugins.

    ``create``, ``list`` and ``update`` need an API key; ``get`` and ``start_session`` are public.
    ``start_session`` can only add a ``reference`` and ``metadata`` to the product's terms.
    """

    def __init__(self, client: "LayerHop") -> None:
        self._c = client

    def create(
        self, name: str, amount: str, settle_chain: Union[str, int], settle_token: str, recipient: str, *,
        description: Optional[str] = None, merchant_name: Optional[str] = None, success_url: Optional[str] = None,
        cancel_url: Optional[str] = None, expires_in_minutes: Optional[int] = None,
        allowed_origins: Optional[List[str]] = None, active: Optional[bool] = None,
    ) -> CheckoutProduct:
        """Create a product priced at ``amount`` (base units of the settlement token). Share its ``url``."""
        return self._c._call("POST", "/checkout/products", json=_Base._product_body(dict(
            name=name, amount=amount, settle_chain=settle_chain, settle_token=settle_token, recipient=recipient,
            description=description, merchant_name=merchant_name, success_url=success_url, cancel_url=cancel_url,
            expires_in_minutes=expires_in_minutes, allowed_origins=allowed_origins, active=active), skip=None))

    def get(self, id: str) -> CheckoutProduct:
        """Public: name, price and settlement. With the owner's API key: every field."""
        return self._c._call("GET", f"/checkout/products/{_seg(id)}")

    def list(
        self, *, active: Optional[bool] = None, cursor: Optional[str] = None, limit: Optional[int] = None,
    ) -> CheckoutProductsPage:
        """Your products of the key's mode (live or test). Pass ``nextCursor`` to page."""
        return self._c._call("GET", "/checkout/products", params=_Base._product_list_params(active, cursor, limit))

    def update(
        self, id: str, *, name: Any = _UNSET, description: Any = _UNSET, merchant_name: Any = _UNSET,
        amount: Any = _UNSET, settle_chain: Any = _UNSET, settle_token: Any = _UNSET, recipient: Any = _UNSET,
        success_url: Any = _UNSET, cancel_url: Any = _UNSET, expires_in_minutes: Any = _UNSET,
        allowed_origins: Any = _UNSET, active: Any = _UNSET,
    ) -> CheckoutProduct:
        """Change only the fields you pass (``None`` clears a nullable field). ``active=False`` stops
        new sessions; existing sessions keep their terms."""
        return self._c._call("PATCH", f"/checkout/products/{_seg(id)}", json=_Base._product_body(dict(
            name=name, amount=amount, settle_chain=settle_chain, settle_token=settle_token, recipient=recipient,
            description=description, merchant_name=merchant_name, success_url=success_url, cancel_url=cancel_url,
            expires_in_minutes=expires_in_minutes, allowed_origins=allowed_origins, active=active), skip=_UNSET))

    def start_session(
        self, id: str, *, reference: Optional[str] = None, metadata: Optional[Dict[str, str]] = None,
    ) -> CheckoutSession:
        """Public. Start a checkout session on the product's terms; send the payer to its ``url``."""
        return self._c._call("POST", f"/checkout/products/{_seg(id)}/sessions",
                             json=_Base._product_session_body(reference, metadata))


class AsyncCheckoutProducts:
    """Products, as ``AsyncLayerHop.checkout.products``. Same methods as :class:`CheckoutProducts`."""

    def __init__(self, client: "AsyncLayerHop") -> None:
        self._c = client

    async def create(
        self, name: str, amount: str, settle_chain: Union[str, int], settle_token: str, recipient: str, *,
        description: Optional[str] = None, merchant_name: Optional[str] = None, success_url: Optional[str] = None,
        cancel_url: Optional[str] = None, expires_in_minutes: Optional[int] = None,
        allowed_origins: Optional[List[str]] = None, active: Optional[bool] = None,
    ) -> CheckoutProduct:
        return await self._c._call("POST", "/checkout/products", json=_Base._product_body(dict(
            name=name, amount=amount, settle_chain=settle_chain, settle_token=settle_token, recipient=recipient,
            description=description, merchant_name=merchant_name, success_url=success_url, cancel_url=cancel_url,
            expires_in_minutes=expires_in_minutes, allowed_origins=allowed_origins, active=active), skip=None))

    async def get(self, id: str) -> CheckoutProduct:
        return await self._c._call("GET", f"/checkout/products/{_seg(id)}")

    async def list(
        self, *, active: Optional[bool] = None, cursor: Optional[str] = None, limit: Optional[int] = None,
    ) -> CheckoutProductsPage:
        return await self._c._call("GET", "/checkout/products", params=_Base._product_list_params(active, cursor, limit))

    async def update(
        self, id: str, *, name: Any = _UNSET, description: Any = _UNSET, merchant_name: Any = _UNSET,
        amount: Any = _UNSET, settle_chain: Any = _UNSET, settle_token: Any = _UNSET, recipient: Any = _UNSET,
        success_url: Any = _UNSET, cancel_url: Any = _UNSET, expires_in_minutes: Any = _UNSET,
        allowed_origins: Any = _UNSET, active: Any = _UNSET,
    ) -> CheckoutProduct:
        return await self._c._call("PATCH", f"/checkout/products/{_seg(id)}", json=_Base._product_body(dict(
            name=name, amount=amount, settle_chain=settle_chain, settle_token=settle_token, recipient=recipient,
            description=description, merchant_name=merchant_name, success_url=success_url, cancel_url=cancel_url,
            expires_in_minutes=expires_in_minutes, allowed_origins=allowed_origins, active=active), skip=_UNSET))

    async def start_session(
        self, id: str, *, reference: Optional[str] = None, metadata: Optional[Dict[str, str]] = None,
    ) -> CheckoutSession:
        return await self._c._call("POST", f"/checkout/products/{_seg(id)}/sessions",
                                   json=_Base._product_session_body(reference, metadata))


class CheckoutRefunds:
    """Refunds of paid sessions, as ``LayerHop.checkout.refunds`` (API key).

    Non-custodial: ``create`` returns a ``quote`` that you build with ``build_tx``, sign from
    ``quote["from"]`` (your wallet) and report with ``report_submitted``. The refund completes when
    that order fills; the session's ``refundedAmount`` grows and ``checkout.session.refunded`` is sent.
    """

    def __init__(self, client: "LayerHop") -> None:
        self._c = client

    def create(
        self, session_id: str, *, amount: Optional[str] = None, reason: Optional[str] = None,
        from_: Optional[str] = None, to: Optional[str] = None,
    ) -> RefundCreateResponse:
        """Refund ``amount`` (settlement-token base units; default: everything not yet refunded).
        ``from_`` is the signing wallet (default: the payout address); ``to`` is ``"original"``
        (the payer's chain and token, default) or ``"settlement"``."""
        return self._c._call("POST", f"/checkout/sessions/{_seg(session_id)}/refunds",
                             json=_Base._refund_body(amount, reason, from_, to))

    def list(self, session_id: str) -> List[Refund]:
        """The session's refunds, newest first."""
        return self._c._call("GET", f"/checkout/sessions/{_seg(session_id)}/refunds")["refunds"]


class AsyncCheckoutRefunds:
    """Refunds, as ``AsyncLayerHop.checkout.refunds``. Same methods as :class:`CheckoutRefunds`."""

    def __init__(self, client: "AsyncLayerHop") -> None:
        self._c = client

    async def create(
        self, session_id: str, *, amount: Optional[str] = None, reason: Optional[str] = None,
        from_: Optional[str] = None, to: Optional[str] = None,
    ) -> RefundCreateResponse:
        return await self._c._call("POST", f"/checkout/sessions/{_seg(session_id)}/refunds",
                                   json=_Base._refund_body(amount, reason, from_, to))

    async def list(self, session_id: str) -> List[Refund]:
        return (await self._c._call("GET", f"/checkout/sessions/{_seg(session_id)}/refunds"))["refunds"]


class Invoices:
    """Invoices, as ``LayerHop.invoices``: line items billed to a customer by email and paid through
    checkout on ``layerhop.com/invoice/{id}``.

    ``create``, ``get``, ``list``, ``update``, ``send`` and ``void`` need an API key; ``public_view``
    and ``pay`` are public (the customer's side).
    """

    def __init__(self, client: "LayerHop") -> None:
        self._c = client

    def create(
        self, line_items: List[InvoiceLineItem], settle_chain: Union[str, int], settle_token: str, recipient: str, *,
        customer_email: Optional[str] = None, customer_name: Optional[str] = None, merchant_name: Optional[str] = None,
        memo: Optional[str] = None, due_at: Optional[str] = None, send: Optional[bool] = None,
    ) -> Invoice:
        """Create a draft invoice (``send=True`` finalizes and emails it right away). Line items are
        ``{"description", "quantity", "unitAmount"}`` with ``unitAmount`` in base units."""
        return self._c._call("POST", "/invoices", json=_Base._invoice_body(dict(
            line_items=line_items, settle_chain=settle_chain, settle_token=settle_token, recipient=recipient,
            customer_email=customer_email, customer_name=customer_name, merchant_name=merchant_name, memo=memo,
            due_at=due_at, send=send), skip=None))

    def get(self, id: str) -> Invoice:
        return self._c._call("GET", f"/invoices/{_seg(id)}")

    def list(
        self, *, status: Optional[InvoiceStatus] = None, cursor: Optional[str] = None, limit: Optional[int] = None,
    ) -> InvoicesPage:
        """Your invoices of the key's mode (live or test), newest first. Pass ``nextCursor`` to page."""
        return self._c._call("GET", "/invoices", params=_Base._orders_params(None, status, cursor, limit))

    def update(
        self, id: str, *, line_items: Any = _UNSET, settle_chain: Any = _UNSET, settle_token: Any = _UNSET,
        recipient: Any = _UNSET, customer_email: Any = _UNSET, customer_name: Any = _UNSET,
        merchant_name: Any = _UNSET, memo: Any = _UNSET, due_at: Any = _UNSET,
    ) -> Invoice:
        """Drafts only. Change only the fields you pass (``None`` clears a nullable field)."""
        return self._c._call("PATCH", f"/invoices/{_seg(id)}", json=_Base._invoice_body(dict(
            line_items=line_items, settle_chain=settle_chain, settle_token=settle_token, recipient=recipient,
            customer_email=customer_email, customer_name=customer_name, merchant_name=merchant_name, memo=memo,
            due_at=due_at), skip=_UNSET))

    def send(self, id: str) -> Invoice:
        """Finalize a draft (draft -> open) and email it; on an open invoice, re-send the email."""
        return self._c._call("POST", f"/invoices/{_seg(id)}/send", json={})

    def void(self, id: str) -> Invoice:
        """Cancel a draft or open invoice (its open checkout session expires)."""
        return self._c._call("POST", f"/invoices/{_seg(id)}/void", json={})

    def public_view(self, id: str) -> PublicInvoice:
        """Public: the customer's view of a sent invoice."""
        return self._c._call("GET", f"/invoices/{_seg(id)}/public")

    def pay(self, id: str) -> InvoicePayResponse:
        """Public: start (or reuse) the checkout session that pays the invoice; send the customer to ``url``."""
        return self._c._call("POST", f"/invoices/{_seg(id)}/pay", json={})


class AsyncInvoices:
    """Invoices, as ``AsyncLayerHop.invoices``. Same methods as :class:`Invoices`."""

    def __init__(self, client: "AsyncLayerHop") -> None:
        self._c = client

    async def create(
        self, line_items: List[InvoiceLineItem], settle_chain: Union[str, int], settle_token: str, recipient: str, *,
        customer_email: Optional[str] = None, customer_name: Optional[str] = None, merchant_name: Optional[str] = None,
        memo: Optional[str] = None, due_at: Optional[str] = None, send: Optional[bool] = None,
    ) -> Invoice:
        return await self._c._call("POST", "/invoices", json=_Base._invoice_body(dict(
            line_items=line_items, settle_chain=settle_chain, settle_token=settle_token, recipient=recipient,
            customer_email=customer_email, customer_name=customer_name, merchant_name=merchant_name, memo=memo,
            due_at=due_at, send=send), skip=None))

    async def get(self, id: str) -> Invoice:
        return await self._c._call("GET", f"/invoices/{_seg(id)}")

    async def list(
        self, *, status: Optional[InvoiceStatus] = None, cursor: Optional[str] = None, limit: Optional[int] = None,
    ) -> InvoicesPage:
        return await self._c._call("GET", "/invoices", params=_Base._orders_params(None, status, cursor, limit))

    async def update(
        self, id: str, *, line_items: Any = _UNSET, settle_chain: Any = _UNSET, settle_token: Any = _UNSET,
        recipient: Any = _UNSET, customer_email: Any = _UNSET, customer_name: Any = _UNSET,
        merchant_name: Any = _UNSET, memo: Any = _UNSET, due_at: Any = _UNSET,
    ) -> Invoice:
        return await self._c._call("PATCH", f"/invoices/{_seg(id)}", json=_Base._invoice_body(dict(
            line_items=line_items, settle_chain=settle_chain, settle_token=settle_token, recipient=recipient,
            customer_email=customer_email, customer_name=customer_name, merchant_name=merchant_name, memo=memo,
            due_at=due_at), skip=_UNSET))

    async def send(self, id: str) -> Invoice:
        return await self._c._call("POST", f"/invoices/{_seg(id)}/send", json={})

    async def void(self, id: str) -> Invoice:
        return await self._c._call("POST", f"/invoices/{_seg(id)}/void", json={})

    async def public_view(self, id: str) -> PublicInvoice:
        return await self._c._call("GET", f"/invoices/{_seg(id)}/public")

    async def pay(self, id: str) -> InvoicePayResponse:
        return await self._c._call("POST", f"/invoices/{_seg(id)}/pay", json={})


class Checkout:
    """Checkout ("pay with any token"), as ``LayerHop.checkout``.

    ``create``, ``list`` and ``expire`` need an API key; ``get`` and ``quote`` are public (the
    payer's side). Pay a quote with ``build_tx`` + ``report_submitted`` as usual. Products (payment
    buttons) are under ``products``, refunds of paid sessions under ``refunds``.
    """

    def __init__(self, client: "LayerHop") -> None:
        self._c = client
        self.products = CheckoutProducts(client)
        self.refunds = CheckoutRefunds(client)

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

    def stream(self, id: str) -> Iterator[CheckoutSession]:
        """Public. Live session status (SSE): yields now and on every change until ``paid``,
        ``expired`` or ``needs_review``, then ends. Break out of the loop to stop early."""
        return self._c._stream(f"/checkout/sessions/{_seg(id)}/events", "session")


class AsyncCheckout:
    """Checkout ("pay with any token"), as ``AsyncLayerHop.checkout``. Same methods as :class:`Checkout`."""

    def __init__(self, client: "AsyncLayerHop") -> None:
        self._c = client
        self.products = AsyncCheckoutProducts(client)
        self.refunds = AsyncCheckoutRefunds(client)

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

    def stream(self, id: str) -> AsyncIterator[CheckoutSession]:
        """``async for session in lh.checkout.stream(id)``; see :meth:`Checkout.stream`."""
        return self._c._stream(f"/checkout/sessions/{_seg(id)}/events", "session")


class Webhooks:
    """Webhook developer tools with an API key, as ``LayerHop.webhooks`` (the CLI's ``listen`` and ``trigger``)."""

    def __init__(self, client: "LayerHop") -> None:
        self._c = client

    def stream(self) -> Iterator[WebhookEvent]:
        """Your account's webhook events (the key's mode) as they are created, with the exact payloads.
        Runs until the server closes the stream (at most 30 minutes) or you break out of the loop."""
        return self._c._stream("/webhooks/stream", "event")

    def trigger(self, type: WebhookEventType) -> TriggerWebhookResponse:
        """A sample event in test mode (test keys only): sent to your test endpoints and open streams."""
        return self._c._call("POST", "/webhooks/trigger", json={"type": type})


class AsyncWebhooks:
    """Webhook developer tools, as ``AsyncLayerHop.webhooks``. Same methods as :class:`Webhooks`."""

    def __init__(self, client: "AsyncLayerHop") -> None:
        self._c = client

    def stream(self) -> AsyncIterator[WebhookEvent]:
        return self._c._stream("/webhooks/stream", "event")

    async def trigger(self, type: WebhookEventType) -> TriggerWebhookResponse:
        return await self._c._call("POST", "/webhooks/trigger", json={"type": type})


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
        stream_timeout: Optional[float] = None,
        http_client: Optional[httpx.Client] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        super().__init__(base_url=base_url, api_key=api_key, channel=channel, integrator=integrator,
                         integrator_fee_bps=integrator_fee_bps, timeout=timeout, stream_timeout=stream_timeout)
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout, transport=transport)
        self.checkout = Checkout(self)
        self.invoices = Invoices(self)
        self.webhooks = Webhooks(self)

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

    def _stream(self, path: str, event: str) -> Iterator[Any]:
        """Read a Server-Sent Events stream, yielding the JSON data of ``event`` frames."""
        with self._client.stream("GET", self._url(path), headers=self._stream_headers(),
                                 timeout=self._stream_timeout_config()) as res:
            if not res.is_success:
                res.read()
                self._handle(res)
            parser = _SseParser(event)
            for line in res.iter_lines():
                data = parser.feed(line)
                if data is not None:
                    yield _json.loads(data)

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
        """A provider order's state."""
        return self._call("GET", f"/orders/{_seg(provider)}/{_seg(id)}")

    def service_status(self) -> StatusResponse:
        """Platform status (``GET /v1/status``, shown at status.layerhop.com). Public."""
        return self._call("GET", "/status")

    def list_orders(
        self, *, address: Optional[str] = None, status: Optional[str] = None,
        cursor: Optional[str] = None, limit: Optional[int] = None,
    ) -> OrdersPage:
        """Orders by sender or recipient address, newest first. Pass ``nextCursor`` to page."""
        return self._call("GET", "/orders", params=self._orders_params(address, status, cursor, limit))

    def stream_order(self, quote_id: str) -> Iterator[Order]:
        """Live order status (Server-Sent Events): yields the order now and on every change, and ends
        when it is final (filled, refunded, failed or expired). Break out of the loop to stop early."""
        return self._stream(f"/orders/{_seg(quote_id)}/events", "order")

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
        stream_timeout: Optional[float] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        super().__init__(base_url=base_url, api_key=api_key, channel=channel, integrator=integrator,
                         integrator_fee_bps=integrator_fee_bps, timeout=timeout, stream_timeout=stream_timeout)
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=timeout, transport=transport)
        self.checkout = AsyncCheckout(self)
        self.invoices = AsyncInvoices(self)
        self.webhooks = AsyncWebhooks(self)

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

    async def _stream(self, path: str, event: str) -> AsyncIterator[Any]:
        async with self._client.stream("GET", self._url(path), headers=self._stream_headers(),
                                       timeout=self._stream_timeout_config()) as res:
            if not res.is_success:
                await res.aread()
                self._handle(res)
            parser = _SseParser(event)
            async for line in res.aiter_lines():
                data = parser.feed(line)
                if data is not None:
                    yield _json.loads(data)

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

    async def service_status(self) -> StatusResponse:
        return await self._call("GET", "/status")

    async def list_orders(
        self, *, address: Optional[str] = None, status: Optional[str] = None,
        cursor: Optional[str] = None, limit: Optional[int] = None,
    ) -> OrdersPage:
        return await self._call("GET", "/orders", params=self._orders_params(address, status, cursor, limit))

    def stream_order(self, quote_id: str) -> AsyncIterator[Order]:
        """``async for order in lh.stream_order(quote_id)``; see :meth:`LayerHop.stream_order`."""
        return self._stream(f"/orders/{_seg(quote_id)}/events", "order")

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
