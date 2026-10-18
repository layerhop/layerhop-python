import json
from typing import AsyncIterator, Iterator, List

import httpx
import pytest

from layerhop import AsyncLayerHop, LayerHop, LayerHopApiError

from .conftest import CHECKOUT_SESSION, FakeApi

CS = CHECKOUT_SESSION["id"]
ORDER = {"quoteId": "q_1", "status": "submitted", "provider": "relay", "srcTxHash": "0xabc"}
EVENT = {"id": "evt_1", "type": "order.filled", "livemode": False, "sample": True,
         "createdAt": "2026-10-18T10:00:00.000Z", "data": {"order": {**ORDER, "status": "filled"}}}


class ChunkStream(httpx.SyncByteStream, httpx.AsyncByteStream):
    """A response body delivered in the given chunks (sync and async), recording when it is closed."""

    def __init__(self, chunks: List[bytes]) -> None:
        self.chunks = chunks
        self.sent = 0
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        for c in self.chunks:
            self.sent += 1
            yield c

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for c in self.chunks:
            self.sent += 1
            yield c

    def close(self) -> None:
        self.closed = True

    async def aclose(self) -> None:
        self.closed = True


def frames(event: str, *payloads: dict) -> List[bytes]:
    """A realistic SSE body split at awkward places: comments, a ready frame, \\r\\n, multi-line data."""
    first, *rest = payloads
    raw = json.dumps(first, separators=(",", ":"))
    half = len(raw) // 2
    chunks = [
        b": connected\r\n\r\nevent: ready\r\ndata: {}\r\n\r\n",
        f"event: {event}\r\ndata: {raw[:half]}".encode(),
        f"{raw[half:]}\r\n\r\n: ping\r\n\r".encode(),
        b"\n",
    ]
    for p in rest:
        lines = json.dumps(p, indent=1).split("\n")  # one data: line per JSON line
        chunks.append((f"event: {event}\n" + "".join(f"data: {ln}\n" for ln in lines) + "\n").encode())
    chunks.append(b"event: other\ndata: {\"ignored\":true}\n\n")
    return chunks


def sse(api: FakeApi, path: str, body: ChunkStream) -> None:
    api.on("GET", path, handler=lambda req: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=body))


def make(api: FakeApi, **kw) -> LayerHop:
    return LayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def amake(api: FakeApi, **kw) -> AsyncLayerHop:
    return AsyncLayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def test_stream_order_parses_frames(api):
    body = ChunkStream(frames("order", ORDER, {**ORDER, "status": "filled", "dstTxHash": "0xdef"}))
    sse(api, "/v1/orders/q%2F1/events", body)
    orders = list(make(api, api_key="lh_live_x").stream_order("q/1"))
    assert orders == [ORDER, {**ORDER, "status": "filled", "dstTxHash": "0xdef"}]
    req = api.last
    assert req.method == "GET" and req.url.raw_path == b"/v1/orders/q%2F1/events"
    assert req.headers["accept"] == "text/event-stream" and req.headers["x-api-key"] == "lh_live_x"
    assert body.closed


def test_stream_is_lazy_and_stops_early(api):
    body = ChunkStream(frames("order", ORDER, {**ORDER, "status": "pending"}, {**ORDER, "status": "filled"}))
    sse(api, "/v1/orders/q_1/events", body)
    it = make(api).stream_order("q_1")
    assert api.requests == []  # nothing is sent until iteration starts
    for o in it:
        assert o["status"] == "submitted"
        break
    it.close()
    assert body.closed and body.sent < len(body.chunks)
    assert "x-api-key" not in api.last.headers


def test_stream_has_no_read_timeout_by_default(api):
    sse(api, "/v1/orders/q_1/events", ChunkStream(frames("order", ORDER)))
    list(make(api, timeout=5).stream_order("q_1"))
    t = api.last.extensions["timeout"]
    assert t["read"] is None and t["connect"] == 5
    list(make(api, stream_timeout=60).stream_order("q_1"))
    assert api.last.extensions["timeout"]["read"] == 60


