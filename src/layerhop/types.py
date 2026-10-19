"""Typed models for the LayerHop API.

Responses are plain ``dict`` objects typed as ``TypedDict`` so unknown fields added by newer API
versions pass through untouched. Keys keep the API's camelCase spelling. Amounts are always
integer strings in base units -- never floats.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Literal, Optional, Union

if sys.version_info >= (3, 11):
    from typing import NotRequired, TypedDict
else:  # pragma: no cover
    from typing_extensions import NotRequired, TypedDict

ProviderId = str
"""``jupiter`` | ``relay`` | ``debridge`` | ``mayan`` | ``zerox`` | ``kyberswap`` | ``odos`` | ``lifi`` | ``mock`` |
``sandbox`` (every request made with an ``lh_test_`` key) | ``direct`` (a plain transfer, used by checkout)"""

FeeChannel = Literal["web", "widget", "bot", "api"]
OrderState = Literal["pending", "filled", "refunded", "failed", "unknown"]
FINAL_STATES = frozenset({"filled", "refunded", "failed"})


class Chain(TypedDict):
    id: int
    slug: str
    name: str
    vm: Literal["evm", "svm"]
    nativeSymbol: str
    nativeDecimals: int
    explorerTx: str


class Token(TypedDict):
    chainId: int
    address: str
    symbol: str
    decimals: int


class FeeBreakdown(TypedDict):
    ourFeeBps: int
    providerFeeUsd: NotRequired[float]
    gasUsd: NotRequired[float]
    integratorFeeBps: NotRequired[int]
    integrator: NotRequired[str]


class Quote(TypedDict):
    quoteId: str
    provider: ProviderId
    dstAmount: str
    dstAmountMin: str
    estimatedSeconds: int
    fees: FeeBreakdown
    expiresAt: int


class ProviderError(TypedDict):
    provider: str
    code: str
    message: str


class QuoteResponse(TypedDict):
    best: Quote
    quotes: List[Quote]
    errors: List[ProviderError]
    livemode: NotRequired[bool]  # ``False`` when the request used an ``lh_test_`` key (sandbox quotes).


class Approval(TypedDict):
    token: str
    spender: str
    amount: str


class EvmTx(TypedDict):
    vm: Literal["evm"]
    chainId: int
    to: str
    data: str
    value: str
    approval: NotRequired[Approval]
    sandbox: NotRequired[bool]  # Test mode only: a placeholder that moves no funds. Never broadcast it.


class SvmTx(TypedDict):
    vm: Literal["svm"]
    serializedTx: str
    submitViaApi: NotRequired[bool]
    sandbox: NotRequired[bool]  # Test mode only: a placeholder that can never land. Never broadcast it.


BuiltTx = Union[EvmTx, SvmTx]


class OrderStatus(TypedDict):
    provider: ProviderId
    id: str
    state: OrderState
    srcTxHash: NotRequired[str]
    dstTxHash: NotRequired[str]


class ReportSubmittedResponse(TypedDict):
    quoteId: str
    status: str


class SimulateError(TypedDict):
    code: str
    message: str
    logs: NotRequired[List[str]]


class SimulateResponse(TypedDict):
    quoteId: str
    provider: ProviderId
    ok: bool
    vm: Literal["evm", "svm"]
    gasEstimate: NotRequired[str]
    computeUnits: NotRequired[int]
    needsApproval: NotRequired[bool]
    simulated: NotRequired[Literal["tx", "approval"]]
    error: NotRequired[SimulateError]
    tx: BuiltTx


class Order(TypedDict, total=False):
    """A recorded order. Fields follow the API; unknown ones are kept as-is."""

    quoteId: str
    provider: ProviderId
    status: str
    statusDetail: Optional[str]
    channel: FeeChannel
    ourFeeBps: int
    partnerFeeBps: int
    sender: str
    recipient: str
    srcChainId: int
    srcToken: str
    dstChainId: int
    dstToken: str
    amount: str
    dstAmount: str
    srcTxHash: str
    dstTxHash: str
    livemode: bool  # ``False`` for test-mode orders.
    checkoutSessionId: Optional[str]  # The checkout session this order pays, if any.
    depositAddressId: Optional[str]  # The deposit address this order came from, if any.
    refundId: NotRequired[Optional[str]]  # The checkout refund this order sends, if any.
    createdAt: str
    updatedAt: str


class OrdersPage(TypedDict):
    orders: List[Order]
    nextCursor: NotRequired[Optional[str]]


CheckoutStatus = Literal["open", "processing", "paid", "expired", "needs_review"]


class CheckoutSettlement(TypedDict):
    chainId: int
    token: str
    symbol: str
    decimals: int


class CheckoutPayment(TypedDict):
    """The current (or final) payment attempt of a checkout session."""

    quoteId: str
    payer: Optional[str]
    srcChainId: Optional[int]
    srcToken: Optional[str]
    srcAmount: Optional[str]
    srcTxHash: Optional[str]
    dstTxHash: Optional[str]
    paidAt: Optional[str]


class CheckoutSession(TypedDict):
    id: str
    object: Literal["checkout.session"]
    livemode: bool
    status: CheckoutStatus
    statusDetail: NotRequired[Optional[str]]
    amount: str
    settlement: CheckoutSettlement
    recipient: str
    merchantName: NotRequired[Optional[str]]
    description: NotRequired[Optional[str]]
    url: str  # The hosted checkout page: send the payer here.
    productId: NotRequired[Optional[str]]  # The product the session was started from, if any.
    invoiceId: NotRequired[Optional[str]]  # The invoice this session pays, if any.
    refundedAmount: NotRequired[str]  # Completed refunds, base units of the settlement token ("0" when none).
    successUrl: NotRequired[Optional[str]]
    cancelUrl: NotRequired[Optional[str]]
    expiresAt: str
    payment: Optional[CheckoutPayment]
    reference: NotRequired[Optional[str]]  # Only with the owning account's API key.
    metadata: NotRequired[Optional[Dict[str, str]]]  # Only with the owning account's API key.
    createdAt: str
    updatedAt: str


class CheckoutSessionsPage(TypedDict):
    sessions: List[CheckoutSession]
    nextCursor: Optional[str]


class CheckoutProduct(TypedDict):
    """A fixed price for payment buttons, ``layerhop.com/buy/{id}`` links and store plugins."""

    id: str
    object: Literal["checkout.product"]
    livemode: bool
    active: bool
    name: str
    description: NotRequired[Optional[str]]
    merchantName: NotRequired[Optional[str]]
    amount: str
    settlement: CheckoutSettlement
    url: str  # ``https://layerhop.com/buy/{id}``: starts a session and opens the payment page.
    # Owner only (with the account's API key):
    recipient: NotRequired[str]
    successUrl: NotRequired[Optional[str]]
    cancelUrl: NotRequired[Optional[str]]
    expiresInMinutes: NotRequired[int]
    allowedOrigins: NotRequired[List[str]]
    createdAt: NotRequired[str]
    updatedAt: NotRequired[str]


class CheckoutProductsPage(TypedDict):
    products: List[CheckoutProduct]
    nextCursor: Optional[str]


class CheckoutQuote(Quote):
    srcAmount: str  # What the payer sends, base units of the chosen token.


class CheckoutQuoteResponse(TypedDict):
    sessionId: str
    livemode: bool
    amountDue: str
    best: CheckoutQuote
    quotes: List[CheckoutQuote]
    errors: List[ProviderError]


WebhookEventType = Literal[
    "order.submitted", "order.filled", "order.refunded", "order.failed",
    "checkout.session.processing", "checkout.session.completed", "checkout.session.payment_failed",
    "checkout.session.expired", "checkout.session.refunded", "invoice.sent", "invoice.paid",
]


class WebhookEvent(TypedDict):
    """The JSON body LayerHop POSTs to your webhook endpoints (and ``webhooks.stream()`` yields)."""

    id: str
    type: str  # A :data:`WebhookEventType`, or ``webhook.test``.
    livemode: bool
    sample: NotRequired[bool]  # Present on samples from the dashboard or ``webhooks.trigger``.
    createdAt: str
    data: Dict[str, Any]  # ``{"order": Order}``, ``{"session": CheckoutSession}``, plus ``refund`` / ``invoice``.


class TriggerWebhookResponse(TypedDict):
    eventId: str
    deliveries: int  # Test endpoints the event was queued for.
    payload: WebhookEvent


InvoiceStatus = Literal["draft", "open", "paid", "void"]


class InvoiceLineItem(TypedDict):
    description: str
    quantity: int  # 1-10000
    unitAmount: str  # Price of one unit, base units of the settlement token.


class PublicInvoice(TypedDict):
    """The customer's view of an invoice (``invoices.public_view``, ``layerhop.com/invoice/{id}``)."""

    id: str
    object: Literal["invoice"]
    livemode: bool
    number: str  # ``INV-0001``, numbered per account and mode.
    status: InvoiceStatus
    merchantName: Optional[str]
    customerName: Optional[str]
    memo: Optional[str]
    lineItems: List[InvoiceLineItem]
    amount: str  # Total, base units of the settlement token.
    settlement: CheckoutSettlement
    dueAt: Optional[str]
    paidAt: Optional[str]
    url: str  # ``https://layerhop.com/invoice/{id}``
    receiptUrl: Optional[str]  # PDF receipt, once paid.
    createdAt: str


