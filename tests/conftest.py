import json
from typing import Any, Callable, Dict, List, Tuple

import httpx
import pytest

Route = Tuple[str, str]  # (method, path)


class FakeApi:
    """A tiny router over httpx.MockTransport that records every request."""

    def __init__(self) -> None:
        self.routes: Dict[Route, Callable[[httpx.Request], httpx.Response]] = {}
        self.requests: List[httpx.Request] = []

    def on(self, method: str, path: str, body: Any = None, status: int = 200, handler: Any = None) -> None:
        if handler is None:
            def handler(_req: httpx.Request, _b: Any = body, _s: int = status) -> httpx.Response:
                return httpx.Response(_s, json=_b)
        self.routes[(method, path)] = handler

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        h = self.routes.get((req.method, req.url.raw_path.decode().split("?")[0]))
        if h is None:
            return httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "no route", "requestId": "r0"}})
        return h(req)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def last_json(self) -> Any:
        return json.loads(self.last.content)


@pytest.fixture
def api() -> FakeApi:
    return FakeApi()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


QUOTE = {
    "quoteId": "q_1", "provider": "relay", "dstAmount": "612345678", "dstAmountMin": "609283949",
    "estimatedSeconds": 8, "fees": {"ourFeeBps": 20}, "expiresAt": 1760000030,
}
QUOTE_RESPONSE = {"best": QUOTE, "quotes": [QUOTE], "errors": []}
EVM_TX = {"vm": "evm", "chainId": 8453, "to": "0xabc", "data": "0x12", "value": "0",
          "approval": {"token": "0xusdc", "spender": "0xabc", "amount": "100000000"}}
