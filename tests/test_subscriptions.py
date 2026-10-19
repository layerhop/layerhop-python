import httpx
import pytest

from layerhop import AsyncLayerHop, LayerHop, LayerHopApiError

from .conftest import INVOICE, SUBSCRIPTION, FakeApi

SID = SUBSCRIPTION["id"]
RECIPIENT = "0x2222222222222222222222222222222222222222"


def make(api: FakeApi, **kw) -> LayerHop:
    return LayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def amake(api: FakeApi, **kw) -> AsyncLayerHop:
    return AsyncLayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def test_create_sends_body_and_parses(api):
    api.on("POST", "/v1/subscriptions", SUBSCRIPTION, status=201)
    lh = make(api, api_key="lh_test_x")
    sub = lh.subscriptions.create(
        "ada@example.com", "month", interval_count=3, amount="49000000", settle_chain=8453, settle_token="USDC",
        recipient=RECIPIENT, description="Pro plan", customer_name="Ada Lovelace", merchant_name="Studio Nine",
        memo=None, days_until_due=5, start_at="2026-11-01T00:00:00.000Z", metadata={"plan": "pro"})
    assert api.last.method == "POST" and api.last.headers["x-api-key"] == "lh_test_x"
    assert api.last_json() == {
        "customerEmail": "ada@example.com", "interval": "month", "intervalCount": 3, "amount": "49000000",
        "settleChain": "8453", "settleToken": "USDC", "recipient": RECIPIENT, "description": "Pro plan",
        "customerName": "Ada Lovelace", "merchantName": "Studio Nine", "daysUntilDue": 5,
        "startAt": "2026-11-01T00:00:00.000Z", "metadata": {"plan": "pro"},
    }
    assert sub["object"] == "subscription" and sub["status"] == "active" and sub["interval"] == "month"
    assert sub["amount"] == "49000000" and sub["settlement"]["symbol"] == "USDC"
    assert sub["cancelAtPeriodEnd"] is False and sub["latestInvoiceId"].startswith("inv_")


def test_create_from_product(api):
    api.on("POST", "/v1/subscriptions", {**SUBSCRIPTION, "productId": "prod_1"}, status=201)
    sub = make(api, api_key="k").subscriptions.create("ada@example.com", "year", product_id="prod_1")
    assert api.last_json() == {"customerEmail": "ada@example.com", "interval": "year", "productId": "prod_1"}
    assert sub["productId"] == "prod_1"


def test_create_rejects_non_string_amount(api):
    with pytest.raises(TypeError):
        make(api).subscriptions.create("a@b.co", "month", amount=49)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        make(api).subscriptions.update(SID, amount=49)
    assert api.requests == []


def test_get_list_and_encoding(api):
    api.on("GET", f"/v1/subscriptions/{SID}", SUBSCRIPTION)
    api.on("GET", "/v1/subscriptions/sub%2Fx", SUBSCRIPTION)
    api.on("GET", "/v1/subscriptions", {"subscriptions": [SUBSCRIPTION], "nextCursor": "c2"})
    lh = make(api, api_key="k")
    assert lh.subscriptions.get(SID)["id"] == SID
    lh.subscriptions.get("sub/x")
    assert api.last.url.raw_path.decode() == "/v1/subscriptions/sub%2Fx"
    page = lh.subscriptions.list(status="past_due", customer_email="ada@example.com", cursor="c1", limit=10)
    assert dict(api.last.url.params) == {"status": "past_due", "customerEmail": "ada@example.com", "cursor": "c1", "limit": "10"}
    assert page["nextCursor"] == "c2" and page["subscriptions"][0]["id"] == SID
    lh.subscriptions.list()
    assert dict(api.last.url.params) == {}


def test_update_sends_only_passed_fields(api):
    api.on("PATCH", f"/v1/subscriptions/{SID}", {**SUBSCRIPTION, "cancelAtPeriodEnd": True})
    lh = make(api, api_key="k")
    sub = lh.subscriptions.update(SID, amount="59000000", memo=None, cancel_at_period_end=True)
    assert api.last.method == "PATCH"
    assert api.last_json() == {"amount": "59000000", "memo": None, "cancelAtPeriodEnd": True}
    assert sub["cancelAtPeriodEnd"] is True
    lh.subscriptions.update(SID, customer_email="new@example.com", days_until_due=0, metadata=None)
    assert api.last_json() == {"customerEmail": "new@example.com", "daysUntilDue": 0, "metadata": None}


