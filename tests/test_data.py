import numpy as np
import pandas as pd
import pytest

from app.data import DataError, build_return_matrix


def test_known_tickers(market):
    assert market.known_tickers() == ("AGG", "GLD", "IEFA", "SPY", "VEA")


def test_gld_yield_missing_treated_as_zero(market):
    gld = market.fund("GLD")
    assert gld.dividend_yield == 0.0
    assert gld.dividend_yield_known is False


def test_known_yields(market):
    assert market.fund("AGG").dividend_yield == pytest.approx(0.03974)
    assert market.fund("SPY").dividend_yield == pytest.approx(0.00987)


def test_unknown_ticker_raises(market):
    with pytest.raises(DataError):
        market.fund("ZZZZ")


def test_alignment_shortens_to_later_start(market):
    # IEFA starts 2012-10-23, SPY starts 1993-01-29: the pair's common window
    # must start at IEFA's start, not SPY's.
    aligned = build_return_matrix(["IEFA", "SPY"], None, market)
    assert aligned.dates.min() == pd.Timestamp("2012-10-23")
    assert aligned.dropped_rows["SPY"] > 0
    assert aligned.dropped_rows["IEFA"] == 0


def test_unrequested_fund_does_not_shorten_others(market):
    # Requesting only SPY+AGG (both start before IEFA) must not be affected
    # by IEFA's later start, since IEFA isn't in this request.
    aligned = build_return_matrix(["SPY", "AGG"], None, market)
    assert aligned.dates.min() == pd.Timestamp("2003-09-26")  # AGG's start, the later of the two


def test_zero_current_weight_ticker_still_participates_in_alignment(market):
    # A ticker requested with 0% current weight still shortens/joins the
    # window - it's investable, just not currently held.
    with_iefa = build_return_matrix(["IEFA", "SPY", "AGG"], None, market)
    without_iefa = build_return_matrix(["SPY", "AGG"], None, market)
    assert with_iefa.dates.min() > without_iefa.dates.min()


def test_inline_returns_replace_bundled(market):
    dates = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07", "2020-01-08"])
    inline = {"SPY": pd.Series([0.01, -0.02, 0.005, 0.0, 0.003], index=dates)}
    aligned = build_return_matrix(["SPY"], inline, market)
    assert aligned.n_obs == 5
    np.testing.assert_allclose(aligned.matrix[:, 0], [0.01, -0.02, 0.005, 0.0, 0.003])


def test_return_le_minus_one_rejected(market):
    dates = pd.to_datetime(["2020-01-02", "2020-01-03"])
    inline = {"SPY": pd.Series([-1.0, 0.01], index=dates)}
    with pytest.raises(DataError):
        build_return_matrix(["SPY"], inline, market)


def test_no_shared_mutation_between_requests(market):
    a = build_return_matrix(["SPY", "AGG"], None, market)
    a.matrix[0, 0] = 999.0
    b = build_return_matrix(["SPY", "AGG"], None, market)
    assert b.matrix[0, 0] != 999.0
