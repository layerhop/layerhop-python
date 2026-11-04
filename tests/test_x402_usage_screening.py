"""x402 (D-066), usage, webhook resend / since, address screening (D-069), checkout transfer and
Bitcoin fields (D-064, D-065, D-067) and the live quote stream (D-068)."""

import json
from urllib.parse import parse_qs

import httpx
import pytest

from layerhop import AsyncLayerHop, LayerHop, LayerHopApiError

from .conftest import CHECKOUT_QUOTE_RESPONSE, CHECKOUT_SESSION, QUOTE, QUOTE_RESPONSE, FakeApi
from .test_streams import ChunkStream, amake, frames, make, sse

CS = CHECKOUT_SESSION["id"]
ADDR = "0x2222222222222222222222222222222222222222"
PAYEE = {
    "id": "x4p_01k7t9m2c4x8q6r0v3b5n7p9d", "network": "eip155:8453", "chainId": 8453,
    "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "depositAddress": "0x4c3f1a0b9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a",
    "merchant": ADDR, "resource": "https://api.example.com/v1/weather", "feeBps": 25,
    "factory": "0x9999999999999999999999999999999999999999", "lastSweepTx": None, "lastSweptAt": None,
}
REQUIREMENTS = {
    "payee": PAYEE, "price": "10000", "amount": "10026", "fee": {"bps": 25, "amount": "26"},
    "accepts": [{"scheme": "exact", "network": "eip155:8453", "amount": "10026", "payTo": PAYEE["depositAddress"]}],
    "acceptsV1": [{"scheme": "exact", "network": "base", "maxAmountRequired": "10026"}],
    "paymentRequired": {"x402Version": 2, "accepts": []},
}
PAYMENT = {
    "id": "x402_01k7t9m2c4x8q6r0v3b5n7p9d", "object": "x402.payment", "status": "settled", "statusDetail": None,
    "network": "eip155:8453", "chainId": 8453, "asset": PAYEE["asset"], "payer": "0x857b06519e91e3a54538791bdbb0e22373e36b66",
    "payTo": PAYEE["depositAddress"], "amount": "10026", "merchantAmount": "10000", "feeBps": 25,
    "resource": PAYEE["resource"], "transaction": "0x1234", "sweepTx": None, "settledAt": "2026-11-04T10:00:00.000Z",
    "createdAt": "2026-11-04T10:00:00.000Z", "updatedAt": "2026-11-04T10:00:00.000Z",
}
PAYLOAD = {"x402Version": 2, "payload": {"signature": "0xsig", "authorization": {"from": PAYMENT["payer"], "value": "10026"}}}
SCREENING = {"source": "ofac_sdn", "listUpdatedAt": "2026-10-28T00:00:00.000Z",
             "sanctioned": [{"address": "0x098B716B8Aaf21512996dC57EB0615e2383E2f96", "role": "recipient", "lists": ["OFAC SDN"]}]}
SCREEN = {
    "results": [
        {"address": "0x098B716B8Aaf21512996dC57EB0615e2383E2f96", "sanctioned": True, "lists": ["OFAC SDN"],
         "source": "ofac_sdn", "listUpdatedAt": "2026-10-28T00:00:00.000Z"},
        {"address": ADDR, "sanctioned": False, "lists": [], "source": "ofac_sdn", "listUpdatedAt": "2026-10-28T00:00:00.000Z"},
    ],
    "list": {"source": "ofac_sdn", "name": "OFAC SDN", "publishedAt": "2026-10-28T00:00:00.000Z",
             "fetchedAt": "2026-11-04T06:00:00.000Z", "addressCount": 1081},
    "enforced": False,
}
COUNTS = {"2xx": 9, "3xx": 0, "4xx": 1, "5xx": 0}
USAGE = {
    "bucket": "day", "from": "2026-11-01T00:00:00.000Z", "to": "2026-11-04T00:00:00.000Z", "livemode": True, "keyId": None,
    "totals": {"requests": 10, "errors": 1, "byStatusClass": COUNTS, "avgMs": 120.5, "p50Ms": 90, "p95Ms": 400},
    "series": [{"ts": "2026-11-03T00:00:00.000Z", "requests": 10, "errors": 1, "byStatusClass": COUNTS, "p50Ms": 90, "p95Ms": 400}],
    "byEndpoint": [{"group": "quote", "requests": 10, "errors": 1, "byStatusClass": COUNTS, "avgMs": 120.5, "p50Ms": 90, "p95Ms": 400}],
    "errorCodes": [{"code": "NO_ROUTE", "count": 1, "byEndpoint": {"quote": 1}}],
}
USAGE_ERROR = {"ts": "2026-11-03T12:00:00.000Z", "keyId": "key_1", "requestId": "req_1", "method": "GET", "path": "/v1/quote",
               "endpointGroup": "quote", "status": 404, "code": "NO_ROUTE", "latencyMs": 812}
