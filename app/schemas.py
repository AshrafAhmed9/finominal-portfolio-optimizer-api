"""Pydantic request/response models. All weight/yield/limit fields are
percentages (0-100) at this boundary; conversion to fractions happens in
app.main before reaching constraints.py / optimize.py."""
from __future__ import annotations

import datetime as _dt
import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .optimize import STRATEGIES


class StrictModel(BaseModel):
    """Base for every request-side model: rejects unknown fields (a typo'd
    constraint key like `max_volatility` used to be silently dropped instead
    of applied or rejected) and rejects NaN/Infinity at every numeric field,
    not just the one place that happened to be checked before (inline
    returns). `"NaN"` and `"Infinity"` are valid JSON strings that pydantic
    would otherwise coerce to a float; allow_inf_nan=False blocks that too."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Strategy(str, Enum):
    equal_weights = "equal_weights"
    risk_parity = "risk_parity"
    minimize_drawdown = "minimize_drawdown"
    minimize_volatility = "minimize_volatility"
    maximize_sharpe = "maximize_sharpe"
    optimize_factor_exposure = "optimize_factor_exposure"


assert set(s.value for s in Strategy) == set(STRATEGIES)  # keep the two in lockstep


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class InlineReturn(StrictModel):
    date: str  # calendar date only, strict "YYYY-MM-DD"
    total_return: float

    @field_validator("date")
    @classmethod
    def _validate_calendar_date(cls, v: str) -> str:
        # Reject anything that isn't exactly YYYY-MM-DD before it ever
        # reaches pandas: garbage strings used to surface as a raw 500,
        # and non-canonical forms ("2020-1-3") or timestamps with a time
        # component used to silently pass through and either duplicate a
        # date or get treated as a distinct observation from the same day.
        if not _ISO_DATE_RE.match(v):
            raise ValueError(f"date {v!r} must be a calendar date in YYYY-MM-DD format, with no time component")
        try:
            _dt.date.fromisoformat(v)
        except ValueError as exc:
            raise ValueError(f"date {v!r} is not a valid calendar date: {exc}") from exc
        return v


class SecurityInput(StrictModel):
    ticker: str
    weight: float = Field(ge=0, le=100)
    returns: list[InlineReturn] | None = None

    @field_validator("ticker")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class PerSecurityBound(StrictModel):
    min: float | None = Field(default=None, ge=0, le=100)
    max: float | None = Field(default=None, ge=0, le=100)


class VolatilityRange(StrictModel):
    min: float | None = Field(default=None, ge=0)
    max: float | None = Field(default=None, ge=0)


class Constraints(StrictModel):
    min_weight: float | None = Field(default=None, ge=0, le=100)
    max_weight: float | None = Field(default=None, ge=0, le=100)
    per_security: dict[str, PerSecurityBound] | None = None
    min_dividend_yield: float | None = Field(default=None, ge=0)
    min_cagr: float | None = None
    max_drawdown: float | None = Field(default=None, ge=0)
    volatility_range: VolatilityRange | None = None

    @field_validator("per_security")
    @classmethod
    def _upper_keys(cls, v):
        if not v:
            return v
        normalized: dict[str, PerSecurityBound] = {}
        for raw_key, bound in v.items():
            key = raw_key.strip().upper()
            if key in normalized:
                raise ValueError(
                    f"per_security has conflicting keys that normalize to the same "
                    f"ticker {key!r} (e.g. {raw_key!r}); specify it once"
                )
            normalized[key] = bound
        return normalized


class FactorTarget(StrictModel):
    factor: Literal["momentum", "value", "size"]
    direction: Literal["maximize", "minimize"]
    importance: float = Field(default=1.0, gt=0)


class OptimizeRequest(StrictModel):
    securities: list[SecurityInput]
    strategy: Strategy
    constraints: Constraints | None = None
    factor_targets: list[FactorTarget] | None = None

    @model_validator(mode="after")
    def _validate(self):
        tickers = [s.ticker for s in self.securities]
        if len(tickers) != len(set(tickers)):
            raise ValueError("duplicate tickers in securities")
        if not self.securities:
            raise ValueError("securities must not be empty")

        has_inline = any(s.returns is not None for s in self.securities)
        no_inline = any(s.returns is None for s in self.securities)
        if has_inline and no_inline:
            raise ValueError(
                "mixed inline/bundled returns are not supported: either every security "
                "supplies `returns`, or none do (bundled dataset is used for all)"
            )
        if has_inline:
            for s in self.securities:
                dates = [r.date for r in s.returns]
                if len(dates) != len(set(dates)):
                    raise ValueError(f"duplicate dates in supplied returns for {s.ticker}")
                if len(s.returns) < 2:
                    raise ValueError(f"supplied returns for {s.ticker} need >= 2 observations")

        total_weight = sum(s.weight for s in self.securities)
        if abs(total_weight - 100.0) > 1e-6:
            raise ValueError(f"security weights must sum to 100, got {total_weight}")

        if self.strategy == Strategy.optimize_factor_exposure and not self.factor_targets:
            raise ValueError("optimize_factor_exposure requires factor_targets")
        if self.strategy != Strategy.optimize_factor_exposure and self.factor_targets:
            raise ValueError("factor_targets is only valid with strategy=optimize_factor_exposure")
        if self.factor_targets:
            names = [t.factor for t in self.factor_targets]
            if len(names) != len(set(names)):
                raise ValueError("duplicate factor_targets entries")
        return self


class AllocationChange(BaseModel):
    ticker: str
    security_name: str
    current_weight: float
    optimized_weight: float
    change: float


class FactorBetasResponse(BaseModel):
    current_portfolio: dict[str, float]
    optimized_portfolio: dict[str, float]


class OptimizeResponse(BaseModel):
    optimization_strategy: str
    allocation_changes: list[AllocationChange]
    factor_betas: FactorBetasResponse | None = None
    meta: dict
