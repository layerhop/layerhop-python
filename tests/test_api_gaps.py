"""Tron txs, gasless swaps, quote extras, destination calls, error details, tokens, prices and balances."""

import httpx
import pytest

import layerhop
from layerhop import (
    TRON_CHAIN_ID,
    AsyncLayerHop,
    LayerHop,
    LayerHopApiError,
    parse_route_suggestions,
)
from layerhop import client as client_mod

from .conftest import QUOTE, QUOTE_RESPONSE, FakeApi


def make(api: FakeApi, **kw) -> LayerHop:
    return LayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def amake(api: FakeApi, **kw) -> AsyncLayerHop:
    return AsyncLayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


TRON_CALL = {"to": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "data": "0xa9059cbb00", "value": "0", "feeLimit": "30000000"}
TRON_UNSIGNED = {
    "txID": "a" * 64, "raw_data_hex": "0a02",
    "raw_data": {"contract": [{"type": "TriggerSmartContract", "parameter": {"value": {"data": "a9059cbb"}}}],
                 "ref_block_bytes": "0f3e", "expiration": 1761000600000, "fee_limit": 30000000},
    "visible": False,
}
TRON_TX = {
    "vm": "tvm", "chainId": 728126428, "from": "TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf",
    "call": TRON_CALL, "unsigned": TRON_UNSIGNED,
    "approval": {"token": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "spender": "TSpender111111111111111111111111111",
                 "amount": "5000000", "call": {**TRON_CALL, "data": "0x095ea7b3"},
                 "unsigned": {**TRON_UNSIGNED, "txID": "b" * 64}},
}
EIP712 = {"types": {"EIP712Domain": [{"name": "name", "type": "string"}], "Permit": [{"name": "owner", "type": "address"}]},
          "domain": {"name": "USD Coin", "chainId": 8453}, "message": {"owner": "0x1", "nested": {"a": [1, 2]}},
          "primaryType": "Permit"}
GASLESS = {"chainId": 8453, "approval": {"type": "permit", "eip712": EIP712},
           "trade": {"type": "settler_metatransaction", "eip712": {**EIP712, "primaryType": "Trade"}},
           "gasFee": {"amount": "12000", "token": "0xusdc"}}
GASLESS_STATUS = {"quoteId": "q_g", "provider": "zerox", "orderId": "0xhash", "state": "pending"}
LEG = {"srcChain": 8453, "srcToken": "0xusdc", "amount": "1000000", "dstChain": 81457, "dstToken": "0x0"}
CHAIN = {
    "id": 81457, "slug": "blast", "name": "Blast", "vm": "evm", "nativeSymbol": "ETH", "nativeDecimals": 18,
    "logoURI": "https://x/blast.png", "explorerTx": "https://blastscan.io/tx/", "explorerAddress": "https://blastscan.io/address/",
    "providers": ["blast-native"], "popular": False, "destinationOnly": True,
    "onlyRoute": {"srcChainId": 1, "srcToken": "0x0000000000000000000000000000000000000000",
                  "dstToken": "0x0000000000000000000000000000000000000000"},
    "routeHealth": {"in": "ok", "out": "failing", "status": "deposit_only", "checkedAt": "2026-10-28T10:00:00.000Z"},
}
TOKEN = {"chainId": 8453, "address": "0x4200000000000000000000000000000000000006", "symbol": "WETH", "name": "Wrapped Ether",
         "decimals": 18, "priceUsd": 2423.34, "verified": True, "popular": True}
RISK = {"chainId": 8453, "address": "0x532f27101965dd16442E59d40670FaF5eBB142E4", "level": "danger", "verified": False,
        "symbol": "BRETT", "reasons": [{"code": "sell_tax", "level": "danger", "message": "Sell tax is 12%.", "value": 12},
                                       {"code": "brand_new_code", "level": "caution", "message": "New check."}],
        "source": "goplus", "checkedAt": "2026-10-28T10:00:00.000Z"}


def test_tron_constant_and_version():
    assert TRON_CHAIN_ID == 728126428
    assert layerhop.SOLANA_CHAIN_ID == 7565164