CHECKOUT_SESSION = {
    "id": "cs_01k7t9m2c4x8q6r0v3b5n7p9d", "object": "checkout.session", "livemode": True, "status": "processing",
    "statusDetail": None, "amount": "49000000",
    "settlement": {"chainId": 8453, "token": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "symbol": "USDC", "decimals": 6},
    "recipient": "0x2222222222222222222222222222222222222222", "merchantName": "Acme", "description": "Pro plan, 1 month",
    "url": "https://layerhop.com/pay/cs_01k7t9m2c4x8q6r0v3b5n7p9d", "successUrl": "https://shop.example.com/thanks",
    "cancelUrl": None, "expiresAt": "2026-10-18T11:00:00.000Z",
    "payment": {"quoteId": "q_9", "payer": "0x1111111111111111111111111111111111111111", "srcChainId": 42161,
                "srcToken": "0x0000000000000000000000000000000000000000", "srcAmount": "15623001000000000",
                "srcTxHash": "0xabc", "dstTxHash": None, "paidAt": None},
    "reference": "order_1042", "metadata": {"plan": "pro"},
    "createdAt": "2026-10-18T10:00:00.000Z", "updatedAt": "2026-10-18T10:02:00.000Z",
}
CHECKOUT_QUOTE = {**QUOTE, "provider": "relay", "srcAmount": "15623001000000000", "dstAmountMin": "49000000"}
CHECKOUT_QUOTE_RESPONSE = {
    "sessionId": CHECKOUT_SESSION["id"], "livemode": False, "amountDue": "49000000",
    "best": CHECKOUT_QUOTE, "quotes": [CHECKOUT_QUOTE],
    "errors": [{"provider": "lifi", "code": "PROVIDER_TIMEOUT", "message": "Timed out"}],
}
CHECKOUT_PRODUCT = {
    "id": "prod_01m57hq2c4x8q6r0v3b5n7p9d", "object": "checkout.product", "livemode": True, "active": True,
    "name": "Pro plan", "description": "1 month", "merchantName": None, "amount": "49000000",
    "settlement": {"chainId": 8453, "token": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "symbol": "USDC", "decimals": 6},
    "url": "https://layerhop.com/buy/prod_01m57hq2c4x8q6r0v3b5n7p9d",
    "recipient": "0x2222222222222222222222222222222222222222", "successUrl": "https://shop.example.com/thanks",
    "cancelUrl": None, "expiresInMinutes": 60, "allowedOrigins": ["https://shop.example.com"],
    "createdAt": "2026-10-18T10:00:00.000Z", "updatedAt": "2026-10-18T10:00:00.000Z",
}
INVOICE = {
    "id": "inv_01m5c2q2c4x8q6r0v3b5n7p9d", "object": "invoice", "livemode": True, "number": "INV-0001", "status": "open",
    "merchantName": "Acme", "customerName": "Client Co", "memo": None,
    "lineItems": [{"description": "Design work", "quantity": 2, "unitAmount": "500000000"}], "amount": "1000000000",
    "settlement": {"chainId": 8453, "token": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "symbol": "USDC", "decimals": 6},
    "dueAt": "2026-11-01T23:59:59.000Z", "paidAt": None,
    "url": "https://layerhop.com/invoice/inv_01m5c2q2c4x8q6r0v3b5n7p9d", "receiptUrl": None,
    "createdAt": "2026-10-18T10:00:00.000Z",
    "customerEmail": "ap@client.example", "recipient": "0x2222222222222222222222222222222222222222", "sessionId": None,
    "sentAt": "2026-10-18T10:00:00.000Z", "receiptSentAt": None, "voidedAt": None, "updatedAt": "2026-10-18T10:00:00.000Z",
}
REFUND = {
    "id": "re_01m5d7a2c4x8q6r0v3b5n7p9d", "object": "refund", "sessionId": CHECKOUT_SESSION["id"], "livemode": True,
    "status": "pending", "statusDetail": None, "amount": "10000000", "reason": "Partial refund", "quoteId": "q_r1",
    "to": {"chainId": 42161, "token": "0x0000000000000000000000000000000000000000",
           "address": "0x1111111111111111111111111111111111111111"},
    "txHash": None, "createdAt": "2026-10-18T12:00:00.000Z", "updatedAt": "2026-10-18T12:00:00.000Z",
}
STATUS = {
    "status": "degraded", "updatedAt": "2026-10-18T12:00:00.000Z",
    "components": [{"id": "api", "name": "API", "group": "Core", "status": "operational", "latencyMs": 41,
                    "uptime90d": 99.98, "days": [{"date": "2026-10-18", "uptime": 100}]},
                   {"id": "provider:relay", "name": "Relay", "group": "Liquidity providers", "status": "degraded",
                    "latencyMs": None, "uptime90d": None, "days": [{"date": "2026-10-18", "uptime": None}]}],
    "incidents": [{"id": "inc_1", "componentId": "provider:relay", "component": "Relay", "title": "Relay quotes failing",
                   "startedAt": "2026-10-18T11:50:00.000Z", "resolvedAt": None}],
    "url": "https://layerhop.com/status",
}
DEPOSIT_ADDRESS = {
    "id": "da_01m5f3k2c4x8q6r0v3b5n7p9d", "object": "deposit_address", "livemode": False, "status": "active",
    "provider": "sandbox", "address": "0x4c3f1a0b9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a", "chainId": 8453,
    "token": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "dstChainId": 42161,
    "dstToken": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "recipient": "0x2222222222222222222222222222222222222222",
    "refundTo": "0x1111111111111111111111111111111111111111", "reusable": True, "amount": None,
    "fees": {"ourFeeBps": 20, "integratorFeeBps": 0, "integrator": None}, "label": "user_42",
    "metadata": {"userId": "42"}, "depositCount": 0, "lastDepositAt": None, "createdAt": "2026-10-19T10:00:00.000Z",
}
DEPOSIT_ORDER = {
    "quoteId": "dep_5f0c1e2d3a4b5c6d7e8f9a0b1c2d3e4f", "provider": "sandbox", "status": "submitted", "statusDetail": None,
    "channel": "api", "ourFeeBps": 20, "partnerFeeBps": 0, "sender": "0x1111111111111111111111111111111111111111",
    "recipient": "0x2222222222222222222222222222222222222222", "srcChainId": 8453,
    "srcToken": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "dstChainId": 42161,
    "dstToken": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "amount": "25000000", "dstAmount": "24930000",
    "srcTxHash": "0xabc", "dstTxHash": None, "livemode": False, "checkoutSessionId": None, "refundId": None,
    "depositAddressId": "da_01m5f3k2c4x8q6r0v3b5n7p9d", "keyId": "key_1", "partnerId": None, "partnerFeeEstimate": "0",
    "createdAt": "2026-10-19T10:05:00.000Z", "updatedAt": "2026-10-19T10:05:00.000Z",
}
SUBSCRIPTION = {
    "id": "sub_01k7v0c2c4x8q6r0v3b5n7p9d", "object": "subscription", "livemode": False, "status": "active",
    "customerEmail": "ada@example.com", "customerName": "Ada Lovelace", "merchantName": "Studio Nine",
    "description": "Pro plan", "memo": None, "productId": None, "amount": "49000000",
    "settlement": {"chainId": 8453, "token": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "symbol": "USDC", "decimals": 6},
    "recipient": "0x2222222222222222222222222222222222222222", "interval": "month", "intervalCount": 1,
    "daysUntilDue": 3, "currentPeriodStart": "2026-10-18T10:00:00.000Z", "currentPeriodEnd": "2026-11-18T10:00:00.000Z",
    "nextInvoiceAt": "2026-11-18T10:00:00.000Z", "cancelAt": None, "cancelAtPeriodEnd": False, "canceledAt": None,
    "cancellationReason": None, "pausedAt": None, "latestInvoiceId": "inv_01m5c2q2c4x8q6r0v3b5n7p9d",
    "metadata": {"plan": "pro"}, "createdAt": "2026-10-18T10:00:00.000Z", "updatedAt": "2026-10-18T10:00:00.000Z",
}
LIMIT_ORDER = {
    "id": "lo_01m5h8r2c4x8q6r0v3b5n7p9d", "object": "limit_order", "livemode": False, "status": "built",
    "statusDetail": None, "provider": "sandbox", "chainId": 7565164,
    "wallet": "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
    "srcToken": "So11111111111111111111111111111111111111112",
    "dstToken": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "amount": "1000000000", "dstAmount": "200000000",
    "expiresAt": None, "fees": {"ourFeeBps": 20, "integratorFeeBps": 0, "integrator": None},
    "providerOrderId": "3kVb1sZ8d6qW2nE4rT7yU9iO0pA5sD3fG6hJ8kL1zX2c", "filledAmount": "0", "filledDstAmount": "0",
    "fillCount": 0, "openTxHash": None, "cancelTxHash": None, "channel": "api", "metadata": {"userId": "42"},
    "createdAt": "2026-10-19T10:00:00.000Z", "updatedAt": "2026-10-19T10:00:00.000Z",
}
LIMIT_ORDER_FILL = {
    **DEPOSIT_ORDER, "quoteId": "lof_7a1c2e3d4b5a6c7d8e9f0a1b2c3d4e5f", "srcChainId": 7565164, "dstChainId": 7565164,
    "srcToken": LIMIT_ORDER["srcToken"], "dstToken": LIMIT_ORDER["dstToken"], "amount": "1000000000",
    "dstAmount": "200000000", "status": "filled", "depositAddressId": None, "limitOrderId": LIMIT_ORDER["id"],
}
SVM_TX = {"vm": "svm", "serializedTx": "AQAAAA==", "submitViaApi": True, "sandbox": True}
