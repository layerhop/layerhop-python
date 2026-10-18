import httpx
import pytest

from layerhop import AsyncLayerHop, LayerHop, LayerHopApiError

from .conftest import CHECKOUT_SESSION, REFUND, STATUS, FakeApi

SID = CHECKOUT_SESSION["id"]
CREATED = {
    "refund": REFUND,
    "quote": {"quoteId": "q_r1", "provider": "relay", "srcAmount": "10000000", "dstAmount": "3123000000000000",
              "dstAmountMin": "3091000000000000", "estimatedSeconds": 12, "expiresAt": 1760790030,
              "from": "0x2222222222222222222222222222222222222222"},
    "next": "Build the transaction with POST /v1/orders { quoteId }, sign it from the `from` wallet, then report it.",
}


def make(api: FakeApi, **kw) -> LayerHop:
    return LayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def amake(api: FakeApi, **kw) -> AsyncLayerHop:
    return AsyncLayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def test_create_sends_options_and_parses(api):
    api.on("POST", f"/v1/checkout/sessions/{SID}/refunds", CREATED, status=201)
    lh = make(api, api_key="lh_live_x")
    r = lh.checkout.refunds.create(SID, amount="10000000", reason="Partial refund",
                                   from_="0x2222222222222222222222222222222222222222", to="settlement")
    assert api.last.method == "POST" and api.last.headers["x-api-key"] == "lh_live_x"
    assert api.last_json() == {"amount": "10000000", "reason": "Partial refund",
                               "from": "0x2222222222222222222222222222222222222222", "to": "settlement"}
    assert r["refund"]["status"] == "pending" and r["refund"]["to"]["chainId"] == 42161
    assert r["quote"]["quoteId"] == r["refund"]["quoteId"] and r["quote"]["from"].startswith("0x22")
    lh.checkout.refunds.create(SID)
    assert api.last_json() == {}


def test_create_rejects_non_string_amount(api):
    with pytest.raises(TypeError):
        make(api).checkout.refunds.create(SID, amount=10)  # type: ignore[arg-type]


def test_refund_flow_build_and_report(api):
    api.on("POST", f"/v1/checkout/sessions/{SID}/refunds", CREATED, status=201)
    api.on("POST", "/v1/orders", {"quoteId": "q_r1", "provider": "relay", "tx": {"vm": "evm", "chainId": 8453, "to": "0xabc",
                                                                                "data": "0x", "value": "0"}})
    api.on("POST", "/v1/orders/q_r1/submitted", {"quoteId": "q_r1", "status": "submitted"})
    lh = make(api, api_key="k")
    q = lh.checkout.refunds.create(SID)["quote"]
    assert lh.build_tx(q["quoteId"])["chainId"] == 8453
    assert lh.report_submitted(q["quoteId"], "0xabc")["status"] == "submitted"


def test_list_unwraps_and_errors(api):
    api.on("GET", f"/v1/checkout/sessions/{SID}/refunds", {"refunds": [{**REFUND, "status": "completed", "txHash": "0xdef"}]})
    api.on("POST", "/v1/checkout/sessions/cs_open/refunds",
           {"error": {"code": "CONFLICT", "message": "Only paid sessions can be refunded; this one is open"}}, status=409)
    lh = make(api, api_key="k")
    rs = lh.checkout.refunds.list(SID)
    assert len(rs) == 1 and rs[0]["status"] == "completed" and rs[0]["txHash"] == "0xdef"
    with pytest.raises(LayerHopApiError) as ei:
        lh.checkout.refunds.create("cs_open")
    assert (ei.value.code, ei.value.status) == ("CONFLICT", 409)


def test_platform_status_and_order_status(api):
    api.on("GET", "/v1/status", STATUS)
    api.on("GET", "/v1/orders/mock/1", {"provider": "mock", "id": "1", "state": "filled"})
    lh = make(api)
    s = lh.status()
    assert api.last.url.raw_path.decode() == "/v1/status" and "x-api-key" not in api.last.headers
    assert s["status"] == "degraded" and s["components"][0]["uptime90d"] == 99.98
    assert s["components"][1]["uptime90d"] is None and s["incidents"][0]["resolvedAt"] is None
    assert lh.status("mock", "1")["state"] == "filled"
    with pytest.raises(TypeError):
        lh.status("mock")  # type: ignore[call-overload]


def test_refunded_session_and_order_fields(api):
    api.on("GET", f"/v1/checkout/sessions/{SID}", {**CHECKOUT_SESSION, "status": "paid", "refundedAmount": "10000000"})
    api.on("GET", "/v1/orders", {"orders": [{"quoteId": "q_r1", "status": "filled", "refundId": REFUND["id"]}], "nextCursor": None})
    lh = make(api, api_key="k")
    assert lh.checkout.get(SID)["refundedAmount"] == "10000000"
    assert lh.list_orders(address="0x22")["orders"][0]["refundId"] == REFUND["id"]


@pytest.mark.anyio
async def test_async_refunds_and_status(api):
    api.on("POST", f"/v1/checkout/sessions/{SID}/refunds", CREATED, status=201)
    api.on("GET", f"/v1/checkout/sessions/{SID}/refunds", {"refunds": [REFUND]})
    api.on("GET", "/v1/status", STATUS)
    async with amake(api, api_key="k") as lh:
        r = await lh.checkout.refunds.create(SID, amount="10000000", to="original")
        assert api.last_json() == {"amount": "10000000", "to": "original"} and r["refund"]["id"] == REFUND["id"]
        assert (await lh.checkout.refunds.list(SID))[0]["amount"] == "10000000"
        assert (await lh.status())["url"] == "https://layerhop.com/status"
