# layerhop (Python SDK)

Best-price cross-chain and same-chain swaps through one non-custodial API. Sync and async clients
on top of [httpx](https://www.python-httpx.org/), mirroring the TypeScript `@layerhop/sdk`.

> **The SDK never holds keys.** It returns *unsigned* transactions. Your own wallet library
> (web3.py, eth-account, solders, a KMS, a hardware wallet…) signs and broadcasts them.

## Install

```bash
pip install layerhop
# from the monorepo:
pip install -e sdks/python
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

Client options: `base_url` (default `https://api.layerhop.com`), `api_key` (sent as `x-api-key`),
`channel` (default `"api"`), `integrator`, `integrator_fee_bps`, `timeout`, and `http_client` /
`transport` for custom httpx setups or tests.

Responses are plain dicts typed with `TypedDict` (keys keep the API's camelCase), so new fields
never break you.

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
cd sdks/python
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
```

MIT licensed.