def test_build_tx_decodes_tron_tx(api):
    api.on("POST", "/v1/orders", {"quoteId": "q_t", "provider": "relay", "tx": TRON_TX})
    tx = make(api).build_tx("q_t")
    assert tx["vm"] == "tvm" and tx["chainId"] == TRON_CHAIN_ID and tx["from"].startswith("T")
    assert tx["call"]["feeLimit"] == "30000000"
    assert tx["unsigned"]["txID"] == "a" * 64 and not tx["unsigned"]["txID"].startswith("0x")
    assert tx["unsigned"]["raw_data"] == TRON_UNSIGNED["raw_data"]  # raw JSON, unchanged
    assert tx["approval"]["unsigned"]["txID"] == "b" * 64 and tx["approval"]["amount"] == "5000000"


def test_simulate_tron_energy_used(api):
    api.on("POST", "/v1/simulate", {"quoteId": "q_t", "provider": "relay", "ok": True, "vm": "tvm",
                                    "energyUsed": 64285, "tx": TRON_TX})
    sim = make(api).simulate("q_t")
    assert sim["vm"] == "tvm" and sim["energyUsed"] == 64285 and sim["tx"]["vm"] == "tvm"


def test_quote_extra_params(api):
    gq = {**QUOTE, "gasless": {"gasFee": {"amount": "12000", "token": "0xusdc"}, "approval": True}}
    api.on("GET", "/v1/quote", {**QUOTE_RESPONSE, "best": gq, "quotes": [gq]})
    r = make(api).quote("base", "USDC", "100000000", "base", "WETH", sender="0xs", recipient="0xr", gasless=True,
                        referrer="0xref", copy_of="q_abc", purpose="split", split_id="spl_1", split_share=2,
                        note="Dinner")
    p = dict(api.last.url.params)
    assert p["gasless"] == "true" and p["referrer"] == "0xref" and p["copyOf"] == "q_abc"
    assert p["purpose"] == "split" and p["splitId"] == "spl_1" and p["splitShare"] == "2" and p["note"] == "Dinner"
    assert r["best"]["gasless"]["approval"] is True and r["best"]["gasless"]["gasFee"]["amount"] == "12000"
    make(api).quote("base", "USDC", "1", "base", "WETH", sender="a", recipient="b", split_share=0)
    p = dict(api.last.url.params)
    assert p["splitShare"] == "0"
    for k in ("gasless", "referrer", "copyOf", "purpose", "splitId", "note"):
        assert k not in p


def test_quote_calls_body(api):
    plan = {"items": [{"to": "0xpool", "data": "0x617ba037", "value": "0"}], "executor": "0xexec", "executed": True,
            "simulation": {"ok": True, "gasUsed": "180000", "leftover": "0"}}
    cq = {**QUOTE, "srcAmount": "100250000", "calls": plan}
    api.on("POST", "/v1/quote", {**QUOTE_RESPONSE, "best": cq, "quotes": [cq]})
    lh = make(api, integrator="acme", integrator_fee_bps=5, channel="widget")
    r = lh.quote_calls("arbitrum", "USDC", 8453, "USDC", "100000000", sender="0xs", recipient="0xr",
                       calls=[{"to": "0xpool", "data": "0x617ba037"}], referrer="0xref", copy_of="0xwallet")
    assert api.last.method == "POST"
    assert api.last_json() == {
        "srcChain": "arbitrum", "srcToken": "USDC", "dstChain": "8453", "dstToken": "USDC", "dstAmount": "100000000",
        "sender": "0xs", "recipient": "0xr", "slippageBps": 50, "channel": "widget",
        "calls": [{"to": "0xpool", "data": "0x617ba037"}], "integrator": "acme", "integratorFeeBps": 5,
        "referrer": "0xref", "copyOf": "0xwallet",
    }
    assert r["best"]["srcAmount"] == "100250000" and r["best"]["calls"]["simulation"]["gasUsed"] == "180000"
    make(api).quote_calls("base", "USDC", "base", "USDC", "5", sender="a", recipient="b", action={"type": "aave-v3-supply"},
                          slippage_bps=30)
    body = api.last_json()
    assert body["action"] == {"type": "aave-v3-supply"} and body["slippageBps"] == 30 and body["channel"] == "api"
    assert "calls" not in body and "integrator" not in body
    with pytest.raises(TypeError):
        make(api).quote_calls("base", "USDC", "base", "USDC", 5, sender="a", recipient="b")  # type: ignore[arg-type]


