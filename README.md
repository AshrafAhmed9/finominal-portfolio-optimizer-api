# Finominal Portfolio Optimizer API

A REST API that replicates the core engine behind Finominal's
[Portfolio Optimizer](https://finominal.com/portfolio-optimizer/US): given a
set of securities, an optimization strategy, and optional constraints, it
returns optimized portfolio weights, plus (bonus) factor betas for a
factor-exposure strategy.

**Reference match status: could not be measured against the live tool.**
Account creation at https://finominal.com/portfolio-optimizer/US
consistently failed with a generic client-side error ("Something unexpected
happened. Please try again.") across multiple attempts, browsers, and a
private window, which blocked capturing the six required live-tool
comparisons. In place of that comparison, correctness is demonstrated with:

- **71 passing tests**, including analytic closed-form fixtures for
  minimum-variance (two-asset) and equal-risk-contribution risk parity
  (two-asset inverse-volatility special case, and a three-asset equal-
  contribution check), a dense-grid cross-check for the non-convex
  `minimize_drawdown` strategy, and a synthetic-coefficient recovery test
  for the factor regression (fit against returns generated from *known*
  betas, confirming the regression recovers them).
- Every strategy's output independently re-verified against a feasible
  baseline (e.g. minimum volatility must not exceed equal-weight variance).
- All constraint types (bounds, dividend yield, CAGR, drawdown, volatility
  range) exercised end-to-end through the API, including a case that is
  provably infeasible and correctly rejected rather than silently producing
  invalid weights.

`tests/golden/scenarios.json` and `scripts/compare_reference.py` are built
and ready - if live-tool access becomes available, capturing the six
scenarios and dropping the weights in is the only remaining step; no code
changes are needed. See `tests/golden/README.md`.

## Setup

Tested with **Python 3.12** (see `requirements.txt` for the exact pinned
versions used).

```bash
python3.12 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

uvicorn app.main:app --reload
# -> http://127.0.0.1:8000/docs for interactive Swagger UI
```

Health check: `curl http://127.0.0.1:8000/health`

## Example requests

**Case 1 - equal weights (no solver needed):**
```bash
curl -s -X POST http://127.0.0.1:8000/optimize \
  -H 'Content-Type: application/json' \
  -d '{"securities":[{"ticker":"IEFA","weight":25},{"ticker":"SPY","weight":75}],"strategy":"equal_weights"}'
```

**Case 3 - minimize volatility, three assets:**
```bash
curl -s -X POST http://127.0.0.1:8000/optimize \
  -H 'Content-Type: application/json' \
  -d '{"securities":[{"ticker":"SPY","weight":60},{"ticker":"AGG","weight":30},{"ticker":"GLD","weight":10}],"strategy":"minimize_volatility"}'
```

**Case 5 - maximize Sharpe with portfolio + security constraints:**
```bash
curl -s -X POST http://127.0.0.1:8000/optimize \
  -H 'Content-Type: application/json' \
  -d @examples/case_05_constrained_sharpe.json
```

**Case 6 - factor exposure (bonus), maximize momentum:**
```bash
curl -s -X POST http://127.0.0.1:8000/optimize \
  -H 'Content-Type: application/json' \
  -d '{"securities":[{"ticker":"IEFA","weight":20},{"ticker":"GLD","weight":20},{"ticker":"AGG","weight":20},{"ticker":"VEA","weight":20},{"ticker":"SPY","weight":20}],"strategy":"optimize_factor_exposure","factor_targets":[{"factor":"momentum","direction":"maximize"}]}'
```

**Supplied return data instead of the bundled dataset** (`examples/inline_returns_request.json`
has a runnable 22-observation example):
```bash
curl -s -X POST http://127.0.0.1:8000/optimize \
  -H 'Content-Type: application/json' \
  -d @examples/inline_returns_request.json
```
Every security in the request must either supply `returns` or omit it - mixed
inline/bundled requests are rejected, and inline returns fully replace the
workbook series for the tickers they cover (fund name/dividend yield still
come from the bundled `Fund Info` sheet).

## Strategies

`equal_weights` `risk_parity` `minimize_drawdown` `minimize_volatility`
`maximize_sharpe` `optimize_factor_exposure` (bonus)

## Constraints

```json
{
  "min_weight": 5,
  "max_weight": 40,
  "per_security": {"SPY": {"min": 10, "max": 50}},
  "min_dividend_yield": 2.5,
  "min_cagr": null,
  "max_drawdown": null,
  "volatility_range": {"min": null, "max": null}
}
```
All bound/limit values are **percentages**. Per-security bounds override the
matching global endpoint for that ticker; the other endpoint still inherits
the global default. `max_drawdown: 20` means "no worse than a 20% loss," not
a target.

## Methodology (stated explicitly, not silently assumed)

- **Portfolio return series:** constant-weight, `r_p[t] = w . R[t, :]`.
- **Annualization:** 252 trading observations/year.
- **Volatility:** sample standard deviation (`ddof=1`) of daily returns,
  annualized by `sqrt(252)`.
- **CAGR:** geometric, compounding the actual observed daily returns:
  `expm1(sum(log1p(r_p)) * 252 / n)`.
- **Sharpe ratio:** `(annualized arithmetic mean return - annual risk-free
  rate) / annualized volatility`. Risk-free rate defaults to **0%** - the
  assignment explicitly permits this ("you may assume a risk-free rate of 0%
  or use a standard value"). A prior public submission of this same
  assignment reported that 2% matched the live tool more closely; that is a
  hypothesis worth testing once live captures exist, not something this
  build assumed without evidence. If reference comparison shows a
  systematic Sharpe-side gap, `ANNUAL_RISK_FREE_RATE` in `app/metrics.py` is
  the single place to change it.
- **Max drawdown:** computed on a wealth index that starts at 1.0 and
  compounds daily returns, so it reflects the starting-capital effect - a
  portfolio that returns -10% then +10% is NOT back to a 0% drawdown at the
  trough (see `tests/test_metrics.py::test_max_drawdown_reflects_starting_capital`).
- **Dividend yield:** linear in weights, `w . y`. GLD's yield cell in
  `Fund Info` is blank; **this dataset only** treats it as 0.0 and discloses
  it in `/securities` (`dividend_yield_known: false`) - this is not a
  general "missing yield = zero" assumption for arbitrary data.
- **Date alignment:** every calculation inner-joins on date across exactly
  the tickers in the request. Funds have very different histories (SPY back
  to 1993, IEFA only from 2012), so a request naming IEFA shortens the
  common window for every fund in that request - but never for funds not in
  the request. See `app/data.py` and `tests/test_data.py`.
- **Risk parity:** true equal-risk-contribution (ERC) - minimizes the
  dispersion of each asset's fractional contribution to total portfolio
  variance, not naive inverse-volatility (which only coincides with ERC in
  the two-asset, zero-correlation special case - see
  `tests/test_optimizers.py::test_risk_parity_two_asset_equals_inverse_volatility`
  vs. `test_risk_parity_three_asset_equal_contributions`).
- **Minimize drawdown:** non-convex and non-smooth; solved via deterministic
  multi-start SLSQP (fixed RNG seed 42) and cross-checked in tests against a
  dense grid search on a two-asset fixture.
- **Factor exposure (bonus):** each asset is regressed once against
  Momentum/Value/Size (OLS via `numpy.linalg.lstsq`); because the design
  matrix doesn't depend on portfolio weights, any constant-weight
  portfolio's betas equal `beta_matrix @ w` (verified against a direct
  regression of the weighted return series in `tests/test_factors.py`).
  That makes "maximize exposure to factor X subject to linear bounds/yield"
  a linear program, solved once via `scipy.optimize.linprog` rather than a
  nonlinear search. Per the assignment, case 6 is **not** expected to match
  the live tool's exact weights (it uses a broader internal factor model
  than this build's three factors) - the pass condition tested is that
  optimized momentum beta strictly exceeds the current portfolio's.

## Error handling

Every failure returns `{"error": {"code", "message", "details"}}`.
Constraint feasibility is checked **analytically before the solver runs**
where possible (e.g. the maximum achievable dividend yield under given
bounds is itself a linear program), so an infeasible request gets a
specific reason, not "optimization failed":

```json
{"error": {"code": "infeasible_or_invalid_constraint",
  "message": "min_dividend_yield of 50.0000% is infeasible under the given weight bounds; maximum achievable yield is 3.9740%"}}
```

Unknown tickers, unsupported strategies, mismatched weight sums, mixed
inline/bundled returns, non-finite values, and returns ≤ -100% (an
unrepresentable "more than total loss" in this simple-return model) are all
rejected with a specific 422, never silently coerced.

## Testing

```bash
pytest -q                        # 71 tests: data, metrics, optimizers, constraints, factors, API
python scripts/compare_reference.py   # live-tool comparison (needs tests/golden/scenarios.json - see that folder's README)
```

Coverage highlights: analytic two-asset minimum-variance and ERC fixtures,
a dense-grid cross-check for minimize-drawdown, a synthetic-coefficient
recovery test for the factor regression, and API-level checks that supplied
inline returns actually change the result (not just accepted and ignored).

## Known limitations / what I'd do with more time

- Live-tool reference comparison could not be run - account creation on the
  live tool failed repeatedly with a generic error (see the status note at
  the top). This is the single biggest open item; the test suite is the
  fallback evidence.
- Risk-free rate is currently a global default (0%), not solved for from
  live-tool evidence, since that evidence was unavailable; §Methodology
  above explains the reasoning and where to change it if it becomes
  available later.
- `minimize_drawdown` has no global-optimum guarantee (the problem is
  non-convex); the deterministic multi-start approach is cross-checked
  against a grid search but a dense global search was out of scope for the
  time budget.
- No persistence, auth, or deployment config - out of scope for a
  single-machine take-home per the assignment's own tips.

## Project layout

```
app/            FastAPI app, data loading, metrics, constraints, optimizers, factor regression
tests/          pytest suite (data, metrics, optimizers, constraints, factors, API, reference)
scripts/        compare_reference.py - live-tool comparison report
examples/       runnable request bodies
docs/           reference screenshots (once captured)
```