class Invoice(PublicInvoice):
    """An invoice as its owner sees it (API key)."""

    customerEmail: Optional[str]
    recipient: str
    sessionId: Optional[str]  # The checkout session paying the invoice.
    sentAt: Optional[str]
    receiptSentAt: Optional[str]
    voidedAt: Optional[str]
    updatedAt: str


class InvoicesPage(TypedDict):
    invoices: List[Invoice]
    nextCursor: Optional[str]


class InvoicePayResponse(TypedDict):
    sessionId: str
    url: str  # The hosted checkout page.


RefundStatus = Literal["pending", "submitted", "completed", "failed"]


class RefundDestination(TypedDict):
    chainId: int
    token: str
    address: str


class Refund(TypedDict):
    id: str
    object: Literal["refund"]
    sessionId: str
    livemode: bool
    status: RefundStatus
    statusDetail: Optional[str]
    amount: str  # Base units of the settlement token.
    reason: Optional[str]
    quoteId: Optional[str]  # build_tx(quoteId), sign from the ``from`` wallet, then report_submitted.
    to: RefundDestination
    txHash: Optional[str]
    createdAt: str
    updatedAt: str


RefundQuote = TypedDict("RefundQuote", {
    "quoteId": str, "provider": str, "srcAmount": str, "dstAmount": str, "dstAmountMin": str,
    "estimatedSeconds": int, "expiresAt": int,
    "from": str,  # The wallet that must sign the refund.
})


