"""Splits, tip jars, payouts and recurring orders."""

import httpx
import pytest

from layerhop import AsyncLayerHop, LayerHop

from .conftest import SVM_TX, FakeApi


def make(api: FakeApi, **kw) -> LayerHop:
    return LayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


def amake(api: FakeApi, **kw) -> AsyncLayerHop:
    return AsyncLayerHop(base_url="http://test", transport=httpx.MockTransport(api), **kw)


SID = "spl_01k8x2m3n4p5q6r7s8t9v0w1x2"
SPLIT = {
    "id": SID, "url": f"https://layerhop.com/split/{SID}", "status": "open", "note": "Dinner at Luigi's",
    "recipient": "0x1111111111111111111111111111111111111111", "recipientName": "alice.eth", "chainId": 8453,
    "chain": "base", "token": {"address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "symbol": "USDC", "decimals": 6},
    "total": "120000000", "collected": "30000000", "paidCount": 1,
    "shares": [{"index": i, "label": "", "amount": "30000000", "received": "30000000" if i == 0 else "0",
                "status": "paid" if i == 0 else "unpaid", "payments": 1 if i == 0 else 0, "pending": 0} for i in range(4)],
    "createdAt": "2026-10-28T12:00:00.000Z", "updatedAt": "2026-10-28T12:00:00.000Z",
}
TIP_JAR = {"address": "0x1111111111111111111111111111111111111111", "tippers": 42, "tips": 57,
           "messages": [{"text": "Love the stream!", "at": "2026-10-28T12:00:00.000Z"}]}
PAYOUT_TOKEN = {"chainId": 8453, "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "symbol": "USDC", "decimals": 6}
PAYOUT_PLAN = {
    "source": {"chainId": 8453, "chain": "base", "sender": "0xAbC", "token": PAYOUT_TOKEN},
    "rows": [{"index": 0, "line": 0, "input": {"recipient": "bob.eth", "amount": "25", "token": "USDC", "chain": "base"},
              "ok": True, "recipient": {"address": "0x3333", "name": "bob.eth"}, "chainId": 8453, "chain": "base",
              "token": PAYOUT_TOKEN, "amount": "25000000", "kind": "transfer"},
             {"index": 1, "line": 0, "input": {"recipient": "x", "amount": "1", "token": "USDC", "chain": "base"},
              "ok": False, "error": {"code": "NOT_FOUND", "message": "Name not found"}}],
    "transfers": [{"chainId": 8453, "token": PAYOUT_TOKEN["address"], "rows": [0], "total": "25000000"}],
    "routes": [], "transferTotal": "25000000",
    "totals": [{**PAYOUT_TOKEN, "token": PAYOUT_TOKEN["address"], "amount": "25000000", "formatted": "25", "rows": 1}],
    "valid": 1, "invalid": 1, "warnings": [],
}
WALLET = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
RO_BUILD = {
    "object": "recurring_order_build", "livemode": False, "provider": "sandbox", "chainId": 7565164, "wallet": WALLET,
    "srcToken": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "dstToken": "So11111111111111111111111111111111111111112",
    "amount": "700000000", "amountPerOrder": "100000000", "orders": 7, "intervalSeconds": 86400,
    "fees": {"ourFeeBps": 0, "integratorFeeBps": 0}, "requestId": "req_1", "tx": SVM_TX,
}
RO = {
    "id": "RoAcct111", "object": "recurring_order", "provider": "jupiter", "chainId": 7565164, "status": "active",
    "wallet": WALLET, "srcToken": RO_BUILD["srcToken"], "dstToken": RO_BUILD["dstToken"], "amount": "700000000",
    "amountPerOrder": "100000000", "orders": 7, "ordersFilled": 1, "intervalSeconds": 86400, "spentAmount": "100000000",
    "withdrawnAmount": "0", "receivedAmount": "520000000", "openTxHash": "5open", "closeTxHash": None,
    "createdAt": "2026-10-28T12:00:00.000Z",
    "fills": [{"txHash": "5fill", "amount": "100000000", "dstAmount": "520000000", "feeAmount": "100000",
               "feeToken": None, "filledAt": "2026-10-28T12:00:00.000Z"}],
}


def test_split_create_get_update(api):
    api.on("POST", "/v1/splits", {**SPLIT, "editToken": "sek_1", "editUrl": f"https://layerhop.com/split/{SID}#k=sek_1"},
           status=201)
    api.on("GET", f"/v1/splits/{SID}", SPLIT)
    api.on("PATCH", f"/v1/splits/{SID}", {**SPLIT, "status": "closed", "note": None})
    lh = make(api)
    s = lh.splits.create("alice.eth", "base", "USDC", "120000000", participants=4, note="Dinner at Luigi's")
    assert api.last_json() == {"recipient": "alice.eth", "chain": "base", "token": "USDC", "total": "120000000",
                               "participants": 4, "note": "Dinner at Luigi's"}
    assert "x-api-key" not in api.last.headers
    assert s["editToken"] == "sek_1" and s["shares"][0]["status"] == "paid"
    lh.splits.create("alice.eth", 8453, "USDC", "3", shares=[{"label": "Bo", "amount": "1"}, {"label": "Al", "amount": "2"}])
    assert api.last_json()["shares"][1] == {"label": "Al", "amount": "2"} and api.last_json()["chain"] == "8453"
    assert lh.splits.get(SID)["collected"] == "30000000"
    u = lh.splits.update(SID, "sek_1", note=None, status="closed")
    assert api.last.method == "PATCH" and api.last.headers["x-edit-token"] == "sek_1"
    assert api.last_json() == {"note": None, "status": "closed"}
    assert u["status"] == "closed" and u["note"] is None
    lh.splits.update(SID, "sek_1", labels=["Bo", "Al", "Cy", "Di"])
    assert api.last_json() == {"labels": ["Bo", "Al", "Cy", "Di"]}
    with pytest.raises(TypeError):
        lh.splits.create("alice.eth", "base", "USDC", 120000000, participants=4)  # type: ignore[arg-type]


def test_tip_jar(api):
    api.on("GET", f"/v1/tip-jars/{TIP_JAR['address']}", TIP_JAR)
    t = make(api).tip_jars.get(TIP_JAR["address"])
    assert t["tippers"] == 42 and t["messages"][0]["text"] == "Love the stream!"


def test_payout_plan_and_transfers(api):
    api.on("POST", "/v1/payouts/plan", PAYOUT_PLAN)
    api.on("POST", "/v1/payouts/transfers", {"vm": "evm", "chainId": 8453, "token": PAYOUT_TOKEN,
                                             "calls": [{"to": PAYOUT_TOKEN["address"], "data": "0xa9059cbb", "value": "0"}]})
    lh = make(api)
    rows = [{"recipient": "bob.eth", "amount": "25", "token": "USDC", "chain": "base", "label": "Bob"}]
    plan = lh.payouts.plan("base", "USDC", "0xAbC", rows=rows)
    assert api.last_json() == {"srcChain": "base", "srcToken": "USDC", "sender": "0xAbC", "rows": rows}
    assert plan["valid"] == 1 and plan["rows"][1]["error"]["code"] == "NOT_FOUND"
    lh.payouts.plan(8453, "USDC", "0xAbC", csv="recipient,amount,token,chain\nbob.eth,25,USDC,base")
    assert api.last_json() == {"srcChain": "8453", "srcToken": "USDC", "sender": "0xAbC",
                               "csv": "recipient,amount,token,chain\nbob.eth,25,USDC,base"}
    t = lh.payouts.transfers("base", "USDC", "0xAbC", [{"recipient": "0x3333", "amount": "25000000"}])
    assert api.last_json() == {"chain": "base", "token": "USDC", "sender": "0xAbC",
                               "transfers": [{"recipient": "0x3333", "amount": "25000000"}]}
    assert t["vm"] == "evm" and t["calls"][0]["data"] == "0xa9059cbb" and "serializedTx" not in t
    with pytest.raises(TypeError):
        lh.payouts.transfers("base", "USDC", "0xAbC", [{"recipient": "0x3333", "amount": 25}])  # type: ignore[list-item]


def test_recurring_orders(api):
    api.on("POST", "/v1/recurring-orders", RO_BUILD, status=201)
    api.on("POST", "/v1/recurring-orders/submit", {"txHash": "5sig", "order": "RoAcct111"})
    api.on("GET", "/v1/recurring-orders", {"recurringOrders": [RO], "page": 1, "totalPages": 1})
    api.on("POST", "/v1/recurring-orders/RoAcct111/cancel", {"requestId": "req_2", "tx": SVM_TX})
    lh = make(api)
    b = lh.recurring_orders.create(WALLET, "SOL", "700000000", 7, 86400, src_token="USDC", chain="solana")
    assert api.last_json() == {"wallet": WALLET, "dstToken": "SOL", "amount": "700000000", "orders": 7,
                               "intervalSeconds": 86400, "srcToken": "USDC", "chain": "solana"}
    assert b["requestId"] == "req_1" and b["tx"]["vm"] == "svm" and b["amountPerOrder"] == "100000000"
    lh.recurring_orders.create(WALLET, "SOL", "700000000", 7, 86400)
    assert api.last_json() == {"wallet": WALLET, "dstToken": "SOL", "amount": "700000000", "orders": 7,
                               "intervalSeconds": 86400}
    r = lh.recurring_orders.submit("req_1", "AQAB")
    assert api.last_json() == {"requestId": "req_1", "signedTransaction": "AQAB"} and r["order"] == "RoAcct111"
    page = lh.recurring_orders.list(WALLET, status="history", page=2)
    assert dict(api.last.url.params) == {"wallet": WALLET, "status": "history", "page": "2"}
    assert page["recurringOrders"][0]["fills"][0]["feeToken"] is None
    lh.recurring_orders.list(WALLET)
    assert dict(api.last.url.params) == {"wallet": WALLET}
    c = lh.recurring_orders.cancel("RoAcct111", WALLET)
    assert api.last_json() == {"wallet": WALLET} and c["requestId"] == "req_2"
    with pytest.raises(TypeError):
        lh.recurring_orders.create(WALLET, "SOL", 700000000, 7, 86400)  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_async_community(api):
    api.on("POST", "/v1/splits", {**SPLIT, "editToken": "sek_1", "editUrl": "u"}, status=201)
    api.on("GET", f"/v1/splits/{SID}", SPLIT)
    api.on("PATCH", f"/v1/splits/{SID}", SPLIT)
    api.on("GET", f"/v1/tip-jars/{TIP_JAR['address']}", TIP_JAR)
    api.on("POST", "/v1/payouts/plan", PAYOUT_PLAN)
    api.on("POST", "/v1/payouts/transfers", {"vm": "svm", "chainId": 7565164, "token": PAYOUT_TOKEN, "serializedTx": "AQ=="})
    api.on("POST", "/v1/recurring-orders", RO_BUILD, status=201)
    api.on("POST", "/v1/recurring-orders/submit", {"txHash": "5sig", "order": None})
    api.on("GET", "/v1/recurring-orders", {"recurringOrders": [], "page": 1, "totalPages": 0})
    api.on("POST", "/v1/recurring-orders/RoAcct111/cancel", {"requestId": "req_2", "tx": SVM_TX})
    async with amake(api) as lh:
        assert (await lh.splits.create("alice.eth", "base", "USDC", "120000000", participants=4))["editToken"] == "sek_1"
        assert (await lh.splits.get(SID))["id"] == SID
        await lh.splits.update(SID, "sek_1", note="New")
        assert api.last.headers["x-edit-token"] == "sek_1" and api.last_json() == {"note": "New"}
        assert (await lh.tip_jars.get(TIP_JAR["address"]))["tips"] == 57
        assert (await lh.payouts.plan("base", "USDC", "0xAbC", csv="a,1,USDC,base"))["invalid"] == 1
        t = await lh.payouts.transfers("solana", "USDC", WALLET, [{"recipient": "9W", "amount": "1"}])
        assert t["serializedTx"] == "AQ=="
        assert (await lh.recurring_orders.create(WALLET, "SOL", "700000000", 7, 86400))["orders"] == 7
        assert (await lh.recurring_orders.submit("req_1", "AQAB"))["order"] is None
        assert (await lh.recurring_orders.list(WALLET, status="active"))["totalPages"] == 0
        assert (await lh.recurring_orders.cancel("RoAcct111", WALLET))["tx"]["vm"] == "svm"
