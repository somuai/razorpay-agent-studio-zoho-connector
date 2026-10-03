# Codex Run Sheet (final) — Zoho Inventory connector, Razorpay FDE assignment

Order of operations: setup → plan → goal → (you, in parallel) Zoho org → live proof → review → audit → submit.
Keep the last 2 hours for live proof, recording and the form. Decide your debugging time-box for live Zoho NOW (suggest 90 minutes). If it still fails after that, submit mock-verified and state "live mode not verified" in the README.

---

## Step 0 — Setup (10 min)

```bash
mkdir zoho-inventory-connector && cd zoho-inventory-connector
git init
# copy AGENTS.md into the repo root
codex --version      # update if old; /goal needs a recent build
```

Enable features: run `/experimental`, toggle **Goals** and **Subagents**, restart Codex. Or add to `~/.codex/config.toml`:

```toml
[features]
goals = true
```

Permissions: workspace-write with approvals on request (`/permissions`). Keep network on (it must read Zoho docs). Do not use any no-sandbox mode.

AGENTS.md may be visible if your repo is public; it contains no secrets. Never paste keys into the Codex chat.

---

## Step 1 — Master prompt (in Plan mode)

Start Codex and paste:

```
/plan You are a Forward-Deployed Engineer on Razorpay's Agent Studio team, assigned to a fictional merchant (Kaveri Home Goods) that uses Zoho Inventory and Razorpay Checkout. Your job is to find the real problem behind the ask, build the first working version yourself, and prove whether it moved the metric. This is not a demo role.

Context: Razorpay Agent Studio is Razorpay's marketplace and builder for autonomous payment agents (built on the Claude Agent SDK). Its Abandoned Cart Conversion and Dispute Responder agents need merchant data that lives outside Razorpay. You are building the MCP connector that gives those agents read-only access to Zoho Inventory. The agent is the end user of every tool you design, so tool descriptions, output size and error messages matter as much as the code. How Agent Studio loads private connectors is not public: record that as an assumption, never claim internal knowledge.

Read AGENTS.md fully (especially section 0, "What Agent Studio is"); it is the PRD and working agreement. Produce an execution plan for milestones M1 through M10 (M11 optional).

For each milestone give: files to create, the FR/NFR IDs covered, the verification command, which subagent role (if any) can take bounded non-overlapping parts in parallel, and the main risk. Specify the order in which Zoho facts must be verified before code depends on them. Flag any requirement that is ambiguous, wrong, or too risky for the time budget and propose a resolution. Confirm the cut order from AGENTS.md section 12 is respected. Make sure M5 prepares live-proof scripts that skip cleanly when credentials are absent, and that the evaluation (FR-10) and the docs set (FR-12) are not dropped under time pressure.

Do not write code yet. Ask nothing; where you would ask, state your assumption and reason.
```

Review the plan against three checks:
1. The mock server comes before the client; Zoho docs are verified first.
2. FR-10 (evaluation) and the merchant docs are present.
3. M5 (live-proof readiness) exists and doesn't block on credentials.

Then say: `Write this plan to docs/PLAN.md.`

---

## Step 2 — Goal (leave Plan mode first)

Press **Shift+Tab** to leave Plan mode (goal work can silently stall in Plan mode on current builds). Then:

```
/goal Complete milestones M1 through M10 in AGENTS.md for the Zoho Inventory MCP connector, following docs/PLAN.md. The goal is achieved only when every item in docs/DONE_CHECKLIST.md is ticked WITH pasted evidence from actually running: make lint, make typecheck, make test (core coverage >= 85%), make eval twice with byte-identical JSON, make demo offline, make clean-clone-test, the secrets scan, and all FR-12 docs present and specific with the README first screen compliant. Do not mark anything done on assumption. If a Zoho fact cannot be verified, mark it UNVERIFIED and continue. Never invent merchant interviews, results, screenshots or live-verification claims; label all evaluation output SIMULATED. Commit at the end of each milestone. If a live credential is needed, continue in mock mode and leave the live claim as "not yet verified".
```

Kick off:

```
Begin with M1. Use subagents per AGENTS.md section 11 for bounded, non-overlapping work: run docs-verifier on docs/API_NOTES.md while you scaffold the repo and Makefile. Never have two agents write the same files. Keep going through the milestones without stopping to ask questions.
```

Check status with `/goal`. If it stalls or hits its budget: `/goal resume`, or reset the goal naming only the remaining milestones.

---

## Step 3 — Your tasks while Codex runs (do these early)

