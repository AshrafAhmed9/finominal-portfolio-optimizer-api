# Finominal Portfolio Optimizer API — Revised Implementation Plan

Reviewed on 2026-09-19 against the complete assignment DOCX, supplied workbook, public reference page, and independent mathematical and hiring reviews. This is a plan; no application, reference match or performance result is validated yet.

## 1. Submission strategy

Build a small Python API that accepts supplied returns, implements every required strategy and constraint, and makes its results reproducible and explainable. Prioritize complete behavior, defensible mathematics, actual comparison evidence and a clear walkthrough. Additional infrastructure contributes little here.

The brief assigns 40% to reference correctness, 30% to code quality, 20% to communication, and +10% to the factor bonus. Preserve those stated weights. Complete the bonus after core correctness. No defensible estimate of hiring probability or ranking among unseen submissions is available.

**Time:** Ashraf confirmed 12 hours. The exact deadline and already-consumed time remain unspecified. The schedule below allocates 12 hours; it does not reset the company’s clock after planning. Check remaining time before implementation. No AI-use policy appears in the supplied document; any additional company instructions take precedence.

**Current evidence:** this directory contains the assignment, workbook and plan, with no application or tests. The public reference page is readable and exposes an annual rebalancing control. Actual optimization outputs have not been captured during this review. That control alone does not establish the optimizer’s internal mathematics.

## 2. Requirements and acceptance evidence

| Requirement | Planned behavior | Submission evidence |
| --- | --- | --- |
| Python REST API, runnable locally | FastAPI, documented Python version, pinned tested dependencies | Fresh-environment setup and HTTP request |
| Securities with their return data | Dated inline simple returns; workbook convenience mode | Runnable inline request and test proving supplied data affects results |
| Five required strategies | Equal weights, ERC risk parity, minimum drawdown, minimum volatility, maximum Sharpe | Reference comparisons plus dedicated drawdown tests |
| Security and portfolio constraints | Bounds, minimum CAGR, volatility range, maximum drawdown, minimum dividend yield | Feasible/infeasible requests and independent checks of returned weights |
| Allocation Changes | Strategy, ticker, name, current weight, optimized weight, change | Actual response JSON for every required case |
| Reference validation | Cases 1–5, per-ticker comparisons | Every case’s response paired with a live-tool screenshot |
| Factor bonus | Optimize exposure and return both sets of betas | Case 6 response/screenshot, OLS correctness and momentum improvement |
| API screenshots | At least three distinct strategies | Screenshots showing actual API responses |
| Public repository and README | Source, required data, setup, examples, tests and limitations | Public link and verified clean checkout |
| 3–5 minute Loom | Working API, code walkthrough, decisions and tradeoffs | Rehearsed recording and accessible link |

Follow the detailed scenario table’s five-fund 20%-each allocation; the prose saying “5 funds … 50/50” is inconsistent. DPG in the sample JSON illustrates the response schema; it is not a supplied fund.

**Case 6 is explicitly exempt from exact live-model matching.** The assignment supplies only three factors. Validate correct regression, increased momentum exposure for its specified input, and all constraints. The explicit clarification takes precedence over broad bonus rubric wording. Never include case 6 in a claim that five required cases match within tolerance.

## 3. Verified data and handling

Preserve `Data.xlsx` unchanged. SHA-256: `9fc7c747ddefbc3464a71b7b40720f7be43335bab71e8037449d996ca73034c6`.

| Fund | Observations | First date | Last date | Dividend yield, decimal |
| --- | ---: | --- | --- | ---: |
| AGG | 5,702 | 2003-09-26 | 2026-05-27 | 0.03974 |
| GLD | 5,413 | 2004-11-18 | 2026-05-27 | missing |
| IEFA | 3,414 | 2012-10-23 | 2026-05-27 | 0.03278 |
| SPY | 8,388 | 1993-01-29 | 2026-05-27 | 0.00987 |
| VEA | 4,739 | 2007-07-26 | 2026-05-27 | 0.02034 |

`Fund Info`: `ticker, fund_name, dividend_yield`. `Fund Returns`: `date, total_return, ticker`, 27,656 rows. `Factor Returns`: `date, total_return, index_ticker`, 19,017 rows. Momentum, Value and Size each have 6,339 observations from 2002-02-04 to 2026-05-22. There are no duplicate dates within a series. Excel serial dates use epoch 1899-12-30; the workbook does not use the 1904 date system.

