#!/usr/bin/env python3
"""Runs every request in tests/golden/scenarios.json against the running
optimization logic (in-process, no server needed) and prints a comparison
table: per-ticker gap, max gap per case, constraint checks, case 6 handled
separately. Exits nonzero if the fixture file is missing or any case is
out of tolerance - this command is the evidence artifact referenced in the
README, and it must not lie by exiting 0 on missing or failing evidence.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GOLDEN_PATH = ROOT / "tests" / "golden" / "scenarios.json"


def main() -> int:
    if not GOLDEN_PATH.exists():
        print(f"MISSING EVIDENCE: {GOLDEN_PATH} does not exist.")
        print("Capture the six scenarios from https://finominal.com/portfolio-optimizer/US first.")
        print("See tests/golden/README.md for the expected format.")
        return 1

    from fastapi.testclient import TestClient
    from app.main import app

    with open(GOLDEN_PATH) as f:
        scenarios = json.load(f)

    any_failed = False
    print(f"{'case':<28} {'strategy':<26} {'max gap (pp)':>12} {'tol':>6}  status")
    print("-" * 90)

    with TestClient(app) as client:
        for scenario in scenarios:
            r = client.post("/optimize", json=scenario["request"])
            if r.status_code != 200:
                print(f"{scenario['name']:<28} {'-':<26} {'-':>12} {'-':>6}  API ERROR: {r.json()}")
                any_failed = True
                continue
            body = r.json()
            actual = {a["ticker"]: a["optimized_weight"] for a in body["allocation_changes"]}
            gaps = {t: abs(actual[t] - expected) for t, expected in scenario["expected_weights"].items()}
            worst = max(gaps.values())
            tol = scenario["tolerance_pp"]
            status = "OK" if worst <= tol else "OUT OF TOLERANCE"
            if worst > tol:
                any_failed = True
            print(f"{scenario['name']:<28} {scenario['request']['strategy']:<26} {worst:>12.4f} {tol:>6.2f}  {status}")
            if worst > tol:
                for t, g in sorted(gaps.items(), key=lambda kv: -kv[1]):
                    print(f"    {t}: actual={actual[t]:.4f}  expected={scenario['expected_weights'][t]:.4f}  gap={g:.4f}")

    print()
    if any_failed:
        print("FAIL: one or more cases missing, erroring, or out of tolerance.")
        return 1
    print(f"PASS: all {len(scenarios)} cases within tolerance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