TRANSFER = {
    "kind": "evm_splitter", "chainId": 8453, "token": PAYEE["asset"], "symbol": "USDC", "decimals": 6,
    "address": PAYEE["depositAddress"], "amount": "49122500", "amountDue": "49000000", "fee": {"bps": 25, "amount": "122500"},
    "uri": "ethereum:0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913@8453/transfer?address=0x4c3f&uint256=49122500",
    "transferUri": None, "reference": None, "received": "0", "seen": "0", "state": "waiting", "txs": [],
    "startedAt": "2026-11-04T10:00:00.000Z", "sweepTxHash": None,
}
BITCOIN = {
    "address": "bc1qexampleaddress0000000000000000000000", "amountSats": "75000", "amountBtc": "0.00075",
    "uri": "bitcoin:bc1qexampleaddress0000000000000000000000?amount=0.00075", "amountOut": "49000000",
    "expiresAt": "2026-11-04T10:15:00.000Z", "expired": False, "status": "waiting", "seenSats": "0", "requestId": "0xreq",
    "feeBps": 25, "refundAddress": "bc1qrefund", "quotes": [],
}
QS = {"src_chain": "base", "src_token": "USDC", "dst_chain": "solana", "dst_token": "SOL"}


def q(req: httpx.Request) -> dict:
    return {k: v[0] for k, v in parse_qs(req.url.query.decode()).items()}


def test_x402_endpoints(api: FakeApi) -> None:
    api.on("GET", "/v1/x402/supported", {"kinds": [{"x402Version": 2, "scheme": "exact", "network": "eip155:8453"}],
                                         "extensions": [], "signers": {}, "settle": False})
    api.on("POST", "/v1/x402/requirements", REQUIREMENTS)
    api.on("POST", "/v1/x402/verify", {"isValid": True, "payer": PAYMENT["payer"]})
    api.on("POST", "/v1/x402/settle", {"success": False, "errorReason": "settlement_pending", "transaction": "0x1234",
                                       "network": "eip155:8453"})
    api.on("GET", "/v1/x402/payments", {"payments": [PAYMENT], "nextCursor": "c2"})
    api.on("GET", "/v1/x402/payments/x402_01k7t9m2c4x8q6r0v3b5n7p9d", PAYMENT)
    lh = make(api, api_key="lh_live_x")

    assert lh.x402.supported()["kinds"][0]["network"] == "eip155:8453"
    r = lh.x402.requirements("10000", ADDR, PAYEE["resource"], description="Current weather")
    assert api.last_json() == {"amount": "10000", "payTo": ADDR, "resource": PAYEE["resource"], "description": "Current weather"}
    assert r["payee"]["depositAddress"] == PAYEE["depositAddress"] and r["fee"]["amount"] == "26"
    lh.x402.requirements("10000", ADDR, "weather", network="arbitrum", mime_type="application/json", max_timeout_seconds=120)
    assert api.last_json() == {"amount": "10000", "payTo": ADDR, "resource": "weather", "network": "arbitrum",
                               "mimeType": "application/json", "maxTimeoutSeconds": 120}
    with pytest.raises(TypeError):
        lh.x402.requirements(10000, ADDR, "weather")  # type: ignore[arg-type]

    v = lh.x402.verify(PAYLOAD, r["accepts"][0])
    assert api.last_json() == {"paymentPayload": PAYLOAD, "paymentRequirements": r["accepts"][0]}
    assert v["isValid"] is True and api.last.headers["x-api-key"] == "lh_live_x"
    s = lh.x402.settle(PAYLOAD, r["acceptsV1"][0], x402_version=1)
    assert api.last_json()["x402Version"] == 1 and api.last.url.path == "/v1/x402/settle"
    assert s["errorReason"] == "settlement_pending"

    page = lh.x402.payments.list(status="settled", limit=10)
    assert q(api.last) == {"status": "settled", "limit": "10"}
    assert page["payments"][0]["merchantAmount"] == "10000" and page["nextCursor"] == "c2"
    lh.x402.payments.list()
    assert api.last.url.query == b""
    assert lh.x402.payments.get(PAYMENT["id"])["status"] == "settled"


