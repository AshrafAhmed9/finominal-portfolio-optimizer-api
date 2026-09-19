"""Shared validation for tests/golden/scenarios.json.

Both scripts/compare_reference.py and tests/test_reference.py import this
module, specifically so the two can never quietly disagree about what
counts as valid evidence. This exists because the first version of the
comparison script could report PASS on an empty fixture list, on a fixture
missing required tickers, and on a case-6 fixture with null expected values
(a TypeError, not a validation error) - see SUBMISSION_REVIEW.md R5.

Nothing here talks to the live tool. It only checks that a scenarios.json,
once someone has captured it, is internally consistent and complete before
any comparison against the running API is trusted.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATH = ROOT / "tests" / "golden" / "scenarios.json"
MAX_TOLERANCE_PP = 0.1  # the assignment's stated tolerance; a fixture may not widen this


class FixtureError(ValueError):
    """Raised for any problem with scenarios.json itself, independent of
    what the running API returns. Always carries a specific, readable
    reason - never a bare crash."""


# The exact required request for each of the six assignment scenarios.
# A captured fixture's `request` must match this exactly (case 6's
# `factor_targets` is checked separately below since it's bonus-only).
_FIVE_FUND_EQUAL = [
    {"ticker": "IEFA", "weight": 20},
    {"ticker": "GLD", "weight": 20},
    {"ticker": "AGG", "weight": 20},
    {"ticker": "VEA", "weight": 20},
    {"ticker": "SPY", "weight": 20},
]

REQUIRED_REQUESTS: dict[int, dict] = {
    1: {
        "securities": [{"ticker": "IEFA", "weight": 25}, {"ticker": "SPY", "weight": 75}],
        "strategy": "equal_weights",
    },
    2: {
        "securities": [{"ticker": "VEA", "weight": 25}, {"ticker": "AGG", "weight": 75}],
        "strategy": "risk_parity",
    },
    3: {
        "securities": [{"ticker": "SPY", "weight": 60}, {"ticker": "AGG", "weight": 30}, {"ticker": "GLD", "weight": 10}],
        "strategy": "minimize_volatility",
    },
    4: {
        "securities": _FIVE_FUND_EQUAL,
        "strategy": "maximize_sharpe",
    },
    5: {
        "securities": _FIVE_FUND_EQUAL,
        "strategy": "maximize_sharpe",
        "constraints": {"min_dividend_yield": 2.5, "min_weight": 5, "max_weight": 40},
    },
    6: {
        "securities": _FIVE_FUND_EQUAL,
        "strategy": "optimize_factor_exposure",
        "factor_targets": [{"factor": "momentum", "direction": "maximize"}],
    },
}
REQUIRED_CASE_IDS = {1, 2, 3, 4, 5}  # case 6 is bonus: validated if present, not required to pass


@dataclass
class Fixture:
    id: int
    name: str
    request_body: dict
    expected_weights: dict[str, float] | None  # None for an unfilled case-6 template entry
    tolerance_pp: float
    reference_screenshot: str | None


@dataclass
class CaseResult:
    fixture: Fixture
    api_status: int
    weight_gaps: dict[str, float] = field(default_factory=dict)  # cases 1-5 only
    max_gap: float | None = None
    sum_ok: bool = True
    nonnegative_ok: bool = True
    case5_constraints_ok: bool | None = None  # only meaningful for case 5
    momentum_improved: bool | None = None  # only meaningful for case 6
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        if self.api_status != 200:
            return False
        if self.errors:
            return False
        if not self.sum_ok or not self.nonnegative_ok:
            return False
        if self.fixture.id == 5 and self.case5_constraints_ok is False:
            return False
        if self.fixture.id == 6:
            return self.momentum_improved is not False
        if self.max_gap is not None:
            return self.max_gap <= self.fixture.tolerance_pp
        return True


def _requests_match(actual: dict, required: dict) -> bool:
    # Compare on the fields that matter for the scenario's identity;
    # a captured fixture is allowed to omit an explicit `constraints: null`
    # the required spec doesn't have.
    for key in ("securities", "strategy"):
        if actual.get(key) != required.get(key):
            return False
    if "constraints" in required and actual.get("constraints") != required["constraints"]:
        return False
    if "factor_targets" in required and actual.get("factor_targets") != required["factor_targets"]:
        return False
    return True


def load_and_validate_fixtures(path: Path = GOLDEN_PATH) -> list[Fixture]:
    """Loads scenarios.json and validates its structure. Raises FixtureError
    with a specific reason on anything wrong - missing file, empty list,
    a missing or duplicated required case, a request that doesn't match the
    assignment's specified scenario, non-finite or incomplete expected
    weights, a tolerance wider than the assignment allows, or a referenced
    screenshot that doesn't exist. Never returns a partially-valid result."""
    if not path.exists():
        raise FixtureError(f"{path} does not exist")

    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise FixtureError(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(raw, list) or len(raw) == 0:
        raise FixtureError(f"{path} must be a non-empty JSON list of scenario fixtures")

    fixtures: list[Fixture] = []
    seen_ids: set[int] = set()
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise FixtureError(f"fixture #{i} is not a JSON object")
        for required_key in ("id", "name", "request", "tolerance_pp"):
            if required_key not in entry:
                raise FixtureError(f"fixture #{i} is missing required key {required_key!r}")

        case_id = entry["id"]
        if case_id in seen_ids:
            raise FixtureError(f"duplicate fixture for case id {case_id}")
        seen_ids.add(case_id)

        tol = entry["tolerance_pp"]
        if not isinstance(tol, (int, float)) or not math.isfinite(tol) or tol <= 0:
            raise FixtureError(f"case {case_id}: tolerance_pp must be a positive finite number")
        if tol > MAX_TOLERANCE_PP:
            raise FixtureError(
                f"case {case_id}: tolerance_pp={tol} exceeds the assignment's stated "
                f"{MAX_TOLERANCE_PP} percentage points; widening the tolerance to hide a "
                f"gap is not a valid fixture"
            )

        if case_id in REQUIRED_REQUESTS and not _requests_match(entry["request"], REQUIRED_REQUESTS[case_id]):
            raise FixtureError(
                f"case {case_id}'s request does not match the assignment's specified "
                f"scenario for that case id (securities/strategy/constraints/factor_targets "
                f"must match exactly)"
            )

        expected = entry.get("expected_weights")
        if expected is not None:
            if not isinstance(expected, dict) or not expected:
                raise FixtureError(f"case {case_id}: expected_weights must be a non-empty object if present")
            request_tickers = {s["ticker"] for s in entry["request"]["securities"]}
            if set(expected) != request_tickers:
                raise FixtureError(
                    f"case {case_id}: expected_weights tickers {sorted(expected)} do not match "
                    f"the request's tickers {sorted(request_tickers)}"
                )
            for t, v in expected.items():
                if not isinstance(v, (int, float)) or not math.isfinite(v):
                    raise FixtureError(f"case {case_id}: expected_weights[{t!r}]={v!r} is not a finite number")
            total = sum(expected.values())
            if abs(total - 100.0) > 0.5:  # a loose sanity check on the *captured* reference, not our output
                raise FixtureError(
                    f"case {case_id}: expected_weights sum to {total:.4f}, not ~100 - looks like a "
                    f"mis-transcribed capture, not a real reference reading"
                )
        elif case_id in REQUIRED_CASE_IDS:
            raise FixtureError(
                f"case {case_id} is required (cases 1-5) but has no expected_weights filled in "
                f"(null placeholders are not evidence)"
            )

        screenshot = entry.get("reference_screenshot")
        if screenshot is not None and not (ROOT / screenshot).exists():
            raise FixtureError(f"case {case_id}: referenced screenshot {screenshot!r} does not exist on disk")

        fixtures.append(
            Fixture(
                id=case_id,
                name=entry["name"],
                request_body=entry["request"],
                expected_weights=expected,
                tolerance_pp=tol,
                reference_screenshot=screenshot,
            )
        )

    missing_required = REQUIRED_CASE_IDS - seen_ids
    if missing_required:
        raise FixtureError(f"missing required case id(s): {sorted(missing_required)} (cases 1-5 are all mandatory)")

    return fixtures


def evaluate_case(fixture: Fixture, response_status: int, response_body: dict | None) -> CaseResult:
    """Runs one fixture's request through generic checks (sum=100, no
    negative weights, case-5 constraints) plus the case-appropriate
    comparison: per-ticker gap against the live tool for cases 1-5, or the
    momentum-improvement check for case 6 (never weight parity for case 6 -
    the assignment explicitly exempts it)."""
    result = CaseResult(fixture=fixture, api_status=response_status)
    if response_status != 200 or response_body is None:
        result.errors.append(f"API returned status {response_status}, not 200")
        return result

    changes = response_body.get("allocation_changes", [])
    actual = {a["ticker"]: a["optimized_weight"] for a in changes}

    total = sum(actual.values())
    result.sum_ok = abs(total - 100.0) <= 1e-3
    result.nonnegative_ok = all(v >= -1e-9 for v in actual.values())

    if fixture.id == 5:
        constraints = fixture.request_body.get("constraints", {}) or {}
        min_w = constraints.get("min_weight")
        max_w = constraints.get("max_weight")
        min_yield_pct = constraints.get("min_dividend_yield")
        ok = True
        if min_w is not None:
            ok = ok and all(v >= min_w - 1e-3 for v in actual.values())
        if max_w is not None:
            ok = ok and all(v <= max_w + 1e-3 for v in actual.values())
        if min_yield_pct is not None:
            achieved_pct = response_body.get("meta", {}).get("metrics", {}).get("optimized", {}).get("dividend_yield", 0) * 100
            ok = ok and achieved_pct >= min_yield_pct - 1e-3
        result.case5_constraints_ok = ok

    if fixture.id == 6:
        betas = response_body.get("factor_betas") or {}
        current = betas.get("current_portfolio", {}).get("momentum")
        optimized = betas.get("optimized_portfolio", {}).get("momentum")
        if current is None or optimized is None:
            result.errors.append("case 6 response is missing factor_betas.momentum for current and/or optimized")
        else:
            result.momentum_improved = optimized > current
        return result  # case 6 never compares weights to the live tool

    if fixture.expected_weights is not None:
        gaps = {t: abs(actual.get(t, float("nan")) - expected) for t, expected in fixture.expected_weights.items()}
        result.weight_gaps = gaps
        result.max_gap = max(gaps.values()) if gaps else None

    return result
