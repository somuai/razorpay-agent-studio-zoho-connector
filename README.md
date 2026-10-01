# Zoho Inventory Connector for Razorpay Agent Studio

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Architecture](https://img.shields.io/badge/MCP-FastMCP-brightgreen.svg)](https://modelcontextprotocol.io/)
[![Evaluation](https://img.shields.io/badge/Evaluation-SIMULATED-orange.svg)](eval/results/summary.json)
[![Security](https://img.shields.io/badge/Security-Read--Only-success.svg)](docs/DESIGN.md)

---

## 1. Merchant Context & The Real Problem Behind the Ask

**Merchant:** *Kaveri Home Goods*, a direct-to-consumer home-decor brand based in Bangalore.  
**Tech Stack:** Razorpay Checkout on custom storefront; Zoho Inventory (India DC) for catalog, inventory stock levels, and sales order fulfillment.

When Kaveri Home Goods approached Razorpay Agent Studio, they presented two seemingly straightforward requests:

| # | Stated Ask | Operational Hypothesis (The Real Problem) | Affected Agent Studio Agent |
|---|---|---|---|
| **P1** | *"Recover more abandoned carts."* | The merchant was firing discounts and re-engagement WhatsApp nudges for items that were already stock-out or committed to prior orders. Marketing spend and discount budget were wasted; customers arrived at checkout only to encounter disappointment and bounce. The agent had zero stock visibility. | **Abandoned Cart Conversion** |
| **P2** | *"Win more chargebacks."* | Merchant rebuttal submissions lacked definitive delivery proof (unlinked tracking numbers, missing carrier timestamps, unsynchronized courier status). Ops agents manually stitched records across Zoho, courier portals, and Razorpay, routinely missing statutory rebuttal deadlines. | **Dispute Responder** |

### Core Metrics & Baseline

| Metric | Business Definition | Naive Agent Baseline | Connector-Aware Target | Headline Result (**SIMULATED**) |
|---|---|---|---|---|
| **M1: Wasted Nudges** | % of nudges sent for unavailable SKUs & wasted discount budget | 28.5% wasted nudges; ₹47,650 discount budget wasted / 200 carts | 0% wasted nudges on stock-out items; ₹0 wasted discount budget | **0.0% wasted nudges**<br>*(₹0 wasted discount)* |
| **M2: Dispute Evidence Completeness** | % of disputes backed by complete fulfillment proof (Order + Invoice + Tracking + Delivery) | 37.5% manual assembly completeness; 18h turnaround | 100% of available proof compiled in 1 tool call (< 150ms) | **100% complete evidence assembly** for eligible orders |
| **M3: Agent API Footprint** | API calls per decision & % of Zoho Free Plan daily quota (1,000 req/day) | > 5 calls/decision; quota exhausted by midday | <= 1.2 calls/decision; < 25% daily quota consumed | **1.05 calls / decision**<br>*(11.2% quota consumed)* |

> **DISCLAIMER:** All evaluation benchmarks and figures reported above and within this repository are **SIMULATED** on fictional merchant datasets (`seed=42`). No real merchant data, customer credentials, or production databases were accessed.

---

## 2. Quickstart Guide

This connector is built to run entirely offline out of the box using a deterministic mock Zoho Inventory server, and can seamlessly connect to live Zoho credentials.

### Prerequisites
- Python 3.11+
- `uv` package manager (recommended) or standard Python virtual environment

### 3-Command Offline Quickstart

```bash
# 1. Setup virtual environment and dependencies
make setup

# 2. Run the deterministic evaluation suite (M1, M2, M3 metrics)
make eval

# 3. Launch end-to-end demo exercising all tools and rate limiting offline
make demo
```

---

## 3. Architecture & Security Guarantees

```
┌─────────────────────────────────────────────────────────────┐
│                 Razorpay Agent Studio                       │
│    (Abandoned Cart Agent  │  Dispute Responder Agent)       │
└──────────────────────────────┬──────────────────────────────┘
                               │ FastMCP Protocol (stdio/JSON-RPC)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│            Zoho Inventory MCP Connector (src/)              │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ FastMCP Tool Layer (8 Read-Only Tools)              │   │
│   │ - Input Sanitization & Bounds (FR-5.5, FR-13)        │   │
│   │ - Response Capping (8 KB) & PII Masking (FR-6)      │   │
│   │ - Stdio Hygiene: logs to stderr only (NFR-8)        │   │
│   └──────────────────────────┬──────────────────────────┘   │
│                              ▼                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ Domain Services Layer                               │   │
│   │ - Stock Availability Service (actual_available)     │   │
│   │ - Dispute Evidence Synthesizer (strict no-guess)    │   │
│   └──────────────────────────┬──────────────────────────┘   │
│                              ▼                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ Client & Resilience Layer                           │   │
│   │ - Strictly GET-Only HTTP Surface (FR-2.1)           │   │
│   │ - In-Process TTL Cache (Items: 300s, Stock: 60s)    │   │
│   │ - Token Bucket (80 req/min) & Concurrency Sem (5)   │   │
│   │ - Circuit Breaker (Code 44/1070) & Zero-Retry 45    │   │
│   │ - Single-Flight TokenManager (FR-1.3)               │   │
│   └──────────────────────────┬──────────────────────────┘   │
└──────────────────────────────┼──────────────────────────────┘
                               │ HTTPS (GET only)
                               ▼
            ┌────────────────────────────────────┐
            │   Zoho Inventory API v1 (India DC) │
            │   or Local Deterministic Mock      │
            └────────────────────────────────────┘
```

### Non-Negotiable Guarantees
1. **Read-Only by Construction:** No HTTP method other than `GET` exists in any client, service, or tool code path.
2. **Input Injection Protection (FR-13):** Every search string, date, SKU, and identifier passes through strict character allowlists and length checks. Parameter delimiters and quote operators are rejected with clear agent guidance.
3. **Stdio Protocol Hygiene (NFR-8):** Zero stdout pollution. All application logs, telemetry, and audit records route to stderr.
4. **Agent-Centric Error Taxonomy (FR-7):** Every failure returns structured, actionable guidance explaining what happened, whether to retry, and alternative strategies.
5. **PII Masking by Default (FR-6.3):** Customer emails, phone numbers, and full names are masked in memory before being returned to LLM contexts.

---

## 4. MCP Tools Overview

| Tool Name | Intended Agent User | Decision Function |
|---|---|---|
| `get_stock_availability` | Abandoned Cart Conversion | Returns sellable inventory (`actual_available_stock`), reorder threshold, status (`in_stock`, `low_stock`, `out_of_stock`), and warehouse breakdown. |
| `get_order_fulfillment_evidence` | Dispute Responder | Synthesizes sales order, invoice, package, carrier tracking, and delivery timestamp into an audit-ready rebuttal payload without speculation. |
| `list_items` | Catalog Discovery | Paged browsing of active items with bounded limits (<= 50). |
| `get_item` | Product Specialist | Granular detail of an item record by numeric ID. |
| `search_items` | Catalog Discovery | Filtered search by name, SKU, and low-stock status. |
| `list_sales_orders` | Order Specialist | Paged browsing of orders by status, date range, or customer ID. |
| `get_sales_order` | Order Specialist | Granular detail of a sales order with attached line items. |
| `search_sales_orders` | Payment Reconciliation | Matches payments to orders via `reference_number` or custom fields, explicitly reporting `match_basis`. |

---

## 5. Live Zoho Integration & Verification

To run against a live Zoho Inventory organization:

1. Copy `.env.example` to `.env` and fill in your Zoho credentials (never committed):
   ```bash
   cp .env.example .env
   ```
2. (Optional) Run the isolated seeding script to populate test items and orders in a trial org:
   ```bash
   python scripts/seed_zoho.py --i-understand-this-writes
   ```
3. Run the read-only live smoke test:
   ```bash
   make live-smoke
   ```
4. Verify via MCP Inspector: See [docs/INSPECTOR_DEMO.md](docs/INSPECTOR_DEMO.md) for step-by-step instructions.

---

## 6. Repository Documentation Map

- [docs/DESIGN.md](docs/DESIGN.md): Technical architecture, decisions, trade-offs, and production roadmap.
- [docs/API_NOTES.md](docs/API_NOTES.md): Verified Zoho API specifications and citations.
- [docs/TOOLS.md](docs/TOOLS.md): Concrete input/output JSON examples for all 8 MCP tools.
- [docs/AGENT_CAPABILITIES.md](docs/AGENT_CAPABILITIES.md): Detailed CAN / CANNOT / DEPENDS ON matrices.
- [docs/MEASUREMENT.md](docs/MEASUREMENT.md): Metric formulations, telemetry schemas, and kill criteria.
- [docs/MERCHANT_DISCOVERY.md](docs/MERCHANT_DISCOVERY.md): Discovery questionnaire and 1-week implementation roadmap.
- [docs/MERCHANT_SUMMARY.md](docs/MERCHANT_SUMMARY.md): Plain-language 1-page operational brief for merchant ops heads.
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md): Transparent limitations and their production solutions.
- [docs/WALKTHROUGH.md](docs/WALKTHROUGH.md): 3-minute executive video presentation script.
- [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md): Architectural decisions and ambiguity resolutions.
- [docs/DONE_CHECKLIST.md](docs/DONE_CHECKLIST.md): Binary verification gate checklist with pasted evidence.
