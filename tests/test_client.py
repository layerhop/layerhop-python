import httpx
import pytest

from layerhop import AsyncLayerHop, LayerHop, LayerHopApiError
from layerhop import client as client_mod

from .conftest import EVM_TX, QUOTE_RESPONSE, FakeApi


def make(api: FakeApi, **kw) -> LayerHop:
    return LayerHop(base_url="http://test/", transport=httpx.MockTransport(api), **kw)


def amake(api: FakeApi, **kw) -> AsyncLayerHop:
    return AsyncLayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def test_default_base_url():
    assert LayerHop().base_url == "https://api.layerhop.com"


def test_health_chains_tokens(api):
    api.on("GET", "/v1/health", {"ok": True, "providers": ["relay"]})
    api.on("GET", "/v1/chains", {"chains": [{"id": 8453, "slug": "base"}]})
    api.on("GET", "/v1/tokens", {"tokens": [{"chainId": 8453, "symbol": "USDC"}]})
    lh = make(api)
    assert lh.health()["ok"] is True
    assert lh.chains()[0]["slug"] == "base"
    assert lh.tokens("base")[0]["symbol"] == "USDC"
    assert api.last.url.params["chain"] == "base"


def test_quote_query_and_api_key(api):
    api.on("GET", "/v1/quote", QUOTE_RESPONSE)
    lh = make(api, api_key="lh_live_x", integrator="myapp", integrator_fee_bps=25)
    r = lh.quote("base", "USDC", "100000000", "solana", "SOL", sender="0xs", recipient="9W")
    assert r["best"]["quoteId"] == "q_1"
    p = api.last.url.params
    assert dict(p) == {
        "srcChain": "base", "srcToken": "USDC", "amount": "100000000", "dstChain": "solana", "dstToken": "SOL",
        "sender": "0xs", "recipient": "9W", "slippageBps": "50", "channel": "api",
        "integrator": "myapp", "integratorFeeBps": "25",
    }
    assert api.last.headers["x-api-key"] == "lh_live_x"


def test_quote_rejects_non_string_amount(api):
    with pytest.raises(TypeError):
        make(api).quote("base", "USDC", 100, "solana", "SOL", sender="a", recipient="b")  # type: ignore[arg-type]


def test_quote_without_key_has_no_header(api):
    api.on("GET", "/v1/quote", QUOTE_RESPONSE)
    make(api, channel="widget").quote(8453, "USDC", "1", 7565164, "SOL", sender="a", recipient="b", slippage_bps=100)
    assert "x-api-key" not in api.last.headers
    assert api.last.url.params["channel"] == "widget"
    assert api.last.url.params["slippageBps"] == "100"
    assert api.last.url.params["srcChain"] == "8453"


def test_build_tx_submit_report_simulate(api):
    api.on("POST", "/v1/orders", {"quoteId": "q_1", "provider": "relay", "tx": EVM_TX})
    api.on("POST", "/v1/orders/submit", {"provider": "jupiter", "txHash": "sig"})
    api.on("POST", "/v1/orders/q_1/submitted", {"quoteId": "q_1", "status": "submitted"})
    api.on("POST", "/v1/simulate", {"ok": True, "vm": "evm", "gasEstimate": "21000", "tx": EVM_TX})
    lh = make(api)
    tx = lh.build_tx("q_1")
    assert tx["vm"] == "evm" and tx["approval"]["amount"] == "100000000"
    assert api.last_json() == {"quoteId": "q_1"}
    assert lh.submit("q_1", "AAAA") == "sig"
    assert api.last_json() == {"quoteId": "q_1", "signedTransaction": "AAAA"}
    assert lh.report_submitted("q_1", "0xhash") == {"quoteId": "q_1", "status": "submitted"}
    assert api.last_json() == {"txHash": "0xhash"}
    sim = lh.simulate("q_1")
    assert sim["ok"] and sim["gasEstimate"] == "21000"
    assert api.last_json() == {"quoteId": "q_1"}


def test_status_encodes_id(api):
    api.on("GET", "/v1/orders/relay/a%2Fb", {"provider": "relay", "id": "a/b", "state": "pending"})
    assert make(api).status("relay", "a/b")["state"] == "pending"


def test_list_orders(api):
    api.on("GET", "/v1/orders", {"orders": [{"quoteId": "q_1", "status": "filled", "extra": 1}], "nextCursor": "c2"})
    page = make(api).list_orders(address="0xs", status="filled", limit=10)
    assert page["nextCursor"] == "c2" and page["orders"][0]["extra"] == 1
    assert dict(api.last.url.params) == {"address": "0xs", "status": "filled", "limit": "10"}
    make(api).list_orders()
    assert dict(api.last.url.params) == {}