def test_gasless_build_submit_status(api):
    api.on("POST", "/v1/orders", {"quoteId": "q_g", "provider": "zerox", "gasless": GASLESS})
    api.on("POST", "/v1/orders/gasless", GASLESS_STATUS)
    api.on("GET", "/v1/orders/gasless/q_g", {**GASLESS_STATUS, "state": "filled", "srcTxHash": "0xmined"})
    lh = make(api)
    g = lh.build_gasless("q_g")
    assert api.last_json() == {"quoteId": "q_g"}
    assert g["approval"]["eip712"] == EIP712 and g["trade"]["eip712"]["primaryType"] == "Trade"
    assert g["gasFee"]["amount"] == "12000"
    st = lh.submit_gasless("q_g", "0x" + "1" * 130, "0x" + "2" * 130)
    assert api.last_json() == {"quoteId": "q_g", "signatures": {"trade": "0x" + "1" * 130, "approval": "0x" + "2" * 130}}
    assert st["state"] == "pending" and st["orderId"] == "0xhash"
    lh.submit_gasless("q_g", "0xt")
    assert api.last_json() == {"quoteId": "q_g", "signatures": {"trade": "0xt"}}
    st = lh.gasless_status("q_g")
    assert st["state"] == "filled" and st["srcTxHash"] == "0xmined"
    with pytest.raises(ValueError, match="gasless; use build_gasless"):
        lh.build_tx("q_g")


def test_build_gasless_on_normal_quote(api):
    api.on("POST", "/v1/orders", {"quoteId": "q_1", "provider": "relay", "tx": {"vm": "svm", "serializedTx": "AA=="}})
    with pytest.raises(ValueError, match="not gasless; use build_tx"):
        make(api).build_gasless("q_1")


def test_gasless_errors_decode(api):
    api.on("GET", "/v1/orders/gasless/q_g", {"error": {"code": "GASLESS_FAILED", "message": "reverted", "requestId": "r"}},
           status=409)
    with pytest.raises(LayerHopApiError) as ei:
        make(api).gasless_status("q_g")
    assert ei.value.code == "GASLESS_FAILED" and ei.value.details is None


def test_no_route_suggestions(api):
    suggestions = [
        {**LEG, "kind": "dst_token", "message": "Receive USDC on Blast instead", "symbol": "USDC", "dstAmount": "990000"},
        {**LEG, "kind": "via_hub", "message": "Go through Arbitrum", "symbol": "USDC",
         "hub": {"chainId": 42161, "token": "0xarbusdc", "symbol": "USDC", "decimals": 6},
         "steps": [{**LEG, "dstChain": 42161, "dstToken": "0xarbusdc"}, {**LEG, "srcChain": 42161, "srcToken": "0xarbusdc"}]},
        {**LEG, "kind": "via_hub", "message": "No hub"},  # dropped: no hub / steps
        {**LEG, "amount": 5, "kind": "src_token", "message": "bad amount"},  # dropped: amount not a string
        {**LEG, "kind": "teleport", "message": "unknown kind"},  # dropped
        "garbage",  # dropped
        {**LEG, "kind": "src_token", "message": "Pay with ETH instead"},
    ]
    api.on("GET", "/v1/quote", {"error": {
        "code": "NO_ROUTE", "message": "No route", "requestId": "r1",
        "details": {"errors": [{"provider": "relay", "code": "NO_ROUTE", "message": "none"}, {"bad": 1}],
                    "suggestions": suggestions}}}, status=404)
    with pytest.raises(LayerHopApiError) as ei:
        make(api).quote("base", "USDC", "1000000", "blast", "ETH", sender="a", recipient="b")
    e = ei.value
    assert e.code == "NO_ROUTE" and e.details is not None
    s = e.suggestions()
    assert [x["kind"] for x in s] == ["dst_token", "via_hub", "src_token"]
    assert s[1]["hub"]["chainId"] == 42161 and len(s[1]["steps"]) == 2
    assert e.provider_errors() == [{"provider": "relay", "code": "NO_ROUTE", "message": "none"}]
    assert e.min_amount is None and e.min_amount_usd is None and e.min_amount_approx is None


