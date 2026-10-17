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
