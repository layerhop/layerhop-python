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
OrderState = Literal["pending", "filled", "refunded", "failed", "unknown", "dropped"]
"""``dropped``: the source transaction never reached the network (no funds moved); final."""
FINAL_STATES = frozenset({"filled", "refunded", "failed", "dropped"})

Vm = Literal["evm", "svm", "tvm"]
"""Virtual machine family: ``svm`` is Solana, ``tvm`` is Tron."""

ErrorCode = Literal[
    "INVALID_PARAMS", "UNSUPPORTED_CHAIN", "UNSUPPORTED_TOKEN", "AMOUNT_TOO_SMALL", "AMOUNT_TOO_LARGE",
    "CALLS_REVERTED", "LAUNCH_IMAGE_INVALID", "NO_ROUTE", "QUOTE_NOT_FOUND", "QUOTE_EXPIRED", "ORDER_NOT_FOUND",
    "PROVIDER_ERROR", "PROVIDER_TIMEOUT", "RATE_LIMITED", "QUOTA_EXCEEDED", "UNAUTHORIZED", "FORBIDDEN",
    "NOT_FOUND", "CONFLICT", "GASLESS_PENDING", "GASLESS_FAILED", "INTERNAL",
]
"""Stable error codes (``LayerHopApiError.code`` is a plain ``str``, so new codes still decode)."""

RouteHealthState = Literal["ok", "failing", "unknown"]


ChainRouteHealth = TypedDict("ChainRouteHealth", {
    "in": str,  # A :data:`RouteHealthState`: probe quotes into the chain.
    "out": str,  # A :data:`RouteHealthState`: probe quotes out of the chain.
    "status": str,  # ``ok`` | ``deposit_only`` | ``withdraw_only`` | ``unavailable`` | ``unknown``
    "checkedAt": NotRequired[str],
})
"""LayerHop's periodic read-only probe quotes of a chain (read ``health["in"]``)."""


class OnlyRoute(TypedDict):
    """The one fixed route into a chain (e.g. Blast: ETH on Ethereum only)."""

    srcChainId: int
    srcToken: str
    dstToken: str


class Chain(TypedDict):
    id: int
    slug: str
    name: str
    vm: Vm
    nativeSymbol: str
    nativeDecimals: int
    explorerTx: str
    logoURI: NotRequired[str]
    explorerAddress: NotRequired[str]
    providers: NotRequired[List[str]]
    popular: NotRequired[bool]
    destinationOnly: NotRequired[bool]  # Deliver-only chains (e.g. Hyperliquid, Blast): hide from source pickers.
    onlyRoute: NotRequired[OnlyRoute]
    routeHealth: NotRequired[ChainRouteHealth]


class Token(TypedDict):
    chainId: int
    address: str
    symbol: str
    decimals: int
    name: NotRequired[str]
    logoURI: NotRequired[str]
    priceUsd: NotRequired[float]
    verified: NotRequired[bool]  # On a provider list or LayerHop's curated list; ``False`` for on-chain-only tokens.
    popular: NotRequired[bool]


class TokensPage(TypedDict):
    tokens: List[Token]
    nextCursor: Optional[str]  # Pass as ``cursor`` for the next page; ``None`` on the last page.


TokenRiskLevel = Literal["ok", "caution", "danger", "unknown"]


class TokenRiskReason(TypedDict):
    code: str  # e.g. ``honeypot``, ``sell_tax``, ``mintable`` (new codes may appear).
    level: str  # ``caution`` | ``danger``
    message: str
    value: NotRequired[float]  # Percent for taxes / transfer fees; holder count for ``few_holders``.


class TokenRisk(TypedDict):
    """A token's safety report. Show ``danger`` prominently and ask for a confirmation before a buy."""

    chainId: int
    address: str
    level: str  # A :data:`TokenRiskLevel`.
    verified: bool
    symbol: NotRequired[str]
    reasons: List[TokenRiskReason]
    source: str  # ``list`` | ``goplus`` | ``none``
    checkedAt: str


class Balance(Token):
    amount: str  # Base units.
    valueUsd: NotRequired[float]


class BalanceError(TypedDict):
    chainId: int
    message: str


class BalancesResponse(TypedDict):
    address: str
    vm: Vm
    balances: List[Balance]  # Highest USD value first.
    totalUsd: float
    errors: List[BalanceError]  # Chains (or requested tokens) that could not be read.


class FeeBreakdown(TypedDict):
    ourFeeBps: int
    providerFeeUsd: NotRequired[float]
    gasUsd: NotRequired[float]
    integratorFeeBps: NotRequired[int]
    integrator: NotRequired[str]


