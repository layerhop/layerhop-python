import httpx
import pytest

from layerhop import AsyncLayerHop, LayerHop, LayerHopApiError

from .conftest import CHECKOUT_QUOTE_RESPONSE, CHECKOUT_SESSION, EVM_TX, QUOTE_RESPONSE, FakeApi

CS = CHECKOUT_SESSION["id"]


def make(api: FakeApi, **kw) -> LayerHop:
    return LayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def amake(api: FakeApi, **kw) -> AsyncLayerHop:
    return AsyncLayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def test_create_sends_body_and_parses_session(api):
    api.on("POST", "/v1/checkout/sessions", CHECKOUT_SESSION, status=201)
    lh = make(api, api_key="lh_live_x")
    s = lh.checkout.create("49000000", "base", "USDC", "0x2222222222222222222222222222222222222222",
                           description="Pro plan, 1 month", reference="order_1042", metadata={"plan": "pro"},
                           success_url="https://shop.example.com/thanks", expires_in_minutes=30)
    assert api.last.method == "POST" and api.last.headers["x-api-key"] == "lh_live_x"
    assert api.last_json() == {
        "amount": "49000000", "settleChain": "base", "settleToken": "USDC",
        "recipient": "0x2222222222222222222222222222222222222222", "description": "Pro plan, 1 month",
        "reference": "order_1042", "metadata": {"plan": "pro"}, "successUrl": "https://shop.example.com/thanks",
        "expiresInMinutes": 30,
    }
    assert s["object"] == "checkout.session" and s["status"] == "processing" and s["livemode"] is True
    assert s["url"].endswith(CS) and s["settlement"]["decimals"] == 6 and s["cancelUrl"] is None
    assert s["payment"] is not None and s["payment"]["srcChainId"] == 42161 and s["payment"]["paidAt"] is None
    assert s["metadata"] == {"plan": "pro"}


def test_create_minimal_and_numeric_chain(api):
    api.on("POST", "/v1/checkout/sessions", CHECKOUT_SESSION, status=201)
    make(api).checkout.create("1000000", 8453, "USDC", "0x22")
    assert api.last_json() == {"amount": "1000000", "settleChain": "8453", "settleToken": "USDC", "recipient": "0x22"}


def test_create_rejects_non_string_amount(api):
    with pytest.raises(TypeError):
        make(api).checkout.create(49000000, "base", "USDC", "0x22")  # type: ignore[arg-type]


def test_get_expire_encode_id(api):
    api.on("GET", f"/v1/checkout/sessions/{CS}", {**CHECKOUT_SESSION, "reference": None, "metadata": None})
    api.on("POST", "/v1/checkout/sessions/cs%2Fx/expire", {**CHECKOUT_SESSION, "status": "expired", "payment": None})
    lh = make(api)
    s = lh.checkout.get(CS)
    assert api.last.method == "GET" and s["reference"] is None
    e = lh.checkout.expire("cs/x")
    assert api.last.method == "POST" and api.last_json() == {}
    assert e["status"] == "expired" and e["payment"] is None


def test_list_query(api):
    api.on("GET", "/v1/checkout/sessions", {"sessions": [CHECKOUT_SESSION], "nextCursor": "c2"})
    lh = make(api, api_key="lh_test_x")
    page = lh.checkout.list(status="paid", cursor="c1", limit=10)
    assert dict(api.last.url.params) == {"status": "paid", "cursor": "c1", "limit": "10"}
    assert page["nextCursor"] == "c2" and page["sessions"][0]["id"] == CS
    lh.checkout.list()
    assert dict(api.last.url.params) == {}


def test_quote_body_and_parse(api):
    api.on("POST", f"/v1/checkout/sessions/{CS}/quote", CHECKOUT_QUOTE_RESPONSE)
    lh = make(api)
    r = lh.checkout.quote(CS, "arbitrum", "ETH", sender="0x11")
    assert api.last_json() == {"srcChain": "arbitrum", "srcToken": "ETH", "sender": "0x11"}
    assert "x-api-key" not in api.last.headers
    assert r["sessionId"] == CS and r["livemode"] is False and r["amountDue"] == "49000000"
    assert r["best"]["srcAmount"] == "15623001000000000" and r["best"]["dstAmountMin"] == "49000000"
    assert r["errors"][0]["code"] == "PROVIDER_TIMEOUT"
    lh.checkout.quote(CS, 42161, "ETH", sender="0x11", slippage_bps=100)
    assert api.last_json() == {"srcChain": "42161", "srcToken": "ETH", "sender": "0x11", "slippageBps": 100}


def test_checkout_error(api):
    api.on("POST", f"/v1/checkout/sessions/{CS}/expire",
           {"error": {"code": "CONFLICT", "message": "Session is paid", "requestId": "r1"}}, status=409)
    with pytest.raises(LayerHopApiError) as ei:
        make(api).checkout.expire(CS)
    assert (ei.value.code, ei.value.status) == ("CONFLICT", 409)


def test_test_mode_fields(api):
    api.on("GET", "/v1/quote", {**QUOTE_RESPONSE, "livemode": False, "best": {**QUOTE_RESPONSE["best"], "provider": "sandbox"}})
    api.on("POST", "/v1/orders", {"tx": {**EVM_TX, "sandbox": True}})
    api.on("GET", "/v1/orders", {"orders": [{"quoteId": "q_1", "livemode": False, "checkoutSessionId": CS}], "nextCursor": None})
    lh = make(api, api_key="lh_test_x")
    q = lh.quote("base", "USDC", "100004001", "solana", "SOL", sender="a", recipient="b")
    assert q["livemode"] is False and q["best"]["provider"] == "sandbox"
    assert lh.build_tx("q_1")["sandbox"] is True
    o = lh.list_orders(address="a")["orders"][0]
    assert o["livemode"] is False and o["checkoutSessionId"] == CS


@pytest.mark.anyio
async def test_async_checkout(api):
    api.on("POST", "/v1/checkout/sessions", CHECKOUT_SESSION, status=201)
    api.on("GET", f"/v1/checkout/sessions/{CS}", CHECKOUT_SESSION)
    api.on("GET", "/v1/checkout/sessions", {"sessions": [], "nextCursor": None})
    api.on("POST", f"/v1/checkout/sessions/{CS}/expire", {**CHECKOUT_SESSION, "status": "expired"})
    api.on("POST", f"/v1/checkout/sessions/{CS}/quote", CHECKOUT_QUOTE_RESPONSE)
    async with amake(api, api_key="k") as lh:
        s = await lh.checkout.create("49000000", "base", "USDC", "0x22", merchant_name="Acme", cancel_url="https://x/c")
        assert api.last_json()["merchantName"] == "Acme" and api.last_json()["cancelUrl"] == "https://x/c"
        assert s["id"] == CS
        assert (await lh.checkout.get(CS))["amount"] == "49000000"
        page = await lh.checkout.list(status="open", limit=5)
        assert page["sessions"] == [] and dict(api.last.url.params) == {"status": "open", "limit": "5"}
        assert (await lh.checkout.expire(CS))["status"] == "expired"
        r = await lh.checkout.quote(CS, "solana", "SOL", sender="9W", slippage_bps=75)
        assert api.last_json() == {"srcChain": "solana", "srcToken": "SOL", "sender": "9W", "slippageBps": 75}
        assert r["best"]["srcAmount"] == "15623001000000000"
