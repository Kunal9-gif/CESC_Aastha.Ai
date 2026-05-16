# AASTHA AI — Bill Payment System: Reviewer-Grade Intelligence Report
## Part 2: Database · Security · Functions · Observability · Failures · FAQ

---

# DATABASE_ANALYSIS

## DynamoDB Tables — Complete Schema (Verified)

### Table 1: `RazorpayPaymentOrders` (RBL Service)
**File:** `razorpay_service/app/db/models.py` + `database.py`

| Field | Type | Purpose | Notes |
|---|---|---|---|
| `razorpay_order_id` | String (PK HASH) | Razorpay order ID | e.g. `order_SXxxxxxxxxxx` |
| `amount` | String | Payment amount in INR | Stored as string (not Decimal) |
| `currency` | String | Currency code | Always `"INR"` |
| `status` | String | Payment lifecycle state | `created` → `captured`/`failed`/`refunded`/`authorized` |
| `customer_id` | String | CESC Consumer ID (CID) | 11-digit LT ID |
| `bill_type` | String | CESC bill type code | Maps to `param_3` in CESC payload |
| `mobile` | String | Registered mobile number | Maps to `param_5` |
| `cid2` | String | Secondary CESC identifier | Maps to `param_2` |
| `cid3` | String | Payment gateway code | Maps to `param_7` |
| `cid4` | String | p8_val | Maps to `param8` |
| `cid5` | String | p9_val | Maps to `param9` |
| `user_id` | String | For SSE routing | WhatsApp number or web user ID |
| `session_id` | String | LangGraph session context | For correlation only |
| `cesc_synced` | Number | CESC sync flag | `0` = pending, `1` = synced |
| `created_at` | String | ISO timestamp of creation | Used for age-based polling decisions |
| `last_notified_payment_id` | String | Dedup guard for failure notifications | Set by polling worker after notifying user |

**Provisioned Throughput:** 5 RCU / 5 WCU (hardcoded — not auto-scaling)
**No GSI defined** — polling worker uses `table.scan()` with `FilterExpression`

---

### Table 2: `RazorpayAxisPaymentOrders` (Axis Service)
**Identical schema** to `RazorpayPaymentOrders`. Completely separate table in DynamoDB.

---

### Table 3: `RetryTracker` (Shared by BOTH services)
**File:** `razorpay_service/app/db/models.py`
**⚠️ SHARED ACROSS RBL AND AXIS SERVICES** — same physical DynamoDB table

| Field | Type | Purpose |
|---|---|---|
| `customer_id` | String (PK HASH) | CID — shared key between both gateways |
| `failed_attempts` | Number | Total consecutive failures |
| `last_failed_at` | String | ISO timestamp of last failure |
| `blocked_until` | String | ISO timestamp when block expires (null if not blocked) |
| `updated_at` | String | Last update timestamp |

**Business Rule:** If a customer fails 3 times on RBL, they are also blocked on Axis (same table). This is by design — the retry limit is per-customer, not per-gateway.

---

### Table 4: `aastha-langgraph-checkpoints` (aastha-web only)
| Field | Purpose |
|---|---|
| `thread_id` (PK) | Composite `{user_id}-{session_id}` |
| LangGraph internal fields | Conversation state, interrupt state, messages |

---

### Table 5: `UserNotifications` (aastha-web only)
Used by SSE system for offline notifications. Not directly used by payment services.

---

### Table 6: `pending_payments` (aastha-web only)
Stores offline payment notifications when user is not connected to SSE stream.

---

## Database Operation Inventory

| Operation | Location | Type | DynamoDB Cost |
|---|---|---|---|
| Create order | `routes.py:create_order` | `put_item` | 1 WCU |
| Read order | `routes.py:check_order_status` | `get_item` (PK) | 0.5 RCU |
| Update status=captured | `routes.py:payment_success` | `update_item` | 1 WCU |
| Update cesc_synced | `routes.py:payment_success` | `update_item` | 1 WCU |
| Reset retry tracker | `routes.py:payment_success` | `update_item` | 1 WCU |
| Scan pending orders | `polling_worker.py:check_pending_orders` | `scan + FilterExpression` | N * 0.5 RCU (costly) |
| Update order status | `polling_worker.py` | `update_item` | 1 WCU |
| Update last_notified_payment_id | `polling_worker.py` | `update_item` | 1 WCU |
| Get/Create retry record | `polling_worker.py:_update_retry_tracker` | `get_item` + `put_item`/`update_item` | 2 WCU |
| Check retry block | `routes.py:_check_retry_block` | `get_item` | 0.5 RCU |

