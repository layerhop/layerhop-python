import httpx
import pytest

from layerhop import AsyncLayerHop, LayerHop, LayerHopApiError

from .conftest import LIMIT_ORDER, LIMIT_ORDER_FILL, SVM_TX, FakeApi

LID = LIMIT_ORDER["id"]
WALLET = LIMIT_ORDER["wallet"]


def make(api: FakeApi, **kw) -> LayerHop:
    return LayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def amake(api: FakeApi, **kw) -> AsyncLayerHop:
    return AsyncLayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def test_create_sends_body_and_parses_tx(api):
    api.on("POST", "/v1/limit-orders", {**LIMIT_ORDER, "tx": SVM_TX}, status=201)
    lh = make(api, api_key="lh_test_x")
    lo = lh.limit_orders.create(WALLET, "SOL", "USDC", "1000000000", "200000000", expires_at=1761000000,
                                chain=7565164, metadata={"userId": "42"}, integrator="acme", integrator_fee_bps=10)
    assert api.last.method == "POST" and api.last.headers["x-api-key"] == "lh_test_x"
    assert api.last_json() == {
        "channel": "api", "wallet": WALLET, "srcToken": "SOL", "dstToken": "USDC", "amount": "1000000000",
        "dstAmount": "200000000", "expiresAt": 1761000000, "chain": "7565164", "metadata": {"userId": "42"},
        "integrator": "acme", "integratorFeeBps": 10,
    }
    assert lo["object"] == "limit_order" and lo["status"] == "built" and lo["provider"] == "sandbox"
    assert lo["chainId"] == 7565164 and lo["fees"] == {"ourFeeBps": 20, "integratorFeeBps": 0, "integrator": None}
    assert lo["tx"]["vm"] == "svm" and lo["tx"]["submitViaApi"] is True


def test_create_minimal_and_client_defaults(api):
    api.on("POST", "/v1/limit-orders", {**LIMIT_ORDER, "tx": SVM_TX}, status=201)
    make(api).limit_orders.create(WALLET, "SOL", "USDC", "1000000000", "200000000")
    assert api.last_json() == {"channel": "api", "wallet": WALLET, "srcToken": "SOL", "dstToken": "USDC",
                               "amount": "1000000000", "dstAmount": "200000000"}
    assert "x-api-key" not in api.last.headers
    make(api, channel="widget", integrator="acme", integrator_fee_bps=5).limit_orders.create(
        WALLET, "SOL", "USDC", "1000000000", "200000000", chain="solana")
    body = api.last_json()
    assert body["channel"] == "widget" and body["integrator"] == "acme" and body["integratorFeeBps"] == 5
    assert body["chain"] == "solana"


def test_create_rejects_non_string_amounts(api):
    with pytest.raises(TypeError):
        make(api).limit_orders.create(WALLET, "SOL", "USDC", 1000000000, "200000000")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        make(api).limit_orders.create(WALLET, "SOL", "USDC", "1000000000", 200000000)  # type: ignore[arg-type]
    assert api.requests == []


def test_live_mode_disabled_is_forbidden(api):
    api.on("POST", "/v1/limit-orders", {"error": {
        "code": "FORBIDDEN", "message": "Limit orders are not enabled for live mode yet.", "requestId": "r1"}}, status=403)
    with pytest.raises(LayerHopApiError) as ei:
        make(api, api_key="lh_live_x").limit_orders.create(WALLET, "SOL", "USDC", "1000000000", "200000000")
    assert (ei.value.code, ei.value.status, ei.value.request_id) == ("FORBIDDEN", 403, "r1")


def test_submit(api):
    api.on("POST", f"/v1/limit-orders/{LID}/submit", {"limitOrder": {**LIMIT_ORDER, "status": "open"}, "txHash": "5sig"})
    r = make(api).limit_orders.submit(LID, "AQAB")
    assert api.last_json() == {"signedTransaction": "AQAB"}
    assert r["txHash"] == "5sig" and r["limitOrder"]["status"] == "open"


def test_get_list_and_encoding(api):
    api.on("GET", f"/v1/limit-orders/{LID}", {**LIMIT_ORDER, "status": "filled", "fillCount": 1, "fills": [LIMIT_ORDER_FILL]})
    api.on("GET", "/v1/limit-orders/lo%2Fx", {**LIMIT_ORDER, "fills": []})
    api.on("GET", "/v1/limit-orders", {"limitOrders": [LIMIT_ORDER], "nextCursor": "c2"})
    lh = make(api, api_key="k")
    lo = lh.limit_orders.get(LID)
    assert lo["fillCount"] == 1 and lo["fills"][0]["limitOrderId"] == LID
    assert lo["fills"][0]["quoteId"].startswith("lof_")
    lh.limit_orders.get("lo/x")
    assert api.last.url.raw_path.decode() == "/v1/limit-orders/lo%2Fx"
    page = lh.limit_orders.list(wallet=WALLET, status="open", cursor="c1", limit=10)
    assert dict(api.last.url.params) == {"wallet": WALLET, "status": "open", "cursor": "c1", "limit": "10"}
    assert page["nextCursor"] == "c2" and page["limitOrders"][0]["id"] == LID
    lh.limit_orders.list()
    assert dict(api.last.url.params) == {}