Treat values as decimal daily simple returns. Validate finite values and dates, sort, and inner-join across exactly the requested funds. Never zero-fill or forward-fill missing returns, or shorten a subset’s history because an unrequested fund starts later. A requested fund with zero current allocation is still investable and participates in alignment. Report period, count, and dropped rows; substantial internal gaps weaken the daily annualization assumption and deserve a warning.

For this dataset, assume GLD’s missing dividend yield is zero and disclose it. Do not generalize missing-yield-equals-zero to arbitrary datasets. Factor regressions use a separate fund/factor intersection; do not silently shorten ordinary optimization to the factor end date.

## 4. Reference capture and calibration

| Case | Current portfolio, percentages | Strategy | Constraints |
| --- | --- | --- | --- |
| 1 | IEFA 25, SPY 75 | Equal weights | None |
| 2 | VEA 25, AGG 75 | Risk parity | None |
| 3 | SPY 60, AGG 30, GLD 10 | Minimum volatility | None |
| 4 | IEFA, GLD, AGG, VEA, SPY 20 each | Maximum Sharpe | None |
| 5 | Same five, 20 each | Maximum Sharpe | Yield ≥2.50%; each weight 5–40% |
| 6 | Same five, 20 each | Factor exposure | Maximize momentum; bonus |

Capture exact inputs, settings, optimized weights, displayed metrics, timestamp and any visible data window. Save Review Results for each case and Comparison for case 6. Use available authorized browser access; ask Ashraf for sign-in or manual captures only if needed. A blocked reference must not stop independent loader, API or synthetic-test work. Return to missing evidence before submission.

Store `docs/validation/case_01/request.json`, `response.json`, `reference.png`, etc., with capture settings in a shared `reference.json`. Actual responses must come from the running implementation. Never create dummy zero golden weights or use another candidate’s results as authoritative fixtures. Tests must run offline against captured evidence.

One `scripts/compare_reference.py` command should run saved requests and print per-ticker gaps, maximum gap per case, constraint checks, and separate case-6 results. Interpret “below 0.1%” as **below 0.1 percentage points of allocation, equivalent to 10 basis points**, and document the interpretation.

### Focused diagnostic sequence

1. Confirm identical tickers, alignment, units and yield data before adjusting formulas.
2. Compare metrics at fixed weights to separate data differences from optimization differences.
3. Begin with daily constant weights, 252 observations/year, sample volatility, arithmetic excess-return Sharpe and 0% annual risk-free rate. These are explicit starting assumptions, not discovered live-tool conventions. The brief permits a standard nonzero rate.
4. Test plausible Sharpe definitions and rates only where discrepancies justify it. A prior submission’s 2% rate is a hypothesis, not authority.
5. Investigate lookback/rebalancing only when visible settings or fixed-weight metrics support it. Distinguish optimizer conventions from displayed backtest conventions.
6. Lock one coherent convention set for all API requests. Never choose settings by scenario ID. If time/access permit, capture one held-out portfolio after calibration and report its result separately.

Cap initial calibration at 45 minutes plus 30 minutes reserved for one specific discrepancy. Eliminate the 1,024-combination sweep. Some axes are unidentifiable from these cases: a common covariance scaling does not change unconstrained minimum-variance/ERC weights; two-asset ERC equals inverse-volatility weights and cannot distinguish the algorithms. Implement ERC because the brief asks for equal risk contributions.

**Potential conflict:** the workbook is a May 2026 snapshot; the live tool may use different returns or yields. Calculate case 5’s live weights against the workbook yield vector. If they violate 2.50%, reproducing those weights and respecting the supplied-data constraint are incompatible. Preserve valid constraints, show the arithmetic, and report the discrepancy. Do not change yields, hardcode allocations, fit per-case rules, or weaken tolerance to manufacture a match. A mismatch remains an evaluation risk, not a passing result.

## 5. Small architecture

```text
app/
  main.py          # FastAPI, startup loading, routes and error translation
  schemas.py       # explicit request/response models
  data.py          # workbook/inline data -> one aligned representation
  metrics.py       # returns, covariance, CAGR, drawdown, yield and Sharpe
  constraints.py   # bounds, linear feasibility and residual checks
  optimize.py      # strategy functions, dispatch map and bounded solver helper
  factors.py       # OLS and factor optimization
tests/             # data, metrics, optimization, API tests and small fixtures
scripts/compare_reference.py
docs/validation/   # real evidence and comparison results
examples/          # runnable requests, including supplied returns
Data.xlsx
README.md
requirements.txt
.gitignore
```

