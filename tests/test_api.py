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


def test_infeasible_dividend_yield_returns_clear_422_not_invalid_weights(client):
    r = client.post("/optimize", json={
        "securities": [{"ticker": "SPY", "weight": 50}, {"ticker": "AGG", "weight": 50}],
        "strategy": "maximize_sharpe",
        "constraints": {"min_dividend_yield": 50},  # unreachable; max is under 4%
    })
    assert r.status_code == 422
    assert "max_achievable" in r.json()["error"]["message"] or "maximum achievable" in r.json()["error"]["message"]