**⚠️ Scaling Risk:** The `table.scan()` in the polling worker reads the ENTIRE table every 45 seconds. At 5 RCU provisioned, with a large table this will hit `ProvisionedThroughputExceededException`.

---

# SECURITY_REVIEW

## Payment Security Mechanisms (Verified)

### ✅ HMAC Signature Verification (Critical — Implemented)
```python
# File: razorpay_service/app/services/razorpay_client.py
client.utility.verify_payment_signature({
    'razorpay_order_id': order_id,
    'razorpay_payment_id': payment_id,
    'razorpay_signature': signature
})
# Uses: HMAC-SHA256(key_secret, order_id + "|" + payment_id)
# Raises: razorpay.errors.SignatureVerificationError on mismatch
# Returns: HTTP 400 if invalid
```
**Assessment:** Correctly implemented. Prevents tampered callbacks from marking orders as captured.

### ✅ Internal Service Auth (`X-Internal-Secret`)
```python
# All /internal/* endpoints check:
headers={"X-Internal-Secret": os.getenv("INTERNAL_SECRET", "cesc-secret-2026")}
```
**Assessment:** Correct pattern. However, the default value `"cesc-secret-2026"` is exposed in `.env` and in the code default. Must use AWS Secrets Manager in production.

### ✅ Retry Block Guard (429 Rate Limiting)
- Checked at order creation before any Razorpay API calls
- Enforced via DynamoDB `RetryTracker` (persistent across restarts)
- Business logic: 3 failures → 30-minute block

---

## Security Risks (Verified — Ranked by Severity)

| # | Risk | Severity | File | Detail |
|---|---|---|---|---|
| 1 | **Test API keys in .env** | 🔴 CRITICAL | `razorpay_service/.env` | `rzp_test_SJy7...` — must swap to live keys before production payments |
| 2 | **No auth on `/api/razorpay/orders`** | 🔴 HIGH | `routes.py:125` | Full table scan returns all orders (customer_id, mobile, amounts) with zero auth |
| 3 | **UAT IP hardcoded in CESC payload** | 🔴 HIGH | `polling_worker.py:146` | `param_4: "10.50.81.31"` — production will send wrong IP |
| 4 | **INTERNAL_SECRET in code default** | 🟠 HIGH | `routes.py:415` | `os.getenv("INTERNAL_SECRET", "cesc-secret-2026")` — default is a known value |
| 5 | **JWT token in payload body** | 🟡 MEDIUM | `cesc_client.py:53` | `payload["bearer_token"] = jwt` — JWT appears in request body, logged in DEBUG logs |
| 6 | **No auth on checkout page** | 🟡 MEDIUM | `routes.py:151` | Anyone who guesses an `order_id` can load the payment page |
| 7 | **CESC_POST_PAYMENT_URL is UAT** | 🟡 MEDIUM | `cesc_client.py:8` | `rlbsti_uat.php` — not a production CESC endpoint |
| 8 | **5 RCU/WCU provisioned** | 🟡 MEDIUM | `models.py:35` | No auto-scaling — throttling under load |
| 9 | **No idempotency on /success** | 🟡 MEDIUM | `routes.py:332` | If Razorpay retries the callback, it will execute the full chain again (double CESC sync, double notification) |
| 10 | **CESC URL contains `/soi49Kkdu/`** | 🟢 LOW | `cesc_client.py:8` | Path segment looks like security-by-obscurity — not a concern if HTTPS is used |

---

# FUNCTION_ANALYSIS

## Complete Function Call Trees

### `create_order()` — Order Creation
```
create_order(request: OrderRequest)
  ├── _check_retry_block(customer_id)
  │     └── dynamodb.Table("RetryTracker").get_item()
  │         → Returns block_info dict or None
  │
  ├── create_razorpay_order(amount, currency, receipt, notes)
  │     └── razorpay.Client.order.create(data)
  │         → amount converted: INR * 100 = paise
  │         → Returns: {id: "order_xxx", ...}
  │
  └── dynamodb.Table(TABLE_NAME).put_item(Item={...})
      → Stores: order_id, amount, customer_id, status="created", cesc_synced=0
```