def test_api_error(api):
    api.on("POST", "/v1/orders", {"error": {"code": "QUOTE_EXPIRED", "message": "Quote expired", "requestId": "rid",
                                            "docsUrl": "https://docs.layerhop.com/errors/QUOTE_EXPIRED"}}, status=410)
    with pytest.raises(LayerHopApiError) as ei:
        make(api).build_tx("q_old")
    e = ei.value
    assert (e.code, e.status, e.request_id, e.message) == ("QUOTE_EXPIRED", 410, "rid", "Quote expired")
    assert "QUOTE_EXPIRED" in str(e)


def test_api_error_without_body(api):
    api.on("GET", "/v1/health", handler=lambda req: httpx.Response(502, text="bad gateway", headers={"x-request-id": "h1"}))
    with pytest.raises(LayerHopApiError) as ei:
        make(api).health()
    assert ei.value.code == "INTERNAL" and ei.value.status == 502 and ei.value.request_id == "h1"


def _sequence(states):
    it = iter(states)

    def handler(req):
        s = next(it)
        return httpx.Response(200, json={"provider": "relay", "id": "0xh", "state": s})
    return handler


def test_watch_yields_changes_until_final(api, monkeypatch):
    monkeypatch.setattr(client_mod.time, "sleep", lambda _s: None)
    api.on("GET", "/v1/orders/relay/0xh", handler=_sequence(["unknown", "pending", "pending", "filled", "pending"]))
    states = [s["state"] for s in make(api).watch("relay", "0xh", interval=0)]
    assert states == ["unknown", "pending", "filled"]
    assert len(api.requests) == 4


def test_watch_timeout(api, monkeypatch):
    monkeypatch.setattr(client_mod.time, "sleep", lambda _s: None)
    api.on("GET", "/v1/orders/relay/0xh", {"provider": "relay", "id": "0xh", "state": "pending"})
    assert [s["state"] for s in make(api).watch("relay", "0xh", timeout=0)] == []


def test_context_manager(api):
    api.on("GET", "/v1/health", {"ok": True})
    with make(api) as lh:
        assert lh.health()["ok"]


@pytest.mark.anyio
async def test_async_client(api):
    api.on("GET", "/v1/chains", {"chains": [{"id": 1}]})
    api.on("GET", "/v1/tokens", {"tokens": []})
    api.on("GET", "/v1/health", {"ok": True})
    api.on("GET", "/v1/quote", QUOTE_RESPONSE)
    api.on("POST", "/v1/orders", {"tx": EVM_TX})
    api.on("POST", "/v1/orders/submit", {"txHash": "sig"})
    api.on("POST", "/v1/orders/q_1/submitted", {"quoteId": "q_1", "status": "submitted"})
    api.on("POST", "/v1/simulate", {"ok": False, "vm": "evm", "error": {"code": "SIMULATION_FAILED", "message": "revert"}, "tx": EVM_TX})
    api.on("GET", "/v1/orders", {"orders": []})
    async with amake(api, api_key="k") as lh:
        assert (await lh.health())["ok"]
        assert (await lh.chains())[0]["id"] == 1
        assert await lh.tokens(1) == []
        q = await lh.quote("base", "USDC", "1", "solana", "SOL", sender="a", recipient="b")
        assert q["best"]["provider"] == "relay"
        assert api.last.headers["x-api-key"] == "k"
        assert (await lh.build_tx("q_1"))["vm"] == "evm"
        assert await lh.submit("q_1", "AA") == "sig"
        assert (await lh.report_submitted("q_1", "0xh"))["status"] == "submitted"
        assert (await lh.simulate("q_1"))["error"]["message"] == "revert"
        assert (await lh.list_orders(address="a"))["orders"] == []


@pytest.mark.anyio
async def test_async_error_and_watch(api):
    api.on("GET", "/v1/quote", {"error": {"code": "NO_ROUTE", "message": "none", "requestId": "x"}}, status=404)
    api.on("GET", "/v1/orders/debridge/0xh", handler=_sequence(["pending", "refunded"]))
    lh = amake(api)
    with pytest.raises(LayerHopApiError) as ei:
        await lh.quote("base", "USDC", "1", "solana", "SOL", sender="a", recipient="b")
    assert ei.value.code == "NO_ROUTE"
    states = [s["state"] async for s in lh.watch("debridge", "0xh", interval=0)]
    assert states == ["pending", "refunded"]
    await lh.aclose()