class GasOnArrival(TypedDict):
    """Native gas a route delivers to the recipient on top of ``dstAmount`` (its cost is already
    taken out of ``dstAmount``)."""

    amount: str  # Base units of the destination chain's native token.
    token: str  # Native token address on the destination chain (EVM: ``0x000...000``).
    symbol: str
    decimals: int
    usd: NotRequired[float]  # USD value at quote time.


class Quote(TypedDict):
    quoteId: str
    provider: ProviderId
    dstAmount: str
    dstAmountMin: str
    estimatedSeconds: int
    fees: FeeBreakdown
    expiresAt: int
    gasOnArrival: NotRequired[GasOnArrival]  # Present when gas on arrival was requested and this route includes it.
    srcAmount: NotRequired[str]  # What the sender pays (base units), on destination-call and checkout quotes.
    calls: NotRequired["DestinationCallsPlan"]  # Destination calls the provider will run (``quote_calls``).
    gasless: NotRequired["GaslessQuoteInfo"]  # Gasless quotes only (``gasless=True``).


class GasFee(TypedDict):
    amount: str  # Base units of ``token``.
    token: str  # The input token.


class GaslessQuoteInfo(TypedDict):
    """On gasless quotes only. ``dstAmount`` already accounts for the gas fee."""

    gasFee: NotRequired[GasFee]  # Network fee the provider's relayer takes from the input token.
    approval: bool  # ``True`` when the wallet signs a gasless approval (permit) before the trade.


class DestinationCall(TypedDict):
    """One contract call on the destination chain (``value`` in wei, native outputs only)."""

    to: str
    data: str
    value: NotRequired[str]


class DestinationCallsSimulation(TypedDict):
    ok: bool
    gasUsed: str
    leftover: NotRequired[str]


class DestinationCallsPlan(TypedDict):
    """The calls a quote's provider committed to run, and their pre-quote simulation."""

    items: List[EvmCall]
    executor: str  # Contract that receives the output and makes the calls (their ``msg.sender``).
    executed: bool
    simulation: NotRequired[DestinationCallsSimulation]


class DestinationAction(TypedDict):
    """A preset that builds the calls server-side: ``{"type": "aave-v3-supply"}``."""

    type: str


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


class EvmCall(TypedDict):
    to: str
    data: str
    value: str


class EvmTx(TypedDict):
    vm: Literal["evm"]
    chainId: int
    to: str
    data: str
    value: str
    approval: NotRequired[Approval]
    # Further calls to send after the main transaction, in order (e.g. LayerHop's fee transfer on a
    # same-token checkout payment). Report the main transaction's hash.
    extraTxs: NotRequired[List[EvmCall]]
    sandbox: NotRequired[bool]  # Test mode only: a placeholder that moves no funds. Never broadcast it.


class SvmTx(TypedDict):
    vm: Literal["svm"]
    serializedTx: str
    submitViaApi: NotRequired[bool]
    sandbox: NotRequired[bool]  # Test mode only: a placeholder that can never land. Never broadcast it.


class TronCall(TypedDict):
    """One Tron smart-contract call. Addresses are base58 T-addresses; ``value`` and ``feeLimit`` are sun."""

    to: str
    data: str  # ABI calldata, ``0x`` hex.
    value: str
    feeLimit: str  # The most TRX (sun) the network may burn for this call's energy.


class TronUnsignedTx(TypedDict):
    """An unsigned Tron transaction exactly as the node built it (TronWeb's transaction object).
    Sign it unchanged and broadcast it before ``raw_data["expiration"]``."""

    txID: str  # The tx hash once broadcast: bare 64-hex, no ``0x``.
    raw_data_hex: str
    raw_data: Dict[str, Any]  # Decoded raw data (free-form JSON): keep it as-is.
    visible: NotRequired[bool]


class TronApproval(TypedDict):
    """TRC-20 approval to send before the main call (its own transaction)."""

    token: str
    spender: str
    amount: str
    call: TronCall
    unsigned: NotRequired[TronUnsignedTx]


TronTx = TypedDict("TronTx", {
    "vm": Literal["tvm"],
    "chainId": int,  # 728126428
    "from": str,  # Owner (signer) of every call, T-address.
    "call": TronCall,
    "unsigned": NotRequired[TronUnsignedTx],
    "approval": NotRequired[TronApproval],
    "sandbox": NotRequired[bool],  # Test mode only: a placeholder that moves no funds. Never broadcast it.
})
"""Tron transaction(s) for a quote. The SDK never signs: sign ``unsigned`` unchanged with a Tron
wallet (TronWeb / TronLink), send ``approval`` first when present, broadcast before
``raw_data["expiration"]``, then ``report_submitted`` with the main tx's ``txID`` (bare 64-hex)."""