### `payment_success()` — Success Callback
```
payment_success(payment_id, order_id, signature)
  ├── verify_payment_signature(order_id, payment_id, signature)
  │     └── razorpay.Client.utility.verify_payment_signature()
  │         → HMAC-SHA256 comparison
  │         → Returns: True / raises SignatureVerificationError
  │
  ├── [IF VALID] table.update_item(status="captured")
  │
  ├── table.get_item(order_id)  ← fetch customer_id
  │
  ├── RetryTracker.update_item(failed_attempts=0, blocked_until=None)
  │
  ├── requests.get(razorpay.com/v1/payments/{payment_id})  ← Basic Auth
  │   → Returns: full payment object
  │
  ├── map_to_cesc_payload(order, payment_details)
  │   → Pure function — builds 20-field dict
  │
  ├── cesc_client.update_payment_status(payload)
  │     ├── _get_jwt_token()
  │     │     ├── GET dice-uat.cesc.co.in/dicekey/botKeyStore.txt
  │     │     └── POST dice-uat.cesc.co.in/api/getSecretKey
  │     └── POST srvcs.cesc.co.in/soi49Kkdu/rlbsti_uat.php
  │         → JWT in header + payload body
  │
  ├── [IF user_id exists] requests.post(aastha-web:8001/internal/payment-notify)
  │     → X-Internal-Secret header
  │
  └── [RETURN] HTMLResponse (success page + 4s redirect)
      [ON ERROR] HTTP 400 (signature invalid)
```

### `check_pending_orders()` — Polling Worker
```
check_pending_orders()   [runs every 45s in daemon thread]
  ├── Guard: if not client: return   ← No-op if Razorpay not configured
  │
  ├── dynamodb.Table(TABLE_NAME).scan(FilterExpression=...)
  │     → status IN [created, authorized] AND created_at BETWEEN (12h ago, 2min ago)
  │
  └── FOR EACH order:
        ├── razorpay.Client.order.payments(order_id)
        │     → Razorpay API: GET /v1/orders/{id}/payments
        │
        ├── [IF no payments AND age > 30min]:
        │     table.update_item(status="failed")
        │     _sync_with_cesc(order, None)
        │     continue
        │
        ├── payments.sort(by created_at, desc)
        │
        ├── [IF latest.status == "failed" AND id != last_notified_payment_id]:
        │     _sync_with_cesc(order, latest_payment)
        │     _update_retry_tracker(customer_id, False)
        │     send_payment_notification(user_id, cid, "failed" message)
        │     table.update_item(last_notified_payment_id=latest.id)
        │
        └── [TERMINAL STATUS CHECK]:
              IF "captured" → update + retry_reset + cesc_sync + notify_success
              IF "refunded" → update only
              IF all "failed" AND age > 15min → update + cesc_sync + notify_failure (if not already notified)

_sync_with_cesc(order, rzp_payment)
  ├── map_to_cesc_payload(order, rzp_payment)
  ├── cesc_client.update_payment_status(cesc_payload)
  │     → 3 HTTP calls (auth x2 + POST)
  └── [IF success] table.update_item(cesc_synced=1)

_update_retry_tracker(customer_id, is_success)
  ├── RetryTracker.get_item(customer_id)
  ├── [IF success] update_item(failed_attempts=0, blocked_until=None, last_failed_at=None)
  └── [IF failure]:
        attempts = existing + 1
        [IF attempts >= MAX_RETRIES]:
          blocked_until = now + COOLDOWN_MINS
          update_item includes blocked_until
        update_item(failed_attempts, last_failed_at, updated_at)

send_payment_notification(user_id, cid, message)
  └── POST {AASTHA_API_URL}/internal/payment-notify
        Headers: X-Internal-Secret
        Timeout: 5s
```

---

# OBSERVABILITY_REPORT

## Current Logging Setup (Verified)

| Service | Logger Name | Framework | Level | Format |
|---|---|---|---|---|
| razorpay-service | `razorpay_worker` | Python `logging` | INFO | `%(asctime)s - %(name)s - %(levelname)s - %(message)s` |
| razorpay-axis-service | `razorpay_worker` (same) | Python `logging` | INFO | Same |
| CESC Client | `razorpay_cesc_client` | Python `logging` | INFO | Same |
| Routes | `__name__` | Python `logging` | INFO | Same |

