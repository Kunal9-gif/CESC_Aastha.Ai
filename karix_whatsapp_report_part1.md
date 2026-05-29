# AASTHA AI — Karix WhatsApp Integration Enterprise Report (Part 1 of 3)
## Executive Summary · Repository Analysis · FastAPI Architecture · LangGraph Runtime · Async Infrastructure

> **VERIFIED FINDINGS ONLY** — All analysis sourced from direct file inspection.
> Inferred items are explicitly marked `[INFERRED]`.

---

# 1. Executive Summary

## Platform Maturity Assessment

| Dimension | Current State | Production-Readiness |
|---|---|---|
| Core AI Orchestration | LangGraph + Bedrock Agents + Strands | ✅ Production-grade |
| Web API | FastAPI, async-safe | ✅ Production-grade |
| Payment Microservices | 3 independent services | ✅ Production-grade |
| WhatsApp Integration | Legacy webhook in `run.py` — **commented out in Docker** | 🔴 NOT deployed |
| Redis | **None detected** anywhere in codebase | 🔴 Not implemented |
| RAG System | **None detected** — uses Bedrock Agent Lambda action groups | 🟡 Via Bedrock |
| Session Management | DynamoDB checkpointer (prod) / MemorySaver (dev) | ✅ Functional |
| Karix Integration | **Zero Karix code found** | 🔴 Not started |
| Observability | Basic `print()` + Python `logging` | 🟡 Minimal |
| Multi-tenancy | Single CESC tenant | 🟡 Single-tenant |

## Critical Finding

> The WhatsApp container (`run.py`, port 8000) is **commented out** in `docker-compose.yml`. The production system currently operates **exclusively via the Web API** (`web_integration/run_web.py`, port 8001). Karix integration requires building a new inbound webhook service from scratch, connecting it to the existing LangGraph runtime.

---

# 2. Repository Capability Analysis (Verified)

## 2.1 What Actually Exists

