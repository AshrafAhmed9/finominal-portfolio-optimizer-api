import numpy as np
import pandas as pd
import pytest

from app.constraints import ConstraintError, build_bounds, build_portfolio_limits
from app.data import build_factor_matrix
from app.factors import optimize_factor_exposure, per_asset_beta_matrix, portfolio_betas, regress_betas

NO_LIMITS = build_portfolio_limits(None, None, None, None)


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
    result, beta_matrix = optimize_factor_exposure(
        tickers, aligned.dates, aligned.matrix, bounds, yields, NO_LIMITS, market,
        [{"factor": "momentum", "direction": "maximize", "importance": 1.0}],
    )
    weights = result.weights
    assert weights.sum() == pytest.approx(1.0)
    assert np.all(weights >= -1e-9)
    # R7 regression: "at most n nonzero weights" is trivially true for any
    # n-asset portfolio and proves nothing about LP quality. The real
    # optimality property: maximizing one linear factor under only sum=1 and
    # [0,1] box bounds puts 100% into whichever single asset has the highest
    # beta for that factor - assert that directly against the known optimum.
    best_asset_idx = int(np.argmax(beta_matrix[0]))  # row 0 = momentum
    achieved_beta = float(beta_matrix[0] @ weights)
    best_possible_beta = float(beta_matrix[0, best_asset_idx])
    assert achieved_beta == pytest.approx(best_possible_beta, abs=1e-6)
    assert weights[best_asset_idx] == pytest.approx(1.0, abs=1e-6)


def test_optimize_factor_exposure_minimize_direction(market):
    tickers = ["IEFA", "GLD", "AGG", "VEA", "SPY"]
    from app.data import build_return_matrix

    aligned = build_return_matrix(tickers, None, market)
    bounds = build_bounds(tickers, None, None, None)
    yields = np.array([market.fund(t).dividend_yield for t in tickers])
    result, beta_matrix = optimize_factor_exposure(
        tickers, aligned.dates, aligned.matrix, bounds, yields, NO_LIMITS, market,
        [{"factor": "value", "direction": "minimize", "importance": 1.0}],
    )
    weights = result.weights
    worst_asset_idx = int(np.argmin(beta_matrix[1]))  # row 1 = value
    assert weights[worst_asset_idx] == pytest.approx(1.0, abs=1e-6)


def test_optimize_factor_exposure_weighted_multi_factor_target(market):
    # Two factors with different importance weights: the objective is the
    # importance-weighted sum of betas, so the winning asset should be the
    # one maximizing that weighted combination, not either factor alone.
    tickers = ["IEFA", "GLD", "AGG", "VEA", "SPY"]
    from app.data import build_return_matrix

    aligned = build_return_matrix(tickers, None, market)
    bounds = build_bounds(tickers, None, None, None)
    yields = np.array([market.fund(t).dividend_yield for t in tickers])
    result, beta_matrix = optimize_factor_exposure(
        tickers, aligned.dates, aligned.matrix, bounds, yields, NO_LIMITS, market,
        [
            {"factor": "momentum", "direction": "maximize", "importance": 3.0},
            {"factor": "size", "direction": "maximize", "importance": 1.0},
        ],
    )
    weights = result.weights
    combined_score = 0.75 * beta_matrix[0] + 0.25 * beta_matrix[2]  # normalized importances
    expected_best = int(np.argmax(combined_score))
    assert weights[expected_best] == pytest.approx(1.0, abs=1e-6)
    achieved = float(combined_score @ weights)
    assert achieved == pytest.approx(float(combined_score[expected_best]), abs=1e-6)


def test_optimize_factor_exposure_binding_bounds_prevent_full_concentration(market):
    # With a 40% per-security cap, the optimizer can no longer put 100% into
    # the single best asset - the cap must actually bind.
    tickers = ["IEFA", "GLD", "AGG", "VEA", "SPY"]
    from app.data import build_return_matrix

    aligned = build_return_matrix(tickers, None, market)
    bounds = build_bounds(tickers, min_weight_pct=0, max_weight_pct=40, per_security_pct=None)
    yields = np.array([market.fund(t).dividend_yield for t in tickers])
    result, beta_matrix = optimize_factor_exposure(
        tickers, aligned.dates, aligned.matrix, bounds, yields, NO_LIMITS, market,
        [{"factor": "momentum", "direction": "maximize", "importance": 1.0}],
    )
    weights = result.weights
    assert np.all(weights <= 0.40 + 1e-6)
    best_asset_idx = int(np.argmax(beta_matrix[0]))
    assert weights[best_asset_idx] == pytest.approx(0.40, abs=1e-6)  # cap is binding on the best asset