## Log Coverage Per Event

| Event | Log Level | Logged? |
|---|---|---|
| Order created | INFO | ✅ Yes — full request logged |
| Retry block triggered | WARNING | ✅ Yes |
| Signature valid/invalid | (none) | ❌ No explicit log on success |
| Payment captured | INFO | ✅ Via polling worker |
| CESC sync success | INFO | ✅ |
| CESC sync failure | ERROR | ✅ |
| Polling scan count | INFO | ✅ `Found N pending orders` |
| Failed payment detected | INFO | ✅ `Detected new failed payment` |
| SSE notification sent | INFO | ✅ `HTTP {status_code}` |
| RetryTracker update | INFO + WARNING | ✅ |

## Observability Gaps

| Gap | Risk | Recommendation |
|---|---|---|
| No request ID / correlation ID | Cannot trace a specific payment across logs | Add `X-Request-ID` header injection middleware |
| No structured JSON logging | CloudWatch Insights queries fail on plaintext | Use `python-json-logger` |
| Health check hits `/docs` not `/health` | Swagger rendering success ≠ service health | Change to `GET /health` |
| No metric emission | Cannot alert on payment failure rate | Add `cloudwatch.put_metric_data()` on each failure |
| No distributed tracing | Cannot trace cross-service calls | Add AWS X-Ray SDK |
| `print()` mixed with `logger` | Inconsistent log stream | Replace all `print()` with `logger` |

---

# FAILURE_MODE_ANALYSIS

## Critical Failure Paths

### Payment Success Handler Failures
| Failure Point | Step | Recovery | Impact |
|---|---|---|---|
| Signature verification fails | Step 1 | Returns 400 — clean rejection | User sees error page |
| Razorpay payment detail fetch fails (Step 4) | Step 4 | `try/except` — logged, continues to HTML | CESC not synced, notification may fail |
| CESC JWT auth fails | Step 6 | Returns `{success: False}` — logged only | Payment captured but CESC not updated |
| SSE notification fails | Step 7 | `try/except` — logged only | User doesn't get push notification |
| Razorpay retries callback | Step 1 | **No idempotency** — all steps re-execute | Double CESC sync, double notification |

### Polling Worker Failures
| Failure | Recovery | Impact |
|---|---|---|
| DynamoDB scan throttled | `except Exception` — logged, skips tick | Orders not polled for 45s |
| Razorpay `order.payments()` fails | Per-order `try/except` | One order skipped, others continue |
| CESC sync fails in worker | Logged only | Order status updated but CESC not synced |
| APScheduler thread dies | No restart — daemon thread | Worker stops silently, no alerting |

### Infrastructure Failures
| Failure | Recovery | Impact |
|---|---|---|
| `aastha-web` container restarts | `restart: unless-stopped` — Docker restarts | In-memory SSE connections lost, pending jobs handled by offline fallback |
| `razorpay-service` restarts | `restart: unless-stopped` — auto restart | APScheduler re-starts via lifespan, DynamoDB state persists |
| DynamoDB outage | No circuit breaker — `Exception` logged | All order creation and status updates fail silently |
| Razorpay API outage | `if not client: return` in worker | Worker no-ops; orders stay `created` until API recovers |

---

# SCALABILITY_ANALYSIS

| Area | Current State | Risk | Recommendation |
|---|---|---|---|
| **DynamoDB provisioning** | 5 RCU / 5 WCU hardcoded | Throttling under load | Use `PAY_PER_REQUEST` billing mode |
| **Polling scan** | `table.scan()` every 45s | O(N) — grows with order volume | Add GSI on `status` + `created_at` |
| **Payment services** | Single container each | No horizontal scaling | Stateless — can scale, but APScheduler would create duplicate polling |
| **APScheduler** | In-process BackgroundScheduler | One container = one scheduler; multiple = duplicate polls | Use DynamoDB-based distributed lock or separate scheduler service |
| **CESC sync latency** | 3 synchronous HTTP calls per payment | Blocks success handler | Move CESC sync to async background task |
| **Retry tracker contention** | Shared DynamoDB table, no locking | Race condition on concurrent failures | Use DynamoDB conditional updates (`ConditionExpression`) |

