import httpx
import pytest

from layerhop import AsyncLayerHop, LayerHop, LayerHopApiError

from .conftest import DEPOSIT_ADDRESS, DEPOSIT_ORDER, FakeApi

DID = DEPOSIT_ADDRESS["id"]
ESTIMATE = {"amount": "100000000", "dstAmount": "99720000", "dstAmountMin": "99221400", "estimatedSeconds": 12}
RECIPIENT = "0x2222222222222222222222222222222222222222"
REFUND_TO = "0x1111111111111111111111111111111111111111"


def make(api: FakeApi, **kw) -> LayerHop:
    return LayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def amake(api: FakeApi, **kw) -> AsyncLayerHop:
    return AsyncLayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def test_create_sends_body_and_parses_estimate(api):
    api.on("POST", "/v1/deposit-addresses", {**DEPOSIT_ADDRESS, "estimate": ESTIMATE}, status=201)
    lh = make(api, api_key="lh_test_x")
    da = lh.deposit_addresses.create("base", "USDC", 42161, "USDC", RECIPIENT, REFUND_TO,
                                     reusable=True, amount="100000000", label="user_42", metadata={"userId": "42"},
                                     integrator="acme", integrator_fee_bps=10)
    assert api.last.method == "POST" and api.last.headers["x-api-key"] == "lh_test_x"
    assert api.last_json() == {
        "srcChain": "base", "srcToken": "USDC", "dstChain": "42161", "dstToken": "USDC", "recipient": RECIPIENT,
        "refundTo": REFUND_TO, "reusable": True, "amount": "100000000", "label": "user_42",
        "metadata": {"userId": "42"}, "integrator": "acme", "integratorFeeBps": 10,
    }
    assert da["object"] == "deposit_address" and da["status"] == "active" and da["provider"] == "sandbox"
    assert da["address"].startswith("0x") and da["chainId"] == 8453 and da["amount"] is None
    assert da["fees"] == {"ourFeeBps": 20, "integratorFeeBps": 0, "integrator": None}
    assert da["estimate"]["dstAmountMin"] == "99221400" and da["estimate"]["estimatedSeconds"] == 12


def test_create_minimal_and_client_integrator_default(api):
    api.on("POST", "/v1/deposit-addresses", {**DEPOSIT_ADDRESS, "estimate": ESTIMATE}, status=201)
    make(api).deposit_addresses.create(8453, "USDC", "arbitrum", "USDC", RECIPIENT, REFUND_TO)
    assert api.last_json() == {"srcChain": "8453", "srcToken": "USDC", "dstChain": "arbitrum", "dstToken": "USDC",
                               "recipient": RECIPIENT, "refundTo": REFUND_TO}
    make(api, integrator="acme", integrator_fee_bps=5).deposit_addresses.create(
        "base", "USDC", "arbitrum", "USDC", RECIPIENT, REFUND_TO, reusable=False, amount="5000000")
    body = api.last_json()
    assert body["integrator"] == "acme" and body["integratorFeeBps"] == 5
    assert body["reusable"] is False and body["amount"] == "5000000"


def test_create_rejects_non_string_amount(api):
    with pytest.raises(TypeError):
        make(api).deposit_addresses.create("base", "USDC", "arbitrum", "USDC", RECIPIENT, REFUND_TO, amount=5)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        make(api).deposit_addresses.simulate(DID, 5)  # type: ignore[arg-type]
    assert api.requests == []


def test_live_mode_disabled_is_forbidden(api):
    api.on("POST", "/v1/deposit-addresses", {"error": {
        "code": "FORBIDDEN", "message": "Deposit addresses are not enabled for live mode yet.", "requestId": "r1"}}, status=403)
    with pytest.raises(LayerHopApiError) as ei:
        make(api, api_key="lh_live_x").deposit_addresses.create("base", "USDC", "arbitrum", "USDC", RECIPIENT, REFUND_TO)
    assert (ei.value.code, ei.value.status, ei.value.request_id) == ("FORBIDDEN", 403, "r1")