class RefundCreateResponse(TypedDict):
    refund: Refund
    quote: RefundQuote
    next: str  # What to do next (build, sign, report).


DepositAddressStatus = Literal["active", "disabled"]


class DepositAddressFees(TypedDict):
    ourFeeBps: int
    integratorFeeBps: int
    integrator: Optional[str]  # The partner id, if a partner fee applies.


class DepositAddress(TypedDict):
    """An address the end user sends ``token`` to on ``chainId``; the provider delivers ``dstToken``
    to ``recipient`` on ``dstChainId``. LayerHop never holds the funds."""

    id: str
    object: Literal["deposit_address"]
    livemode: bool
    status: DepositAddressStatus
    provider: ProviderId  # ``relay`` (live) or ``sandbox`` (test mode).
    address: str  # Show this to your user: they send ``token`` here on ``chainId``.
    chainId: int  # Source chain.
    token: str  # Source token address.
    dstChainId: int
    dstToken: str
    recipient: str  # Receives ``dstToken`` on ``dstChainId``.
    refundTo: str  # Refund address on ``chainId``.
    reusable: bool  # ``False``: a one-time address for exactly ``amount``.
    amount: Optional[str]  # One-time addresses only, base units of ``token``.
    fees: DepositAddressFees
    label: Optional[str]
    metadata: Optional[Dict[str, str]]
    depositCount: int
    lastDepositAt: Optional[str]
    createdAt: str


class DepositAddressEstimate(TypedDict):
    amount: str  # The amount the estimate was priced for, base units of ``token``.
    dstAmount: str
    dstAmountMin: str
    estimatedSeconds: int


class CreatedDepositAddress(DepositAddress):
    """Response of ``deposit_addresses.create``: the address plus an ``estimate``."""

    estimate: DepositAddressEstimate


class DepositAddressWithDeposits(DepositAddress):
    """Response of ``deposit_addresses.get``: the address plus its 20 most recent deposits (orders)."""

    deposits: List[Order]


class DepositAddressesPage(TypedDict):
    depositAddresses: List[DepositAddress]
    nextCursor: Optional[str]


class SimulateDepositResponse(TypedDict):
    order: Order  # The test deposit order (``provider`` ``sandbox``), settled like any test order.


StatusComponentState = Literal["operational", "degraded", "down"]


class StatusDay(TypedDict):
    date: str
    uptime: Optional[float]


class StatusComponent(TypedDict):
    id: str
    name: str
    group: str
    status: StatusComponentState
    latencyMs: Optional[int]
    uptime90d: Optional[float]  # Percent over 90 days.
    days: List[StatusDay]  # 90 days, oldest first.


class StatusIncident(TypedDict):
    id: str
    componentId: str
    component: str
    title: str
    startedAt: str
    resolvedAt: Optional[str]


class StatusResponse(TypedDict):
    """``GET /v1/status`` (shown at status.layerhop.com)."""

    status: Literal["operational", "degraded", "outage"]
    updatedAt: str
    components: List[StatusComponent]
    incidents: List[StatusIncident]  # The last 14 days.
    url: str


Json = Dict[str, Any]