---

# REVIEWER_FAQ

**Q1: Why microservices for payment gateways?**
Each gateway (BillDesk, Razorpay RBL, Razorpay Axis) has different credentials, APIs, callback URLs, and DynamoDB tables. Isolation means a crash in one service cannot affect others. It also allows independent deployment when credentials rotate.

**Q2: Why separate RBL and Axis services?**
CESC may route different bill types or customer segments to different bank gateways. Axis Bank and RBL Bank have different Razorpay key pairs. Keeping them separate allows independent scaling and credential management.

**Q3: How is idempotency handled?**
**Partial.** The `last_notified_payment_id` in DynamoDB prevents duplicate SSE notifications for the same failed payment. However, the `/success` callback has no idempotency guard — a Razorpay callback retry would re-execute CESC sync and notifications.

**Q4: How are duplicate payments prevented?**
The `RetryTracker` blocks new order creation after 3 failures. However, a user can still try multiple times within the limit. The Razorpay SDK prevents duplicate captures for the same `order_id`.

**Q5: How are webhooks verified?**
Razorpay does not use traditional webhooks in this implementation — it uses a browser form POST to `/success`. The authenticity is verified via HMAC-SHA256 signature using `RAZORPAY_KEY_SECRET`. Invalid signatures return HTTP 400.

**Q6: What happens if the `/success` callback fails mid-way?**
- If the DynamoDB update fails: order stays `created`, polling worker will eventually detect `captured` status via Razorpay API and recover.
- If CESC sync fails: `cesc_synced` stays `0`, but no automated retry exists. Manual re-sync is required.
- If SSE notification fails: User doesn't get push notification; they can check status manually.

**Q7: How are retries handled?**
Two layers: (1) APScheduler polls every 45s and detects status changes via Razorpay API. (2) RetryTracker limits payment attempts to 3 per cooldown window. There is no automatic retry for failed CESC sync.

**Q8: How are transactions reconciled?**
The `cesc_synced` field acts as a reconciliation flag. The polling worker calls `_sync_with_cesc()` for both success and failure states, setting `cesc_synced=1` on success. Orders with `cesc_synced=0` and terminal status are candidates for manual reconciliation.

**Q9: How is scalability achieved?**
Currently limited. The services are stateless (DynamoDB handles state), enabling horizontal scaling of the API layer. The APScheduler polling creates a challenge — multiple instances would run duplicate polling jobs. A distributed lock or dedicated scheduler is needed for true horizontal scaling.

**Q10: What are the security controls?**
(1) HMAC signature on payment callbacks. (2) `X-Internal-Secret` for service-to-service calls. (3) RetryTracker rate limiting. (4) Razorpay API accessed with Basic Auth. (5) CESC accessed with JWT (refreshed per request).

**Q11: How is observability implemented?**
Python `logging` module with INFO/ERROR levels. Logs go to Docker stdout (captured by CloudWatch if configured). No structured logging, no correlation IDs, no metrics. Health checks exist but are shallow.

**Q12: How is fault tolerance handled?**
`restart: unless-stopped` in Docker Compose handles container crashes. `try/except` blocks in the polling worker ensure one order failure doesn't crash the entire polling cycle. DynamoDB state persists across restarts.

**Q13: What are the known limitations?**
(1) No idempotency on `/success` callback. (2) `table.scan()` does not scale. (3) CESC sync is synchronous and blocking. (4) APScheduler cannot run in multi-instance mode. (5) No circuit breaker for CESC outages. (6) UAT IP hardcoded in CESC payload.

**Q14: What are the biggest technical risks?**
(1) Production CESC URL is UAT (`rlbsti_uat.php`) — payments won't reconcile in production. (2) Test Razorpay keys in `.env` — live payments impossible. (3) No idempotency on callback — double billing risk. (4) No alerting when APScheduler thread dies — polling stops silently.

**Q15: What would you improve first?**
1. Replace `table.scan()` with DynamoDB GSI queries.
2. Add idempotency key to `/success` handler (check if `status == "captured"` before re-processing).
3. Move CESC sync to an async background task (remove from the synchronous callback chain).
4. Add structured JSON logging with correlation IDs.
5. Replace UAT CESC URL with env-configurable production URL.
