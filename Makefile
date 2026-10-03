.PHONY: help setup lint format typecheck test mock-server spec eval demo live-preflight live-smoke live-probe live-assert live-pii-check live-token-status zoho-token net-watch live-burst check-secrets clean clean-clone-test screenshots-check

PYTHON ?= .venv/bin/python
UVICORN ?= .venv/bin/uvicorn
RUFF ?= .venv/bin/ruff
MYPY ?= .venv/bin/mypy
PYTEST ?= .venv/bin/pytest

help:
	@echo "Zoho Inventory Connector - Razorpay Agent Studio"
	@echo "Available targets:"
	@echo "  make setup          - Initialize Python venv and install dependencies"
	@echo "  make lint           - Run linter (ruff)"
	@echo "  make format         - Autoformat code with ruff"
	@echo "  make typecheck      - Run static type checking (mypy)"
	@echo "  make test           - Run full test suite with >=85% core coverage check"
	@echo "  make mock-server    - Launch deterministic mock Zoho Inventory server"
	@echo "  make spec           - Generate and verify mcp/tool_spec.json"
	@echo "  make eval           - Run M1/M2/M3 evaluation harness (deterministic)"
	@echo "  make demo           - Run end-to-end demo offline against mock server"
	@echo "  make live-preflight - Validate live credentials and read access (bounded, read-only)"
	@echo "  make live-smoke     - Run smoke test against live Zoho instance (read-only)"
	@echo "  make live-probe     - Record read-only live API response shapes"
	@echo "  make live-assert    - Compare live test records with local expected output"
	@echo "  make live-pii-check - Verify default PII masking for one order (--mock is offline)"
	@echo "  make live-token-status - Inspect local token cache metadata (no network)"
	@echo "  make zoho-token     - Run local Zoho OAuth setup and save a private refresh token"
	@echo "  make net-watch     - Wait for unauthenticated Zoho hosts to answer (ARGS=--mock for local mock)"
	@echo "  make live-burst    - Run one bounded live sequence; use ARGS=--mock for offline testing"
	@echo "  make check-secrets  - Audit repo for committed secrets/tokens"
	@echo "  make clean-clone-test - Clone to temp dir and verify README quickstart offline"
	@echo "  make screenshots-check - List expected screenshot files present or missing"

setup:
	@which uv > /dev/null 2>&1 || (echo "uv is required. Please install uv." && exit 1)
	@test -d .venv || uv venv .venv --python 3.11
	uv pip install --python $(PYTHON) -r requirements.lock
	uv pip install --python $(PYTHON) --no-deps -e .

lint:
	$(RUFF) check .
	$(RUFF) format --check .

format:
	$(RUFF) format .
	$(RUFF) check --fix .

typecheck:
	$(MYPY) src/

test:
	$(PYTEST) --cov=src/zoho_inventory_connector --cov-report=term-missing --cov-fail-under=85 tests/

mock-server:
	$(PYTHON) -m uvicorn mock_zoho.app:app --host 127.0.0.1 --port 8000 --log-level warning

spec:
	$(PYTHON) -m zoho_inventory_connector.mcp_server.spec
	$(PYTHON) -m zoho_inventory_connector.mcp_server.spec --verify

eval:
	$(PYTHON) -m eval.run_eval

demo:
	$(PYTHON) -m examples.demo

live-preflight:
	$(PYTHON) -m examples.live_preflight

live-smoke:
	$(PYTHON) -m examples.live_smoke

live-probe:
	$(PYTHON) -m examples.live_probe

live-assert:
	$(PYTHON) -m examples.live_assert

live-pii-check:
	$(PYTHON) -m examples.live_pii_check $(ARGS)

live-token-status:
	$(PYTHON) -m examples.live_token_status

zoho-token:
	$(PYTHON) -m examples.zoho_token

net-watch:
	bash scripts/live_burst.sh net-watch $(ARGS)

live-burst:
	bash scripts/live_burst.sh live-burst $(ARGS)

