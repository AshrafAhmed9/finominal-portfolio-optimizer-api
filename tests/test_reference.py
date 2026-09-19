"""Asserts every request in tests/golden/scenarios.json against the live
tool's captured weights, within each case's stated tolerance.

This module is explicitly skipped (never silently passed) when the golden
fixture file doesn't exist yet - see tests/golden/README.md. Do not delete
this file or the skip reason; it exists so the absence of reference
evidence is loud in `pytest -q` output, not invisible.
"""
import json
from pathlib import Path

import pytest

GOLDEN_PATH = Path(__file__).parent / "golden" / "scenarios.json"

if not GOLDEN_PATH.exists():
    pytest.skip(
        f"reference fixtures not captured yet: {GOLDEN_PATH} does not exist. "
        "See tests/golden/README.md - this requires running the live tool at "
        "https://finominal.com/portfolio-optimizer/US and is NOT a passing result "
        "until populated.",
        allow_module_level=True,
    )

with open(GOLDEN_PATH) as f:
    SCENARIOS = json.load(f)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s["name"])
def test_matches_live_tool(client, scenario):
    r = client.post("/optimize", json=scenario["request"])
    assert r.status_code == 200, r.json()
    body = r.json()
    actual = {a["ticker"]: a["optimized_weight"] for a in body["allocation_changes"]}
    tol = scenario["tolerance_pp"]
    gaps = {t: abs(actual[t] - expected) for t, expected in scenario["expected_weights"].items()}
    worst = max(gaps.values())
    assert worst <= tol, f"{scenario['name']}: max gap {worst:.3f}pp exceeds tolerance {tol}pp: {gaps}"