Use FastAPI, uvicorn, Pydantic, NumPy, pandas, SciPy and openpyxl; pytest and httpx for tests. Pin a compatible set after installing/testing it and state the tested Python version. JSON fixtures avoid a YAML dependency. Load the workbook once at startup; isolate request arrays from shared data. Use ordinary sync routes for CPU-bound calculation rather than blocking an async event loop.

Split `optimize.py` only if readability warrants it. No database, frontend, authentication, queue, cloud deployment or dependency-injection framework. A small CI test job is useful only after required behavior and evidence. Extra competition manifestos and `CLAUDE.md` are unnecessary. Keep this internal planning document out of the reviewer-facing narrative; the README should describe the completed work.

## 6. API contract

`POST /optimize` accepts the five known tickers, current percentage weights, strategy, optional constraints and optional factor targets. **Supplied return support is core scope.** Omitting returns selects the bundled dataset for convenient reference reproduction.

```json
{
  "securities": [
    {"ticker": "SPY", "weight": 60},
    {"ticker": "AGG", "weight": 30},
    {"ticker": "GLD", "weight": 10}
  ],
  "strategy": "minimize_volatility",
  "constraints": {
    "min_weight": 0,
    "max_weight": 100,
    "per_security": {"SPY": {"min": 5, "max": 70}},
    "min_dividend_yield": null,
    "min_cagr": null,
    "max_drawdown": null,
    "volatility_range": {"min": null, "max": null}
  }
}
```

Inline mode adds `returns` to every security, e.g. `"returns": [{"date":"2020-01-02","total_return":0.012}, ...]`. This fragment illustrates schema; ship a runnable example with enough observations. Reject mixed inline/bundled mode. Supplied returns completely replace workbook returns; names/yields still come from supplied fund metadata. Arbitrary new funds, uploads and external data feeds are out of scope.

Validate duplicate tickers/dates, unknown tickers, finite numeric values, unknown fields, empty histories, invalid dates/bounds, unrequested constraint tickers and inconsistent factor parameters. Use a documented minimum of two aligned observations for covariance metrics and warn on very short samples. Factor estimation needs more than four observations and a full-rank intercept-plus-three-factor design. Avoid inventing a 30-day requirement.

For this historical model reject returns ≤-1 with a clear unsupported bankruptcy-observation error; do not clip or silently replace them. Negative returns above -1 are valid. Weights must be in [0,100] and sum to 100 within a small floating-point tolerance, e.g. 1e-6 percentage points. Do not normalize materially incorrect input totals.

Identifiers: `equal_weights`, `risk_parity`, `minimize_drawdown`, `minimize_volatility`, `maximize_sharpe`, `optimize_factor_exposure`.

Boundary units: weights, yields, CAGR, volatility and drawdown limits are percentage numbers; supplied daily returns are decimals; betas are dimensionless. `max_drawdown: 20` means a positive 20% loss limit. Internally use fractions. Per-security bounds override the corresponding global endpoint; omitted endpoints inherit it. Constraints apply to optimized weights, not necessarily current weights.

For bonus targets use `factor_targets`, e.g. `[{"factor":"momentum","direction":"maximize","importance":1}]`. Allow one or more distinct factors with positive importance, default 1; normalize importances for a signed weighted-beta objective. Explain that a combined objective does not guarantee every factor improves. Reject duplicate targets or targets supplied for unrelated strategies.

### Responses and failure semantics

Preserve the brief’s `optimization_strategy`, `allocation_changes`, `ticker`, `security_name`, `current_weight`, `optimized_weight`, and `change`, in request order. Bonus responses include both `factor_betas.current_portfolio` and `factor_betas.optimized_portfolio`. Optional betas must not make an otherwise valid core request fail.

Keep `meta` focused: source, period/count, conventions, current/optimized metrics, solver termination and maximum constraint violation. Include separate factor dates where relevant and explicit percentage suffixes for extra metrics. Do not call a local result globally optimal. Undefined optional metrics are null with a reason; never JSON NaN/Infinity.

