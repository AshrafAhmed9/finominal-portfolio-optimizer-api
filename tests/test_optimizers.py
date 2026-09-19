"""Analytic and near-analytic fixtures for each strategy, independent of
the bundled workbook, plus repeatability and feasible-baseline checks."""
import numpy as np
import pytest

from app.constraints import Bounds, ConstraintError, build_portfolio_limits
from app.metrics import covariance_matrix
from app.optimize import (
    equal_weights,
    maximize_sharpe,
    minimize_drawdown,
    minimize_volatility,
    risk_parity,
)

NO_LIMITS = build_portfolio_limits(None, None, None, None)


def _unbounded(n):
    return Bounds(lower=np.zeros(n), upper=np.ones(n))


def _two_asset_returns(rng, n=1000, vol_a=0.01, vol_b=0.03, corr=0.2, mean_a=0.0003, mean_b=0.0005):
    cov = np.array([[vol_a**2, corr * vol_a * vol_b], [corr * vol_a * vol_b, vol_b**2]])
    return rng.multivariate_normal([mean_a, mean_b], cov, size=n)


def test_equal_weights_baseline():
    tickers = ["A", "B", "C", "D"]
    r = np.random.default_rng(1).normal(0, 0.01, size=(500, 4))
    y = np.zeros(4)
    result = equal_weights(tickers, _unbounded(4), r, y, NO_LIMITS)
    np.testing.assert_allclose(result.weights, [0.25] * 4)


def test_equal_weights_rejects_incompatible_constraint():
    tickers = ["A", "B"]
    r = np.random.default_rng(1).normal(0, 0.01, size=(500, 2))
    y = np.zeros(2)
    bounds = Bounds(lower=np.array([0.0, 0.6]), upper=np.array([0.4, 1.0]))  # 1/n=0.5 violates B's 0.6 floor
    with pytest.raises(ConstraintError):
        equal_weights(tickers, bounds, r, y, NO_LIMITS)


def test_min_volatility_matches_analytic_two_asset_solution():
    # R7 regression: the previous version of this test requested zero *true*
    # correlation but then compared against the zero-correlation-only
    # formula var_b/(var_a+var_b) - the *empirical* sample covariance always
    # has some nonzero cov_ab from sampling noise, and a wide 0.01 absolute
    # tolerance was masking that mismatch rather than actually verifying
    # anything. This uses a genuinely correlated series and the general
    # closed-form two-asset minimum-variance solution, which accounts for
    # the covariance term, at a much tighter tolerance.
    rng = np.random.default_rng(2)
    r = _two_asset_returns(rng, n=5000, vol_a=0.01, vol_b=0.04, corr=0.35)
    cov = covariance_matrix(r)
    result = minimize_volatility(["A", "B"], _unbounded(2), r, np.zeros(2), NO_LIMITS, cov)

    var_a, var_b, cov_ab = cov[0, 0], cov[1, 1], cov[0, 1]
    expected_wa = (var_b - cov_ab) / (var_a + var_b - 2 * cov_ab)
    expected_wa = float(np.clip(expected_wa, 0.0, 1.0))
    assert result.weights[0] == pytest.approx(expected_wa, abs=1e-3)


def test_min_volatility_beats_equal_weight_feasible_baseline():
    rng = np.random.default_rng(3)
    r = _two_asset_returns(rng, vol_a=0.01, vol_b=0.05, corr=0.1)
    cov = covariance_matrix(r)
    result = minimize_volatility(["A", "B"], _unbounded(2), r, np.zeros(2), NO_LIMITS, cov)
    equal = np.array([0.5, 0.5])
    assert (result.weights @ cov @ result.weights) <= (equal @ cov @ equal) + 1e-9