BuiltTx = Union[EvmTx, SvmTx, TronTx]


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
    vm: Vm
    gasEstimate: NotRequired[str]
    energyUsed: NotRequired[int]  # Tron: energy the simulated call used.
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
    limitOrderId: Optional[str]  # The limit order this order is a fill of, if any (``quoteId`` starts with ``lof_``).
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
    """A checkout quote. ``srcAmount`` (what the payer sends, base units of the chosen token) is
    always present."""


class CheckoutQuoteResponse(TypedDict):
    sessionId: str
    livemode: bool
    amountDue: str
    best: CheckoutQuote
    quotes: List[CheckoutQuote]
    errors: List[ProviderError]


WebhookEventType = Literal[
    "order.submitted", "order.filled", "order.refunded", "order.failed", "order.dropped",
    "checkout.session.processing", "checkout.session.completed", "checkout.session.payment_failed",
    "checkout.session.expired", "checkout.session.refunded", "invoice.sent", "invoice.paid",
    "subscription.created", "subscription.renewed", "subscription.past_due", "subscription.canceled",
    "limit_order.opened", "limit_order.filled", "limit_order.cancelled", "limit_order.expired", "limit_order.failed",
]


class WebhookEvent(TypedDict):
    """The JSON body LayerHop POSTs to your webhook endpoints (and ``webhooks.stream()`` yields)."""

    id: str
    type: str  # A :data:`WebhookEventType`, or ``webhook.test``.
    livemode: bool
    sample: NotRequired[bool]  # Present on samples from the dashboard or ``webhooks.trigger``.
    createdAt: str
    # ``{"order": Order}``, ``{"session": CheckoutSession}``, plus ``refund`` / ``invoice``;
    # ``{"subscription": Subscription}`` (``renewed`` / ``past_due`` add ``invoice``);
    # ``{"limitOrder": LimitOrder}`` (``limit_order.filled`` adds ``fill``, the fill's OrderSummary).
    data: Dict[str, Any]


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
    subscriptionId: NotRequired[Optional[str]]  # The subscription this invoice bills a period of, if any.
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


SubscriptionStatus = Literal["active", "past_due", "canceled", "paused"]
"""``active`` (billing each period), ``past_due`` (an invoice is unpaid past its due date: reminders go
out and renewals wait), ``paused`` (no invoices or reminders), ``canceled`` (by you, or 7 days past due)."""

SubscriptionInterval = Literal["day", "week", "month", "year"]


class Subscription(TypedDict):
    """Recurring billing: LayerHop issues and emails an invoice every period."""

    id: str
    object: Literal["subscription"]
    livemode: bool
    status: SubscriptionStatus
    customerEmail: str
    customerName: Optional[str]
    merchantName: Optional[str]
    description: str  # The invoice line item; each invoice adds the period's dates.
    memo: Optional[str]
    productId: Optional[str]
    amount: str  # Price per period, base units of the settlement token.
    settlement: CheckoutSettlement
    recipient: str  # Your payout address.
    interval: SubscriptionInterval
    intervalCount: int
    daysUntilDue: int
    currentPeriodStart: Optional[str]  # Start of the period last invoiced (``None`` before the first invoice).
    currentPeriodEnd: Optional[str]
    nextInvoiceAt: Optional[str]  # When the next invoice is issued (``None`` when paused or canceled).
    cancelAt: Optional[str]  # Scheduled cancel (the end of the current period).
    cancelAtPeriodEnd: bool
    canceledAt: Optional[str]
    cancellationReason: Optional[str]  # ``requested`` (you canceled) or ``unpaid`` (7 days past due).
    pausedAt: Optional[str]
    latestInvoiceId: Optional[str]  # The invoice of the current period.
    metadata: Optional[Dict[str, str]]
    createdAt: str
    updatedAt: str


class SubscriptionsPage(TypedDict):
    subscriptions: List[Subscription]
    nextCursor: Optional[str]


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


LimitOrderStatus = Literal["built", "open", "filled", "cancelled", "expired", "failed"]
"""``built`` (tx built, not submitted), ``open`` (live on chain, may be partly filled), ``filled``,
``cancelled`` (unfilled input returned), ``expired`` (reached ``expiresAt``), ``failed`` (the order tx
never landed)."""

LimitOrderOutcome = Literal["fill", "partial_fill", "expire"]


