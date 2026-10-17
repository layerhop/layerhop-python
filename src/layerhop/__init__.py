"""LayerHop Python SDK -- best-price cross-chain and same-chain swaps.

The SDK never holds private keys: it returns unsigned transactions for your own wallet to sign.
"""

from .client import DEFAULT_BASE_URL, AsyncLayerHop, LayerHop, __version__
from .errors import LayerHopApiError, WebhookSignatureError
from .types import (
    FINAL_STATES,
    Approval,
    BuiltTx,
    Chain,
    EvmTx,
    FeeBreakdown,
    FeeChannel,
    Order,
    OrdersPage,
    OrderState,
    OrderStatus,
    ProviderError,
    ProviderId,
    Quote,
    QuoteResponse,
    ReportSubmittedResponse,
    SimulateError,
    SimulateResponse,
    SvmTx,
    Token,
)
from .webhooks import (
    SIGNATURE_HEADER,
    compute_webhook_signature,
    construct_webhook_event,
    verify_webhook_signature,
)

SOLANA_CHAIN_ID = 7565164
EVM_NATIVE = "0x0000000000000000000000000000000000000000"
SOL_NATIVE = "So11111111111111111111111111111111111111112"

__all__ = [
    "LayerHop", "AsyncLayerHop", "LayerHopApiError", "WebhookSignatureError", "DEFAULT_BASE_URL", "__version__",
    "verify_webhook_signature", "construct_webhook_event", "compute_webhook_signature", "SIGNATURE_HEADER",
    "SOLANA_CHAIN_ID", "EVM_NATIVE", "SOL_NATIVE", "FINAL_STATES",
    "Approval", "BuiltTx", "Chain", "EvmTx", "FeeBreakdown", "FeeChannel", "Order", "OrdersPage", "OrderState",
    "OrderStatus", "ProviderError", "ProviderId", "Quote", "QuoteResponse", "ReportSubmittedResponse",
    "SimulateError", "SimulateResponse", "SvmTx", "Token",
]