def test_risk_parity_two_asset_equals_inverse_volatility():
    # R9 correction: two-asset ERC equals inverse-volatility weighting in
    # general, NOT only at zero correlation - the covariance cross-term
    # cancels algebraically when solving w1*(Sigma w)_1 = w2*(Sigma w)_2,
    # leaving w1/w2 = sigma2/sigma1 for any correlation that keeps
    # portfolio variance positive. Run this at a genuinely nonzero
    # correlation specifically so the test can't be satisfied by accident.
    rng = np.random.default_rng(4)
    r = _two_asset_returns(rng, n=3000, vol_a=0.01, vol_b=0.04, corr=0.4)
    cov = covariance_matrix(r)
    assert abs(cov[0, 1]) > 1e-6  # sanity: the correlation really is nonzero here
    result = risk_parity(["A", "B"], _unbounded(2), r, np.zeros(2), NO_LIMITS, cov)
    inv_vol = 1 / np.sqrt(np.diag(cov))
    expected = inv_vol / inv_vol.sum()
    np.testing.assert_allclose(result.weights, expected, atol=0.01)


def test_risk_parity_three_asset_equal_contributions():
    rng = np.random.default_rng(5)
    n, k = 800, 3
    vols = np.array([0.01, 0.02, 0.03])
    corr = np.array([[1.0, 0.3, 0.1], [0.3, 1.0, 0.2], [0.1, 0.2, 1.0]])
    cov_daily = np.outer(vols, vols) * corr
    r = rng.multivariate_normal(np.zeros(k), cov_daily, size=n)
    cov = covariance_matrix(r)
    result = risk_parity(["A", "B", "C"], _unbounded(3), r, np.zeros(3), NO_LIMITS, cov)
    w = result.weights
    marginal = cov @ w
    port_var = w @ cov @ w
    contributions = w * marginal / port_var
    np.testing.assert_allclose(contributions, [1 / 3] * 3, atol=0.02)


def test_maximize_sharpe_beats_equal_weight_feasible_baseline():
    rng = np.random.default_rng(6)
    r = _two_asset_returns(rng, vol_a=0.01, vol_b=0.02, corr=0.0, mean_a=0.0002, mean_b=0.0008)
    from app.metrics import sharpe_ratio, portfolio_returns

    result = maximize_sharpe(["A", "B"], _unbounded(2), r, np.zeros(2), NO_LIMITS, risk_free_rate=0.0)
    equal = np.array([0.5, 0.5])
    s_opt = sharpe_ratio(portfolio_returns(result.weights, r), 0.0)
    s_equal = sharpe_ratio(portfolio_returns(equal, r), 0.0)
    assert s_opt >= s_equal - 1e-9


def test_minimize_drawdown_repeatable():
    rng = np.random.default_rng(7)
    r = _two_asset_returns(rng, n=300, vol_a=0.02, vol_b=0.04, corr=0.3)
    result_1 = minimize_drawdown(["A", "B"], _unbounded(2), r, np.zeros(2), NO_LIMITS)
    result_2 = minimize_drawdown(["A", "B"], _unbounded(2), r, np.zeros(2), NO_LIMITS)
    np.testing.assert_allclose(result_1.weights, result_2.weights, atol=1e-9)


def test_minimize_drawdown_beats_dense_two_asset_grid():
    rng = np.random.default_rng(8)
    r = _two_asset_returns(rng, n=300, vol_a=0.02, vol_b=0.05, corr=0.1)
    from app.metrics import max_drawdown, portfolio_returns

    result = minimize_drawdown(["A", "B"], _unbounded(2), r, np.zeros(2), NO_LIMITS)
    solver_mdd = max_drawdown(portfolio_returns(result.weights, r))

    grid_best = min(
        max_drawdown(portfolio_returns(np.array([wa, 1 - wa]), r)) for wa in np.linspace(0, 1, 2001)
    )
    assert solver_mdd <= grid_best + 0.005  # small solver-vs-grid tolerance, not equality


def test_bounds_sum_infeasible_raises():
    from app.constraints import build_bounds

    with pytest.raises(ConstraintError):
        build_bounds(["A", "B"], min_weight_pct=60, max_weight_pct=None, per_security_pct=None)
