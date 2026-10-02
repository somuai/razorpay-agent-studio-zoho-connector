.PHONY: help setup lint format typecheck test mock-server spec eval demo live-preflight live-smoke live-probe live-assert live-token-status zoho-token check-secrets clean clean-clone-test screenshots-check

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
	@echo "  make live-token-status - Inspect local token cache metadata (no network)"
	@echo "  make zoho-token     - Run local Zoho OAuth setup and save a private refresh token"
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

live-token-status:
	$(PYTHON) -m examples.live_token_status

zoho-token:
	$(PYTHON) -m examples.zoho_token

clean-clone-test:
	@echo "Running clean-clone test..."
	@python3 -c "import re, sys; text = open('README.md').read(); matches = re.findall(r'<[a-zA-Z0-9_\-]+>', text); sys.exit(f'Found unreplaced placeholders in README.md: {matches}') if matches else print('README placeholder check passed.')"
	@FDE_CLONE_DIR=$$(mktemp -d) && FDE_WORKTREE_PATCH=$$(mktemp) && \
	echo "Cloning to temp dir $$FDE_CLONE_DIR..." && \
	git diff --binary HEAD > "$$FDE_WORKTREE_PATCH" && \
	git clone --no-hardlinks . "$$FDE_CLONE_DIR/repo" && \
	(cd "$$FDE_CLONE_DIR/repo" && git apply "$$FDE_WORKTREE_PATCH") && \
	cp docs/assets/CAPTURE_GUIDE.md "$$FDE_CLONE_DIR/repo/docs/assets/CAPTURE_GUIDE.md" && \
	cp docs/FIELD_NOTES.md "$$FDE_CLONE_DIR/repo/docs/FIELD_NOTES.md" && \
	cp docs/SUBMISSION_NOTE.md "$$FDE_CLONE_DIR/repo/docs/SUBMISSION_NOTE.md" && \
	mkdir -p "$$FDE_CLONE_DIR/repo/docs/evidence" && cp docs/evidence/*.txt "$$FDE_CLONE_DIR/repo/docs/evidence/" && \
	cd "$$FDE_CLONE_DIR/repo" && \
	make setup && \
	make eval && \
	make demo && \
	make spec && \
	rm -rf "$$FDE_CLONE_DIR" && rm -f "$$FDE_WORKTREE_PATCH" && \
		echo "clean-clone-test passed successfully."

screenshots-check:
	@for file in tests_passing.png eval_simulated.png demo_mock.png live_preflight_masked.png live_smoke_masked.png live_probe_findings.png live_assert_masked.png mcp_inspector_live.png zoho_inventory_fictional_records.png; do \
		if test -f "docs/assets/$$file"; then echo "PRESENT docs/assets/$$file"; else echo "MISSING docs/assets/$$file"; fi; \
	done

check-secrets:
	@echo "Auditing codebase for committed credentials, secrets, or raw auth headers..."
	@matches=$$(git grep -i -E "(client_secret[ \t]*=[ \t]*['\"][a-zA-Z0-9_\-]{8,}['\"]|refresh_token[ \t]*=[ \t]*['\"][a-zA-Z0-9_\-]{16,}['\"]|access_token[ \t]*=[ \t]*['\"][a-zA-Z0-9_\-]{16,}['\"])" -- ':!.env.example' ':!docs/*' ':!tests/*' | grep -viE 'mock|example|placeholder' || true); \
	if test -n "$$matches"; then printf '%s\n' "$$matches"; exit 1; fi
	@echo "Secrets audit clean."

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov dist build *.egg-info
