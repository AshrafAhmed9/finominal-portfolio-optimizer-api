"""Constraint validation, feasibility pre-checks and residual functions.

Two kinds of constraint:
  - security-level: per-ticker [min, max] weight bounds (global defaults,
    overridable per ticker)
  - portfolio-level: min_dividend_yield, min_cagr, max_drawdown (a loss
    limit, e.g. 20 means "no worse than -20%"), volatility_range

All bound/limit values arrive as percentages (0-100) at the API boundary and
are converted to fractions [0, 1] before reaching this module.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

from .metrics import (
    cagr as compute_cagr,
    dividend_yield as compute_dividend_yield,
    max_drawdown as compute_max_drawdown,
    portfolio_returns,
)

FEASIBILITY_TOLERANCE = 1e-8  # fractional units, e.g. 1e-8 == 1e-6 percentage points


class ConstraintError(ValueError):
    """Raised when bounds or portfolio-level constraints are self-contradictory
    or provably infeasible, independent of any particular strategy."""


@dataclass(frozen=True)
class Bounds:
    lower: np.ndarray  # fractions, shape (n,)
    upper: np.ndarray

    def as_scipy_bounds(self) -> list[tuple[float, float]]:
        return list(zip(self.lower.tolist(), self.upper.tolist()))


def build_bounds(
    tickers: list[str],
    min_weight_pct: float | None,
    max_weight_pct: float | None,
    per_security_pct: dict[str, dict[str, float | None]] | None,
) -> Bounds:
    n = len(tickers)
    default_lo = (min_weight_pct if min_weight_pct is not None else 0.0) / 100.0
    default_hi = (max_weight_pct if max_weight_pct is not None else 100.0) / 100.0
    lower = np.full(n, default_lo, dtype=float)
    upper = np.full(n, default_hi, dtype=float)

    per_security_pct = per_security_pct or {}
    for ticker, spec in per_security_pct.items():
        if ticker not in tickers:
            raise ConstraintError(
                f"per_security constraint given for {ticker!r}, which is not in this request's securities"
            )
        idx = tickers.index(ticker)
        if spec.get("min") is not None:
            lower[idx] = spec["min"] / 100.0
        if spec.get("max") is not None:
            upper[idx] = spec["max"] / 100.0

    for t, lo, hi in zip(tickers, lower, upper):
        if lo < 0 or hi > 1:
            raise ConstraintError(f"bounds for {t} must fall within [0, 100] percent")
        if lo > hi:
            raise ConstraintError(f"bounds for {t} are inverted: min {lo*100:.4f}% > max {hi*100:.4f}%")

    if lower.sum() > 1.0 + FEASIBILITY_TOLERANCE:
        raise ConstraintError(
            f"sum of minimum weights ({lower.sum()*100:.4f}%) exceeds 100%; no allocation can satisfy every lower bound"
        )
    if upper.sum() < 1.0 - FEASIBILITY_TOLERANCE:
        raise ConstraintError(
            f"sum of maximum weights ({upper.sum()*100:.4f}%) is below 100%; no allocation can reach full investment"
        )
    return Bounds(lower=lower, upper=upper)


def max_achievable_dividend_yield(bounds: Bounds, yields: np.ndarray) -> tuple[float, np.ndarray]:
    """Solves the bound-constrained linear program maximizing w . yields
    subject to sum(w) = 1 and bounds. Returns (max_yield, weights_at_max)."""
    n = len(yields)
    result = linprog(
        c=-yields,
        A_eq=np.ones((1, n)),
        b_eq=[1.0],
        bounds=bounds.as_scipy_bounds(),
        method="highs",
    )
    if not result.success:
        raise ConstraintError(f"could not solve for maximum achievable dividend yield: {result.message}")
    return float(-result.fun), result.x


def check_dividend_yield_feasible(bounds: Bounds, yields: np.ndarray, min_yield_pct: float) -> None:
    min_yield = min_yield_pct / 100.0
    max_yield, weights_at_max = max_achievable_dividend_yield(bounds, yields)
    if max_yield < min_yield - FEASIBILITY_TOLERANCE:
        raise ConstraintError(
            f"min_dividend_yield of {min_yield_pct:.4f}% is infeasible under the given weight bounds; "
            f"maximum achievable yield is {max_yield*100:.4f}%"
        )


@dataclass(frozen=True)
class PortfolioLimits:
    min_cagr: float | None  # fraction
    max_drawdown_limit: float | None  # fraction, e.g. 0.20 == "no worse than -20%"
    min_volatility: float | None
    max_volatility: float | None
    min_dividend_yield: float | None  # fraction


def build_portfolio_limits(
    min_cagr_pct: float | None,
    max_drawdown_pct: float | None,
    volatility_range_pct: dict[str, float | None] | None,
    min_dividend_yield_pct: float | None,
) -> PortfolioLimits:
    vol_range = volatility_range_pct or {}
    vol_min_pct, vol_max_pct = vol_range.get("min"), vol_range.get("max")
    if vol_min_pct is not None and vol_max_pct is not None and vol_min_pct > vol_max_pct:
        raise ConstraintError(
            f"volatility_range is inverted: min {vol_min_pct}% > max {vol_max_pct}%"
        )
    if max_drawdown_pct is not None and max_drawdown_pct < 0:
        raise ConstraintError("max_drawdown must be a non-negative percentage loss limit")
    return PortfolioLimits(
        min_cagr=None if min_cagr_pct is None else min_cagr_pct / 100.0,
        max_drawdown_limit=None if max_drawdown_pct is None else max_drawdown_pct / 100.0,
        min_volatility=None if vol_min_pct is None else vol_min_pct / 100.0,
        max_volatility=None if vol_max_pct is None else vol_max_pct / 100.0,
        min_dividend_yield=None if min_dividend_yield_pct is None else min_dividend_yield_pct / 100.0,
    )


def portfolio_constraint_violations(
    weights: np.ndarray,
    return_matrix: np.ndarray,
    yields: np.ndarray,
    limits: PortfolioLimits,
    volatility_fn,
) -> dict[str, float]:
    """Returns {constraint_name: violation_amount} for every violated
    portfolio-level constraint (positive = amount by which it's violated,
    in fractional units). Empty dict means every constraint holds within
    FEASIBILITY_TOLERANCE."""
    violations: dict[str, float] = {}
    r_p = portfolio_returns(weights, return_matrix)

    if limits.min_cagr is not None:
        gap = limits.min_cagr - compute_cagr(r_p)
        if gap > FEASIBILITY_TOLERANCE:
            violations["min_cagr"] = gap

    if limits.max_drawdown_limit is not None:
        gap = compute_max_drawdown(r_p) - limits.max_drawdown_limit
        if gap > FEASIBILITY_TOLERANCE:
            violations["max_drawdown"] = gap

    vol = volatility_fn(r_p)
    if limits.min_volatility is not None:
        gap = limits.min_volatility - vol
        if gap > FEASIBILITY_TOLERANCE:
            violations["volatility_range.min"] = gap
    if limits.max_volatility is not None:
        gap = vol - limits.max_volatility
        if gap > FEASIBILITY_TOLERANCE:
            violations["volatility_range.max"] = gap

    if limits.min_dividend_yield is not None:
        gap = limits.min_dividend_yield - compute_dividend_yield(weights, yields)
        if gap > FEASIBILITY_TOLERANCE:
            violations["min_dividend_yield"] = gap

    return violations
