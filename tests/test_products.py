import httpx
import pytest

import layerhop
from layerhop import AsyncLayerHop, LayerHop, LayerHopApiError

from .conftest import CHECKOUT_PRODUCT, CHECKOUT_SESSION, FakeApi

PID = CHECKOUT_PRODUCT["id"]
SESSION = {**CHECKOUT_SESSION, "productId": PID}


def make(api: FakeApi, **kw) -> LayerHop:
    return LayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def amake(api: FakeApi, **kw) -> AsyncLayerHop:
    return AsyncLayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def test_version():
    assert layerhop.__version__ == "0.6.0"


def test_create_sends_body_and_parses_product(api):
    api.on("POST", "/v1/checkout/products", CHECKOUT_PRODUCT, status=201)
    lh = make(api, api_key="lh_live_x")
    p = lh.checkout.products.create("Pro plan", "49000000", "base", "USDC", "0x2222222222222222222222222222222222222222",
                                    description="1 month", success_url="https://shop.example.com/thanks",
                                    allowed_origins=["https://shop.example.com"], expires_in_minutes=60)
    assert api.last.method == "POST" and api.last.headers["x-api-key"] == "lh_live_x"
    assert api.last_json() == {
        "name": "Pro plan", "description": "1 month", "amount": "49000000", "settleChain": "base",
        "settleToken": "USDC", "recipient": "0x2222222222222222222222222222222222222222",
        "successUrl": "https://shop.example.com/thanks", "expiresInMinutes": 60,
        "allowedOrigins": ["https://shop.example.com"],
    }
    assert p["object"] == "checkout.product" and p["id"] == PID and p["active"] is True
    assert p["url"] == f"https://layerhop.com/buy/{PID}" and p["settlement"]["symbol"] == "USDC"
    assert p["merchantName"] is None and p["allowedOrigins"] == ["https://shop.example.com"]


def test_create_minimal_numeric_chain_and_active(api):
    api.on("POST", "/v1/checkout/products", CHECKOUT_PRODUCT, status=201)
    make(api).checkout.products.create("Tip", "1000000", 8453, "USDC", "0x22", active=False)
    assert api.last_json() == {"name": "Tip", "amount": "1000000", "settleChain": "8453", "settleToken": "USDC",
                               "recipient": "0x22", "active": False}


def test_create_rejects_non_string_amount(api):
    with pytest.raises(TypeError):
        make(api).checkout.products.create("Tip", 1000000, "base", "USDC", "0x22")  # type: ignore[arg-type]


def test_get_public_and_encoded(api):
    public = {k: CHECKOUT_PRODUCT[k] for k in ("id", "object", "livemode", "active", "name", "description",
                                              "merchantName", "amount", "settlement", "url")}
    api.on("GET", f"/v1/checkout/products/{PID}", public)
    api.on("GET", "/v1/checkout/products/prod%2Fx", public)
    lh = make(api)
    p = lh.checkout.products.get(PID)
    assert api.last.method == "GET" and "x-api-key" not in api.last.headers
    assert p["amount"] == "49000000" and "recipient" not in p
    lh.checkout.products.get("prod/x")
    assert api.last.url.raw_path.decode() == "/v1/checkout/products/prod%2Fx"


def test_list_query(api):
    api.on("GET", "/v1/checkout/products", {"products": [CHECKOUT_PRODUCT], "nextCursor": "c2"})
    lh = make(api, api_key="lh_test_x")
    page = lh.checkout.products.list(active=True, cursor="c1", limit=10)
    assert dict(api.last.url.params) == {"active": "true", "cursor": "c1", "limit": "10"}
    assert page["nextCursor"] == "c2" and page["products"][0]["id"] == PID
    lh.checkout.products.list(active=False)
    assert dict(api.last.url.params) == {"active": "false"}
    lh.checkout.products.list()
    assert dict(api.last.url.params) == {}


def test_update_is_partial(api):
    api.on("PATCH", f"/v1/checkout/products/{PID}", {**CHECKOUT_PRODUCT, "active": False, "description": None})
    lh = make(api, api_key="k")
    p = lh.checkout.products.update(PID, active=False)
    assert api.last.method == "PATCH" and api.last_json() == {"active": False}
    assert p["active"] is False
    lh.checkout.products.update(PID, description=None, amount="50000000", settle_chain=42161, allowed_origins=[])
    assert api.last_json() == {"description": None, "amount": "50000000", "settleChain": "42161", "allowedOrigins": []}
    with pytest.raises(TypeError):
        lh.checkout.products.update(PID, amount=5)


def test_start_session(api):
    api.on("POST", f"/v1/checkout/products/{PID}/sessions", SESSION, status=201)
    lh = make(api)
    s = lh.checkout.products.start_session(PID, reference="order_1042", metadata={"plan": "pro"})
    assert api.last.method == "POST" and "x-api-key" not in api.last.headers
    assert api.last_json() == {"reference": "order_1042", "metadata": {"plan": "pro"}}
    assert s["object"] == "checkout.session" and s["productId"] == PID
    lh.checkout.products.start_session(PID)
    assert api.last_json() == {}


def test_session_product_id_parsed(api):
    api.on("GET", f"/v1/checkout/sessions/{CHECKOUT_SESSION['id']}", {**CHECKOUT_SESSION, "productId": None})
    assert make(api).checkout.get(CHECKOUT_SESSION["id"])["productId"] is None


def test_inactive_product_conflict(api):
    api.on("POST", f"/v1/checkout/products/{PID}/sessions",
           {"error": {"code": "CONFLICT", "message": "Product is inactive", "requestId": "r1"}}, status=409)
    with pytest.raises(LayerHopApiError) as ei:
        make(api).checkout.products.start_session(PID)
    assert (ei.value.code, ei.value.status) == ("CONFLICT", 409)


@pytest.mark.anyio
async def test_async_products(api):
    api.on("POST", "/v1/checkout/products", CHECKOUT_PRODUCT, status=201)
    api.on("GET", f"/v1/checkout/products/{PID}", CHECKOUT_PRODUCT)
    api.on("GET", "/v1/checkout/products", {"products": [], "nextCursor": None})
    api.on("PATCH", f"/v1/checkout/products/{PID}", {**CHECKOUT_PRODUCT, "name": "Pro"})
    api.on("POST", f"/v1/checkout/products/{PID}/sessions", SESSION, status=201)
    async with amake(api, api_key="k") as lh:
        p = await lh.checkout.products.create("Pro plan", "49000000", "base", "USDC", "0x22", merchant_name="Acme",
                                              cancel_url="https://x/c")
        assert api.last_json()["merchantName"] == "Acme" and api.last_json()["cancelUrl"] == "https://x/c"
        assert p["id"] == PID
        assert (await lh.checkout.products.get(PID))["amount"] == "49000000"
        page = await lh.checkout.products.list(active=True, limit=5)
        assert page["products"] == [] and dict(api.last.url.params) == {"active": "true", "limit": "5"}
        assert (await lh.checkout.products.update(PID, name="Pro"))["name"] == "Pro"
        assert api.last.method == "PATCH" and api.last_json() == {"name": "Pro"}
        s = await lh.checkout.products.start_session(PID, reference="o1")
        assert api.last_json() == {"reference": "o1"} and s["productId"] == PID
