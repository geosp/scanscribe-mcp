"""Every setting is documented in the README table and the decision log (task 02/5.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scanscribe_mcp.config import ScanscribeMcpConfig

ROOT = Path(__file__).resolve().parent.parent
FIELDS = sorted(ScanscribeMcpConfig.model_fields)


@pytest.mark.parametrize("field", FIELDS)
def test_setting_is_documented(field: str) -> None:
    name = f"SCANSCRIBE_MCP_{field.upper()}"
    readme_rows = [
        line for line in (ROOT / "README.md").read_text().splitlines() if line.startswith("| `")
    ]
    assert any(f"`{name}`" in row for row in readme_rows), f"{name} is not in the README table"
    log = (ROOT / "docs" / "decision-log.md").read_text()
    assert f"`{name}`" in log or f"`_{field.upper()}`" in log, f"{name} is not in the log"