Keep sufficient numeric precision in returned allocations. The sample’s two decimals do not mandate two-decimal quantization. Round-and-renormalize can breach a binding yield floor or weight cap. Recompute metrics, changes and constraints from the actual serialized weights. Document the sum tolerance (e.g. 1e-6 percentage points) and internal constraint tolerance (e.g. 1e-8 in fractional units). Display rounding belongs in comparison tables. Any tiny residual correction must pass all checks again.

Use one envelope: `{"error":{"code":"...","message":"...","details":{...}}}`. Return 422 for invalid input, proven infeasibility, or equal-weight/constraint conflicts. Return distinct `optimization_failed` 500 for numerical search exhaustion without exposing a stack trace or fake allocation. Distinguish failure to find a feasible point from proven mathematical infeasibility. Corrupt/missing bundled data should fail startup clearly.

`GET /health` reports readiness after loading; `GET /securities` is optional convenience. FastAPI `/docs` is enough for an interactive demonstration.

## 7. Mathematics and numerical guarantees

### Shared metrics

Baseline constant-weight portfolio: `r_p = R @ w`, `sum(w)=1`, `w>=0`. Covariance uses the same common sample. Annual volatility is sample standard deviation times `sqrt(252)`; arithmetic annual return is `mean(r_p)*252`.

CAGR: `expm1(sum(log1p(r_p))*252/n)`, explicitly a trading-observation convention. Baseline Sharpe: `(annual_arithmetic_return - annual_rf)/annual_volatility`. If evidence supports geometric Sharpe, change and label the convention consistently in both objective and reporting.

Include starting capital in drawdown:

```python
wealth = np.r_[1.0, np.cumprod(1.0 + portfolio_returns)]
maximum_drawdown = (1.0 - wealth / np.maximum.accumulate(wealth)).max()
```

For `[-0.10, 0.10]`, drawdown is 10%, not zero. Yield is `w @ yields`. Handle zero variance explicitly: minimum variance can validly be zero; Sharpe is undefined; ERC needs a documented zero-risk degeneracy response. Do not silently regularize covariance to hide a failure or alter the problem.

If evidence requires drift-and-rebalance returns, test rebalance timing and apply that model consistently to objectives and constraints. `w.T @ covariance @ w` and linear beta aggregation do not generally describe annually drifting portfolios. Do not change only displayed metrics and claim they explain the objective.

### Strategies, in the brief’s order

1. **Equal weights:** 1/n without a solver, followed by every constraint check. Reject incompatible constraints as `strategy_constraint_conflict`. Do not return a near-equal allocation or falsely declare all portfolios infeasible.
2. **Risk parity:** equalize fractional contributions `q_i = w_i*(Sigma @ w)_i/(w.T @ Sigma @ w)` by minimizing `sum((q_i-1/n)**2)`. Use scaled covariance, feasible starts and explicit zero-variance handling. Inverse volatility is a seed, not the general answer. Binding constraints may prevent exact ERC; report the residual. Verify on a correlated three-asset fixture as well as the mandated two-asset case.
3. **Minimum drawdown:** deterministic bounded multistart SLSQP, including feasible current/equal allocations and diverse feasible starts. The objective is nonsmooth and nonconvex; no global guarantee. Set starts/iterations from measured runtime, not an arbitrary minimum of 30. Independently compare to a dense two-asset grid and a feasible baseline. Report the best feasible converged candidate found. Investigate a failed quality check before adding bonus work.
4. **Minimum volatility:** minimize scaled/annualized `w.T @ Sigma @ w`, gradient `2*Sigma @ w`. With linear constraints this is convex; additional nonlinear constraints may change that guarantee. Verify against an analytic two-asset fixture and feasible baseline.
5. **Maximum Sharpe:** minimize negative Sharpe from a small deterministic set of feasible starts. Check objective quality and constraints independently. Analytic tangency weights apply only to an appropriate arithmetic, unconstrained fixture; they do not validate CAGR Sharpe, arbitrary bounds or annual drifting weights.

One candidate acceptance function checks finite complete weights, sum, bounds, every requested constraint, objective and successful relevant solver termination. Choose the best accepted candidate with deterministic tie-breaking. Preserve and compare a known feasible baseline; never silently return a worse or failed result as optimized. Record actual starts/iterations. Measure slowest required scenarios and bound work; do not invent latency claims or add distributed workers.

### Constraints

Validate `0 <= lower_i <= upper_i <= 1` and `sum(lower) <= 1 <= sum(upper)`. Bounds and dividend yield admit a small linear feasibility problem using HiGHS, or bounded greedy fill for maximum yield. This supplies an initial feasible point.

