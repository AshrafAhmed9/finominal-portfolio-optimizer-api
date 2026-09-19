#!/usr/bin/env python3
"""Runs every request in tests/golden/scenarios.json against the running
optimization logic (in-process, no server needed) and prints a comparison
table: per-ticker gap for cases 1-5, momentum-improvement check for case 6,
plus generic checks (weights sum to 100, no negatives, case-5 constraints
respected) for every case. Exits nonzero if the fixture file is missing,
malformed, incomplete, or any case fails - this command is the evidence
artifact referenced in the README, and it must not lie by exiting 0 on
missing or failing evidence.

Fixture validation itself (structure, required cases, tolerance limits) is
shared with tests/test_reference.py via scripts/reference_fixtures.py, so
the two can never silently disagree about what counts as valid evidence.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.reference_fixtures import FixtureError, evaluate_case, load_and_validate_fixtures


def main() -> int:
    try:
        fixtures = load_and_validate_fixtures()
    except FixtureError as exc:
        print(f"MISSING OR INVALID EVIDENCE: {exc}")
        print("See tests/golden/README.md for the expected format and requirements.")
        return 1

    from fastapi.testclient import TestClient
    from app.main import app

    print(f"{'case':<28} {'strategy':<26} {'result':<12} detail")
    print("-" * 100)

    any_failed = False
    with TestClient(app) as client:
        for fixture in sorted(fixtures, key=lambda f: f.id):
            r = client.post("/optimize", json=fixture.request_body)
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else None
            result = evaluate_case(fixture, r.status_code, body)

            if not result.passed:
                any_failed = True

            if fixture.id == 6:
                detail = (
                    f"momentum {'improved' if result.momentum_improved else 'DID NOT improve'}"
                    if result.momentum_improved is not None
                    else "; ".join(result.errors) or "no factor_betas in response"
                )
            elif result.errors:
                detail = "; ".join(result.errors)
            elif result.max_gap is not None:
                detail = f"max gap {result.max_gap:.4f}pp (tol {fixture.tolerance_pp}pp)"
            else:
                detail = "no expected_weights to compare (informal only)"

            if fixture.id == 5 and result.case5_constraints_ok is False:
                detail += " | CASE 5 CONSTRAINTS VIOLATED"
            if not result.sum_ok:
                detail += " | weights do not sum to 100"
            if not result.nonnegative_ok:
                detail += " | negative weight present"

            status = "PASS" if result.passed else "FAIL"
            print(f"{fixture.name:<28} {fixture.request_body['strategy']:<26} {status:<12} {detail}")

            if result.weight_gaps and (result.max_gap or 0) > fixture.tolerance_pp:
                for t, g in sorted(result.weight_gaps.items(), key=lambda kv: -kv[1]):
                    print(f"    {t}: gap={g:.4f}pp")

    print()
    if any_failed:
        print("FAIL: one or more cases missing, erroring, out of tolerance, or violating a constraint.")
        return 1
    print(f"PASS: all {len(fixtures)} cases passed their respective checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
