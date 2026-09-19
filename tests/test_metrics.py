import numpy as np
import pytest

from app.metrics import annual_volatility, cagr, dividend_yield, max_drawdown, sharpe_ratio


def test_volatility_hand_calculated():
    r = np.array([0.01, -0.02, 0.015, -0.005, 0.02])
    expected = np.std(r, ddof=1) * np.sqrt(252)
    assert annual_volatility(r) == pytest.approx(expected)


def test_cagr_hand_calculated():
    r = np.array([0.01, 0.01, 0.01, 0.01])  # 4 days of +1%
    wealth = np.prod(1 + r)
    expected = wealth ** (252 / 4) - 1
    assert cagr(r) == pytest.approx(expected)


def test_dividend_yield_is_linear():
    w = np.array([0.6, 0.4])
    y = np.array([0.02, 0.05])
    assert dividend_yield(w, y) == pytest.approx(0.6 * 0.02 + 0.4 * 0.05)


def test_max_drawdown_first_day_loss():
    # -10% on day 1 then flat: trough is immediately -10%.
    r = np.array([-0.10, 0.0, 0.0])
    assert max_drawdown(r) == pytest.approx(0.10)


def test_max_drawdown_reflects_starting_capital():
    # -10% then +10%: NOT back to breakeven (1 * 0.9 * 1.1 = 0.99), so the
    # trough drawdown is 10%, matching the peak-at-day-0 reference point.
    r = np.array([-0.10, 0.10])
    assert max_drawdown(r) == pytest.approx(0.10)


def test_max_drawdown_monotonic_gain_is_zero():
    r = np.array([0.01, 0.02, 0.005, 0.03])
    assert max_drawdown(r) == pytest.approx(0.0)


def test_max_drawdown_recovery_above_prior_peak():
    # Down then up past the old peak: MDD is the worst trough-from-peak, not
    # the final level.
    r = np.array([0.10, -0.30, 0.50])
    wealth = np.concatenate(([1.0], np.cumprod(1 + r)))
    expected = np.max(1 - wealth / np.maximum.accumulate(wealth))
    assert max_drawdown(r) == pytest.approx(expected)
    assert max_drawdown(r) > 0.15  # sanity: the -30% day creates a real drawdown


def test_sharpe_zero_variance_is_undefined():
    r = np.zeros(10)
    assert sharpe_ratio(r) is None


def test_sharpe_uses_risk_free_rate():
    rng = np.random.default_rng(0)
    r = rng.normal(loc=0.001, scale=0.01, size=252)
    s_zero = sharpe_ratio(r, risk_free_rate=0.0)
    s_high = sharpe_ratio(r, risk_free_rate=0.10)
    assert s_high < s_zero


# --- R8 regression: numerically-near-constant returns must stay undefined --
# --- rather than producing an astronomically large "Sharpe ratio" ---------

def test_sharpe_repeated_constant_return_is_undefined_not_huge():
    # Same value repeated: exact std is 0.0 for 3 observations but a tiny
    # nonzero float for 10 (rounding, not real variation). Both must return
    # None, not a real number in the tens of quadrillions for the 10-case.
    assert sharpe_ratio(np.full(3, 0.01)) is None
    assert sharpe_ratio(np.full(10, 0.01)) is None
    assert sharpe_ratio(np.full(10, -0.01)) is None


def test_sharpe_genuinely_low_but_real_variance_still_defined():
    # A bond-like series with small but real day-to-day variation must NOT
    # be swept into the same "undefined" bucket just because the numbers
    # are individually small - only near-zero *variance* is undefined.
    rng = np.random.default_rng(1)
    r = rng.normal(loc=0.0001, scale=0.0005, size=252)
    s = sharpe_ratio(r)
    assert s is not None
    assert np.isfinite(s)


def test_risk_parity_zero_variance_asset_does_not_produce_nan_seed():
    from app.constraints import Bounds, build_portfolio_limits
    from app.optimize import risk_parity

    limits = build_portfolio_limits(None, None, None, None)
    n = 200
    zero_col = np.zeros(n)  # exactly-constant asset: zero true variance
    real_col = np.random.default_rng(2).normal(0, 0.01, n)
    return_matrix = np.column_stack([zero_col, real_col])
    covariance = np.array([[0.0, 0.0], [0.0, np.var(real_col, ddof=1) * 252]])
    bounds = Bounds(lower=np.zeros(2), upper=np.ones(2))

    result = risk_parity(["ZERO", "REAL"], bounds, return_matrix, np.zeros(2), limits, covariance)
    assert np.all(np.isfinite(result.weights))
    assert result.weights.sum() == pytest.approx(1.0)