Under case 5 bounds, maximum workbook yield is **3.15355%**, at AGG 40%, IEFA 40%, VEA 10%, SPY 5%, GLD 5%. Thus the 2.50% floor is feasible. Compute the result from data in tests; do not hardcode a special case into the engine.

Residuals: `CAGR-min_cagr >= 0`, `vol-min_vol >= 0`, `max_vol-vol >= 0`, `drawdown_limit-MDD >= 0`. Reject reversed ranges and invalid domains. Joint nonlinear constraints require a bounded feasibility search; its failure is not a certificate of impossibility. Independently recheck final feasibility rather than relying only on solver callbacks. Avoid post-solve clipping/normalization that changes the constraints. Tolerances accommodate floating-point error, not meaningful violations.

## 8. Factor bonus

Fit `portfolio_return = alpha + b_mom*Momentum + b_value*Value + b_size*Size` on common portfolio/factor dates. Use `numpy.linalg.lstsq`, checking rank, sample size and finite coefficients. Never combine asset regressions fitted over different windows.

With constant weights and a shared design matrix, OLS is linear in the dependent variable: fit asset returns together, then multiply their beta matrix by portfolio weights. Verify this against direct regression of `R @ w`. Under only linear bounds/yield constraints, maximizing a beta or signed weighted factor objective is a linear program (`scipy.optimize.linprog`). Reuse nonlinear optimization only for nonlinear constraints. No repeated OLS is necessary inside every objective evaluation.

For case 6, assert increased momentum using unrounded betas and valid constraints; include both portfolios and a live comparison screenshot. Test an already-optimal synthetic portfolio: strict improvement is not always possible. Cover minimization and multi-factor targets. No usable factor overlap should clearly reject factor optimization while leaving ordinary strategies usable.

## 9. Verification that earns its time

Write tests alongside behavior, using independent expected results and actual HTTP serialization.

| Area | Coverage |
| --- | --- |
| Data | Dates, subset alignment, different starts, duplicate/missing dates, inline data actually used, no shared mutation |
| Metrics | Hand-calculated volatility/CAGR/yield; first-day loss; recovery/monotonic paths; zero variance |
| Equal/ERC | Equal baseline, incompatible constraints, single asset, two-asset ERC ratio, correlated three-asset contributions |
| Optimizers | Analytic two-asset minimum variance, independent drawdown grid, Sharpe quality, repeatability, feasible baseline |
| Constraints | Each portfolio constraint feasible; impossible bounds/yield; nonlinear conflict; failure is not false infeasibility |
| API | Field names and changes, supplied returns, unknown fields/tickers/strategies, nonfinite input, missing history, target validation |
| Serialization | Returned weights meet bounds/yield/sum; metrics reproduce from them; finite JSON |
| Failures | Mock nonconvergence, nonfinite or constraint-violating solver outputs; never return success |
| Factors | Known synthetic coefficients, direct versus aggregated regression, rank failure, common dates, case-6 improvement |
| Reference | Cases 1–5 against captured outputs; case 6 separately; held-out case if available |

Core tests must pass. The reference comparison command exits nonzero for missing evidence or out-of-tolerance gaps and prints explanations. Never silently skip, xfail, loosen or replace assertions to obtain a green demo. If live data prevents parity, show core tests and the honest comparison report separately.

Remove the 20,000-random-portfolios check from API requests. Random search can expose a poor solution, but cannot prove optimality. Optional offline sampling is justified only by an unresolved solver-quality concern; report feasible sample counts, tolerances and limitations. Analytic fixtures and small deterministic grids are more useful first checks.

## 10. Twelve-hour execution allocation

Read this against actual remaining time. Capture references alongside independent work when practical.

| Elapsed hours | Work and exit condition |
| --- | --- |
| 0–0.5 | Confirm clock/instructions, data audit, begin reference captures, environment and request fixtures |
| 0.5–1.5 | Loader, inline schema, metric tests, working equal-weight HTTP endpoint |
| 1.5–2.5 | ERC, shared feasibility and errors; compare cases 1–2 |
| 2.5–3.5 | Drawdown, first-day-loss and independent grid checks |
| 3.5–4.25 | Minimum volatility, analytic test and case 3 |
| 4.25–5.5 | Maximum Sharpe, cases 4–5 and bounded convention investigation |
| 5.5–6.5 | Nonlinear constraints, API edge cases, serialization and failure tests |
| 6.5–7.25 | Factor regression/optimization if the core works |
| 7.25–8.25 | Independent adversarial review, defect fixes and reference evidence |
| 8.25–9 | README, fresh-environment run, comparison report and measured runtime; freeze features |
| 9–10 | Actual response captures, API screenshots and submission blockers |
| 10–11.25 | Rehearse and record Loom |
| 11.25–12 | Verify public repo, video and evidence links; final review and submission |