def test_usage_and_webhook_resend(api: FakeApi) -> None:
    api.on("GET", "/v1/usage", USAGE)
    api.on("GET", "/v1/usage/errors", {"errors": [USAGE_ERROR]})
    api.on("POST", "/v1/webhooks/events/evt%2F1/resend",
           {"eventId": "evt/1", "type": "order.filled", "livemode": True, "deliveries": [{"id": "del_1", "endpointId": "we_1"}]},
           status=202)
    lh = make(api, api_key="lh_live_x")

    u = lh.usage.get(bucket="day", from_="2026-11-01", to="1762214400", key_id="key_1")
    assert q(api.last) == {"bucket": "day", "from": "2026-11-01", "to": "1762214400", "keyId": "key_1"}
    assert u["totals"]["byStatusClass"]["4xx"] == 1 and u["from"] == "2026-11-01T00:00:00.000Z"
    lh.usage.get()
    assert api.last.url.query == b""
    errs = lh.usage.errors(code="NO_ROUTE", limit=5)
    assert q(api.last) == {"code": "NO_ROUTE", "limit": "5"}
    assert errs == [USAGE_ERROR]

    r = lh.webhooks.resend("evt/1")
    assert api.last_json() == {} and api.last.url.raw_path == b"/v1/webhooks/events/evt%2F1/resend"
    assert r["deliveries"][0]["endpointId"] == "we_1"
    lh.webhooks.resend("evt/1", endpoint_id="we_2")
    assert api.last_json() == {"endpointId": "we_2"}


def test_webhook_stream_since(api: FakeApi) -> None:
    event = {"id": "evt_1", "type": "x402.payment.settled", "livemode": True, "createdAt": "2026-11-04T10:00:00.000Z",
             "data": {"payment": PAYMENT}}
    sse(api, "/v1/webhooks/stream", ChunkStream(frames("event", event)))
    events = list(make(api, api_key="lh_live_x").webhooks.stream(since="2026-11-04T09:30:00.000Z"))
    assert q(api.last) == {"since": "2026-11-04T09:30:00.000Z"}
    assert events[0]["data"]["payment"]["id"] == PAYMENT["id"]


def test_screen_and_screening_fields(api: FakeApi) -> None:
    api.on("POST", "/v1/screen", SCREEN)
    api.on("GET", "/v1/quote", {**QUOTE_RESPONSE, "screening": SCREENING})
    api.on("POST", f"/v1/checkout/sessions/{CS}/quote", {**CHECKOUT_QUOTE_RESPONSE, "screening": SCREENING})
    lh = make(api)
    r = lh.screen(("0x098B716B8Aaf21512996dC57EB0615e2383E2f96", ADDR))
    assert api.last_json() == {"addresses": ["0x098B716B8Aaf21512996dC57EB0615e2383E2f96", ADDR]}
    assert [x["sanctioned"] for x in r["results"]] == [True, False] and r["list"]["addressCount"] == 1081
    assert r["enforced"] is False
    quote = lh.quote("base", "USDC", "1000000", "base", "WETH", sender=ADDR, recipient=ADDR)
    assert quote["screening"]["sanctioned"][0]["role"] == "recipient"
    cq = lh.checkout.quote(CS, "base", "USDC", sender=ADDR)
    assert cq["screening"]["source"] == "ofac_sdn"


