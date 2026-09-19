"""Factor beta regression and the factor-exposure optimization strategy.

portfolio_return = alpha + b_momentum*Momentum + b_value*Value + b_size*Size + error

Key simplification used by the optimizer (verified against direct regression
in tests/test_factors.py): with constant weights and a shared date window,
the portfolio's betas are the weighted average of each asset's own betas,
because OLS is linear in the dependent variable and the design matrix (the
factor columns) does not depend on the portfolio weights at all. So instead
of re-running an OLS per weight vector inside the optimizer (slow, and
non-linear in w for no reason), we regress each asset separately once, then
the objective is a *linear* function of w: b_target(w) = beta_matrix @ w.
That makes "maximize exposure to one factor, subject to linear bounds/yield
constraints" a linear program, solved once with scipy.optimize.linprog
rather than SLSQP.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

from .constraints import Bounds, ConstraintError, check_dividend_yield_feasible
from .data import FACTOR_NAMES, MarketData, build_factor_matrix

BETA_INDEX = {name: i + 1 for i, name in enumerate(FACTOR_NAMES)}  # +1 skips the intercept column


@dataclass(frozen=True)
class FactorBetas:
    momentum: float
    value: float
    size: float

    def as_dict(self) -> dict:
        return {"momentum": self.momentum, "value": self.value, "size": self.size}


def regress_betas(X: np.ndarray, y: np.ndarray) -> tuple[float, FactorBetas]:
    """OLS via lstsq; returns (alpha, betas). Raises if the design is
    rank-deficient (caller should validate rank before calling, but this is
    a second, cheap check)."""
    coeffs, _residuals, rank, _sv = np.linalg.lstsq(X, y, rcond=None)
    if rank < X.shape[1]:
        raise ConstraintError("factor regression design matrix is rank-deficient")
    if not np.all(np.isfinite(coeffs)):
        raise ConstraintError("factor regression produced non-finite coefficients")
    alpha = float(coeffs[0])
    betas = FactorBetas(momentum=float(coeffs[1]), value=float(coeffs[2]), size=float(coeffs[3]))
    return alpha, betas


def portfolio_betas(
    tickers: list[str],
    dates,
    return_matrix: np.ndarray,
    weights: np.ndarray,
    market: MarketData,
) -> FactorBetas:
    X, y, _dates = build_factor_matrix(dates, return_matrix @ weights, market)
    _alpha, betas = regress_betas(X, y)
    return betas


def per_asset_beta_matrix(
    tickers: list[str],
    dates,
    return_matrix: np.ndarray,
    market: MarketData,
) -> np.ndarray:
    """Regresses each asset's own return series on the factors (all over the
    same common portfolio-date window, intersected with factor dates), and
    returns a (3, n_assets) matrix of [momentum; value; size] betas, one
    column per asset. Portfolio betas for any weight vector w are then this
    matrix @ w - verified equal to a direct regression in tests."""
    n = len(tickers)
    betas = np.zeros((3, n))
    for j in range(n):
        X, y, _dates = build_factor_matrix(dates, return_matrix[:, j], market)
        _alpha, b = regress_betas(X, y)
        betas[:, j] = [b.momentum, b.value, b.size]
    return betas


def optimize_factor_exposure(
    tickers: list[str],
    dates,
    return_matrix: np.ndarray,
    bounds: Bounds,
    yields: np.ndarray,
    min_dividend_yield: float | None,
    market: MarketData,
    factor_targets: list[dict],
) -> tuple[np.ndarray, np.ndarray]:
    """factor_targets: [{"factor": "momentum", "direction": "maximize", "importance": 1.0}, ...]
    Returns (weights, per_asset_beta_matrix) - the caller uses the beta
    matrix to report both current and optimized betas without re-regressing.
    """
    if not factor_targets:
        raise ConstraintError("optimize_factor_exposure requires at least one factor_targets entry")
    seen = set()
    for t in factor_targets:
        if t["factor"] not in FACTOR_NAMES:
            raise ConstraintError(f"unknown factor {t['factor']!r}; expected one of {FACTOR_NAMES}")
        if t["factor"] in seen:
            raise ConstraintError(f"duplicate factor_targets entry for {t['factor']!r}")
        seen.add(t["factor"])
        if t.get("importance", 1.0) <= 0:
            raise ConstraintError(f"importance for {t['factor']!r} must be positive")

    beta_matrix = per_asset_beta_matrix(tickers, dates, return_matrix, market)  # (3, n)

    total_importance = sum(t.get("importance", 1.0) for t in factor_targets)
    objective_row = np.zeros(len(tickers))
    for t in factor_targets:
        sign = -1.0 if t["direction"] == "maximize" else 1.0  # linprog minimizes
        weight = t.get("importance", 1.0) / total_importance
        objective_row += sign * weight * beta_matrix[BETA_INDEX[t["factor"]] - 1]

    if min_dividend_yield is not None:
        check_dividend_yield_feasible(bounds, yields, min_dividend_yield * 100.0)

    A_ub, b_ub = None, None
    if min_dividend_yield is not None:
        A_ub = np.array([-yields])
        b_ub = np.array([-min_dividend_yield])

    result = linprog(
        c=objective_row,
        A_ub=A_ub,
        b_ub=b_ub,
        A_eq=np.ones((1, len(tickers))),
        b_eq=[1.0],
        bounds=bounds.as_scipy_bounds(),
        method="highs",
    )
    if not result.success:
        raise ConstraintError(f"factor exposure optimization is infeasible: {result.message}")
    return result.x, beta_matrix