def test_get_list_and_encoding(api):
    api.on("GET", f"/v1/deposit-addresses/{DID}", {**DEPOSIT_ADDRESS, "depositCount": 1, "deposits": [DEPOSIT_ORDER]})
    api.on("GET", "/v1/deposit-addresses/da%2Fx", {**DEPOSIT_ADDRESS, "deposits": []})
    api.on("GET", "/v1/deposit-addresses", {"depositAddresses": [DEPOSIT_ADDRESS], "nextCursor": "c2"})
    lh = make(api, api_key="k")
    da = lh.deposit_addresses.get(DID)
    assert da["depositCount"] == 1 and da["deposits"][0]["depositAddressId"] == DID
    assert da["deposits"][0]["amount"] == "25000000"
    lh.deposit_addresses.get("da/x")
    assert api.last.url.raw_path.decode() == "/v1/deposit-addresses/da%2Fx"
    page = lh.deposit_addresses.list(status="active", label="user_42", cursor="c1", limit=10)
    assert dict(api.last.url.params) == {"status": "active", "label": "user_42", "cursor": "c1", "limit": "10"}
    assert page["nextCursor"] == "c2" and page["depositAddresses"][0]["id"] == DID
    lh.deposit_addresses.list()
    assert dict(api.last.url.params) == {}


def test_refresh_disable_and_simulate(api):
    api.on("POST", f"/v1/deposit-addresses/{DID}/refresh", DEPOSIT_ADDRESS, status=202)
    api.on("POST", f"/v1/deposit-addresses/{DID}/disable", {**DEPOSIT_ADDRESS, "status": "disabled"})
    api.on("POST", f"/v1/deposit-addresses/{DID}/simulate", {"order": DEPOSIT_ORDER}, status=201)
    lh = make(api, api_key="lh_test_k")
    assert lh.deposit_addresses.refresh(DID)["status"] == "active"
    assert api.last.method == "POST" and api.last_json() == {}
    assert lh.deposit_addresses.disable(DID)["status"] == "disabled"
    assert api.last_json() == {}
    sim = lh.deposit_addresses.simulate(DID, "25000000")
    assert api.last_json() == {"amount": "25000000"}
    assert sim["order"]["provider"] == "sandbox" and sim["order"]["depositAddressId"] == DID


def test_disabled_address_conflict(api):
    api.on("POST", f"/v1/deposit-addresses/{DID}/refresh",
           {"error": {"code": "CONFLICT", "message": "This deposit address is disabled", "requestId": "r2"}}, status=409)
    with pytest.raises(LayerHopApiError) as ei:
        make(api, api_key="k").deposit_addresses.refresh(DID)
    assert (ei.value.code, ei.value.status) == ("CONFLICT", 409)


def test_order_deposit_address_id_parsed(api):
    api.on("GET", "/v1/orders", {"orders": [DEPOSIT_ORDER], "nextCursor": None})
    page = make(api).list_orders(address=RECIPIENT)
    assert page["orders"][0]["depositAddressId"] == DID


@pytest.mark.anyio
async def test_async_deposit_addresses(api):
    api.on("POST", "/v1/deposit-addresses", {**DEPOSIT_ADDRESS, "estimate": ESTIMATE}, status=201)
    api.on("GET", f"/v1/deposit-addresses/{DID}", {**DEPOSIT_ADDRESS, "deposits": []})
    api.on("GET", "/v1/deposit-addresses", {"depositAddresses": [], "nextCursor": None})
    api.on("POST", f"/v1/deposit-addresses/{DID}/refresh", DEPOSIT_ADDRESS, status=202)
    api.on("POST", f"/v1/deposit-addresses/{DID}/disable", {**DEPOSIT_ADDRESS, "status": "disabled"})
    api.on("POST", f"/v1/deposit-addresses/{DID}/simulate", {"order": DEPOSIT_ORDER}, status=201)
    async with amake(api, api_key="k") as lh:
        da = await lh.deposit_addresses.create("base", "USDC", "arbitrum", "USDC", RECIPIENT, REFUND_TO, label="u1")
        assert api.last_json()["label"] == "u1" and da["estimate"]["amount"] == "100000000"
        assert (await lh.deposit_addresses.get(DID))["deposits"] == []
        page = await lh.deposit_addresses.list(status="disabled")
        assert page["depositAddresses"] == [] and dict(api.last.url.params) == {"status": "disabled"}
        assert (await lh.deposit_addresses.refresh(DID))["id"] == DID
        assert (await lh.deposit_addresses.disable(DID))["status"] == "disabled"
        assert (await lh.deposit_addresses.simulate(DID, "25000000"))["order"]["depositAddressId"] == DID
        assert api.last_json() == {"amount": "25000000"}