class LimitOrderFees(TypedDict):
    ourFeeBps: int  # LayerHop's fee written into the order (0 when ``dstToken`` carries no fee).
    integratorFeeBps: int
    integrator: Optional[str]  # The partner id, if a partner fee applies.


class LimitOrder(TypedDict):
    """A Solana limit order (Jupiter Trigger). Fills are orders whose ``quoteId`` starts with ``lof_``."""

    id: str
    object: Literal["limit_order"]
    livemode: bool
    status: LimitOrderStatus
    statusDetail: Optional[str]
    provider: ProviderId  # ``jupiter`` (live) or ``sandbox`` (test mode).
    chainId: int  # Always ``7565164`` (Solana) for now.
    wallet: str  # The maker wallet.
    srcToken: str  # Mint sold.
    dstToken: str  # Mint bought.
    amount: str  # Input, base units.
    dstAmount: str  # Minimum output for the whole order, base units.
    expiresAt: Optional[str]
    fees: LimitOrderFees
    providerOrderId: str
    filledAmount: str  # Input filled so far.
    filledDstAmount: str  # Output received so far.
    fillCount: int
    openTxHash: Optional[str]
    cancelTxHash: Optional[str]  # Set once a cancel tx was submitted; the status turns ``cancelled`` when confirmed.
    channel: FeeChannel
    metadata: Optional[Dict[str, str]]
    createdAt: str
    updatedAt: str


class CreatedLimitOrder(LimitOrder):
    """Response of ``limit_orders.create``: the order plus the unsigned ``tx`` (``submitViaApi``) for
    ``wallet`` to sign."""

    tx: SvmTx


class LimitOrderWithFills(LimitOrder):
    """Response of ``limit_orders.get``: the order plus its ``fills`` (orders), newest first."""

    fills: List[Order]


class LimitOrdersPage(TypedDict):
    limitOrders: List[LimitOrder]
    nextCursor: Optional[str]


class LimitOrderSubmitResponse(TypedDict):
    limitOrder: LimitOrder
    txHash: str  # The landed transaction's signature.


class LimitOrderCancelResponse(TypedDict):
    limitOrder: LimitOrder
    tx: Optional[SvmTx]  # The cancel tx to sign and submit, or ``None`` when a ``built`` order was cancelled at once.


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


class Eip712TypedData(TypedDict):
    """EIP-712 typed data exactly as the provider returned it. Sign it unchanged
    (``eth_account``'s ``sign_typed_data`` / ``eth_signTypedData_v4``)."""

    types: Dict[str, Any]
    domain: Dict[str, Any]
    message: Dict[str, Any]
    primaryType: str


class GaslessSignable(TypedDict):
    type: str  # Provider's kind, e.g. ``permit`` (approvals) or ``settler_metatransaction`` (trade).
    eip712: Eip712TypedData


class GaslessSignRequest(TypedDict):
    """What the wallet signs for a gasless quote: ``approval`` (when present) and ``trade``, on ``chainId``."""

    chainId: int
    approval: NotRequired[GaslessSignable]
    trade: GaslessSignable
    gasFee: NotRequired[GasFee]


class GaslessOrderStatus(TypedDict):
    """State of a submitted gasless order (``srcTxHash`` once the relayer's tx is mined)."""

    quoteId: str
    provider: ProviderId
    orderId: str
    state: OrderState
    srcTxHash: NotRequired[str]
    reason: NotRequired[str]  # Provider failure reason when ``failed``.


QuotePurpose = Literal["tip", "split", "payout", "gather", "rebalance", "fund"]


class RouteLeg(TypedDict):
    """One quotable leg, in the same terms as a quote request. Amounts are base units."""

    srcChain: int
    srcToken: str
    amount: str
    dstChain: int
    dstToken: str
    dstAmount: NotRequired[str]  # Estimated output (quote again before signing).


class RouteHub(TypedDict):
    chainId: int
    token: str
    symbol: str
    decimals: int


class RouteSuggestion(RouteLeg):
    """An alternative to a route that returned no quote (``NO_ROUTE``). ``dst_token``: another
    destination token. ``src_token``: another source token worth the same. ``via_hub``: two signed
    steps through ``hub`` (``steps[0]`` then ``steps[1]``); the top-level fields describe the whole trip."""

    kind: str  # ``dst_token`` | ``src_token`` | ``via_hub``
    message: str  # Short text for a button.
    symbol: NotRequired[str]
    hub: NotRequired[RouteHub]
    steps: NotRequired[List[RouteLeg]]


SplitStatus = Literal["open", "closed"]


