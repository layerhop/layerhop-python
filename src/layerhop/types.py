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
"""``jupiter`` | ``relay`` | ``debridge`` | ``mayan`` | ``zerox`` | ``kyberswap`` | ``odos`` | ``lifi`` | ``mock``"""

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


class SvmTx(TypedDict):
    vm: Literal["svm"]
    serializedTx: str
    submitViaApi: NotRequired[bool]


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
    createdAt: str
    updatedAt: str


class OrdersPage(TypedDict):
    orders: List[Order]
    nextCursor: NotRequired[Optional[str]]


Json = Dict[str, Any]
