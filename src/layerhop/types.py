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
    "checkout.session.expired",
]


class WebhookEvent(TypedDict):
    """The JSON body LayerHop POSTs to your webhook endpoints (and ``webhooks.stream()`` yields)."""

    id: str
    type: str  # A :data:`WebhookEventType`, or ``webhook.test``.
    livemode: bool
    sample: NotRequired[bool]  # Present on samples from the dashboard or ``webhooks.trigger``.
    createdAt: str
    data: Dict[str, Any]  # ``{"order": Order}`` or ``{"session": CheckoutSession}``.


class TriggerWebhookResponse(TypedDict):
    eventId: str
    deliveries: int  # Test endpoints the event was queued for.
    payload: WebhookEvent


Json = Dict[str, Any]
