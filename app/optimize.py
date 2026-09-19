"""Strategy implementations, a shared candidate-acceptance/selection helper,
and the strategy dispatch map.

Every strategy returns an `OptimizationResult`: the chosen weights plus
enough bookkeeping (starts tried, solver status, objective value) to report
honestly in the API's `meta` block. None of them silently return a worse or
infeasible result as "optimized" - if no accepted candidate exists, the
caller raises `ConstraintError`.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from .constraints import (
    Bounds,
    ConstraintError,
    PortfolioLimits,
    portfolio_constraint_violations,
)
from .metrics import annual_volatility, portfolio_returns, sharpe_ratio

_RNG_SEED = 42


@dataclass
class OptimizationResult:
    weights: np.ndarray
    objective_value: float
    solver_status: str
    starts_tried: int
    iterations: int


def _feasible_starts(bounds: Bounds, extra: list[np.ndarray] | None = None) -> list[np.ndarray]:
    """A small deterministic set of starting points, each projected onto the
    simplex-with-bounds so every start is itself feasible for the equality
    constraint (sum = 1) before the solver even begins."""
    n = len(bounds.lower)
    candidates: list[np.ndarray] = [np.full(n, 1.0 / n)]
    for i in range(n):
        corner = bounds.lower.copy()
        remaining = 1.0 - corner.sum()
        room = bounds.upper - corner
        if remaining > 0 and room.sum() > 0:
            corner = corner + room * (remaining / room.sum())
        candidates.append(corner)
    if extra:
        candidates.extend(extra)
    rng = np.random.default_rng(_RNG_SEED)
    for _ in range(6):
        raw = rng.dirichlet(np.ones(n))
        scaled = bounds.lower + raw * (bounds.upper - bounds.lower)
        scaled = scaled / scaled.sum()
        candidates.append(scaled)
    return [_project_to_bounds_sum_one(c, bounds) for c in candidates]


def _project_to_bounds_sum_one(w: np.ndarray, bounds: Bounds) -> np.ndarray:
    w = np.clip(w, bounds.lower, bounds.upper)
    total = w.sum()
    if abs(total - 1.0) < 1e-12:
        return w
    # redistribute the shortfall/excess proportionally to available room
    if total < 1.0:
        room = bounds.upper - w
    else:
        room = w - bounds.lower
    room_sum = room.sum()
    if room_sum <= 0:
        return w  # bounds pin the allocation exactly; caller's feasibility check will catch this
    w = w + (1.0 - total) * (room / room_sum) if total < 1.0 else w - (total - 1.0) * (room / room_sum)
    return np.clip(w, bounds.lower, bounds.upper)


def _sum_to_one_constraint():
    return {"type": "eq", "fun": lambda w: np.sum(w) - 1.0}


def _portfolio_limit_constraints(return_matrix: np.ndarray, yields: np.ndarray, limits: PortfolioLimits) -> list[dict]:
    """SLSQP inequality constraints (fun(w) >= 0) for each set portfolio-level
    limit, so the solver actually searches the feasible region instead of
    relying on rejecting infeasible post-hoc candidates - the latter alone
    can miss a feasible high-objective region entirely when none of the
    deterministic starts happens to land in it."""
    from .metrics import cagr as _cagr, max_drawdown as _mdd, portfolio_returns as _pr

    cons: list[dict] = []
    if limits.min_dividend_yield is not None:
        cons.append({"type": "ineq", "fun": lambda w: w @ yields - limits.min_dividend_yield})
    if limits.min_cagr is not None:
        cons.append({"type": "ineq", "fun": lambda w: _cagr(_pr(w, return_matrix)) - limits.min_cagr})
    if limits.max_drawdown_limit is not None:
        cons.append({"type": "ineq", "fun": lambda w: limits.max_drawdown_limit - _mdd(_pr(w, return_matrix))})
    if limits.min_volatility is not None:
        cons.append({"type": "ineq", "fun": lambda w: annual_volatility(_pr(w, return_matrix)) - limits.min_volatility})
    if limits.max_volatility is not None:
        cons.append({"type": "ineq", "fun": lambda w: limits.max_volatility - annual_volatility(_pr(w, return_matrix))})
    return cons


def _acceptable(
    weights: np.ndarray,
    return_matrix: np.ndarray,
    yields: np.ndarray,
    bounds: Bounds,
    limits: PortfolioLimits,
) -> bool:
    if not np.all(np.isfinite(weights)):
        return False
    if abs(weights.sum() - 1.0) > 1e-6:
        return False
    if np.any(weights < bounds.lower - 1e-6) or np.any(weights > bounds.upper + 1e-6):
        return False
    violations = portfolio_constraint_violations(weights, return_matrix, yields, limits, annual_volatility)
    return len(violations) == 0


def _run_multistart(
    objective,
    bounds: Bounds,
    return_matrix: np.ndarray,
    yields: np.ndarray,
    limits: PortfolioLimits,
    extra_starts: list[np.ndarray] | None = None,
    maxiter: int = 200,
) -> OptimizationResult:
    starts = _feasible_starts(bounds, extra_starts)
    best: OptimizationResult | None = None
    total_iterations = 0
    scipy_constraints = [_sum_to_one_constraint(), *_portfolio_limit_constraints(return_matrix, yields, limits)]
    for start in starts:
        result = minimize(
            objective,
            start,
            method="SLSQP",
            bounds=bounds.as_scipy_bounds(),
            constraints=scipy_constraints,
            options={"maxiter": maxiter, "ftol": 1e-12},
        )
        total_iterations += result.nit
        w = np.clip(result.x, bounds.lower, bounds.upper)
        w = w / w.sum() if w.sum() > 0 else w
        if not result.success:
            continue
        if not _acceptable(w, return_matrix, yields, bounds, limits):
            continue
        value = float(objective(w))
        if best is None or value < best.objective_value:
            best = OptimizationResult(
                weights=w,
                objective_value=value,
                solver_status=result.message,
                starts_tried=len(starts),
                iterations=total_iterations,
            )
    if best is None:
        raise ConstraintError(
            "no feasible allocation satisfying all constraints was found from "
            f"{len(starts)} deterministic starting points; this may mean the "
            "constraints are jointly infeasible, or that the search needs a "
            "different starting point than this implementation tries"
        )
    return best


# --- individual strategies -------------------------------------------------

def equal_weights(
    tickers: list[str],
    bounds: Bounds,
    return_matrix: np.ndarray,
    yields: np.ndarray,
    limits: PortfolioLimits,
) -> OptimizationResult:
    n = len(tickers)
    w = np.full(n, 1.0 / n)
    if not _acceptable(w, return_matrix, yields, bounds, limits):
        raise ConstraintError(
            "equal weights (1/n each) violates the given bounds or portfolio-level "
            "constraints; equal weights is not compatible with the requested constraints"
        )
    return OptimizationResult(weights=w, objective_value=0.0, solver_status="closed_form", starts_tried=1, iterations=0)


def risk_parity(
    tickers: list[str],
    bounds: Bounds,
    return_matrix: np.ndarray,
    yields: np.ndarray,
    limits: PortfolioLimits,
    covariance: np.ndarray,
) -> OptimizationResult:
    n = len(tickers)

    def risk_contributions(w: np.ndarray) -> np.ndarray:
        port_var = w @ covariance @ w
        if port_var <= 0:
            return np.zeros(n)  # degenerate: no risk to distribute (e.g. single zero-vol asset)
        marginal = covariance @ w
        return w * marginal / port_var  # fractional contributions, sum to 1

    def objective(w: np.ndarray) -> float:
        q = risk_contributions(w)
        return float(np.sum((q - 1.0 / n) ** 2)) * 1e4  # scaled off the 1e-10 floor

    inv_vol = 1.0 / np.sqrt(np.diag(covariance))
    inv_vol_seed = inv_vol / inv_vol.sum()
    return _run_multistart(objective, bounds, return_matrix, yields, limits, extra_starts=[inv_vol_seed])


def minimize_volatility(
    tickers: list[str],
    bounds: Bounds,
    return_matrix: np.ndarray,
    yields: np.ndarray,
    limits: PortfolioLimits,
    covariance: np.ndarray,
) -> OptimizationResult:
    def objective(w: np.ndarray) -> float:
        return float(w @ covariance @ w)

    return _run_multistart(objective, bounds, return_matrix, yields, limits)


def maximize_sharpe(
    tickers: list[str],
    bounds: Bounds,
    return_matrix: np.ndarray,
    yields: np.ndarray,
    limits: PortfolioLimits,
    risk_free_rate: float,
) -> OptimizationResult:
    def objective(w: np.ndarray) -> float:
        r_p = portfolio_returns(w, return_matrix)
        s = sharpe_ratio(r_p, risk_free_rate)
        return -s if s is not None else 1e6  # penalize the zero-variance degenerate case

    return _run_multistart(objective, bounds, return_matrix, yields, limits)


def minimize_drawdown(
    tickers: list[str],
    bounds: Bounds,
    return_matrix: np.ndarray,
    yields: np.ndarray,
    limits: PortfolioLimits,
) -> OptimizationResult:
    def objective(w: np.ndarray) -> float:
        r_p = portfolio_returns(w, return_matrix)
        wealth = np.concatenate(([1.0], np.cumprod(1.0 + r_p)))
        peak = np.maximum.accumulate(wealth)
        return float(np.max(1.0 - wealth / peak))

    n = len(tickers)
    rng = np.random.default_rng(_RNG_SEED)
    extra = [
        bounds.lower + rng.dirichlet(np.ones(n)) * (bounds.upper - bounds.lower)
        for _ in range(24)
    ]
    extra = [c / c.sum() for c in extra]
    return _run_multistart(objective, bounds, return_matrix, yields, limits, extra_starts=extra, maxiter=300)


STRATEGIES = (
    "equal_weights",
    "risk_parity",
    "minimize_drawdown",
    "minimize_volatility",
    "maximize_sharpe",
    "optimize_factor_exposure",
)