1. **Zoho org (India DC):** sign up at zoho.in, create a throwaway Inventory org (free plan or trial). Use no real business data.
2. **Organization ID:** find it in the org profile settings.
3. **Self Client:** create one at api-console.zoho.in. You'll get a client ID and secret. Don't generate the grant code yet.
4. **After M5 is committed** (scripts exist):
   - Put `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`, `ZOHO_ORG_ID`, `ZOHO_DC=in` in `.env`.
   - Generate a grant code with the **read-only** scopes in `docs/API_NOTES.md`, then immediately run `make zoho-token` (codes expire in minutes).
   - For seeding only: generate a separate grant with the seeding scopes, run the seed helper's token step, then `python scripts/seed_zoho.py`. Revoke the write-scope token afterwards.
   - Run `make live-smoke`.
5. **Capture evidence:** screenshots of the masked live-smoke output and of the MCP Inspector (`docs/INSPECTOR_DEMO.md`) into `docs/assets/`. Only then tell Codex: `Live verification confirmed on <date>. Update README's Live verification section with the screenshots and mark docs accordingly.`
6. **If live fails:** paste the error into Codex: `Debug against docs/API_NOTES.md; fix the connector; keep mock tests green.` Stop at your time-box.

---

## Step 4 — Adversarial review (after M9)

```
Act as the reviewer subagent from AGENTS.md: read-only, edit nothing. Review against: (1) every FR/NFR and acceptance criterion with file:line evidence or "missing"; (2) the honesty rules in section 10, quoting any sentence in README or docs that overclaims, implies real merchant data, or claims live verification without confirmation; (3) security: any path where a token, Authorization header, or PII could be logged, returned by a tool, or committed; (4) any non-GET request in src/; (5) query-injection and stdout-hygiene tests; (6) MCP tool descriptions: would an LLM know when to use and not use each tool; (7) a hiring manager's 10-minute read: does the README first screen explain the merchant problem, the metrics and the simulated result in plain language, and is the live-verification status stated accurately. Return findings ranked by severity.
```

Then:

```
Fix every high and medium finding. Add or update tests where applicable. Re-run all gate commands and update docs/DONE_CHECKLIST.md with fresh evidence.
```

---

## Step 5 — Final audit

```
Run the final audit: make lint, make typecheck, make test, make eval twice (diff the JSON), make demo, make clean-clone-test, and the secrets scan. Confirm no file contains a real credential or real personal data, every evaluation artifact says SIMULATED, and the README's live-verification status matches reality. Print the final report from AGENTS.md section 12.
```

---

## Step 6 — Optional (only if everything above is green)

```
M11: implement examples/agent_demo.py per FR-11.5 using a free-tier Gemini model. Read the current Google Gen AI SDK docs first; do not rely on memory. GEMINI_API_KEY comes from the environment; exit with a clear message if missing. Cap model calls, add a delay between them, back off on 429. Mock data only. Answer: "Should I send a cart nudge for SKU <low-stock SKU>, and what offer?" and "Assemble dispute evidence for order <seeded order> and tell me what's missing." State in the README that Agent Studio is built on Claude's Agent SDK and this demo only shows the server is model-agnostic.
```

A free key comes from Google AI Studio. Check the limits shown there; they change.

---

## Step 7 — Submission checklist (you)

- [ ] Repo public, or shared with the account the form names.
- [ ] `git status` clean; no `.env` or token files; secrets scan passed on the final commit.
- [ ] README first screen: problem, metrics, simulated result, live-verification status (true).
- [ ] `docs/MERCHANT_SUMMARY.md` readable by a non-engineer.
- [ ] 2–3 minute screen recording in your own voice, following `docs/WALKTHROUGH.md` as an outline.
- [ ] Revoke the Zoho Self Client or tokens after submitting.
- [ ] Form: assignment link, essay answers (Talcher deployment as the main example; claim only what you can defend), on-site answer, start-date answer.

---

## Troubleshooting

- **Goal active, nothing happens:** you're likely still in Plan mode. Shift+Tab, then `/goal resume`.
- **Codex asks questions:** reply `Follow AGENTS.md section 11 (Autonomy): assume, log in docs/ASSUMPTIONS.md, continue.`
- **No subagents:** `Subagents are unavailable; do the same work sequentially in plan order.`
- **Context heavy:** `Summarize progress into docs/PLAN.md (done / next / risks), then continue.`
- **Docs unreachable:** have Codex mark facts UNVERIFIED and make them configurable; or paste Zoho doc pages into `docs/vendor/` for it to read.
- **Scope creep (write tools, UI, database):** `Out of scope per AGENTS.md section 2. Revert and continue.`
- **Grant code expired:** regenerate it and rerun `make zoho-token` immediately.
- **Zoho 429 / code 45 during live tests:** you may have hit the daily cap on a free org. Stop, wait for reset, and rely on mock tests for the rest.