def test_cancel_pause_resume(api):
    api.on("POST", f"/v1/subscriptions/{SID}/cancel", {**SUBSCRIPTION, "status": "canceled", "cancellationReason": "requested"})
    api.on("POST", f"/v1/subscriptions/{SID}/pause", {**SUBSCRIPTION, "status": "paused", "nextInvoiceAt": None})
    api.on("POST", f"/v1/subscriptions/{SID}/resume", SUBSCRIPTION)
    lh = make(api, api_key="k")
    sub = lh.subscriptions.cancel(SID)
    assert api.last_json() == {} and sub["status"] == "canceled" and sub["cancellationReason"] == "requested"
    lh.subscriptions.cancel(SID, at_period_end=True)
    assert api.last_json() == {"atPeriodEnd": True}
    paused = lh.subscriptions.pause(SID)
    assert api.last_json() == {} and paused["status"] == "paused" and paused["nextInvoiceAt"] is None
    assert lh.subscriptions.resume(SID)["status"] == "active"
    assert api.last.method == "POST" and api.last_json() == {}


def test_invoices_unwraps_and_carries_subscription_id(api):
    api.on("GET", f"/v1/subscriptions/{SID}/invoices", {"invoices": [{**INVOICE, "subscriptionId": SID}]})
    invs = make(api, api_key="k").subscriptions.invoices(SID)
    assert len(invs) == 1 and invs[0]["subscriptionId"] == SID and invs[0]["number"] == "INV-0001"


def test_conflict_error(api):
    api.on("POST", f"/v1/subscriptions/{SID}/pause",
           {"error": {"code": "CONFLICT", "message": "Only an active subscription can be paused", "requestId": "r3"}}, status=409)
    with pytest.raises(LayerHopApiError) as ei:
        make(api, api_key="k").subscriptions.pause(SID)
    assert (ei.value.code, ei.value.status, ei.value.request_id) == ("CONFLICT", 409, "r3")


def test_trigger_subscription_event(api):
    payload = {"id": "evt_1", "type": "subscription.renewed", "livemode": False, "sample": True,
               "createdAt": "2026-10-19T10:00:00.000Z", "data": {"subscription": SUBSCRIPTION, "invoice": INVOICE}}
    api.on("POST", "/v1/webhooks/trigger", {"eventId": "evt_1", "deliveries": 1, "payload": payload}, status=201)
    r = make(api, api_key="lh_test_k").webhooks.trigger("subscription.renewed")
    assert api.last_json() == {"type": "subscription.renewed"}
    assert r["payload"]["data"]["subscription"]["id"] == SID


@pytest.mark.anyio
async def test_async_subscriptions(api):
    api.on("POST", "/v1/subscriptions", SUBSCRIPTION, status=201)
    api.on("GET", f"/v1/subscriptions/{SID}", SUBSCRIPTION)
    api.on("GET", "/v1/subscriptions", {"subscriptions": [], "nextCursor": None})
    api.on("PATCH", f"/v1/subscriptions/{SID}", SUBSCRIPTION)
    api.on("POST", f"/v1/subscriptions/{SID}/cancel", {**SUBSCRIPTION, "cancelAtPeriodEnd": True})
    api.on("POST", f"/v1/subscriptions/{SID}/pause", {**SUBSCRIPTION, "status": "paused"})
    api.on("POST", f"/v1/subscriptions/{SID}/resume", SUBSCRIPTION)
    api.on("GET", f"/v1/subscriptions/{SID}/invoices", {"invoices": []})
    async with amake(api, api_key="k") as lh:
        await lh.subscriptions.create("ada@example.com", "week", product_id="prod_1")
        assert api.last_json() == {"customerEmail": "ada@example.com", "interval": "week", "productId": "prod_1"}
        assert (await lh.subscriptions.get(SID))["id"] == SID
        page = await lh.subscriptions.list(status="paused")
        assert page["subscriptions"] == [] and dict(api.last.url.params) == {"status": "paused"}
        await lh.subscriptions.update(SID, description="Team plan")
        assert api.last_json() == {"description": "Team plan"}
        assert (await lh.subscriptions.cancel(SID, at_period_end=True))["cancelAtPeriodEnd"] is True
        assert api.last_json() == {"atPeriodEnd": True}
        assert (await lh.subscriptions.pause(SID))["status"] == "paused"
        assert (await lh.subscriptions.resume(SID))["status"] == "active"
        assert await lh.subscriptions.invoices(SID) == []