def test_address_sanctioned_error(api: FakeApi) -> None:
    api.on("GET", "/v1/quote", {"error": {"code": "ADDRESS_SANCTIONED", "message": "Listed address", "requestId": "r9",
                                          "details": {"sanctioned": SCREENING["sanctioned"]}}}, status=451)
    with pytest.raises(LayerHopApiError) as ei:
        make(api).quote("base", "USDC", "1000000", "base", "WETH", sender=ADDR, recipient=ADDR)
    assert (ei.value.code, ei.value.status, ei.value.request_id) == ("ADDRESS_SANCTIONED", 451, "r9")
    assert ei.value.details["sanctioned"][0]["lists"] == ["OFAC SDN"]


def test_checkout_embed_transfer_bitcoin(api: FakeApi) -> None:
    session = {**CHECKOUT_SESSION, "status": "open", "embedOrigins": ["https://shop.example.com"],
               "transferAvailable": True, "transfer": None, "bitcoinAvailable": True, "bitcoin": None}
    api.on("POST", "/v1/checkout/sessions", session, status=201)
    api.on("POST", f"/v1/checkout/sessions/{CS}/transfer", {**session, "transfer": TRANSFER})
    api.on("POST", f"/v1/checkout/sessions/{CS}/bitcoin", {**session, "bitcoin": BITCOIN})
    api.on("GET", f"/v1/checkout/sessions/{CS}", {
        **session, "status": "paid", "transfer": {**TRANSFER, "state": "paid"},
        "payment": {**CHECKOUT_SESSION["payment"], "method": "transfer", "quoteId": None}})
    lh = make(api, api_key="lh_live_x")

    s = lh.checkout.create("49000000", "base", "USDC", ADDR, embed_origins=["https://shop.example.com"])
    assert api.last_json()["embedOrigins"] == ["https://shop.example.com"]
    assert s["embedOrigins"] == ["https://shop.example.com"] and s["transferAvailable"] is True
    lh.checkout.create("49000000", "base", "USDC", ADDR)
    assert "embedOrigins" not in api.last_json()

    t = lh.checkout.start_transfer(CS)
    assert api.last_json() == {} and t["transfer"]["kind"] == "evm_splitter" and t["transfer"]["fee"]["bps"] == 25
    b = lh.checkout.start_bitcoin(CS, refund_address="bc1qrefund")
    assert api.last_json() == {"refundAddress": "bc1qrefund"}
    assert b["bitcoin"]["amountSats"] == "75000" and b["bitcoin"]["uri"].startswith("bitcoin:")
    lh.checkout.start_bitcoin(CS)
    assert api.last_json() == {}
    paid = lh.checkout.get(CS)
    assert paid["payment"]["method"] == "transfer" and paid["payment"]["quoteId"] is None


def _quote_frames(*updates: dict, tail: bytes) -> list:
    return frames("quote", *updates)[:-1] + [tail]


def test_quote_stream_yields_updates_and_ends(api: FakeApi) -> None:
    u1 = {**QUOTE_RESPONSE, "seq": 1}
    u2 = {**QUOTE_RESPONSE, "best": {**QUOTE, "dstAmount": "612400000"}, "seq": 2}
    body = ChunkStream(_quote_frames(u1, u2, tail=b'event: end\ndata: {"reason":"expired","quotesSent":2}\n\n'
                                                  b'event: quote\ndata: {"seq":99}\n\n'))
    sse(api, "/v1/quote/stream", body)
    lh = make(api, api_key="lh_live_x", integrator="acme")
    it = lh.quotes.stream(QS["src_chain"], QS["src_token"], "100000000", QS["dst_chain"], QS["dst_token"],
                          sender=ADDR, recipient="9WzD", interval_ms=5000, exclude_providers=["relay"])
    assert api.requests == []  # lazy
    updates = list(it)
    assert [u["seq"] for u in updates] == [1, 2]  # nothing after `end`
    assert updates[1]["best"]["dstAmount"] == "612400000"
    params = q(api.last)
    assert params["amount"] == "100000000" and params["intervalMs"] == "5000" and params["integrator"] == "acme"
    assert params["excludeProviders"] == "relay" and params["channel"] == "api" and "dstAmount" not in params
    assert api.last.headers["accept"] == "text/event-stream" and body.closed