def test_checkout_stream(api):
    paid = {**CHECKOUT_SESSION, "status": "paid"}
    sse(api, f"/v1/checkout/sessions/{CS}/events", ChunkStream(frames("session", CHECKOUT_SESSION, paid)))
    sessions = list(make(api).checkout.stream(CS))
    assert [s["status"] for s in sessions] == ["processing", "paid"]
    assert sessions[1]["settlement"]["decimals"] == 6


def test_webhooks_stream_and_trigger(api):
    sse(api, "/v1/webhooks/stream", ChunkStream(frames("event", EVENT, {**EVENT, "id": "evt_2"})))
    api.on("POST", "/v1/webhooks/trigger", {"eventId": "evt_1", "deliveries": 2, "payload": EVENT}, status=202)
    lh = make(api, api_key="lh_test_x")
    events = list(lh.webhooks.stream())
    assert [e["id"] for e in events] == ["evt_1", "evt_2"]
    assert events[0]["data"]["order"]["status"] == "filled" and events[0]["sample"] is True
    assert api.last.headers["x-api-key"] == "lh_test_x"
    r = lh.webhooks.trigger("order.filled")
    assert api.last_json() == {"type": "order.filled"}
    assert r["eventId"] == "evt_1" and r["deliveries"] == 2 and r["payload"]["type"] == "order.filled"


def test_stream_errors(api):
    api.on("GET", "/v1/orders/q_x/events",
           {"error": {"code": "ORDER_NOT_FOUND", "message": "No order", "requestId": "r1"}}, status=404)
    api.on("GET", "/v1/webhooks/stream", {"error": {"code": "UNAUTHORIZED", "message": "Missing key"}}, status=401)
    api.on("POST", "/v1/webhooks/trigger", {"error": {"code": "FORBIDDEN", "message": "Use a test key"}}, status=403)
    lh = make(api, api_key="lh_live_x")
    with pytest.raises(LayerHopApiError) as ei:
        next(lh.stream_order("q_x"))
    assert (ei.value.code, ei.value.status, ei.value.request_id) == ("ORDER_NOT_FOUND", 404, "r1")
    with pytest.raises(LayerHopApiError) as ei:
        list(lh.webhooks.stream())
    assert ei.value.status == 401
    with pytest.raises(LayerHopApiError) as ei:
        lh.webhooks.trigger("order.filled")
    assert (ei.value.code, ei.value.status) == ("FORBIDDEN", 403)


@pytest.mark.anyio
async def test_async_streams(api):
    sse(api, "/v1/orders/q_1/events", ChunkStream(frames("order", ORDER, {**ORDER, "status": "filled"})))
    sse(api, f"/v1/checkout/sessions/{CS}/events", ChunkStream(frames("session", CHECKOUT_SESSION)))
    body = ChunkStream(frames("event", EVENT, {**EVENT, "id": "evt_2"}, {**EVENT, "id": "evt_3"}))
    sse(api, "/v1/webhooks/stream", body)
    api.on("POST", "/v1/webhooks/trigger", {"eventId": "evt_9", "deliveries": 0, "payload": EVENT}, status=202)
    async with amake(api, api_key="lh_test_x") as lh:
        assert [o["status"] async for o in lh.stream_order("q_1")] == ["submitted", "filled"]
        assert api.last.headers["accept"] == "text/event-stream"
        assert [s["id"] async for s in lh.checkout.stream(CS)] == [CS]
        it = lh.webhooks.stream()
        async for e in it:
            assert e["id"] == "evt_1"
            break
        await it.aclose()  # type: ignore[attr-defined]
        assert body.closed and body.sent < len(body.chunks)
        assert (await lh.webhooks.trigger("checkout.session.completed"))["eventId"] == "evt_9"
        assert api.last_json() == {"type": "checkout.session.completed"}


@pytest.mark.anyio
async def test_async_stream_error(api):
    api.on("GET", f"/v1/checkout/sessions/{CS}/events",
           {"error": {"code": "NOT_FOUND", "message": "No session", "requestId": "r2"}}, status=404)
    lh = amake(api)
    with pytest.raises(LayerHopApiError) as ei:
        async for _ in lh.checkout.stream(CS):
            pass
    assert (ei.value.code, ei.value.status, ei.value.request_id) == ("NOT_FOUND", 404, "r2")
    await lh.aclose()