If behind, cut optional endpoints, broad calibration, CI and benchmark polish before mandatory input support, strategies, constraint validity or evidence. Full bonus is the target; omit it honestly if core correctness needs the time. Never advertise unimplemented constraints. Hour 9 freezes new features; it does not prohibit correcting a real blocker.

## 11. README and Loom

Start with what the API does, followed by measured evidence once available. Example structure: “Five portfolio optimization strategies using supplied fund data, request-supplied returns and portfolio constraints.” Then “Cases 1–5: [measured count]/5 within 0.1 percentage points; deviations below.” State bonus results separately. No placeholders or unverified claims in the delivered README.

Include tested setup, one useful request, units/strategies/constraints, test commands, compact comparison table linked to every case artifact, methodology and actual limitations. Put long responses in example files. Attribute sources and assistance according to company rules. Do not copy another candidate’s code or presentation.

Suggested four-minute recording in Ashraf’s own words:

- 0:00–0:25: Inputs, supported behavior and actual validation result, including any gap.
- 0:25–1:15: Run a constrained request; show weights, yield and bounds together.
- 1:15–2:00: Explain one short request-to-validation-to-solver code path, common dates and units.
- 2:00–2:45: Tests and reference comparison, including dedicated drawdown coverage.
- 2:45–3:15: Infeasible request and supplied-return support.
- 3:15–4:00: Factor improvement if complete, numerical/data limitations and useful next improvement.

Avoid a folder tour and do not claim the tool’s “true” risk-free rate was identified from a few weights. Ashraf should be able to explain date intersection, ERC versus inverse volatility, arithmetic/geometric Sharpe, starting-capital drawdown, feasibility, local/global optima and regression without reading a script.

## 12. Final adversarial gate

Review the finished work and reread the assignment:

- Fresh checkout installs/runs exactly as documented, without local paths or undeclared packages.
- All five strategies and advertised constraints work on real and synthetic inputs.
- Supplied returns visibly affect calculations.
- Serialized weights, metrics and constraints agree.
- Every required case has actual API JSON and a genuine live screenshot; bonus case included if attempted.
- At least three strategies have screenshots of the running API.
- Core tests pass; reference discrepancies and missing evidence remain visible.
- Every numerical claim has a reproducible command or artifact.
- Loom is 3–5 minutes, with code, working API and explained decisions/shortcuts.
- Public repository and video links work; no secrets, caches, environment or unrelated internal notes.
- Deadline and actual submission channel are satisfied. Do not assume the clarification email is the submission destination.
- Ashraf can defend the decisions and limitations in discussion.

Ask: “What credible reason remains for a senior reviewer to choose another candidate?” Fix missing behavior, invalid constraints, unexplained discrepancies, unreproducible setup or weak understanding before cosmetic polish. Iterate while an improvement justifies its remaining time and risk.

## 13. Sources and research boundaries

The supplied DOCX is authoritative; workbook facts above were directly inspected. The [public reference page](https://finominal.com/portfolio-optimizer/US) shows annual rebalancing but does not establish optimizer conventions. Live scenario outputs still need capture.

The [public prior submission README](https://github.com/Zyrexam/Finominal-Portfolio-Optimizer-engine) self-reports a Sharpe discrepancy and a yield-data mismatch. These are failure hypotheses, not verified reference results, proof of hiring success or evidence about the candidate pool. Its implementation was not used. Winner-history and product idea selection are inapplicable to this fixed take-home; no documented winning submission was established.

Method references: [SciPy SLSQP](https://docs.scipy.org/doc/scipy/reference/optimize.minimize-slsqp.html), [SciPy linear programming](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linprog.html), [NumPy least squares](https://numpy.org/doc/stable/reference/generated/numpy.linalg.lstsq.html). They support method use and termination/rank checks, not a guarantee of reference parity. Verify installed versions during implementation.
