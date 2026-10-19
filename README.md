# layerhop (Python SDK)

[![PyPI](https://img.shields.io/pypi/v/layerhop?color=c3f06b&labelColor=090d15&cacheSeconds=3600)](https://pypi.org/project/layerhop/) [![Python](https://img.shields.io/pypi/pyversions/layerhop?color=7ddec8&labelColor=090d15)](https://pypi.org/project/layerhop/) [![license](https://img.shields.io/pypi/l/layerhop?color=7ddec8&labelColor=090d15)](https://opensource.org/license/mit) [![docs](https://img.shields.io/badge/docs-docs.layerhop.com-7ddec8?labelColor=090d15)](https://docs.layerhop.com/sdks/python)

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
| `quote(src_chain, src_token, amount, dst_chain, dst_token, *, sender, recipient, slippage_bps=50, gas_on_arrival=None)` | `GET /v1/quote` |
| `build_tx(quote_id)` | `POST /v1/orders` → the `tx` |
| `simulate(quote_id)` | `POST /v1/simulate` (dry-run, records nothing) |
| `submit(quote_id, signed_transaction)` | `POST /v1/orders/submit` (Solana `submitViaApi` only) |
| `report_submitted(quote_id, tx_hash)` | `POST /v1/orders/{quoteId}/submitted` |
| `status(provider, id)` | `GET /v1/orders/{provider}/{id}` |
| `watch(provider, id, *, interval=3.0, timeout=1800)` | polls `status`, yields on change, stops when final |
| `stream_order(quote_id)` | `GET /v1/orders/{quoteId}/events` (SSE), yields the order until final |
| `list_orders(*, address, status, cursor, limit)` | `GET /v1/orders` |
| `checkout.create(amount, settle_chain, settle_token, recipient, *, merchant_name, description, reference, metadata, success_url, cancel_url, expires_in_minutes)` | `POST /v1/checkout/sessions` |
| `checkout.list(*, status, cursor, limit)` | `GET /v1/checkout/sessions` |
| `checkout.get(id)` | `GET /v1/checkout/sessions/{id}` (public) |
| `checkout.expire(id)` | `POST /v1/checkout/sessions/{id}/expire` |
| `checkout.quote(id, src_chain, src_token, *, sender, slippage_bps=None)` | `POST /v1/checkout/sessions/{id}/quote` (public) |
| `checkout.stream(id)` | `GET /v1/checkout/sessions/{id}/events` (SSE, public) |
| `checkout.products.create(name, amount, settle_chain, settle_token, recipient, *, description, merchant_name, success_url, cancel_url, expires_in_minutes, allowed_origins, active)` | `POST /v1/checkout/products` |
| `checkout.products.list(*, active, cursor, limit)` | `GET /v1/checkout/products` |
| `checkout.products.get(id)` | `GET /v1/checkout/products/{id}` (public) |
| `checkout.products.update(id, **fields)` | `PATCH /v1/checkout/products/{id}` (only the fields you pass) |
| `checkout.products.start_session(id, *, reference, metadata)` | `POST /v1/checkout/products/{id}/sessions` (public) |
| `checkout.refunds.create(session_id, *, amount, reason, from_, to)` | `POST /v1/checkout/sessions/{id}/refunds` |
| `checkout.refunds.list(session_id)` | `GET /v1/checkout/sessions/{id}/refunds` |
| `invoices.create(line_items, settle_chain, settle_token, recipient, *, customer_email, customer_name, merchant_name, memo, due_at, send)` | `POST /v1/invoices` |
| `invoices.list(*, status, cursor, limit)` · `invoices.get(id)` · `invoices.update(id, **fields)` | `GET /v1/invoices` · `GET`/`PATCH /v1/invoices/{id}` |
| `invoices.send(id)` · `invoices.void(id)` | `POST /v1/invoices/{id}/send` · `/void` |
| `invoices.public_view(id)` · `invoices.pay(id)` | `GET /v1/invoices/{id}/public` · `POST /v1/invoices/{id}/pay` (public) |
| `subscriptions.create(customer_email, interval, *, interval_count, product_id, amount, settle_chain, settle_token, recipient, description, customer_name, merchant_name, memo, days_until_due, start_at, metadata)` | `POST /v1/subscriptions` |
| `subscriptions.list(*, status, customer_email, cursor, limit)` · `subscriptions.get(id)` · `subscriptions.update(id, **fields)` | `GET /v1/subscriptions` · `GET`/`PATCH /v1/subscriptions/{id}` |
| `subscriptions.cancel(id, *, at_period_end)` · `subscriptions.pause(id)` · `subscriptions.resume(id)` | `POST /v1/subscriptions/{id}/cancel` · `/pause` · `/resume` |
| `subscriptions.invoices(id)` | `GET /v1/subscriptions/{id}/invoices` → the `invoices` |
| `deposit_addresses.create(src_chain, src_token, dst_chain, dst_token, recipient, refund_to, *, reusable, amount, label, metadata, integrator, integrator_fee_bps)` | `POST /v1/deposit-addresses` |
| `deposit_addresses.list(*, status, label, cursor, limit)` · `deposit_addresses.get(id)` | `GET /v1/deposit-addresses` · `GET /v1/deposit-addresses/{id}` |
| `deposit_addresses.refresh(id)` · `deposit_addresses.disable(id)` | `POST /v1/deposit-addresses/{id}/refresh` · `/disable` |
| `deposit_addresses.simulate(id, amount)` | `POST /v1/deposit-addresses/{id}/simulate` (test keys only) |
| `limit_orders.create(wallet, src_token, dst_token, amount, dst_amount, *, expires_at, chain, metadata, integrator, integrator_fee_bps)` | `POST /v1/limit-orders` |
| `limit_orders.submit(id, signed_transaction)` | `POST /v1/limit-orders/{id}/submit` |
| `limit_orders.list(*, wallet, status, cursor, limit)` · `limit_orders.get(id)` | `GET /v1/limit-orders` · `GET /v1/limit-orders/{id}` |
| `limit_orders.cancel(id)` | `POST /v1/limit-orders/{id}/cancel` |
| `limit_orders.simulate(id, outcome)` | `POST /v1/limit-orders/{id}/simulate` (test keys only) |
| `service_status()` | `GET /v1/status` (platform status, public) |
| `webhooks.stream()` | `GET /v1/webhooks/stream` (SSE, API key) |
| `webhooks.trigger(type)` | `POST /v1/webhooks/trigger` (test keys only) |

Client options: `base_url` (default `https://api.layerhop.com`), `api_key` (sent as `x-api-key`),
`channel` (default `"api"`), `integrator`, `integrator_fee_bps`, `timeout`, `stream_timeout` (read
timeout of streams; `None`, the default, waits forever), and `http_client` /
`transport` for custom httpx setups or tests.

Responses are plain dicts typed with `TypedDict` (keys keep the API's camelCase), so new fields
never break you.

### Gas on arrival

Pass `gas_on_arrival=True` to also deliver $2 of native gas to the recipient on the destination
chain, or a USD amount from 0.5 to 20 (`gas_on_arrival=5`). Quotes that include it carry
`gasOnArrival` (`amount`, `token`, `symbol`, `decimals`, `usd`); its cost is already taken out of
`dstAmount`. It is ignored for same-chain swaps, non-EVM destinations and native outputs, and
providers that can't do it ignore it, so check the quote.

```python
q = lh.quote("solana", "USDC", "100000000", "base", "USDC",
             sender="YourSolanaAddress", recipient="0xYourEvmAddress", gas_on_arrival=True)
goa = q["best"].get("gasOnArrival")
if goa:
    print(goa["amount"], goa["symbol"], goa.get("usd"))  # e.g. 800000000000000 ETH 2.0
```

## Live order status

`stream_order` follows an order over Server-Sent Events instead of polling: it yields the order
now and on every change, and ends once it is final (`filled`, `refunded`, `failed` or `expired`).
`checkout.stream(id)` does the same for a checkout session (until `paid`, `expired` or
`needs_review`).

```python
for order in lh.stream_order(best["quoteId"]):
    print(order["status"], order.get("dstTxHash"))

# async
async for session in alh.checkout.stream(session_id):
    print(session["status"])
```

The request is sent when iteration starts; break out of the loop to close the connection. A
missing order raises `LayerHopApiError` (`ORDER_NOT_FOUND`). Guide:
https://docs.layerhop.com/guides/live-status

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

## Products and payment buttons

A product is a fixed price (amount, settlement token, payout address and redirect URLs) that
anyone may start a session from without being able to change it: the backing for payment
buttons, `https://layerhop.com/buy/{id}` links and store plugins. `create`, `list` and `update`
need your API key; `get` and `start_session` are public.

```python
product = lh.checkout.products.create("Pro plan", "49000000", "base", "USDC", "0xYourPayoutAddress",
                                      description="1 month", success_url="https://shop.example.com/thanks",
                                      allowed_origins=["https://shop.example.com"])
print(product["url"])  # https://layerhop.com/buy/prod_...: share it or put it behind a button

lh.checkout.products.list(active=True)
lh.checkout.products.update(product["id"], active=False)  # stops new sessions; only passed fields change

# Public (no key): start a session on the product's terms, adding only your order id.
session = LayerHop().checkout.products.start_session(product["id"], reference="order_1042")
print(session["url"], session["productId"])
```

`update` sends only the fields you pass; pass `None` to clear a nullable field such as
`description`. Guide: https://docs.layerhop.com/guides/payment-buttons

## Invoices

Bill a customer by email for one or more line items; they pay with any token on the hosted page
`https://layerhop.com/invoice/{id}` and get a receipt (with a PDF) once it is paid. `create`, `get`,
`list`, `update`, `send` and `void` need an API key; `public_view` and `pay` are public.

```python
inv = lh.invoices.create(
    [{"description": "Design work (hours)", "quantity": 10, "unitAmount": "80000000"}],  # 10 x 80 USDC
    "base", "USDC", "0xYourPayoutAddress",
    customer_email="ap@client.example", customer_name="Client Co", due_at="2026-11-01",
    send=True,  # finalize and email now (otherwise it stays a draft you can update)
)
print(inv["number"], inv["url"])  # INV-0001 https://layerhop.com/invoice/inv_...

lh.invoices.list(status="open")
lh.invoices.send(inv["id"])   # re-sends the email of an open invoice
lh.invoices.void(inv["id"])   # draft or open only
# Fulfil on the invoice.paid webhook. Statuses: draft, open, paid, void.
```

## Subscriptions

Recurring billing. Crypto can't be pulled from a wallet, so LayerHop issues and emails an invoice
every period and the customer pays it with any token. Unpaid past the due date, the subscription
turns `past_due` (reminders on day 1 and 3) and is canceled after 7 days. Everything needs an API key.

```python
sub = lh.subscriptions.create(
    "ada@example.com", "month",  # interval: day, week, month or year
    amount="49000000", settle_chain="base", settle_token="USDC", recipient="0xYourPayoutAddress",
    description="Pro plan",      # or product_id="prod_..." instead of these five
    interval_count=1, days_until_due=3,
)
print(sub["status"], sub["nextInvoiceAt"])

lh.subscriptions.update(sub["id"], amount="59000000")         # applies from the next invoice
lh.subscriptions.cancel(sub["id"], at_period_end=True)         # or cancel(id) to cancel now
lh.subscriptions.update(sub["id"], cancel_at_period_end=False)  # undo the scheduled cancel
lh.subscriptions.pause(sub["id"]); lh.subscriptions.resume(sub["id"])
lh.subscriptions.invoices(sub["id"])  # its invoices (with subscriptionId), newest first
lh.subscriptions.list(status="past_due")
```

Statuses: `active`, `past_due`, `paused`, `canceled`. Webhooks: `subscription.created`,
`subscription.renewed` (a period's invoice was issued, with `data.invoice`), `subscription.past_due`
and `subscription.canceled`; the period invoices send the usual `invoice.paid`.

## Deposit addresses

Let a user swap or bridge by just **sending** tokens to an address: no wallet connection, no
signing in your app. The provider (Relay) owns the address and delivers `dst_token` to `recipient`;
LayerHop never holds the funds. Each detected deposit becomes an order with `depositAddressId` set
and the usual `order.*` webhooks. Everything needs an API key.

```python
da = lh.deposit_addresses.create(
    "base", "USDC", "arbitrum", "USDC",
    "0xRecipientOnArbitrum", "0xUserRefundAddressOnBase",  # refund_to: never a CEX deposit address
    label="user_42",  # reusable=True by default; reusable=False + amount = one-time address
)
print(da["address"], da["estimate"]["dstAmount"])  # show the address to your user

lh.deposit_addresses.refresh(da["id"])            # "I sent it": check for deposits now
lh.deposit_addresses.get(da["id"])["deposits"]    # its 20 most recent deposits (orders)
lh.deposit_addresses.list(label="user_42")
lh.deposit_addresses.disable(da["id"])
```

Live mode may be disabled by the operator: `create` with a live key then raises a
`LayerHopApiError` with code `FORBIDDEN`. Test keys always work, and
`lh.deposit_addresses.simulate(da["id"], "25000000")` records a test deposit that settles like any
test order. Deposits under $1 may not be processed.

## Limit orders (Solana)

Sell a token at your price or better (Jupiter Trigger, beta). The order lives on chain; the user's
wallet signs it and keeps custody. Each fill becomes an order with `limitOrderId` set. An API key is
optional (without one, `list` needs `wallet`).

```python
lo = lh.limit_orders.create(
    "UserSolanaWallet", "SOL", "USDC",
    "1000000000", "200000000",  # sell 1 SOL for at least 200 USDC (worth at least $5)
    expires_at=None,            # unix seconds, or None for good-till-cancelled
)
# lo["tx"]["serializedTx"]: base64 VersionedTransaction. Only SIGN it (submitViaApi), then:
r = lh.limit_orders.submit(lo["id"], signed_b64)  # {"limitOrder": {... "status": "open"}, "txHash"}

lh.limit_orders.get(lo["id"])["fills"]            # its fills (orders), newest first
lh.limit_orders.list(wallet="UserSolanaWallet", status="open")
c = lh.limit_orders.cancel(lo["id"])               # c["tx"]: sign and submit it the same way
                                                   # (None when the order was never submitted)
```

Statuses: `built`, `open`, `filled`, `cancelled`, `expired`, `failed`. Webhooks: `limit_order.opened`,
`limit_order.filled` (with the fill in `data.fill`), `limit_order.cancelled`, `limit_order.expired`,
`limit_order.failed`. Our fee applies when `dst_token` is SOL, USDC or USDT.

Live mode may be disabled by the operator: `create` with a live key (or no key) then raises a
`LayerHopApiError` with code `FORBIDDEN`. Test keys always work, and
`lh.limit_orders.simulate(lo["id"], "fill")` (or `"partial_fill"`, `"expire"`) settles an open test order.

## Refunds

Refunds are non-custodial: you sign them from your own wallet. `create` returns a quote that you
build, sign from `quote["from"]` (by default the session's payout address) and report; the refund
goes back to the payer's original chain and token (`to="original"`, the default) or as the
settlement token (`to="settlement"`). Leave out `amount` to refund everything not yet refunded.

```python
r = lh.checkout.refunds.create("cs_...", amount="10000000", reason="Partial refund")
tx = lh.build_tx(r["quote"]["quoteId"])   # sign and broadcast from r["quote"]["from"]
lh.report_submitted(r["quote"]["quoteId"], tx_hash)
lh.checkout.refunds.list("cs_...")        # pending -> submitted -> completed (or failed)
# The session's refundedAmount grows and checkout.session.refunded is sent.
```

## Platform status

`lh.service_status()` returns `GET /v1/status`, the data behind status.layerhop.com:
the overall `status` (`operational`, `degraded` or `outage`), each component with its 90-day uptime,
and the last 14 days of incidents. `lh.status(provider, id)` is still the provider order status.

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

### Webhook tools

With an API key, `webhooks.stream()` yields your account's webhook events (in the key's live or
test mode) as they are created, with the exact payloads your endpoints receive. `webhooks.trigger`
creates a sample event in test mode (test keys only; a live key raises `FORBIDDEN`).

```python
lh = LayerHop(api_key="lh_test_...")
r = lh.webhooks.trigger("order.filled")  # {"eventId", "deliveries", "payload"}
for event in lh.webhooks.stream():       # runs until you break (or the server closes it)
    print(event["type"], event["data"])
```

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
```

MIT licensed.
