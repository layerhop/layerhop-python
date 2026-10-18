# layerhop (Python SDK)

[![PyPI](https://img.shields.io/pypi/v/layerhop?color=c3f06b&labelColor=090d15)](https://pypi.org/project/layerhop/) [![Python](https://img.shields.io/pypi/pyversions/layerhop?color=7ddec8&labelColor=090d15)](https://pypi.org/project/layerhop/) [![license](https://img.shields.io/pypi/l/layerhop?color=7ddec8&labelColor=090d15)](https://opensource.org/license/mit) [![docs](https://img.shields.io/badge/docs-docs.layerhop.com-7ddec8?labelColor=090d15)](https://docs.layerhop.com/sdks/python)

Best-price cross-chain and same-chain swaps through one non-custodial API. Sync and async clients
on top of [httpx](https://www.python-httpx.org/), mirroring the TypeScript `@layerhop/sdk`.

> **The SDK never holds keys.** It returns *unsigned* transactions. Your own wallet library
> (web3.py, eth-account, solders, a KMS, a hardware wallet…) signs and broadcasts them.

## Install

```bash
pip install layerhop
```

Python 3.9+. The only runtime dependency is `httpx`.

## Quickstart

Amounts are **integer strings in base units** (100 USDC = `"100000000"`), never floats.

```python
from layerhop import LayerHop

lh = LayerHop(api_key="lh_live_...")  # api_key is optional

# 1. Quote: every provider is asked; `best` pays the user the most.
q = lh.quote("base", "USDC", "100000000", "solana", "SOL",
             sender="0xYourEvmAddress", recipient="YourSolanaAddress")
best = q["best"]
print(best["provider"], best["dstAmount"], best["estimatedSeconds"])

# 2. Build the unsigned transaction.
tx = lh.build_tx(best["quoteId"])

# 3. Sign and send with YOUR wallet library (example: web3.py on Base).
if tx["vm"] == "evm":
    # if tx.get("approval"): send ERC-20 approve(spender, amount) on approval["token"] first
    tx_hash = w3.eth.send_transaction({
        "to": tx["to"], "data": tx["data"], "value": int(tx["value"]), "chainId": tx["chainId"],
    }).hex()
else:
    # Solana: tx["serializedTx"] is a base64 VersionedTransaction; sign it with solders.
    # When tx.get("submitViaApi") is true, only sign, then: tx_hash = lh.submit(best["quoteId"], signed_b64)
    ...

# 4. Tell LayerHop you broadcast it (enables tracking, history and webhooks).
lh.report_submitted(best["quoteId"], tx_hash)

# 5. Track until filled / refunded / failed.
for s in lh.watch(best["provider"], tx_hash):
    print(s["state"], s.get("dstTxHash"))
```

### Async

```python
from layerhop import AsyncLayerHop

async with AsyncLayerHop() as lh:
    q = await lh.quote("base", "USDC", "100000000", "solana", "SOL", sender=s, recipient=r)
    async for st in lh.watch("relay", tx_hash):
        print(st["state"])
```

## API

| Method | Endpoint |
|---|---|
| `health()` | `GET /v1/health` |
| `chains()` | `GET /v1/chains` |
| `tokens(chain)` | `GET /v1/tokens?chain=` |
| `quote(src_chain, src_token, amount, dst_chain, dst_token, *, sender, recipient, slippage_bps=50)` | `GET /v1/quote` |
| `build_tx(quote_id)` | `POST /v1/orders` → the `tx` |
| `simulate(quote_id)` | `POST /v1/simulate` (dry-run, records nothing) |
| `submit(quote_id, signed_transaction)` | `POST /v1/orders/submit` (Solana `submitViaApi` only) |
| `report_submitted(quote_id, tx_hash)` | `POST /v1/orders/{quoteId}/submitted` |
| `status(provider, id)` | `GET /v1/orders/{provider}/{id}` |
| `watch(provider, id, *, interval=3.0, timeout=1800)` | polls `status`, yields on change, stops when final |
| `list_orders(*, address, status, cursor, limit)` | `GET /v1/orders` |
| `checkout.create(amount, settle_chain, settle_token, recipient, *, merchant_name, description, reference, metadata, success_url, cancel_url, expires_in_minutes)` | `POST /v1/checkout/sessions` |
| `checkout.list(*, status, cursor, limit)` | `GET /v1/checkout/sessions` |
| `checkout.get(id)` | `GET /v1/checkout/sessions/{id}` (public) |
| `checkout.expire(id)` | `POST /v1/checkout/sessions/{id}/expire` |
| `checkout.quote(id, src_chain, src_token, *, sender, slippage_bps=None)` | `POST /v1/checkout/sessions/{id}/quote` (public) |

Client options: `base_url` (default `https://api.layerhop.com`), `api_key` (sent as `x-api-key`),
`channel` (default `"api"`), `integrator`, `integrator_fee_bps`, `timeout`, and `http_client` /
`transport` for custom httpx setups or tests.

Responses are plain dicts typed with `TypedDict` (keys keep the API's camelCase), so new fields
never break you.

## Checkout (pay with any token)

Get paid in USDC or USDT on the chain you choose while the customer pays with any token on any
chain. Create a session with your API key and send the customer to its hosted `url`; the session
becomes `paid` (and a `checkout.session.completed` webhook fires) once the delivery is verified on
chain.

```python
lh = LayerHop(api_key="lh_live_...")

session = lh.checkout.create("49000000", "base", "USDC", "0xYourPayoutAddress",  # 49 USDC
                             description="Pro plan, 1 month", reference="order_1042",
                             success_url="https://shop.example.com/thanks")
print(session["url"])  # redirect the customer here

lh.checkout.get(session["id"])["status"]  # open | processing | paid | expired | needs_review
lh.checkout.list(status="paid", limit=20)
lh.checkout.expire(session["id"])         # cancel an open session
```

Building your own payment page instead? `get` and `quote` are public (no key needed):

```python
q = lh.checkout.quote(session_id, "arbitrum", "ETH", sender=payer_address)
best = q["best"]  # best["srcAmount"] is what the payer sends; dstAmountMin >= amount due
tx = lh.build_tx(best["quoteId"])
# ... the payer's wallet signs and broadcasts tx ...
lh.report_submitted(best["quoteId"], tx_hash)
```

The async client has the same methods under `await lh.checkout.…`. Guide:
https://docs.layerhop.com/guides/checkout

## Test mode

Use an `lh_test_` key exactly like a live key: everything is served by the `sandbox` provider,
responses carry `livemode: False`, and built transactions have `sandbox: True` (never broadcast
them; report any hash with `report_submitted`). The last digits of `amount` pick the outcome:
`…4001` refunds, `…4002` fails, `…4004` returns `NO_ROUTE`. Checkout sessions created with a
test key (`cs_test_…`) are paid through the sandbox too. See
https://docs.layerhop.com/guides/test-mode

## Errors

Every non-2xx response raises `LayerHopApiError` with a stable `code` (`QUOTE_EXPIRED`,
`NO_ROUTE`, …), `status`, `message` and `request_id`. See
`https://docs.layerhop.com/errors/<code>`.

```python
from layerhop import LayerHopApiError
try:
    lh.build_tx(quote_id)
except LayerHopApiError as e:
    if e.code == "QUOTE_EXPIRED":
        ...  # re-quote
```

## Webhooks

```python
from layerhop import verify_webhook_signature, construct_webhook_event

# Flask example — use the RAW body
ok = verify_webhook_signature(secret, request.get_data(), request.headers.get("LayerHop-Signature"))
event = construct_webhook_event(secret, request.get_data(), request.headers.get("LayerHop-Signature"))
```

The header is `t=<unix>,v1=<hex HMAC-SHA256(secret, "<t>.<body>")>`. Signatures older or newer
than 300 s (`tolerance`) are rejected; comparison is constant-time.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
```

MIT licensed.