def test_cancel_open_and_built(api):
    api.on("POST", f"/v1/limit-orders/{LID}/cancel", {"limitOrder": {**LIMIT_ORDER, "status": "open"}, "tx": SVM_TX})
    lh = make(api)
    r = lh.limit_orders.cancel(LID)
    assert api.last.method == "POST" and api.last_json() == {}
    assert r["tx"] is not None and r["tx"]["serializedTx"] == "AQAAAA=="
    api.on("POST", f"/v1/limit-orders/{LID}/cancel", {"limitOrder": {**LIMIT_ORDER, "status": "cancelled"}, "tx": None})
    r = lh.limit_orders.cancel(LID)
    assert r["tx"] is None and r["limitOrder"]["status"] == "cancelled"


def test_simulate(api):
    api.on("POST", f"/v1/limit-orders/{LID}/simulate", {**LIMIT_ORDER, "status": "open"}, status=202)
    lo = make(api, api_key="lh_test_k").limit_orders.simulate(LID, "partial_fill")
    assert api.last_json() == {"outcome": "partial_fill"} and lo["id"] == LID


def test_conflict_error(api):
    api.on("POST", f"/v1/limit-orders/{LID}/submit",
           {"error": {"code": "CONFLICT", "message": "This order was already submitted", "requestId": "r2"}}, status=409)
    with pytest.raises(LayerHopApiError) as ei:
        make(api).limit_orders.submit(LID, "AQAB")
    assert (ei.value.code, ei.value.status) == ("CONFLICT", 409)


def test_order_limit_order_id_parsed(api):
    api.on("GET", "/v1/orders", {"orders": [LIMIT_ORDER_FILL], "nextCursor": None})
    page = make(api).list_orders(address=WALLET)
    assert page["orders"][0]["limitOrderId"] == LID


def test_trigger_limit_order_event(api):
    payload = {"id": "evt_2", "type": "limit_order.filled", "livemode": False, "sample": True,
               "createdAt": "2026-10-19T10:00:00.000Z", "data": {"limitOrder": LIMIT_ORDER, "fill": LIMIT_ORDER_FILL}}
    api.on("POST", "/v1/webhooks/trigger", {"eventId": "evt_2", "deliveries": 0, "payload": payload}, status=201)
    r = make(api, api_key="lh_test_k").webhooks.trigger("limit_order.filled")
    assert api.last_json() == {"type": "limit_order.filled"}
    assert r["payload"]["data"]["limitOrder"]["id"] == LID
    assert r["payload"]["data"]["fill"]["limitOrderId"] == LID


@pytest.mark.anyio
async def test_async_limit_orders(api):
    api.on("POST", "/v1/limit-orders", {**LIMIT_ORDER, "tx": SVM_TX}, status=201)
    api.on("POST", f"/v1/limit-orders/{LID}/submit", {"limitOrder": LIMIT_ORDER, "txHash": "5sig"})
    api.on("GET", f"/v1/limit-orders/{LID}", {**LIMIT_ORDER, "fills": []})
    api.on("GET", "/v1/limit-orders", {"limitOrders": [], "nextCursor": None})
    api.on("POST", f"/v1/limit-orders/{LID}/cancel", {"limitOrder": LIMIT_ORDER, "tx": None})
    api.on("POST", f"/v1/limit-orders/{LID}/simulate", LIMIT_ORDER, status=202)
    async with amake(api, api_key="k") as lh:
        lo = await lh.limit_orders.create(WALLET, "SOL", "USDC", "1000000000", "200000000", expires_at=1761000000)
        assert api.last_json()["expiresAt"] == 1761000000 and lo["tx"]["vm"] == "svm"
        assert (await lh.limit_orders.submit(LID, "AQAB"))["txHash"] == "5sig"
        assert (await lh.limit_orders.get(LID))["fills"] == []
        page = await lh.limit_orders.list(status="filled")
        assert page["limitOrders"] == [] and dict(api.last.url.params) == {"status": "filled"}
        assert (await lh.limit_orders.cancel(LID))["tx"] is None
        assert (await lh.limit_orders.simulate(LID, "expire"))["id"] == LID
        assert api.last_json() == {"outcome": "expire"}