def test_parse_route_suggestions_limits():
    many = [{**LEG, "kind": "dst_token", "message": str(i)} for i in range(6)]
    assert len(parse_route_suggestions({"suggestions": many})) == 4
    assert parse_route_suggestions(None) == [] and parse_route_suggestions({"suggestions": "x"}) == []
    assert parse_route_suggestions({"suggestions": [{**LEG, "amount": "0", "kind": "dst_token", "message": "m"}]}) == []


def test_amount_too_small_details_and_unknown_code(api):
    api.on("GET", "/v1/quote", {"error": {"code": "AMOUNT_TOO_SMALL", "message": "Too small", "requestId": "r2",
                                          "details": {"minAmount": "5000000", "minAmountUsd": 5, "minAmountApprox": True}}},
           status=400)
    with pytest.raises(LayerHopApiError) as ei:
        make(api).quote("base", "USDC", "1", "solana", "SOL", sender="a", recipient="b")
    e = ei.value
    assert (e.min_amount, e.min_amount_usd, e.min_amount_approx) == ("5000000", 5.0, True)
    assert e.suggestions() == [] and e.provider_errors() == []
    api.on("GET", "/v1/quote", {"error": {"code": "BRAND_NEW_CODE", "message": "?", "details": "not-an-object"}}, status=400)
    with pytest.raises(LayerHopApiError) as ei:
        make(api).quote("base", "USDC", "1", "solana", "SOL", sender="a", recipient="b")
    assert ei.value.code == "BRAND_NEW_CODE" and ei.value.details is None


def test_chain_route_health_fields(api):
    api.on("GET", "/v1/chains", {"chains": [CHAIN, {"id": 728126428, "slug": "tron", "vm": "tvm"}]})
    chains = make(api).chains()
    c = chains[0]
    assert c["destinationOnly"] is True and c["onlyRoute"]["srcChainId"] == 1
    assert c["routeHealth"]["in"] == "ok" and c["routeHealth"]["status"] == "deposit_only"
    assert chains[1]["vm"] == "tvm"


def test_tokens_search_and_page(api):
    api.on("GET", "/v1/tokens", {"tokens": [TOKEN], "nextCursor": "c2"})
    lh = make(api)
    assert lh.tokens("base")[0]["verified"] is True
    assert dict(api.last.url.params) == {"chain": "base"}
    page = lh.tokens_page(8453, q="weth", limit=20, cursor="c1")
    assert dict(api.last.url.params) == {"chain": "8453", "q": "weth", "limit": "20", "cursor": "c1"}
    assert page["nextCursor"] == "c2" and page["tokens"][0]["name"] == "Wrapped Ether"
    lh.tokens("base", q="usd")
    assert api.last.url.params["q"] == "usd"


def test_lookup_token_with_and_without_chain(api):
    api.on("GET", "/v1/tokens/lookup", {"token": TOKEN})
    lh = make(api)
    t = lh.lookup_token(TOKEN["address"])
    assert dict(api.last.url.params) == {"address": TOKEN["address"]} and t["symbol"] == "WETH"
    lh.lookup_token(TOKEN["address"], "base")
    assert dict(api.last.url.params) == {"address": TOKEN["address"], "chain": "base"}
    lh.lookup_token(TOKEN["address"], chain=8453)
    assert api.last.url.params["chain"] == "8453"


def test_token_risk(api):
    api.on("GET", f"/v1/tokens/base/{RISK['address']}/risk", {"risk": RISK})
    r = make(api).token_risk("base", RISK["address"])
    assert r["level"] == "danger" and r["reasons"][0]["value"] == 12 and r["reasons"][1]["code"] == "brand_new_code"
    assert r["source"] == "goplus"


