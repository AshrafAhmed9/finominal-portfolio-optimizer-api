"""Portfolio return series and the metrics derived from it.

Conventions (stated explicitly, not discovered from the live tool - see
README "Methodology" for why and docs/validation for the comparison):
  - constant-weight (buy-and-hold-then-rebalance-daily) portfolio return:
    r_p[t] = w . R[t, :]
  - annualization factor: 252 trading observations/year
  - volatility: sample standard deviation (ddof=1) of daily returns, annualized
    by sqrt(252)
  - CAGR: geometric, compounding the actual daily observations:
    expm1(sum(log1p(r_p)) * 252 / n)
  - Sharpe: (annualized arithmetic mean return - annual risk-free rate) / annualized volatility
  - max drawdown: on a wealth index starting at 1.0, i.e. it reflects the
    starting-capital effect (a portfolio that returns -10% then +10% is at
    a 10% drawdown at the trough, not 0%)
  - dividend yield: linear in weights, w . y
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TRADING_DAYS_PER_YEAR = 252
ANNUAL_RISK_FREE_RATE = 0.0  # brief permits 0% or a standard value; see README


def portfolio_returns(weights: np.ndarray, return_matrix: np.ndarray) -> np.ndarray:
    return return_matrix @ weights


def annual_volatility(port_returns: np.ndarray) -> float:
    n = len(port_returns)
    if n < 2:
        raise ValueError("need >= 2 observations to compute volatility")
    return float(np.std(port_returns, ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def cagr(port_returns: np.ndarray) -> float:
    n = len(port_returns)
    if n == 0:
        raise ValueError("need >= 1 observation to compute CAGR")
    log_growth = np.sum(np.log1p(port_returns))
    return float(np.expm1(log_growth * TRADING_DAYS_PER_YEAR / n))


def arithmetic_annual_return(port_returns: np.ndarray) -> float:
    return float(np.mean(port_returns) * TRADING_DAYS_PER_YEAR)


def _is_effectively_constant(port_returns: np.ndarray) -> bool:
    """True when the daily return series has no real variation, only
    floating-point noise. A genuinely zero-variance series (e.g. an
    all-cash portfolio) computes an *exact* 0.0 standard deviation, but a
    portfolio built from real market data that happens to be numerically
    close to constant (repeated 0.01 returns, say) computes a standard
    deviation on the order of 1e-18: nonzero, but meaningless relative to
    the data itself, and annualizing it by sqrt(252) then dividing by it
    produces a Sharpe in the tens of quadrillions instead of the intended
    "undefined" result.

    The threshold combines an absolute floor (1e-9, comfortably above
    float64 rounding error for numbers in the 0.001-1.0 range these return
    series live in) with a relative floor tied to the series' own scale
    (1e-6 x mean absolute return), so a genuinely low but real-variance
    series - a bond fund with tiny day-to-day moves - is never misclassified
    as constant just because its numbers are individually small.
    """
    daily_std = np.std(port_returns, ddof=1)
    scale = np.mean(np.abs(port_returns))
    return bool(daily_std <= 1e-9 + 1e-6 * scale)


def sharpe_ratio(port_returns: np.ndarray, risk_free_rate: float = ANNUAL_RISK_FREE_RATE) -> float | None:
    if _is_effectively_constant(port_returns):
        return None  # undefined; a (numerically) zero-variance portfolio has no risk-adjusted ratio
    vol = annual_volatility(port_returns)
    return (arithmetic_annual_return(port_returns) - risk_free_rate) / vol


def max_drawdown(port_returns: np.ndarray) -> float:
    """Fraction in [0, 1]; 0.20 means a 20% peak-to-trough loss."""
    wealth = np.concatenate(([1.0], np.cumprod(1.0 + port_returns)))
    running_peak = np.maximum.accumulate(wealth)
    drawdown = 1.0 - wealth / running_peak
    return float(np.max(drawdown))


def dividend_yield(weights: np.ndarray, yields: np.ndarray) -> float:
    return float(weights @ yields)


@dataclass(frozen=True)
class PortfolioMetrics:
    cagr: float
    volatility: float
    sharpe: float | None
    max_drawdown: float
    dividend_yield: float

    def as_dict(self) -> dict:
        return {
            "cagr": self.cagr,
            "volatility": self.volatility,
            "sharpe": self.sharpe,
            "max_drawdown": self.max_drawdown,
            "dividend_yield": self.dividend_yield,
        }


def compute_metrics(
    weights: np.ndarray,
    return_matrix: np.ndarray,
    yields: np.ndarray,
    risk_free_rate: float = ANNUAL_RISK_FREE_RATE,
) -> PortfolioMetrics:
    r_p = portfolio_returns(weights, return_matrix)
    return PortfolioMetrics(
        cagr=cagr(r_p),
        volatility=annual_volatility(r_p),
        sharpe=sharpe_ratio(r_p, risk_free_rate),
        max_drawdown=max_drawdown(r_p),
        dividend_yield=dividend_yield(weights, yields),
    )


def covariance_matrix(return_matrix: np.ndarray) -> np.ndarray:
    """Annualized sample covariance (ddof=1), consistent with annual_volatility.

    Always returns a 2D (n_assets, n_assets) array. np.cov collapses to a
    0-d scalar for a single-column input, which then breaks any caller doing
    matrix multiplication or np.diag() on it - np.atleast_2d guards that.
    """
    cov = np.cov(return_matrix, rowvar=False, ddof=1) * TRADING_DAYS_PER_YEAR
    return np.atleast_2d(cov)
