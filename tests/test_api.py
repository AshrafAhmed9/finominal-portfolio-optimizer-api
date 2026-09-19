import numpy as np
import pytest


FIVE_FUND_EQUAL = [
    {"ticker": "IEFA", "weight": 20},
    {"ticker": "GLD", "weight": 20},
    {"ticker": "AGG", "weight": 20},
    {"ticker": "VEA", "weight": 20},
    {"ticker": "SPY", "weight": 20},
]


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_securities_lists_gld_with_zero_yield_and_disclosure(client):
    r = client.get("/securities")
    assert r.status_code == 200
    gld = next(s for s in r.json() if s["ticker"] == "GLD")
    assert gld["dividend_yield"] == 0.0
    assert gld["dividend_yield_known"] is False


def test_unknown_ticker_returns_422_with_available_list(client):
    r = client.post("/optimize", json={"securities": [{"ticker": "NOPE", "weight": 100}], "strategy": "equal_weights"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "unknown_ticker"
    assert "AGG" in body["error"]["details"]["known_tickers"]


def test_unsupported_strategy_returns_422(client):
    r = client.post("/optimize", json={"securities": [{"ticker": "SPY", "weight": 100}], "strategy": "not_a_strategy"})
    assert r.status_code == 422


def test_weights_not_summing_to_100_rejected(client):
    r = client.post("/optimize", json={"securities": [{"ticker": "SPY", "weight": 60}, {"ticker": "AGG", "weight": 30}], "strategy": "equal_weights"})
    assert r.status_code == 422


def test_duplicate_ticker_rejected(client):
    r = client.post("/optimize", json={
        "securities": [{"ticker": "SPY", "weight": 50}, {"ticker": "SPY", "weight": 50}],
        "strategy": "equal_weights",
    })
    assert r.status_code == 422


def test_non_finite_supplied_return_rejected(client):
    import json as _json

    # Standard JSON has no NaN literal, so this exercises the raw wire
    # format (many JSON libraries emit `NaN` non-strictly) rather than
    # httpx's stricter Python-side encoder.
    payload = {
        "securities": [
            {"ticker": "SPY", "weight": 100, "returns": [
                {"date": "2020-01-02", "total_return": float("nan")},
                {"date": "2020-01-03", "total_return": 0.01},
            ]},
        ],
        "strategy": "equal_weights",
    }
    body = _json.dumps(payload, allow_nan=True)
    r = client.post("/optimize", content=body, headers={"Content-Type": "application/json"})
    assert r.status_code in (400, 422)


# --- R3/R4 regressions: nonfinite values, unknown fields, and invalid ------
# --- calendar dates used to bypass validation instead of being rejected ---

def test_unknown_field_in_constraints_rejected(client):
    # `max_volatility` isn't a field (it's `volatility_range.max`); this used
    # to be silently dropped by pydantic's default extra-field handling,
    # so the constraint was neither applied nor reported as an error.
    r = client.post("/optimize", json={
        "securities": [{"ticker": "SPY", "weight": 100}],
        "strategy": "equal_weights",
        "constraints": {"max_volatility": 0},
    })
    assert r.status_code == 422


@pytest.mark.parametrize(
    "constraints",
    [
        {"min_cagr": "NaN"},
        {"max_drawdown": "Infinity"},
        {"min_dividend_yield": "-Infinity"},
    ],
)
def test_nonfinite_string_constraint_values_rejected(client, constraints):
    # These are valid JSON strings, not the nonstandard bare NaN/Infinity
    # tokens - pydantic would otherwise happily coerce them to float and let
    # NaN comparisons silently bypass every constraint check downstream.
    r = client.post("/optimize", json={
        "securities": [{"ticker": "SPY", "weight": 100}],
        "strategy": "equal_weights",
        "constraints": constraints,
    })
    assert r.status_code == 422


def test_nonfinite_factor_target_importance_rejected(client):
    r = client.post("/optimize", json={
        "securities": [{"ticker": "SPY", "weight": 50}, {"ticker": "AGG", "weight": 50}],
        "strategy": "optimize_factor_exposure",
        "factor_targets": [{"factor": "momentum", "direction": "maximize", "importance": "Infinity"}],
    })
    assert r.status_code == 422


def test_conflicting_per_security_keys_after_normalization_rejected(client):
    r = client.post("/optimize", json={
        "securities": [{"ticker": "SPY", "weight": 50}, {"ticker": "AGG", "weight": 50}],
        "strategy": "equal_weights",
        "constraints": {"per_security": {"SPY": {"min": 10}, "spy": {"max": 60}}},
    })
    assert r.status_code == 422


@pytest.mark.parametrize(
    "bad_date",
    ["garbage", "NaT", "", "2020-1-3", "2020-01-03T00:00:00Z", "2020-02-30", "2020/01/03"],
)
def test_invalid_calendar_dates_rejected(client, bad_date):
    # Each of these used to either crash with a raw pandas exception, or
    # silently pass through and get miscounted as an observation (a
    # non-canonical form like "2020-1-3" used to duplicate "2020-01-03"
    # instead of being recognized as the same date, or being rejected).
    r = client.post("/optimize", json={
        "securities": [{"ticker": "SPY", "weight": 100, "returns": [
            {"date": bad_date, "total_return": 0.01},
            {"date": "2020-01-06", "total_return": -0.01},
        ]}],
        "strategy": "equal_weights",
    })
    assert r.status_code == 422


def test_valid_unsorted_inline_dates_are_sorted_and_aligned(client):
    r = client.post("/optimize", json={
        "securities": [{"ticker": "SPY", "weight": 100, "returns": [
            {"date": "2020-01-08", "total_return": 0.01},
            {"date": "2020-01-02", "total_return": -0.02},
            {"date": "2020-01-06", "total_return": 0.005},
        ]}],
        "strategy": "equal_weights",
    })
    assert r.status_code == 200, r.json()
    assert r.json()["meta"]["date_range"]["start"] == "2020-01-02"
    assert r.json()["meta"]["date_range"]["end"] == "2020-01-08"
    assert r.json()["meta"]["date_range"]["observations"] == 3


def test_mixed_inline_and_bundled_rejected(client):
    r = client.post("/optimize", json={
        "securities": [
            {"ticker": "SPY", "weight": 50, "returns": [
                {"date": "2020-01-02", "total_return": 0.01},
                {"date": "2020-01-03", "total_return": -0.01},
            ]},
            {"ticker": "AGG", "weight": 50},
        ],
        "strategy": "equal_weights",
    })
    assert r.status_code == 422


def test_supplied_returns_actually_affect_the_result(client):
    # Two extreme, hand-built series for a 2-asset minimize_volatility
    # request: A is dead flat (zero variance), B is wildly volatile. The
    # minimum-variance optimum must load almost entirely on A.
    dates = [f"2020-01-{d:02d}" for d in range(2, 32) if d not in (4, 5, 11, 12, 18, 19, 25, 26)]
    flat = [{"date": d, "total_return": 0.0} for d in dates]
    wild = [{"date": d, "total_return": v} for d, v in zip(dates, [0.05, -0.05] * (len(dates) // 2 + 1))]
    r = client.post("/optimize", json={
        "securities": [
            {"ticker": "SPY", "weight": 50, "returns": flat},
            {"ticker": "AGG", "weight": 50, "returns": wild[: len(dates)]},
        ],
        "strategy": "minimize_volatility",
    })
    assert r.status_code == 200
    weights = {a["ticker"]: a["optimized_weight"] for a in r.json()["allocation_changes"]}
    assert weights["SPY"] > weights["AGG"]


def test_factor_targets_rejected_for_non_factor_strategy(client):
    r = client.post("/optimize", json={
        "securities": FIVE_FUND_EQUAL,
        "strategy": "equal_weights",
        "factor_targets": [{"factor": "momentum", "direction": "maximize"}],
    })
    assert r.status_code == 422


def test_factor_strategy_requires_factor_targets(client):
    r = client.post("/optimize", json={"securities": FIVE_FUND_EQUAL, "strategy": "optimize_factor_exposure"})
    assert r.status_code == 422


@pytest.mark.parametrize("strategy", ["equal_weights", "risk_parity", "minimize_volatility", "maximize_sharpe", "minimize_drawdown"])
def test_serialized_weights_satisfy_invariants(client, strategy):
    r = client.post("/optimize", json={
        "securities": [{"ticker": "SPY", "weight": 60}, {"ticker": "AGG", "weight": 30}, {"ticker": "GLD", "weight": 10}],
        "strategy": strategy,
    })
    assert r.status_code == 200, r.json()
    changes = r.json()["allocation_changes"]
    total = sum(a["optimized_weight"] for a in changes)
    assert total == pytest.approx(100.0, abs=0.01)
    for a in changes:
        assert a["optimized_weight"] >= -1e-6
        assert a["change"] == pytest.approx(a["optimized_weight"] - a["current_weight"], abs=1e-9)
        assert a["ticker"]
        assert a["security_name"]


def test_response_metrics_recompute_from_serialized_weights(client):
    r = client.post("/optimize", json={"securities": FIVE_FUND_EQUAL, "strategy": "minimize_volatility"})
    assert r.status_code == 200
    body = r.json()
    weights = np.array([a["optimized_weight"] for a in body["allocation_changes"]]) / 100.0
    assert weights.sum() == pytest.approx(1.0, abs=1e-6)


def test_case5_respects_yield_and_bounds(client):
    r = client.post("/optimize", json={
        "securities": FIVE_FUND_EQUAL,
        "strategy": "maximize_sharpe",
        "constraints": {"min_dividend_yield": 2.5, "min_weight": 5, "max_weight": 40},
    })
    assert r.status_code == 200, r.json()
    body = r.json()
    for a in body["allocation_changes"]:
        assert 5.0 - 0.01 <= a["optimized_weight"] <= 40.0 + 0.01
    assert body["meta"]["metrics"]["optimized"]["dividend_yield"] >= 0.025 - 1e-6


def test_case6_returns_factor_betas_for_both_portfolios(client):
    r = client.post("/optimize", json={
        "securities": FIVE_FUND_EQUAL,
        "strategy": "optimize_factor_exposure",
        "factor_targets": [{"factor": "momentum", "direction": "maximize"}],
    })
    assert r.status_code == 200, r.json()
    body = r.json()
    betas = body["factor_betas"]
    assert set(betas["current_portfolio"]) == {"momentum", "value", "size"}
    assert betas["optimized_portfolio"]["momentum"] > betas["current_portfolio"]["momentum"]


def test_min_cagr_portfolio_constraint_respected(client):
    r = client.post("/optimize", json={
        "securities": [{"ticker": "SPY", "weight": 60}, {"ticker": "AGG", "weight": 40}],
        "strategy": "minimize_volatility",
        "constraints": {"min_cagr": 2},  # 2%, comfortably achievable by this pair historically
    })
    assert r.status_code == 200, r.json()
    assert r.json()["meta"]["metrics"]["optimized"]["cagr"] >= 0.02 - 1e-6


def test_max_drawdown_portfolio_constraint_respected_when_feasible(client):
    r = client.post("/optimize", json={
        "securities": [{"ticker": "SPY", "weight": 60}, {"ticker": "AGG", "weight": 40}],
        "strategy": "maximize_sharpe",
        "constraints": {"max_drawdown": 20},
    })
    assert r.status_code == 200, r.json()
    assert r.json()["meta"]["metrics"]["optimized"]["max_drawdown"] <= 0.20 + 1e-6


def test_max_drawdown_portfolio_constraint_rejected_when_infeasible(client):
    # SPY (2008) and AGG (2022) both have historical drawdowns well above 15%
    # over their full common history, so a 15% cap for only these two assets
    # is genuinely infeasible - this must be a clear 422, not silently
    # invalid weights or a wrong "success".
    r = client.post("/optimize", json={
        "securities": [{"ticker": "SPY", "weight": 60}, {"ticker": "AGG", "weight": 40}],
        "strategy": "maximize_sharpe",
        "constraints": {"max_drawdown": 15},
    })
    assert r.status_code == 422


def test_volatility_range_constraint_respected(client):
    r = client.post("/optimize", json={
        "securities": [{"ticker": "SPY", "weight": 60}, {"ticker": "AGG", "weight": 40}],
        "strategy": "maximize_sharpe",
        "constraints": {"volatility_range": {"min": 5, "max": 10}},
    })
    assert r.status_code == 200, r.json()
    vol_pct = r.json()["meta"]["metrics"]["optimized"]["volatility"] * 100
    assert 5.0 - 0.01 <= vol_pct <= 10.0 + 0.01


@pytest.mark.parametrize(
    "strategy", ["equal_weights", "risk_parity", "minimize_volatility", "maximize_sharpe", "minimize_drawdown"]
)
def test_single_security_portfolio_across_strategies(client, strategy):
    # R2b regression: a single requested security used to crash risk_parity
    # and minimize_volatility (np.cov collapses to a 0-d scalar for one
    # column, breaking matrix ops downstream). Every strategy must handle it.
    r = client.post("/optimize", json={"securities": [{"ticker": "SPY", "weight": 100}], "strategy": strategy})
    assert r.status_code == 200, r.json()
    changes = r.json()["allocation_changes"]
    assert len(changes) == 1
    assert changes[0]["optimized_weight"] == pytest.approx(100.0)


@pytest.mark.parametrize(
    "strategy", ["equal_weights", "risk_parity", "minimize_volatility", "maximize_sharpe", "minimize_drawdown"]
)
def test_fully_fixed_weights_across_strategies(client, strategy):
    # R2a regression: min_weight == max_weight == 50 for both securities
    # pins every variable, which used to crash on a missing `result.nit`
    # attribute that SciPy's SLSQP omits (not zeroes) when every variable is
    # fixed by bounds before the solver ever iterates.
    r = client.post("/optimize", json={
        "securities": [{"ticker": "SPY", "weight": 50}, {"ticker": "AGG", "weight": 50}],
        "strategy": strategy,
        "constraints": {"min_weight": 50, "max_weight": 50},
    })
    assert r.status_code == 200, r.json()
    for a in r.json()["allocation_changes"]:
        assert a["optimized_weight"] == pytest.approx(50.0, abs=1e-6)


def test_fully_fixed_weights_violating_a_limit_returns_structured_error(client):
    # A fixed allocation that cannot satisfy a portfolio-level limit must
    # come back as a clear error, not a crash and not a false success.
    r = client.post("/optimize", json={
        "securities": [{"ticker": "SPY", "weight": 50}, {"ticker": "AGG", "weight": 50}],
        "strategy": "maximize_sharpe",
        "constraints": {"min_weight": 50, "max_weight": 50, "min_dividend_yield": 50},
    })
    assert r.status_code == 422


def test_infeasible_dividend_yield_returns_clear_422_not_invalid_weights(client):
    r = client.post("/optimize", json={
        "securities": [{"ticker": "SPY", "weight": 50}, {"ticker": "AGG", "weight": 50}],
        "strategy": "maximize_sharpe",
        "constraints": {"min_dividend_yield": 50},  # unreachable; max is under 4%
    })
    assert r.status_code == 422
    assert "max_achievable" in r.json()["error"]["message"] or "maximum achievable" in r.json()["error"]["message"]
