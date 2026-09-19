import numpy as np
import pytest

from app.constraints import (
    ConstraintError,
    build_bounds,
    build_portfolio_limits,
    check_dividend_yield_feasible,
    max_achievable_dividend_yield,
    portfolio_constraint_violations,
)
from app.metrics import annual_volatility


def test_per_security_bounds_override_global():
    bounds = build_bounds(
        ["A", "B", "C"],
        min_weight_pct=0,
        max_weight_pct=100,
        per_security_pct={"B": {"min": 10, "max": 20}},
    )
    assert bounds.lower[1] == pytest.approx(0.10)
    assert bounds.upper[1] == pytest.approx(0.20)


def test_per_security_unknown_ticker_rejected():
    with pytest.raises(ConstraintError):
        build_bounds(["A", "B"], None, None, {"ZZZ": {"min": 10, "max": 20}})


def test_inverted_bounds_rejected():
    with pytest.raises(ConstraintError):
        build_bounds(["A"], None, None, {"A": {"min": 50, "max": 10}})


def test_max_achievable_dividend_yield_case5_bounds():
    # The five-fund, 5-40% bounded case from the assignment's case 5.
    tickers = ["IEFA", "GLD", "AGG", "VEA", "SPY"]
    yields = np.array([0.03278, 0.0, 0.03974, 0.02034, 0.00987])
    bounds = build_bounds(tickers, min_weight_pct=5, max_weight_pct=40, per_security_pct=None)
    max_yield, weights = max_achievable_dividend_yield(bounds, yields)
    assert max_yield == pytest.approx(0.0315355, abs=1e-5)
    assert max_yield > 0.025  # confirms the 2.50% floor is feasible under these bounds


def test_dividend_yield_feasibility_check_raises_when_unreachable():
    bounds = build_bounds(["A", "B"], min_weight_pct=0, max_weight_pct=100, per_security_pct=None)
    yields = np.array([0.01, 0.02])
    with pytest.raises(ConstraintError):
        check_dividend_yield_feasible(bounds, yields, min_yield_pct=5.0)  # max possible is 2%


def test_dividend_yield_feasibility_check_passes_when_reachable():
    bounds = build_bounds(["A", "B"], min_weight_pct=0, max_weight_pct=100, per_security_pct=None)
    yields = np.array([0.01, 0.05])
    check_dividend_yield_feasible(bounds, yields, min_yield_pct=3.0)  # should not raise


def test_bound_sums_below_100_infeasible():
    with pytest.raises(ConstraintError):
        build_bounds(["A", "B"], min_weight_pct=None, max_weight_pct=30, per_security_pct=None)


def test_inverted_volatility_range_rejected():
    with pytest.raises(ConstraintError):
        build_portfolio_limits(None, None, {"min": 20, "max": 5}, None)


def test_portfolio_violations_detects_max_drawdown_breach():
    limits = build_portfolio_limits(None, max_drawdown_pct=5.0, volatility_range_pct=None, min_dividend_yield_pct=None)
    r = np.array([[-0.10], [0.0], [0.0]])  # single asset, -10% day 1 -> 10% drawdown, limit is 5%
    w = np.array([1.0])
    violations = portfolio_constraint_violations(w, r, np.zeros(1), limits, annual_volatility)
    assert "max_drawdown" in violations


def test_portfolio_violations_empty_when_satisfied():
    limits = build_portfolio_limits(None, max_drawdown_pct=50.0, volatility_range_pct=None, min_dividend_yield_pct=None)
    r = np.array([[-0.10], [0.0], [0.0]])
    w = np.array([1.0])
    violations = portfolio_constraint_violations(w, r, np.zeros(1), limits, annual_volatility)
    assert violations == {}


def test_failure_to_find_feasible_point_is_not_a_false_infeasibility_certificate():
    # A jointly-satisfiable region exists (yield >=1% is trivially reachable),
    # so the feasibility check should not raise even though it can't prove
    # every nonlinear constraint combination is solvable in general.
    bounds = build_bounds(["A", "B"], min_weight_pct=0, max_weight_pct=100, per_security_pct=None)
    yields = np.array([0.01, 0.05])
    check_dividend_yield_feasible(bounds, yields, min_yield_pct=1.0)