def test_optimize_factor_exposure_rejects_duplicate_targets(market):
    tickers = ["IEFA", "SPY"]
    from app.data import build_return_matrix

    aligned = build_return_matrix(tickers, None, market)
    bounds = build_bounds(tickers, None, None, None)
    yields = np.array([market.fund(t).dividend_yield for t in tickers])
    with pytest.raises(ConstraintError):
        optimize_factor_exposure(
            tickers, aligned.dates, aligned.matrix, bounds, yields, NO_LIMITS, market,
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

    result, beta_matrix = optimize_factor_exposure(
        tickers, aligned.dates, aligned.matrix, bounds, yields, NO_LIMITS, market,
        [{"factor": "momentum", "direction": "maximize", "importance": 1.0}],
    )
    weights = result.weights
    current_momentum_beta = (beta_matrix @ current_weights)[0]
    optimized_momentum_beta = (beta_matrix @ weights)[0]
    assert optimized_momentum_beta > current_momentum_beta
    assert weights.sum() == pytest.approx(1.0)
    assert np.all(weights >= -1e-9)


# --- R1 regression: nonlinear portfolio-level constraints must actually ----
# --- bind on the factor-exposure strategy, not be silently discarded ------

def _five_fund_setup(market):
    tickers = ["IEFA", "GLD", "AGG", "VEA", "SPY"]
    from app.data import build_return_matrix

    aligned = build_return_matrix(tickers, None, market)
    bounds = build_bounds(tickers, None, None, None)
    yields = np.array([market.fund(t).dividend_yield for t in tickers])
    return tickers, aligned, bounds, yields


def test_factor_exposure_respects_volatility_max_when_feasible(market):
    tickers, aligned, bounds, yields = _five_fund_setup(market)
    limits = build_portfolio_limits(None, None, {"max": 10}, None)
    result, _beta_matrix = optimize_factor_exposure(
        tickers, aligned.dates, aligned.matrix, bounds, yields, limits, market,
        [{"factor": "momentum", "direction": "maximize", "importance": 1.0}],
    )
    from app.metrics import annual_volatility, portfolio_returns

    vol = annual_volatility(portfolio_returns(result.weights, aligned.matrix))
    assert vol <= 0.10 + 1e-6


def test_factor_exposure_respects_max_drawdown_when_feasible(market):
    tickers, aligned, bounds, yields = _five_fund_setup(market)
    limits = build_portfolio_limits(None, 20, None, None)
    result, _beta_matrix = optimize_factor_exposure(
        tickers, aligned.dates, aligned.matrix, bounds, yields, limits, market,
        [{"factor": "momentum", "direction": "maximize", "importance": 1.0}],
    )
    from app.metrics import max_drawdown, portfolio_returns

    mdd = max_drawdown(portfolio_returns(result.weights, aligned.matrix))
    assert mdd <= 0.20 + 1e-6


def test_factor_exposure_rejects_unreachable_min_cagr(market):
    # Unlike dividend yield (an LP, so feasibility is provable analytically),
    # min_cagr feasibility can't be certified without actually solving the
    # nonconvex problem - so an unreachable 50% CAGR target correctly
    # surfaces as OptimizationFailedError (the search never converged),
    # not ConstraintError (which would falsely claim proven infeasibility).
    from app.optimize import OptimizationFailedError

    tickers, aligned, bounds, yields = _five_fund_setup(market)
    limits = build_portfolio_limits(50, None, None, None)  # 50% CAGR: not achievable by any of these 5 funds
    with pytest.raises((ConstraintError, OptimizationFailedError)):
        optimize_factor_exposure(
            tickers, aligned.dates, aligned.matrix, bounds, yields, limits, market,
            [{"factor": "momentum", "direction": "maximize", "importance": 1.0}],
        )


def test_factor_exposure_respects_combined_bounds_yield_and_drawdown(market):
    tickers, aligned, bounds_full = None, None, None
    from app.data import build_return_matrix

    tickers = ["IEFA", "GLD", "AGG", "VEA", "SPY"]
    aligned = build_return_matrix(tickers, None, market)
    bounds = build_bounds(tickers, min_weight_pct=5, max_weight_pct=40, per_security_pct=None)
    yields = np.array([market.fund(t).dividend_yield for t in tickers])
    limits = build_portfolio_limits(None, 25, None, 1.0)  # max_drawdown 25%, min yield 1%

    result, _beta_matrix = optimize_factor_exposure(
        tickers, aligned.dates, aligned.matrix, bounds, yields, limits, market,
        [{"factor": "momentum", "direction": "maximize", "importance": 1.0}],
    )
    from app.metrics import dividend_yield, max_drawdown, portfolio_returns

    w = result.weights
    assert w.sum() == pytest.approx(1.0)
    assert np.all(w >= 0.05 - 1e-6) and np.all(w <= 0.40 + 1e-6)
    assert dividend_yield(w, yields) >= 0.01 - 1e-6
    assert max_drawdown(portfolio_returns(w, aligned.matrix)) <= 0.25 + 1e-6
