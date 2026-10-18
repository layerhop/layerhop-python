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
