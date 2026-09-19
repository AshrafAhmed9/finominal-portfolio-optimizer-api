"""Loads Data.xlsx once at startup and aligns per-request return series.

Two data sources feed an optimization request:
  - the bundled workbook (default), or
  - returns supplied inline in the request body, which fully replace the
    workbook's return series for the requested tickers (fund names/yields
    still come from the workbook's Fund Info sheet).

Alignment is always an inner join across exactly the requested tickers: a
fund that starts later shortens the common window for everyone in the
request, but never for funds outside the request. We never forward-fill or
zero-fill a missing observation - that would fabricate history.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

KNOWN_TICKERS = ("AGG", "GLD", "IEFA", "SPY", "VEA")
FACTOR_NAMES = ("momentum", "value", "size")
_FACTOR_SHEET_NAMES = {
    "momentum": "Momentum Factor",
    "value": "Value Factor",
    "size": "Size Factor",
}


class DataError(ValueError):
    """Raised for problems with the bundled or supplied data itself."""


@dataclass(frozen=True)
class FundInfo:
    ticker: str
    security_name: str
    dividend_yield: float  # fraction, e.g. 0.03974; GLD's missing cell -> 0.0
    dividend_yield_known: bool


class MarketData:
    """Immutable in-memory view of the workbook, loaded once at startup."""

    def __init__(self, xlsx_path: str):
        try:
            fund_info = pd.read_excel(xlsx_path, sheet_name="Fund Info")
            fund_returns = pd.read_excel(xlsx_path, sheet_name="Fund Returns")
            factor_returns = pd.read_excel(xlsx_path, sheet_name="Factor Returns")
        except Exception as exc:  # noqa: BLE001 - fail startup loudly either way
            raise DataError(f"could not load {xlsx_path}: {exc}") from exc

        self.fund_info: dict[str, FundInfo] = {}
        for _, row in fund_info.iterrows():
            ticker = str(row["ticker"]).strip().upper()
            yield_raw = row["dividend_yield"]
            known = not (yield_raw is None or (isinstance(yield_raw, float) and math.isnan(yield_raw)))
            self.fund_info[ticker] = FundInfo(
                ticker=ticker,
                security_name=str(row["fund_name"]).strip(),
                dividend_yield=float(yield_raw) if known else 0.0,
                dividend_yield_known=known,
            )

        fund_returns = fund_returns.copy()
        fund_returns["ticker"] = fund_returns["ticker"].str.strip().str.upper()
        fund_returns["date"] = pd.to_datetime(fund_returns["date"])
        if fund_returns.duplicated(subset=["ticker", "date"]).any():
            raise DataError("Fund Returns has duplicate (ticker, date) rows")
        if not np.isfinite(fund_returns["total_return"]).all():
            raise DataError("Fund Returns has non-finite values")
        # ticker -> Series indexed by date, sorted
        self._fund_returns: dict[str, pd.Series] = {
            t: g.sort_values("date").set_index("date")["total_return"]
            for t, g in fund_returns.groupby("ticker")
        }

        factor_returns = factor_returns.copy()
        factor_returns["date"] = pd.to_datetime(factor_returns["date"])
        if not np.isfinite(factor_returns["total_return"]).all():
            raise DataError("Factor Returns has non-finite values")
        self._factor_returns: dict[str, pd.Series] = {}
        for key, sheet_name in _FACTOR_SHEET_NAMES.items():
            g = factor_returns[factor_returns["index_ticker"] == sheet_name]
            if g.empty:
                raise DataError(f"Factor Returns missing series {sheet_name!r}")
            if g["date"].duplicated().any():
                raise DataError(f"Factor Returns has duplicate dates for {sheet_name!r}")
            self._factor_returns[key] = g.sort_values("date").set_index("date")["total_return"]

    def known_tickers(self) -> tuple[str, ...]:
        return tuple(sorted(self.fund_info))

    def fund(self, ticker: str) -> FundInfo:
        ticker = ticker.upper()
        if ticker not in self.fund_info:
            raise DataError(f"unknown ticker {ticker!r}")
        return self.fund_info[ticker]

    def raw_returns(self, ticker: str) -> pd.Series:
        ticker = ticker.upper()
        if ticker not in self._fund_returns:
            raise DataError(f"unknown ticker {ticker!r}")
        return self._fund_returns[ticker]

    def factor_series(self, name: str) -> pd.Series:
        if name not in self._factor_returns:
            raise DataError(f"unknown factor {name!r}")
        return self._factor_returns[name]


@dataclass(frozen=True)
class AlignedReturns:
    """Common-date return matrix for exactly the requested tickers."""

    tickers: tuple[str, ...]
    dates: pd.DatetimeIndex
    matrix: np.ndarray  # shape (n_obs, n_tickers), columns ordered as `tickers`
    dropped_rows: dict[str, int]  # per-ticker rows outside the common window

    @property
    def n_obs(self) -> int:
        return self.matrix.shape[0]


def build_return_matrix(
    tickers: list[str],
    inline_returns: dict[str, pd.Series] | None,
    market: MarketData,
) -> AlignedReturns:
    """Inner-joins each requested ticker's return series on date.

    inline_returns, when given, fully replaces the workbook series for the
    tickers it covers; any requested ticker absent from it falls back to
    the workbook. Every value must be finite and > -1 (a total loss is not
    representable as a further return in this simple-return model, and a
    value <= -1 signals a bad input, not an achievable observation).
    """
    series_by_ticker: dict[str, pd.Series] = {}
    original_lengths: dict[str, int] = {}
    for t in tickers:
        s = (inline_returns or {}).get(t)
        if s is None:
            s = market.raw_returns(t)
        else:
            if not np.isfinite(s.to_numpy()).all():
                raise DataError(f"supplied returns for {t} contain non-finite values")
        if (s <= -1.0).any():
            raise DataError(
                f"supplied or bundled returns for {t} contain a value <= -1 "
                "(a total loss); this simple-return model cannot represent it"
            )
        series_by_ticker[t] = s
        original_lengths[t] = len(s)

    frame = pd.DataFrame(series_by_ticker)
    aligned = frame.dropna(how="any")
    if aligned.empty:
        raise DataError(f"no overlapping dates across requested tickers: {tickers}")
    if aligned.shape[0] < 2:
        raise DataError(
            f"only {aligned.shape[0]} overlapping observation(s) across {tickers}; "
            "at least 2 are required to compute variance/covariance"
        )

    dropped = {t: original_lengths[t] - aligned.shape[0] for t in tickers}
    return AlignedReturns(
        tickers=tuple(tickers),
        dates=aligned.index,
        matrix=aligned.to_numpy(dtype=float, copy=True),
        dropped_rows=dropped,
    )


def build_factor_matrix(
    portfolio_dates: pd.DatetimeIndex,
    portfolio_returns: np.ndarray,
    market: MarketData,
) -> tuple[np.ndarray, np.ndarray, pd.DatetimeIndex]:
    """Returns (X, y, dates) aligned on the intersection of portfolio and
    factor dates. X has an intercept column followed by momentum, value,
    size (in that order); y is the portfolio return on those dates.
    """
    port = pd.Series(portfolio_returns, index=portfolio_dates)
    frame = pd.DataFrame({"portfolio": port})
    for name in FACTOR_NAMES:
        frame[name] = market.factor_series(name)
    aligned = frame.dropna(how="any")
    if aligned.shape[0] < 5:
        raise DataError(
            f"only {aligned.shape[0]} overlapping portfolio/factor observation(s); "
            "at least 5 are required for a rank-4 regression (intercept + 3 factors)"
        )
    y = aligned["portfolio"].to_numpy(dtype=float)
    X = np.column_stack(
        [np.ones(len(aligned)), aligned["momentum"], aligned["value"], aligned["size"]]
    )
    if np.linalg.matrix_rank(X) < X.shape[1]:
        raise DataError("factor design matrix is rank-deficient over the common date range")
    return X, y, aligned.index
