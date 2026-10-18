import httpx
import pytest

from layerhop import AsyncLayerHop, LayerHop, LayerHopApiError

from .conftest import CHECKOUT_SESSION, INVOICE, FakeApi

IID = INVOICE["id"]
ITEMS = [{"description": "Design work", "quantity": 2, "unitAmount": "500000000"}]


def make(api: FakeApi, **kw) -> LayerHop:
    return LayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def amake(api: FakeApi, **kw) -> AsyncLayerHop:
    return AsyncLayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def test_create_sends_body_and_parses_invoice(api):
    api.on("POST", "/v1/invoices", INVOICE, status=201)
    lh = make(api, api_key="lh_live_x")
    inv = lh.invoices.create(ITEMS, "base", "USDC", "0x2222222222222222222222222222222222222222",
                             customer_email="ap@client.example", customer_name="Client Co", merchant_name="Acme",
                             due_at="2026-11-01", send=True)
    assert api.last.method == "POST" and api.last.headers["x-api-key"] == "lh_live_x"
    assert api.last_json() == {
        "customerEmail": "ap@client.example", "customerName": "Client Co", "merchantName": "Acme",
        "lineItems": ITEMS, "settleChain": "base", "settleToken": "USDC",
        "recipient": "0x2222222222222222222222222222222222222222", "dueAt": "2026-11-01", "send": True,
    }
    assert inv["object"] == "invoice" and inv["number"] == "INV-0001" and inv["status"] == "open"
    assert inv["amount"] == "1000000000" and inv["url"].endswith(f"/invoice/{IID}") and inv["memo"] is None


def test_create_minimal_numeric_chain(api):
    api.on("POST", "/v1/invoices", {**INVOICE, "status": "draft"}, status=201)
    make(api).invoices.create(ITEMS, 8453, "USDC", "0x22")
    assert api.last_json() == {"lineItems": ITEMS, "settleChain": "8453", "settleToken": "USDC", "recipient": "0x22"}


def test_create_rejects_non_string_unit_amount(api):
    with pytest.raises(TypeError):
        make(api).invoices.create([{"description": "x", "quantity": 1, "unitAmount": 5}], "base", "USDC", "0x22")  # type: ignore[list-item]


def test_get_list_and_encoding(api):
    api.on("GET", f"/v1/invoices/{IID}", INVOICE)
    api.on("GET", "/v1/invoices/inv%2Fx", INVOICE)
    api.on("GET", "/v1/invoices", {"invoices": [INVOICE], "nextCursor": "c2"})
    lh = make(api, api_key="k")
    assert lh.invoices.get(IID)["customerEmail"] == "ap@client.example"
    lh.invoices.get("inv/x")
    assert api.last.url.raw_path.decode() == "/v1/invoices/inv%2Fx"
    page = lh.invoices.list(status="open", cursor="c1", limit=10)
    assert dict(api.last.url.params) == {"status": "open", "cursor": "c1", "limit": "10"}
    assert page["nextCursor"] == "c2" and page["invoices"][0]["id"] == IID
    lh.invoices.list()
    assert dict(api.last.url.params) == {}


def test_update_is_partial(api):
    api.on("PATCH", f"/v1/invoices/{IID}", {**INVOICE, "status": "draft", "memo": None})
    lh = make(api, api_key="k")
    lh.invoices.update(IID, memo=None, due_at="2026-12-01")
    assert api.last.method == "PATCH" and api.last_json() == {"memo": None, "dueAt": "2026-12-01"}
    lh.invoices.update(IID, line_items=ITEMS, settle_chain=42161)
    assert api.last_json() == {"lineItems": ITEMS, "settleChain": "42161"}


def test_send_void_public_and_pay(api):
    api.on("POST", f"/v1/invoices/{IID}/send", INVOICE)
    api.on("POST", f"/v1/invoices/{IID}/void", {**INVOICE, "status": "void", "voidedAt": "2026-10-19T00:00:00.000Z"})
    public = {k: v for k, v in INVOICE.items() if k not in ("customerEmail", "recipient", "sessionId", "sentAt",
                                                            "receiptSentAt", "voidedAt", "updatedAt")}
    api.on("GET", f"/v1/invoices/{IID}/public", public)
    api.on("POST", f"/v1/invoices/{IID}/pay", {"sessionId": CHECKOUT_SESSION["id"], "url": CHECKOUT_SESSION["url"]}, status=201)
    lh = make(api, api_key="k")
    assert lh.invoices.send(IID)["sentAt"] is not None
    assert api.last.method == "POST" and api.last_json() == {}
    assert lh.invoices.void(IID)["status"] == "void"
    anon = make(api)
    pv = anon.invoices.public_view(IID)
    assert "x-api-key" not in api.last.headers and "customerEmail" not in pv and pv["lineItems"] == ITEMS
    pay = anon.invoices.pay(IID)
    assert api.last.method == "POST" and pay == {"sessionId": CHECKOUT_SESSION["id"], "url": CHECKOUT_SESSION["url"]}


def test_paid_invoice_conflict(api):
    api.on("POST", f"/v1/invoices/{IID}/pay",
           {"error": {"code": "CONFLICT", "message": "This invoice is already paid", "requestId": "r1"}}, status=409)
    with pytest.raises(LayerHopApiError) as ei:
        make(api).invoices.pay(IID)
    assert (ei.value.code, ei.value.status) == ("CONFLICT", 409)


def test_session_invoice_fields_parsed(api):
    api.on("GET", f"/v1/checkout/sessions/{CHECKOUT_SESSION['id']}",
           {**CHECKOUT_SESSION, "invoiceId": IID, "refundedAmount": "0"})
    s = make(api).checkout.get(CHECKOUT_SESSION["id"])
    assert s["invoiceId"] == IID and s["refundedAmount"] == "0"


@pytest.mark.anyio
async def test_async_invoices(api):
    api.on("POST", "/v1/invoices", INVOICE, status=201)
    api.on("GET", f"/v1/invoices/{IID}", INVOICE)
    api.on("GET", "/v1/invoices", {"invoices": [], "nextCursor": None})
    api.on("PATCH", f"/v1/invoices/{IID}", {**INVOICE, "memo": "Thanks"})
    api.on("POST", f"/v1/invoices/{IID}/send", INVOICE)
    api.on("POST", f"/v1/invoices/{IID}/void", {**INVOICE, "status": "void"})
    api.on("GET", f"/v1/invoices/{IID}/public", INVOICE)
    api.on("POST", f"/v1/invoices/{IID}/pay", {"sessionId": "cs_1", "url": "https://layerhop.com/pay/cs_1"})
    async with amake(api, api_key="k") as lh:
        inv = await lh.invoices.create(ITEMS, "base", "USDC", "0x22", memo="Thanks")
        assert api.last_json()["memo"] == "Thanks" and inv["id"] == IID
        assert (await lh.invoices.get(IID))["number"] == "INV-0001"
        page = await lh.invoices.list(status="paid")
        assert page["invoices"] == [] and dict(api.last.url.params) == {"status": "paid"}
        assert (await lh.invoices.update(IID, memo="Thanks"))["memo"] == "Thanks"
        assert api.last_json() == {"memo": "Thanks"}
        await lh.invoices.send(IID)
        assert (await lh.invoices.void(IID))["status"] == "void"
        assert (await lh.invoices.public_view(IID))["id"] == IID
        assert (await lh.invoices.pay(IID))["sessionId"] == "cs_1"
