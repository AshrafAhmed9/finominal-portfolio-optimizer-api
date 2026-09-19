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