def test_quote_stream_exact_output_and_validation(api: FakeApi) -> None:
    sse(api, "/v1/quote/stream", ChunkStream(frames("quote", {**QUOTE_RESPONSE, "seq": 1})))
    lh = make(api)
    out = list(lh.quotes.stream("base", "USDC", None, "arbitrum", "USDC", sender=ADDR, recipient=ADDR, dst_amount="5000000"))
    assert out[0]["seq"] == 1
    params = q(api.last)
    assert params["dstAmount"] == "5000000" and "amount" not in params and "intervalMs" not in params
    with pytest.raises(TypeError):
        lh.quotes.stream("base", "USDC", "1", "arbitrum", "USDC", sender=ADDR, recipient=ADDR, dst_amount="5")
    with pytest.raises(TypeError):
        lh.quotes.stream("base", "USDC", None, "arbitrum", "USDC", sender=ADDR, recipient=ADDR)
    with pytest.raises(TypeError):
        lh.quotes.stream("base", "USDC", None, "arbitrum", "USDC", sender=ADDR, recipient=ADDR, dst_amount="5", gasless=True)


def test_quote_stream_error_event(api: FakeApi) -> None:
    err = {"error": {"code": "ADDRESS_SANCTIONED", "message": "Listed", "requestId": "r7", "details": {"x": 1}}, "status": 451}
    body = ChunkStream(_quote_frames({**QUOTE_RESPONSE, "seq": 1}, tail=f"event: error\ndata: {json.dumps(err)}\n\n".encode()))
    sse(api, "/v1/quote/stream", body)
    seen = []
    with pytest.raises(LayerHopApiError) as ei:
        for u in make(api).quotes.stream("base", "USDC", "1000000", "solana", "SOL", sender=ADDR, recipient="9WzD"):
            seen.append(u["seq"])
    assert seen == [1]
    assert (ei.value.code, ei.value.status, ei.value.request_id, ei.value.details) == ("ADDRESS_SANCTIONED", 451, "r7", {"x": 1})
    assert body.closed

    # A malformed error frame still raises with fallbacks.
    sse(api, "/v1/quote/stream", ChunkStream([b"event: error\ndata: {}\n\n"]))
    with pytest.raises(LayerHopApiError) as ei:
        list(make(api).quotes.stream("base", "USDC", "1000000", "solana", "SOL", sender=ADDR, recipient="9WzD"))
    assert (ei.value.code, ei.value.status) == ("INTERNAL", 500)


def test_quote_stream_http_error(api: FakeApi) -> None:
    api.on("GET", "/v1/quote/stream", {"error": {"code": "NO_ROUTE", "message": "No route", "requestId": "r1"}}, status=404)
    with pytest.raises(LayerHopApiError) as ei:
        next(make(api).quotes.stream("base", "USDC", "1", "solana", "SOL", sender=ADDR, recipient="9WzD"))
    assert (ei.value.code, ei.value.status) == ("NO_ROUTE", 404)