def test_prices_and_balances(api):
    api.on("GET", "/v1/prices", {"prices": {"8453:0xusdc": 1.0}})
    api.on("GET", "/v1/balances", {"address": "0xA", "vm": "evm", "totalUsd": 12.5,
                                   "balances": [{**TOKEN, "amount": "5000000000000000", "valueUsd": 12.5}],
                                   "errors": [{"chainId": 10, "message": "RPC down"}]})
    lh = make(api)
    assert lh.prices([]) == {} and api.requests == []
    p = lh.prices(["8453:0xusdc", (1, "0x0"), {"chainId": 7565164, "address": "So1"}])
    assert api.last.url.params["ids"] == "8453:0xusdc,1:0x0,7565164:So1" and p == {"8453:0xusdc": 1.0}
    b = lh.balances("0xA", ["base", 10], tokens=["8453:0xusdc"], fresh=True)
    assert dict(api.last.url.params) == {"address": "0xA", "chains": "base,10", "tokens": "8453:0xusdc", "fresh": "1"}
    assert b["balances"][0]["amount"] == "5000000000000000" and b["errors"][0]["chainId"] == 10
    lh.balances("0xA")
    assert dict(api.last.url.params) == {"address": "0xA"}


def test_watch_stops_on_dropped(api, monkeypatch):
    monkeypatch.setattr(client_mod.time, "sleep", lambda _s: None)
    states = iter(["pending", "dropped", "pending"])
    api.on("GET", "/v1/orders/relay/0xh",
           handler=lambda req: httpx.Response(200, json={"provider": "relay", "id": "0xh", "state": next(states)}))
    assert [s["state"] for s in make(api).watch("relay", "0xh", interval=0)] == ["pending", "dropped"]
    assert "dropped" in layerhop.FINAL_STATES


@pytest.mark.anyio
async def test_async_new_methods(api):
    api.on("POST", "/v1/orders", {"quoteId": "q_g", "provider": "zerox", "gasless": GASLESS})
    api.on("POST", "/v1/orders/gasless", GASLESS_STATUS)
    api.on("GET", "/v1/orders/gasless/q_g", GASLESS_STATUS)
    api.on("POST", "/v1/quote", QUOTE_RESPONSE)
    api.on("GET", "/v1/quote", QUOTE_RESPONSE)
    api.on("GET", "/v1/tokens", {"tokens": [TOKEN], "nextCursor": None})
    api.on("GET", "/v1/tokens/lookup", {"token": TOKEN})
    api.on("GET", "/v1/tokens/8453/0xabc/risk", {"risk": RISK})
    api.on("GET", "/v1/prices", {"prices": {"8453:0xusdc": 1.0}})
    api.on("GET", "/v1/balances", {"address": "9W", "vm": "svm", "totalUsd": 0, "balances": [], "errors": []})
    async with amake(api) as lh:
        assert (await lh.build_gasless("q_g"))["chainId"] == 8453
        with pytest.raises(ValueError):
            await lh.build_tx("q_g")
        assert (await lh.submit_gasless("q_g", "0xt"))["state"] == "pending"
        assert (await lh.gasless_status("q_g"))["orderId"] == "0xhash"
        await lh.quote_calls("base", "USDC", "base", "USDC", "1", sender="a", recipient="b", action={"type": "aave-v3-supply"})
        assert api.last.method == "POST" and api.last_json()["dstAmount"] == "1"
        await lh.quote("base", "USDC", "1", "base", "WETH", sender="a", recipient="b", gasless=True, purpose="tip", note="hi")
        assert api.last.url.params["gasless"] == "true" and api.last.url.params["purpose"] == "tip"
        assert (await lh.tokens("base", q="we"))[0]["symbol"] == "WETH"
        assert (await lh.tokens_page("base"))["nextCursor"] is None
        assert (await lh.lookup_token("0xabc"))["symbol"] == "WETH"
        assert "chain" not in api.last.url.params
        assert (await lh.token_risk(8453, "0xabc"))["level"] == "danger"
        assert await lh.prices([]) == {}
        assert (await lh.prices(["8453:0xusdc"]))["8453:0xusdc"] == 1.0
        assert (await lh.balances("9W", ["solana"]))["vm"] == "svm"