class SplitShare(TypedDict):
    index: int  # ``split_share`` on quotes.
    label: str
    amount: str  # Base units of the split's token.
    received: str
    status: str  # ``unpaid`` | ``partial`` | ``paid``
    payments: int
    pending: int


class SplitToken(TypedDict):
    address: str
    symbol: str
    decimals: int


class Split(TypedDict):
    """A bill split: shares of ``total`` that anyone pays with a quote (``purpose="split"``)."""

    id: str
    url: str
    status: SplitStatus
    note: Optional[str]
    recipient: str
    recipientName: Optional[str]
    chainId: int
    chain: str
    token: SplitToken
    total: str  # Base units.
    collected: str
    paidCount: int
    shares: List[SplitShare]
    createdAt: str
    updatedAt: str


class SplitCreated(Split):
    editToken: str  # The edit secret, shown only once: keep it to update the split.
    editUrl: str


class SplitShareInput(TypedDict, total=False):
    label: str
    amount: str  # Base units (all shares or none; they must add up to ``total``).


class TipJarMessage(TypedDict):
    text: str
    at: str


class TipJar(TypedDict):
    address: str
    tippers: int
    tips: int
    messages: List[TipJarMessage]  # At most 10.


class PayoutRowInput(TypedDict):
    recipient: str  # Address, ENS name or .sol name.
    amount: Union[str, float]  # HUMAN units of ``token`` ("25", "0.5").
    token: str
    chain: Union[str, int]
    label: NotRequired[str]


class PayoutToken(TypedDict):
    chainId: int
    address: str
    symbol: str
    decimals: int
    usd: NotRequired[float]


class PayoutPlan(TypedDict):
    """``POST /v1/payouts/plan``: rows resolved and grouped into transfer batches and routed rows."""

    source: Dict[str, Any]  # ``{chainId, chain, sender, token}``
    rows: List[Dict[str, Any]]  # ``{index, line, input, ok, error?, recipient?, chainId?, chain?, token?, amount?, kind?}``
    transfers: List[Dict[str, Any]]  # ``{chainId, token, rows, total}``
    routes: List[Dict[str, Any]]  # ``{chainId, rows}``
    transferTotal: str
    totals: List[Dict[str, Any]]
    valid: int
    invalid: int
    warnings: List[str]


class PayoutTransfer(TypedDict):
    recipient: str  # An address (resolve names with the plan first).
    amount: str  # Base units.


class PayoutTransfers(TypedDict):
    """Unsigned transfers: EVM ``calls`` (one per transfer) or a Solana ``serializedTx``. Never signed by LayerHop."""

    vm: Literal["evm", "svm"]
    chainId: int
    token: PayoutToken
    calls: NotRequired[List[EvmCall]]
    serializedTx: NotRequired[str]


class RecurringOrderBuild(TypedDict):
    """``recurring_orders.create``: the unsigned ``tx`` for ``wallet`` to sign, and the ``requestId``."""

    object: Literal["recurring_order_build"]
    livemode: bool
    provider: str  # ``jupiter`` (live) or ``sandbox`` (test mode).
    chainId: int
    wallet: str
    srcToken: str
    dstToken: str
    amount: str
    amountPerOrder: str
    orders: int
    intervalSeconds: int
    fees: Dict[str, int]  # Always 0.
    requestId: str
    tx: SvmTx


class RecurringOrderFill(TypedDict):
    txHash: str
    amount: str
    dstAmount: str
    feeAmount: str
    feeToken: Optional[str]
    filledAt: Optional[str]


class RecurringOrder(TypedDict):
    """A Solana recurring order (Jupiter Recurring), read live from Jupiter. Base units throughout."""

    id: str
    object: Literal["recurring_order"]
    provider: str
    chainId: int
    status: str  # ``active`` | ``completed`` | ``cancelled``
    wallet: str
    srcToken: str
    dstToken: str
    amount: str
    amountPerOrder: str
    orders: int
    ordersFilled: int
    intervalSeconds: int
    spentAmount: str
    withdrawnAmount: str
    receivedAmount: str
    openTxHash: Optional[str]
    closeTxHash: Optional[str]
    createdAt: Optional[str]
    fills: List[RecurringOrderFill]


class RecurringOrderList(TypedDict):
    recurringOrders: List[RecurringOrder]
    page: int
    totalPages: int


class RecurringOrderSubmitResponse(TypedDict):
    txHash: str
    order: Optional[str]  # The order account (create).


class RecurringOrderCancelResponse(TypedDict):
    requestId: str
    tx: SvmTx


Json = Dict[str, Any]
