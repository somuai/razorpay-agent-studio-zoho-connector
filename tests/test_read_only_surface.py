"""Guard the Zoho Inventory surface against accidental mutating operations."""

import ast
from pathlib import Path


def test_source_http_mutations_are_limited_to_accounts_oauth_post() -> None:
    source_root = Path("src/zoho_inventory_connector")
    writes: list[tuple[str, str]] = []
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr.lower() in {"post", "put", "patch", "delete", "request"}:
                    writes.append((str(path), node.func.attr.lower()))

    assert writes, "OAuth token exchange POST should remain the only non-GET HTTP call in src/."
    assert all(path.endswith("auth/oauth.py") and method == "post" for path, method in writes)
    oauth_source = (source_root / "auth/oauth.py").read_text(encoding="utf-8")
    assert "/oauth/v2/token" in oauth_source