@pytest.mark.anyio
async def test_async_new_endpoints(api: FakeApi) -> None:
    api.on("GET", "/v1/x402/supported", {"kinds": [], "extensions": [], "signers": {}, "settle": True})
    api.on("POST", "/v1/x402/requirements", REQUIREMENTS)
    api.on("POST", "/v1/x402/verify", {"isValid": False, "invalidReason": "insufficient_funds"})
    api.on("POST", "/v1/x402/settle", {"success": True, "transaction": "0x1", "network": "eip155:8453"})
    api.on("GET", "/v1/x402/payments", {"payments": [PAYMENT], "nextCursor": None})
    api.on("GET", f"/v1/x402/payments/{PAYMENT['id']}", PAYMENT)
    api.on("GET", "/v1/usage", USAGE)
    api.on("GET", "/v1/usage/errors", {"errors": [USAGE_ERROR]})
    api.on("POST", "/v1/webhooks/events/evt_1/resend", {"eventId": "evt_1", "type": "order.filled", "livemode": True,
                                                        "deliveries": []}, status=202)
    api.on("POST", "/v1/screen", SCREEN)
    api.on("POST", f"/v1/checkout/sessions/{CS}/transfer", {**CHECKOUT_SESSION, "transfer": TRANSFER})
    api.on("POST", f"/v1/checkout/sessions/{CS}/bitcoin", {**CHECKOUT_SESSION, "bitcoin": BITCOIN})
    api.on("POST", "/v1/checkout/sessions", CHECKOUT_SESSION, status=201)
    async with amake(api, api_key="lh_live_x") as lh:
        assert (await lh.x402.supported())["settle"] is True
        assert (await lh.x402.requirements("10000", ADDR, "r", network="base"))["price"] == "10000"
        assert api.last_json()["network"] == "base"
        assert (await lh.x402.verify(PAYLOAD, {}))["invalidReason"] == "insufficient_funds"
        assert (await lh.x402.settle(PAYLOAD, {}, x402_version=2))["success"] is True
        assert api.last_json()["x402Version"] == 2
        assert (await lh.x402.payments.list(cursor="c1"))["nextCursor"] is None
        assert q(api.last) == {"cursor": "c1"}
        assert (await lh.x402.payments.get(PAYMENT["id"]))["id"] == PAYMENT["id"]
        assert (await lh.usage.get(bucket="hour"))["errorCodes"][0]["code"] == "NO_ROUTE"
        assert q(api.last) == {"bucket": "hour"}
        assert (await lh.usage.errors(key_id="key_1"))[0]["latencyMs"] == 812
        assert q(api.last) == {"keyId": "key_1"}
        assert (await lh.webhooks.resend("evt_1", endpoint_id="we_1"))["deliveries"] == []
        assert api.last_json() == {"endpointId": "we_1"}
        assert (await lh.screen([ADDR]))["results"][1]["address"] == ADDR
        assert (await lh.checkout.start_transfer(CS))["transfer"]["state"] == "waiting"
        assert (await lh.checkout.start_bitcoin(CS, refund_address="bc1q"))["bitcoin"]["feeBps"] == 25
        await lh.checkout.create("1", "base", "USDC", ADDR, embed_origins=[])
        assert api.last_json()["embedOrigins"] == []


@pytest.mark.anyio
async def test_async_quote_stream(api: FakeApi) -> None:
    body = ChunkStream(frames("quote", {**QUOTE_RESPONSE, "seq": 1}, {**QUOTE_RESPONSE, "seq": 2}))
    sse(api, "/v1/quote/stream", body)
    sse(api, "/v1/webhooks/stream", ChunkStream(frames("event", {"id": "evt_1"})))
    async with amake(api) as lh:
        it = lh.quotes.stream("base", "USDC", "1000000", "solana", "SOL", sender=ADDR, recipient="9WzD", interval_ms=8000)
        async for u in it:
            assert u["seq"] == 1
            break
        await it.aclose()  # type: ignore[attr-defined]
        assert body.closed and body.sent < len(body.chunks)
        assert q(api.last)["intervalMs"] == "8000"
        assert [e["id"] async for e in lh.webhooks.stream(since="2026-11-04T09:00:00Z")] == ["evt_1"]
        assert q(api.last) == {"since": "2026-11-04T09:00:00Z"}

    err = {"error": {"code": "RATE_LIMITED", "message": "Slow down"}, "status": 429}
    sse(api, "/v1/quote/stream", ChunkStream([f"event: error\ndata: {json.dumps(err)}\n\n".encode()]))
    async with amake(api) as lh:
        with pytest.raises(LayerHopApiError) as ei:
            async for _ in lh.quotes.stream("base", "USDC", "1", "solana", "SOL", sender=ADDR, recipient="9WzD"):
                pass
        assert (ei.value.code, ei.value.status) == ("RATE_LIMITED", 429)