clean-clone-test:
	@echo "Running clean-clone test..."
	@python3 -c "import re, sys; text = open('README.md').read(); matches = re.findall(r'<[a-zA-Z0-9_\-]+>', text); sys.exit(f'Found unreplaced placeholders in README.md: {matches}') if matches else print('README placeholder check passed.')"
	@FDE_CLONE_DIR=$$(mktemp -d) && FDE_WORKTREE_PATCH=$$(mktemp) && \
	echo "Cloning to temp dir $$FDE_CLONE_DIR..." && \
	git diff --binary HEAD > "$$FDE_WORKTREE_PATCH" && \
	git clone --no-hardlinks . "$$FDE_CLONE_DIR/repo" && \
	if test -s "$$FDE_WORKTREE_PATCH"; then (cd "$$FDE_CLONE_DIR/repo" && git apply "$$FDE_WORKTREE_PATCH"); fi && \
	mkdir -p "$$FDE_CLONE_DIR/repo/docs/process" && \
	cp docs/assets/CAPTURE_GUIDE.md "$$FDE_CLONE_DIR/repo/docs/assets/CAPTURE_GUIDE.md" && \
	cp docs/process/CODEX_RUNSHEET.md "$$FDE_CLONE_DIR/repo/docs/process/CODEX_RUNSHEET.md" && \
	cp docs/FIELD_NOTES.md "$$FDE_CLONE_DIR/repo/docs/FIELD_NOTES.md" && \
	cp docs/SUBMISSION_NOTE.md "$$FDE_CLONE_DIR/repo/docs/SUBMISSION_NOTE.md" && \
	cp examples/live_pii_check.py "$$FDE_CLONE_DIR/repo/examples/live_pii_check.py" && \
	cp tests/test_live_pii_check.py "$$FDE_CLONE_DIR/repo/tests/test_live_pii_check.py" && \
	mkdir -p "$$FDE_CLONE_DIR/repo/docs/evidence" "$$FDE_CLONE_DIR/repo/docs/process" && cp docs/evidence/*.txt "$$FDE_CLONE_DIR/repo/docs/evidence/" && \
	cd "$$FDE_CLONE_DIR/repo" && \
	make setup && \
	make eval && \
	make demo && \
	make spec && \
	rm -rf "$$FDE_CLONE_DIR" && rm -f "$$FDE_WORKTREE_PATCH" && \
		echo "clean-clone-test passed successfully."

screenshots-check:
	@for stem in tests_passing eval_simulated demo_mock live_preflight_masked live_smoke_masked live_probe_findings live_assert_masked mcp_inspector_live live_pii_masking; do \
		if test -f "docs/assets/$$stem.png"; then echo "PRESENT docs/assets/$$stem.png"; \
		elif test -f "docs/assets/$$stem.jpg"; then echo "PRESENT docs/assets/$$stem.jpg"; \
		elif test -f "docs/assets/$$stem.heic"; then echo "PRESENT docs/assets/$$stem.heic (review privacy; HEIC may not render on GitHub)"; \
		else echo "MISSING docs/assets/$$stem.(png|jpg|heic)"; fi; \
	done
	@items=0; orders=0; \
	for ext in png jpg heic; do \
	  test ! -f "docs/assets/zoho_items_ui.$$ext" || items=1; \
	  test ! -f "docs/assets/zoho_sales_orders_ui.$$ext" || orders=1; \
	done; \
	if test "$$items" = 1 && test "$$orders" = 1; then echo "PRESENT Zoho item and sales-order UI captures"; \
	else echo "MISSING Zoho Inventory fictional-record capture(s)"; fi

check-secrets:
	@echo "Auditing codebase for committed credentials, secrets, or raw auth headers..."
	@matches=$$(git grep -i -E "(client_secret[ \t]*=[ \t]*['\"][a-zA-Z0-9_\-]{8,}['\"]|refresh_token[ \t]*=[ \t]*['\"][a-zA-Z0-9_\-]{16,}['\"]|access_token[ \t]*=[ \t]*['\"][a-zA-Z0-9_\-]{16,}['\"])" -- ':!.env.example' ':!docs/*' ':!tests/*' | grep -viE 'mock|example|placeholder' || true); \
	if test -n "$$matches"; then printf '%s\n' "$$matches"; exit 1; fi
	@echo "Secrets audit clean."

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov dist build *.egg-info
