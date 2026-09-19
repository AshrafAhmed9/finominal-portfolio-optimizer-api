"""FastAPI app: startup data loading, the /optimize endpoint, and a single
error-translation layer so every failure mode returns the same envelope:
{"error": {"code": ..., "message": ..., "details": {...}}}
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .constraints import (
    Bounds,
    ConstraintError,
    build_bounds,
    build_portfolio_limits,
    check_dividend_yield_feasible,
)
from .data import DataError, MarketData, build_return_matrix
from .factors import optimize_factor_exposure
from .metrics import ANNUAL_RISK_FREE_RATE, compute_metrics, covariance_matrix
from .optimize import (
    OptimizationFailedError,
    equal_weights,
    maximize_sharpe,
    minimize_drawdown,
    minimize_volatility,
    risk_parity,
)
from .schemas import OptimizeRequest, OptimizeResponse, Strategy

DATA_PATH = Path(os.environ.get("FINOMINAL_DATA_PATH", Path(__file__).resolve().parent.parent / "Data.xlsx"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fails startup loudly (per plan §6) if the bundled workbook is missing or malformed.
    app.state.market = MarketData(str(DATA_PATH))
    yield


app = FastAPI(title="Finominal Portfolio Optimizer API", lifespan=lifespan)


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


@app.exception_handler(ApiError)
async def _api_error_handler(_request: Request, exc: ApiError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


@app.exception_handler(OptimizationFailedError)
async def _optimization_failed_handler(_request: Request, exc: OptimizationFailedError):
    # Distinct from ConstraintError/422: this means the numerical search
    # itself never converged, not that the constraints were proven
    # impossible to satisfy. A 500 here is honest about which of those two
    # things happened; conflating them into one 422 would misrepresent a
    # solver limitation as a fact about the request.
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "optimization_failed", "message": str(exc), "details": {}}},
    )


@app.exception_handler(ConstraintError)
async def _constraint_error_handler(_request: Request, exc: ConstraintError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "infeasible_or_invalid_constraint", "message": str(exc), "details": {}}},
    )


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(_request: Request, exc: RequestValidationError):
    # Build our own envelope rather than letting Starlette echo the raw
    # invalid input back into the response: a NaN/Infinity in the request
    # body is exactly the kind of value this handler exists to reject, and
    # standard JSON cannot represent it even in an error message.
    errors = [
        {"loc": list(e.get("loc", [])), "msg": e.get("msg", "invalid input")}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "invalid_request", "message": "request validation failed", "details": {"errors": errors}}},
    )


@app.exception_handler(DataError)
async def _data_error_handler(_request: Request, exc: DataError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "data_error", "message": str(exc), "details": {}}},
    )


@app.get("/health")
def health():
    market: MarketData = app.state.market
    return {"status": "ok", "known_tickers": market.known_tickers()}


@app.get("/securities")
def securities():
    market: MarketData = app.state.market
    return [
        {
            "ticker": f.ticker,
            "security_name": f.security_name,
            "dividend_yield": f.dividend_yield,
            "dividend_yield_known": f.dividend_yield_known,
        }
        for f in sorted(market.fund_info.values(), key=lambda f: f.ticker)
    ]


def _inline_returns_from_request(req: OptimizeRequest) -> dict[str, pd.Series] | None:
    if not any(s.returns is not None for s in req.securities):
        return None
    out: dict[str, pd.Series] = {}
    for s in req.securities:
        idx = pd.to_datetime([r.date for r in s.returns])
        out[s.ticker] = pd.Series([r.total_return for r in s.returns], index=idx).sort_index()
    return out


@app.post("/optimize", response_model=OptimizeResponse)
def optimize(req: OptimizeRequest):
    market: MarketData = app.state.market
    tickers = [s.ticker for s in req.securities]

    for t in tickers:
        if t not in market.fund_info:
            raise ApiError(
                422, "unknown_ticker", f"unknown ticker {t!r}",
                {"ticker": t, "known_tickers": list(market.known_tickers())},
            )

    inline = _inline_returns_from_request(req)
    aligned = build_return_matrix(tickers, inline, market)
    yields = np.array([market.fund(t).dividend_yield for t in tickers])
    current_weights = np.array([s.weight for s in req.securities]) / 100.0

    c = req.constraints
    bounds: Bounds = build_bounds(
        tickers,
        c.min_weight if c else None,
        c.max_weight if c else None,
        {k: v.model_dump() for k, v in c.per_security.items()} if c and c.per_security else None,
    )
    limits = build_portfolio_limits(
        c.min_cagr if c else None,
        c.max_drawdown if c else None,
        c.volatility_range.model_dump() if c and c.volatility_range else None,
        c.min_dividend_yield if c else None,
    )
    if limits.min_dividend_yield is not None:
        check_dividend_yield_feasible(bounds, yields, limits.min_dividend_yield * 100.0)

    covariance = None
    if req.strategy in (Strategy.risk_parity, Strategy.minimize_volatility):
        covariance = covariance_matrix(aligned.matrix)

    factor_betas_payload = None

    if req.strategy == Strategy.equal_weights:
        result = equal_weights(tickers, bounds, aligned.matrix, yields, limits)
    elif req.strategy == Strategy.risk_parity:
        result = risk_parity(tickers, bounds, aligned.matrix, yields, limits, covariance)
    elif req.strategy == Strategy.minimize_volatility:
        result = minimize_volatility(tickers, bounds, aligned.matrix, yields, limits, covariance)
    elif req.strategy == Strategy.maximize_sharpe:
        result = maximize_sharpe(tickers, bounds, aligned.matrix, yields, limits, ANNUAL_RISK_FREE_RATE)
    elif req.strategy == Strategy.minimize_drawdown:
        result = minimize_drawdown(tickers, bounds, aligned.matrix, yields, limits)
    elif req.strategy == Strategy.optimize_factor_exposure:
        targets = [t.model_dump() for t in req.factor_targets]
        result, beta_matrix = optimize_factor_exposure(
            tickers, aligned.dates, aligned.matrix, bounds, yields,
            limits, market, targets,
        )

        current_betas = beta_matrix @ current_weights
        optimized_betas = beta_matrix @ result.weights
        factor_betas_payload = {
            "current_portfolio": {"momentum": float(current_betas[0]), "value": float(current_betas[1]), "size": float(current_betas[2])},
            "optimized_portfolio": {"momentum": float(optimized_betas[0]), "value": float(optimized_betas[1]), "size": float(optimized_betas[2])},
        }
    else:
        raise ApiError(422, "unsupported_strategy", f"unsupported strategy {req.strategy!r}", {"supported": [s.value for s in Strategy]})

    optimized_weights = result.weights

    allocation_changes = []
    for i, t in enumerate(tickers):
        cur_pct = current_weights[i] * 100.0
        opt_pct = optimized_weights[i] * 100.0
        allocation_changes.append({
            "ticker": t,
            "security_name": market.fund(t).security_name,
            "current_weight": cur_pct,
            "optimized_weight": opt_pct,
            "change": opt_pct - cur_pct,
        })

    current_metrics = compute_metrics(current_weights, aligned.matrix, yields, ANNUAL_RISK_FREE_RATE)
    optimized_metrics = compute_metrics(optimized_weights, aligned.matrix, yields, ANNUAL_RISK_FREE_RATE)

    meta = {
        "date_range": {
            "start": str(aligned.dates.min().date()),
            "end": str(aligned.dates.max().date()),
            "observations": aligned.n_obs,
            "dropped_rows_per_ticker": aligned.dropped_rows,
        },
        "conventions": {
            "risk_free_rate": ANNUAL_RISK_FREE_RATE,
            "annualization": 252,
            "cagr": "geometric, compounded over actual observations",
            "sharpe": "arithmetic annual excess return / annualized sample volatility",
        },
        "solver": {
            "status": result.solver_status,
            "starts_tried": result.starts_tried,
            "iterations": result.iterations,
        },
        "metrics": {
            "current": current_metrics.as_dict(),
            "optimized": optimized_metrics.as_dict(),
        },
    }

    return {
        "optimization_strategy": req.strategy.value,
        "allocation_changes": allocation_changes,
        "factor_betas": factor_betas_payload,
        "meta": meta,
    }
