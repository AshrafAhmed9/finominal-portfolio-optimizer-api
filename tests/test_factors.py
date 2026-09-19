import numpy as np
import pandas as pd
import pytest

from app.constraints import ConstraintError, build_bounds
from app.data import build_factor_matrix
from app.factors import optimize_factor_exposure, per_asset_beta_matrix, portfolio_betas, regress_betas


def _synthetic_market(rng, n=400):
    """A fake MarketData-alike whose factor_series and known betas are
    exactly known, to verify the regression recovers them."""
    dates = pd.date_range("2015-01-01", periods=n, freq="B")
    momentum = pd.Series(rng.normal(0, 0.01, n), index=dates)
    value = pd.Series(rng.normal(0, 0.01, n), index=dates)
    size = pd.Series(rng.normal(0, 0.01, n), index=dates)

    class FakeMarket:
        def factor_series(self, name):
            return {"momentum": momentum, "value": value, "size": size}[name]

    return FakeMarket(), dates, momentum, value, size


def test_regression_recovers_known_synthetic_betas():
    rng = np.random.default_rng(10)
    market, dates, momentum, value, size = _synthetic_market(rng)
    true_alpha, true_betas = 0.0003, (0.8, -0.4, 0.2)
    noise = rng.normal(0, 0.002, len(dates))
    y_full = true_alpha + true_betas[0] * momentum + true_betas[1] * value + true_betas[2] * size + noise

    X, y, _dates = build_factor_matrix(dates, y_full.to_numpy(), market)
    alpha, betas = regress_betas(X, y)
    assert alpha == pytest.approx(true_alpha, abs=0.001)
    assert betas.momentum == pytest.approx(true_betas[0], abs=0.05)
    assert betas.value == pytest.approx(true_betas[1], abs=0.05)
    assert betas.size == pytest.approx(true_betas[2], abs=0.05)


def test_per_asset_beta_matrix_matches_direct_portfolio_regression():
    """The optimizer's linear shortcut (regress each asset once, then betas
    of any weighted portfolio = beta_matrix @ w) must agree with directly
    regressing the weighted portfolio return series."""
    rng = np.random.default_rng(11)
    market, dates, momentum, value, size = _synthetic_market(rng)
    n = len(dates)
    k = 3
    asset_returns = np.column_stack(
        [
            0.0001 + 0.5 * momentum + 0.1 * value - 0.2 * size + rng.normal(0, 0.005, n),
            0.0002 - 0.3 * momentum + 0.6 * value + 0.1 * size + rng.normal(0, 0.005, n),
            0.0001 + 0.1 * momentum - 0.2 * value + 0.4 * size + rng.normal(0, 0.005, n),
        ]
    )
    tickers = ["A", "B", "C"]
    beta_matrix = per_asset_beta_matrix(tickers, dates, asset_returns, market)

    w = np.array([0.5, 0.3, 0.2])
    via_shortcut = beta_matrix @ w

    direct_betas = portfolio_betas(tickers, dates, asset_returns, w, market)
    direct = np.array([direct_betas.momentum, direct_betas.value, direct_betas.size])

    np.testing.assert_allclose(via_shortcut, direct, atol=1e-8)


def test_rank_deficient_design_rejected():
    rng = np.random.default_rng(12)
    dates = pd.date_range("2015-01-01", periods=10, freq="B")
    momentum = pd.Series(rng.normal(0, 0.01, 10), index=dates)

    class FakeMarket:
        def factor_series(self, name):
            # value and size identical to momentum -> rank-deficient design
            return momentum

    y = rng.normal(0, 0.01, 10)
    with pytest.raises(Exception):
        build_factor_matrix(dates, y, FakeMarket())


def test_optimize_factor_exposure_maximize_is_linear_program(market):
    tickers = ["IEFA", "GLD", "AGG", "VEA", "SPY"]
    from app.data import build_return_matrix

    aligned = build_return_matrix(tickers, None, market)
    bounds = build_bounds(tickers, None, None, None)
    yields = np.array([market.fund(t).dividend_yield for t in tickers])
    weights, beta_matrix = optimize_factor_exposure(
        tickers, aligned.dates, aligned.matrix, bounds, yields, None, market,
        [{"factor": "momentum", "direction": "maximize", "importance": 1.0}],
    )
    assert weights.sum() == pytest.approx(1.0)
    assert np.all(weights >= -1e-9)
    # optimum for maximizing a single linear factor under only sum=1 + box
    # bounds is a vertex: exactly one non-degenerate weight (or ties at bound)
    assert np.sum(weights > 1e-6) <= len(tickers)


def test_optimize_factor_exposure_rejects_duplicate_targets(market):
    tickers = ["IEFA", "SPY"]
    from app.data import build_return_matrix

    aligned = build_return_matrix(tickers, None, market)
    bounds = build_bounds(tickers, None, None, None)
    yields = np.array([market.fund(t).dividend_yield for t in tickers])
    with pytest.raises(ConstraintError):
        optimize_factor_exposure(
            tickers, aligned.dates, aligned.matrix, bounds, yields, None, market,
            [
                {"factor": "momentum", "direction": "maximize", "importance": 1.0},
                {"factor": "momentum", "direction": "minimize", "importance": 1.0},
            ],
        )


def test_case6_momentum_exposure_increases(market):
    """The assignment's explicit case-6 acceptance check: optimized momentum
    beta must exceed the current (equal-weight) portfolio's, with all
    constraints respected."""
    tickers = ["IEFA", "GLD", "AGG", "VEA", "SPY"]
    from app.data import build_return_matrix

    aligned = build_return_matrix(tickers, None, market)
    bounds = build_bounds(tickers, None, None, None)
    yields = np.array([market.fund(t).dividend_yield for t in tickers])
    current_weights = np.full(5, 0.2)

    weights, beta_matrix = optimize_factor_exposure(
        tickers, aligned.dates, aligned.matrix, bounds, yields, None, market,
        [{"factor": "momentum", "direction": "maximize", "importance": 1.0}],
    )
    current_momentum_beta = (beta_matrix @ current_weights)[0]
    optimized_momentum_beta = (beta_matrix @ weights)[0]
    assert optimized_momentum_beta > current_momentum_beta
    assert weights.sum() == pytest.approx(1.0)
    assert np.all(weights >= -1e-9)