### ✅ VERIFIED — FastAPI Web API
- **File:** `web_integration/run_web.py` (753 lines)
- Endpoints: `/chat`, `/health`, `/notification-stream/{user_id}`, `/internal/payment-notify`, `/internal/outage-notify`, `/pending-notifications/{user_id}`, `/presigned-url`
- Uses custom raw ASGI CORS middleware (not FastAPI's built-in)
- Async-safe: uses `asyncio.to_thread()` to offload blocking LangGraph calls

### ✅ VERIFIED — LangGraph Multi-Agent Orchestration
- **File:** `graphs/master_graph.py`
- 12+ journey subgraphs (bill payment, supply off, name change, new connection, etc.)
- Two AI runtime patterns: Strands (synchronous tool-calling) + Bedrock Agents (async Lambda)
- Interrupt/resume capability via `langgraph.types.interrupt`
- Checkpointing: `MemorySaver` (dev) or `DynamoDBSaver` (prod, table: `aastha-langgraph-checkpoints`)

### ✅ VERIFIED — APScheduler Background Workers
- **Files:** `razorpay_service/app/workers/polling_worker.py`, `razorpay_axis_service/app/workers/polling_worker.py`, `billdesk_service/app/workers/polling_worker.py`
- `BackgroundScheduler` — 45-second polling interval
- No Redis, no Celery, no RQ — pure APScheduler + DynamoDB

### ✅ VERIFIED — SSE Notification System
- In-memory dict: `notification_sse_connections = {}` (user_id → list[asyncio.Queue])
- Online: direct SSE push via `queue.put()`
- Offline: DynamoDB fallback (`pending_messages`, `pending_payments` tables)
- **Critical limitation:** In-memory — does NOT survive restarts, NOT multi-process safe

### ✅ VERIFIED — WhatsApp Webhook (Legacy, NOT Deployed)
- **File:** `run.py` (148 lines)
- Receives WhatsApp events, extracts messages, invokes LangGraph
- Uses `COMP_SRC` env var to switch WhatsApp/Web modes
- Audio transcription support (`audio_to_text()` before graph invocation)
- **Status:** Container commented out in `docker-compose.yml`

### ✅ VERIFIED — Payment Microservices (3 services)
- BillDesk (port 8002), Razorpay RBL (port 8003), Razorpay Axis (port 8004)
- Each has: FastAPI routes, DynamoDB storage, APScheduler polling, CESC sync
- Internal communication via Docker network (`http://razorpay-service:8003`)

### ✅ VERIFIED — Multilingual Support
- **File:** `nodes/linear_flow_nodes/translation_node.py`
- Languages: English, Hindi, Hinglish, Bengali, Benglish
- Fast path: local keyword detection for ASCII text
- Slow path: Claude Sonnet 4 via Bedrock for non-ASCII

### ✅ VERIFIED — CESC API Integration
- Dual-step JWT auth: `botKeyStore.txt` → `getSecretKey` → Bearer token
- APIs used: `chkconsumer`, `consumerDetails`, `GetBillDetailsBreakUp`, `CreatePaymentOrder`, `saveChatHistory`, `chkComplaintStatus`, `getHTComplaintStatus`, `getComplaintStatus`

### ❌ NOT FOUND — Redis
- No `redis`, `aioredis`, `redis-py`, `celery`, `rq` in `requirements.txt`
- No Redis connection strings in any `.env` file
- No Redis imports in any Python file scanned

### ❌ NOT FOUND — RAG Pipeline
- No vector database (Pinecone, Chroma, FAISS, Weaviate)
- No embedding generation in codebase
- No chunking/indexing pipeline
- Bedrock Agents use Lambda action groups for knowledge retrieval [INFERRED from agent pattern]

### ❌ NOT FOUND — Karix Integration
- No Karix SDK or HTTP client
- No Karix API endpoints
- No WhatsApp template management code
- No delivery status handlers for Karix

---

# 3. FastAPI Architecture (Verified)

## 3.1 Application Topology

```
aastha-web (port 8001)          → Primary API — web frontend + SSE
razorpay-service (port 8003)    → Payment microservice (independent FastAPI app)
razorpay-axis-service (port 8004) → Payment microservice (independent FastAPI app)
billdesk-service (port 8002)    → Payment microservice (independent FastAPI app)
```

## 3.2 aastha-web FastAPI App (`run_web.py`)

```python
# Startup sequence (verified)
1. load_dotenv()
2. boto3.resource("dynamodb")          # DynamoDB client initialized
3. user_notifications_table setup      # UserNotifications table
4. pending_table setup                 # pending_messages table
5. pending_payments_table setup        # pending_payments table

# Checkpointer selection
if USE_DYNAMODB=true:
    from langgraph.checkpoint.dynamodb import DynamoDBSaver
    checkpointer = DynamoDBSaver(table_name="aastha-langgraph-checkpoints")
    graph = graph_builder.compile(checkpointer=checkpointer)
else:
    from graphs.master_graph import master_graph as graph  # MemorySaver pre-compiled

# CORS: Custom raw ASGI middleware (not FastAPI CORSMiddleware)
# Handles preflight OPTIONS, injects Access-Control headers into all responses
# CORS whitelisted origins: ALLOWED_ORIGINS env var
```

## 3.3 `/chat` Endpoint — Full Verified Flow

```
POST /chat
├── Extract: user_id, session_id, text, document_file_name, user_lat, user_long,
│           channel, mob, consumer_type, opt_in, new_opt_in
├── Validate: user_id required, session_id required, text OR document required
├── Build composite thread_id: "{user_id}-{session_id}" (max 100 chars)
├── asyncio.to_thread(invoke_graph, ...)   ← offloads blocking call
│   └── invoke_graph():
│       ├── graph.get_state(config)        ← check for interrupt
│       ├── IF interrupt: graph.invoke(Command(resume=text))
│       └── ELSE: graph.invoke(initial_state, config)
└── Return: {status, reply, interrupted, interrupt_question, opted_in, routing}
```

## 3.4 Internal Security Model

```python
# Service-to-service auth
X-Internal-Secret: cesc-secret-2026   # Verified in .env: INTERNAL_SECRET

# Endpoints protected by this header:
POST /internal/payment-notify
POST /internal/outage-notify

# No JWT auth on public endpoints (/chat, /notification-stream, /pending-notifications)
# [RISK: /chat is unauthenticated — any caller can invoke the AI]
```

## 3.5 Middleware Stack

```
Raw ASGI CORS Middleware (custom)
    ↓
FastAPI Router
    ↓
Endpoint handlers
```

No rate limiting, no request ID injection, no structured logging middleware detected.

---

# 4. LangGraph Runtime Analysis (Verified)

## 4.1 Graph Compilation

```python
# File: graphs/master_graph.py
graph_builder = StateGraph(AgentState)

# Node registration (verified from imports)
graph_builder.add_node("session_node", session_node)
graph_builder.add_node("translation_node", translation_node)
graph_builder.add_node("optin_gate_node", optin_gate_node)
graph_builder.add_node("router_agent", router_agent_node)
graph_builder.add_node("clarification_node", clarification_node)
# ... 12+ journey subgraphs as nodes

master_graph = graph_builder.compile(checkpointer=MemorySaver())
```

## 4.2 State Persistence

| Environment | Checkpointer | Scope |
|---|---|---|
| Development | `MemorySaver` | In-process only |
| Production | `DynamoDBSaver` | Persistent, cross-restart |
| Isolation | Per `thread_id = user_id-session_id` | Per-user-per-session |

## 4.3 Interrupt/Resume Pattern

```python
# In clarification_node.py — verified
user_reply = interrupt(masked_question)
# → Graph execution PAUSES here
# → run_web.py returns {"status": "interrupted", "interrupt_question": ...}

# On next user message:
# → graph.get_state(config).next is non-empty
# → graph.invoke(Command(resume=user_reply), config)
# → Graph resumes from interrupt point
```

## 4.4 Two AI Runtime Patterns

### Pattern A — Strands Agent (Tool-Calling)
```
Used by: bill_payment_graph, router_agent, whatsapp_optin_graph, name_change_graph

bill_payment_llm = Agent(
    system_prompt=BILL_PAYMENT_SYSTEM_PROMPT,
    tools=[...8 tools...]
)
result = bill_payment_llm(prompt, structured_output_model=BillPaymentDecision)
# → Synchronous execution, blocks thread
# → Tools call CESC APIs, payment microservices
# → Structured Pydantic output
```

### Pattern B — Bedrock Agent + Schema Parser (Two-Phase)
```
Used by: report_supply_off_graph, discovery_graph, billing_complaints_graph, etc.

Phase 1: raw = invoke_bedrock_agent(agent_id, alias_id, session_id, enriched_input)
         → AWS Bedrock Agent Runtime API
         → Agent internally invokes Lambda action groups
         → Read timeout: 300s (5 minutes)
         → Returns free-form text

Phase 2: decision = parse_to_schema(raw, ReportSupplyOffDecision)
         → Claude Sonnet 4 via Bedrock Runtime
         → Extracts typed Pydantic schema from raw text
         → Read timeout: 120s (2 minutes)
```

## 4.5 Session Namespacing

```python
# Composite thread_id prevents cross-user collision
composite_session_id = f"{user_id}-{session_id}"
if len(composite_session_id) > 100:
    composite_session_id = composite_session_id[-100:]

# Bedrock Agent session uses same composite ID + journey suffix
# e.g., "user123-session456_rso" for Report Supply Off
```

---

# 5. Async Infrastructure Analysis (Verified)

## 5.1 Actual Async Components

| Component | Mechanism | Thread-Safe? |
|---|---|---|
| `/chat` handler | `asyncio.to_thread()` | ✅ Yes |
| SSE stream | `asyncio.Queue` per user | ✅ Yes |
| DynamoDB writes in async routes | `loop.run_in_executor(None, lambda: ...)` | ✅ Yes |
| APScheduler polling workers | BackgroundScheduler (daemon thread) | ✅ Yes |
| Notification background tasks | `asyncio.create_task()` | ✅ Yes |
| LangGraph invocation | Synchronous (runs in thread pool) | ✅ Via to_thread |
| CESC API calls | Synchronous `requests.post()` | ⚠️ Blocking in worker thread |

## 5.2 Missing Async Infrastructure

| Component | Status | Impact |
|---|---|---|
| Redis / Message Queue | ❌ Not present | Single-process only, no horizontal scaling |
| Celery / RQ / ARQ | ❌ Not present | No distributed task processing |
| WebSocket support | ❌ Not present | SSE only |
| Request ID / trace correlation | ❌ Not present | Hard to debug distributed issues |
| Circuit breakers | ❌ Not present | CESC API failures cascade |

## 5.3 Current Processing Bottlenecks

```
[BOTTLENECK 1] LangGraph invocation (via asyncio.to_thread)
  → Strands Agent calls block the worker thread for 5-30 seconds
  → Bedrock Agent calls can block for up to 5 minutes
  → Each concurrent user consumes one thread from the thread pool

[BOTTLENECK 2] SSE in-memory dict
  → notification_sse_connections is a plain Python dict
  → Dies on process restart
  → Cannot serve multiple uvicorn workers (--workers > 1)

[BOTTLENECK 3] APScheduler polling
  → scan() on DynamoDB every 45s — no pagination, O(N) on table size
  → All three payment services have independent schedulers
```

---

# 6. WhatsApp / Karix Readiness (Verified vs Required)

## 6.1 Current WhatsApp Code (`run.py`) — Verified

```python
# Verified from run.py lines 1-148

@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()
    
    # Extract WhatsApp message structure
    entry = body.get("entry", [{}])[0]
    changes = entry.get("changes", [{}])[0]
    value = changes.get("value", {})
    messages = value.get("messages", [])
    
    if not messages:
        return {"status": "no messages"}
    
    message = messages[0]
    user_id = message.get("from")           # WhatsApp phone number
    message_body = message.get("text", {}).get("body", "")
    
    # Audio message handling
    if message.get("type") == "audio":
        audio_path = message.get("simulated_audio_path")   # ← Simulated! Not real Karix
    
    # Invoke LangGraph
    result = invoke_graph(user_id, session_id, message_body, audio_path)
    return result
```

**Critical Finding:** The `simulated_audio_path` field reveals this was built against a **simulated WhatsApp API**, not Karix's actual schema. The audio handling will need a full rewrite for Karix.

## 6.2 Karix Readiness Gap Analysis

| Capability | Current State | Karix Requirement | Gap |
|---|---|---|---|
| Inbound webhook receiver | ✅ Basic POST handler in `run.py` | Karix event schema | 🟡 Schema mismatch |
| Webhook signature validation | ❌ None | HMAC/secret validation | 🔴 Must implement |
| Message deduplication | ❌ None | Idempotency key | 🔴 Must implement |
| Outbound messaging | ❌ None (only graph result returned) | Karix Send Message API | 🔴 Must implement |
| Media/audio handling | ⚠️ Simulated only | Karix media download API | 🔴 Must rewrite |
| Template message sending | ❌ None | Karix Template API | 🔴 Must implement |
| Delivery status handling | ❌ None | Karix status webhooks | 🔴 Must implement |
| Multi-user concurrency | ⚠️ Thread pool limited | Per-user isolation | 🟡 Needs queue |
| Session window (24h) | ❌ No enforcement | WhatsApp 24h rule | 🔴 Must implement |
| Typing indicators | ❌ None | Optional Karix API | 🟡 Nice-to-have |
| Read receipts | ❌ None | Optional Karix API | 🟡 Nice-to-have |
| Interactive buttons | ❌ None | Karix interactive messages | 🔴 Journey UX need |
| Message chunking | ❌ None | WA 4096 char limit | 🔴 Must implement |

## 6.3 What Can Be Reused

| Component | Reuse Potential |
|---|---|
| LangGraph orchestration (`graphs/`) | ✅ 100% — no changes needed |
| All journey agents (`agents/`) | ✅ 100% — pure Python logic |
| CESC API tools (`agents/orchestrator/tools.py`) | ✅ 100% — no WhatsApp dependency |
| Translation node | ✅ 100% — language-agnostic |
| Payment microservices | ✅ 100% — independent services |
| DynamoDB session checkpointing | ✅ 100% — already persistent |
| SSE system (`run_web.py`) | ✅ Keep for web channel |
| `invoke_graph()` function | ✅ 100% — channel-agnostic |
| `extract_reply()` function | ✅ 100% |

---
