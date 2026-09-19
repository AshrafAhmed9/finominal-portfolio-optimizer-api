# Submission review and remediation instructions

**Verdict: BLOCK — fix the demonstrated correctness defects before treating this as ready to submit.**

Reviewed 2026-09-19 at commit `c9bdb8864d809491d97eb14db91ff479730af88d`. This supersedes the earlier **plan-level** clearance in `PLAN_REVIEW.md`; a sound plan did not establish implementation correctness. This review changes no application code.

The implementation has a useful foundation, but 71 passing tests miss valid-request crashes and silently ignored constraints. The missing live-tool comparisons are a separate external-access/evidence issue, not proof that the mathematical engine is wrong.

## Instructions for the implementing agent

1. Read the assignment DOCX, this report, and the affected code. The assignment is authoritative; do not blindly implement everything in the old plan.
2. Reproduce each finding, make the smallest correction, and add its regression tests. Preserve the small architecture and existing response shape. No rewrite, new infrastructure, frontend or broad dependency churn.
3. Work in the order below. Reference access and recording can progress independently of code fixes.
4. Re-run the core tests, all six scenario requests, and genuine reference comparisons if available. Regenerate affected responses/screenshots after behavior changes.
5. Update this report or an accompanying checklist with actual commands/results. Do not label a task complete because code was written without its acceptance check.
6. Do not fabricate reference weights/screenshots, silently weaken assertions, fit separate settings per case, or describe internal tests as a substitute satisfying the reference requirement. Do not send email or other external messages without Ashraf's authorization.

## Evidence collected

| Check | Observed result |
| --- | --- |
| Existing environment, `.venv/bin/python -m pytest -q` | **71 passed, 1 skipped**, 2 deprecation warnings, 13.65s |
| Fresh Python 3.12 environment installed from `requirements.txt`, clean `git archive HEAD` checkout | Installation succeeds; **71 passed, 1 skipped**, 21.93s |
| `pip check` | No broken requirements |
| Real Uvicorn process from clean checkout | `/health` and case-5 HTTP request succeed |
| Six assignment scenario requests through TestClient | All return 200; this does **not** establish live-tool parity |
| `python scripts/compare_reference.py` | Exit 1: missing `tests/golden/scenarios.json` |
| Public GitHub repository | Exists and is public; remote HEAD equals reviewed commit |
| Screenshot inspection | Actual Swagger responses for equal weights, constrained Sharpe and factor exposure exist |
| Actual Loom recording | No recording URL found in repository; scripts exist. Recording may have been shared separately, so verify rather than assume absent |
| Independent adversarial requests | Confirmed constraint bypass, valid-request crashes, invalid-date handling and nonfinite-input defects below |

Public repository: [finominal-portfolio-optimizer-api](https://github.com/AshrafAhmed9/finominal-portfolio-optimizer-api).

## Priority order

| ID | Severity | Task | Exit condition |
| --- | --- | --- | --- |
| R1 | CRITICAL | Enforce all constraints for factor optimization | No successful response violates an accepted constraint; feasible constrained factor cases work |
| R2 | WARNING | Fix single-asset and fully fixed-weight crashes | Valid unique allocations work across strategies; invalid ones return structured errors |
| R3 | WARNING | Reject unknown fields and all nonfinite numeric inputs | Malformed/ignored risk limits cannot return success |
| R4 | WARNING | Validate calendar dates before pandas parsing | Bad dates and duplicate normalized dates return structured 422 |
| R5 | WARNING | Repair reference validator and bonus semantics | Empty/partial evidence cannot pass; case 6 is not gated on live weight parity |
| R6 | CRITICAL evidence gap | Complete required scenario artifacts and resolve/reference access status | Required comparisons captured, or unresolved blocker explicitly acknowledged; never a false match claim |
| R7 | WARNING | Repair misleading tests and solver error semantics | Meaningful independent assertions and failure-path coverage |
| R8 | WARNING | Handle constant-return numerical degeneracy | Undefined Sharpe cannot become an enormous claimed finite result |
| R9 | WARNING / NOTE | Correct README, recording claims and final packaging | Claims reflect measured behavior and delivered artifacts |
| R10 | NOTE | Correct redundant starts and solver bookkeeping | Reported work matches actual work; distinct starts where claimed |

## R1 — Factor optimization silently ignores nonlinear portfolio constraints

**Locations:** `app/main.py:177–197`, `app/factors.py:86–140`. The call passes only `limits.min_dividend_yield`, discarding `min_cagr`, `max_drawdown_limit`, and both volatility limits. There is no final common feasibility check before response construction at `app/main.py:201`.

**Reproduction:** POST this to `/optimize`:

```json
{
  "securities": [{"ticker":"SPY","weight":50},{"ticker":"AGG","weight":50}],
  "strategy": "optimize_factor_exposure",
  "factor_targets": [{"factor":"momentum","direction":"maximize"}],
  "constraints": {"volatility_range":{"max":10}}
}
```

**Actual:** HTTP 200, SPY 100%, reported annual volatility `0.18606772987937356` = **18.6068%**, above the requested 10%. This is not an impossible request: the same pair's minimum-volatility allocation has **4.9835%** volatility and is a feasible witness.

Replacing constraints with `{"max_drawdown":20}` also returns 200 with **55.2012% drawdown**; `{"min_cagr":50}` returns 200 with **11.3293% CAGR**. These are accepted, advertised constraints, not unknown fields.

**Smallest complete correction:**

- Pass the complete `PortfolioLimits` to factor optimization.
- Keep the existing linear program when all active constraints are linear. When nonlinear limits are present, optimize the already-linear beta objective through the shared constrained nonlinear solver.
- Use one final allocation validator for **every** strategy, including the LP path: finite weights, sum, bounds and every requested limit. Independently recompute the metrics on the actual returned allocation.
- Do not only reject an invalid unconstrained LP result: that would reject requests with a feasible constrained optimum. Explicit rejection of unsupported combinations is a safer temporary fallback than silent ignoring, but does not complete advertised constraint support.

**Acceptance tests:** feasible binding and impossible requests for minimum CAGR, maximum drawdown, volatility minimum and maximum on factor strategy; include a combination with bounds/yield. Assert independently recomputed output metrics meet each requested limit. Unconstrained case 6 must continue to improve momentum.

## R2 — Ordinary valid allocation cases crash

### R2a: Fully fixed weights

**Location:** `app/optimize.py:143` assumes `result.nit` exists.

```json
{
  "securities": [{"ticker":"SPY","weight":50},{"ticker":"AGG","weight":50}],
  "strategy": "minimize_volatility",
  "constraints": {"min_weight":50,"max_weight":50}
}
```

**Actual:** HTTP 500, `AttributeError: nit`. Reproduced for `risk_parity`, `maximize_sharpe`, and `minimize_drawdown` too. SciPy's all-variables-fixed result does not carry the assumed iteration field.

**Fix:** handle a uniquely fixed allocation explicitly, validate all constraints, and return that allocation with honest fixed-solution metadata. Read optional solver metadata defensively, e.g. `getattr(result, "nit", 0)`. A fixed allocation violating a portfolio limit must return a specific structured error, not an internal crash.

### R2b: One requested security

**Locations:** `app/metrics.py:104–106`, `app/optimize.py:209` and `:223`.

```json
{"securities":[{"ticker":"SPY","weight":100}],"strategy":"minimize_volatility"}
```

**Actual:** HTTP 500. `risk_parity` also crashes. `np.cov` returns a scalar for a single return column; matrix multiplication/diagonal extraction expects a matrix.

**Fix:** guarantee covariance shape `(n_assets, n_assets)`, including `(1,1)` using `np.atleast_2d`, and handle the sole feasible 100% allocation consistently after validating bounds/limits. A one-asset Sharpe with zero variance needs the explicit undefined-objective policy, not automatic success.

**Acceptance:** parameterize one-asset requests and fixed allocations across all strategies. Check feasible outputs and conflicting-limit errors. The current single-security test covers only `equal_weights`, so it misses both crashes.

## R3 — Nonfinite inputs and unknown fields bypass validation

**Locations:** request models in `app/schemas.py`, especially `Constraints:52–59`, `FactorTarget:67–70`. Only inline `total_return` explicitly rejects nonfinite values; Pydantic's default extra-field handling silently ignores typos.

With `SPY:100` and `strategy:equal_weights`:

| Constraint input | Actual result |
| --- | --- |
| `{"min_cagr":"NaN"}` | 200; NaN comparisons bypass the constraint |
| `{"max_drawdown":"Infinity"}` | 200 |
| `{"max_volatility":0}` | 200; unknown field silently ignored |

These string values are **valid JSON**; this is not limited to nonstandard JSON NaN literals. Factor target `importance:"Infinity"` produces a plain 500.

**Fix:** introduce a small shared request-model base with `ConfigDict(extra="forbid", allow_inf_nan=False)` and make **every nested request model** inherit it. Preserve the existing useful field limits. Validate per-security keys after normalization so conflicting keys such as `SPY`/`spy` cannot silently overwrite one another. No blanket `strict=True` is necessary merely to fix these issues.

**Acceptance:** structured 422 for NaN/Infinity strings and raw nonstandard nonfinite values at numeric boundaries, and extra fields at top level, security, return, constraints, per-security bound, volatility-range and factor-target levels. Valid documented examples still work.

## R4 — Invalid and duplicate calendar dates reach the numerical pipeline

**Locations:** `app/schemas.py:26–28`, `:94–99`, `app/main.py:118–125`. Dates are arbitrary strings; duplicate detection precedes normalization; pandas parsing exceptions are not translated.

Use `equal_weights`, one `SPY:100` security, and two supplied returns `.01` and `-.01`:

| Dates | Actual result |
| --- | --- |
| `garbage`, `2020-01-03` | Plain-text 500 |
| `NaT`, `2020-01-03` | 200; invalid date counted as an observation |
| empty string, `2020-01-03` | 200; blank date counted |
| `2020-1-3`, `2020-01-03` | 200; same date counted twice; start=end with two observations |
| `2020-01-03`, `2020-01-03T00:00:00Z` | Plain-text 500 |

**Fix:** validate a calendar-date-only input contract at the schema boundary. Require ISO `YYYY-MM-DD` if that is the documented contract. Reject missing/invalid dates and either reject noncanonical forms or normalize before duplicate checks. Construct pandas series only from validated dates. Do not allow a `NaT` index into alignment.

**Acceptance:** the above cases produce structured 422; a valid unsorted series is sorted and aligned correctly; genuinely nonoverlapping series return a data error. Duplicates must not become extra return observations.

## R5 — The reference harness can issue a false PASS and contradicts bonus rules

**Locations:** `scripts/compare_reference.py:31–63`, `tests/test_reference.py:25–38`, `tests/golden/scenarios.template.json`, `tests/golden/README.md:15`.

Reproduced with isolated temporary fixtures, without changing repository evidence:

- `[]` prints `PASS: all 0 cases within tolerance.` and exits 0.
- Only case 1 with `expected_weights:{"IEFA":50}` exits 0, omitting SPY and required cases 2–5.
- The template's case-6 null expected values raise `TypeError` during subtraction.
- Both CLI and pytest enforce case-6 weight parity when values are populated, although the assignment explicitly exempts that case. The script's docstring claims separate bonus/constraint handling that the implementation does not perform.

**Fix:**

1. Share a small fixture-validation/comparison helper between CLI and pytest.
2. Require exactly one of each mandatory case ID 1–5, matching the specified requests; reject missing/duplicate cases. Require case-6 evidence when claiming the bonus, but evaluate it separately.
3. Validate full expected ticker sets, finite numeric allocations, allocation sums and justified tolerance (do not permit widening beyond the assignment's interpreted 0.1 percentage points). Check referenced screenshots exist. Missing or malformed fixtures must produce a readable nonzero result.
4. Check cases 1–5 per ticker. For case 6, validate beta fields, momentum improvement and all allocation constraints; live-tool weights may be shown as informal comparison, never required equality.
5. Validate output sum, nonnegative weights and case-5 constraints in the comparison report itself.
6. Correct the golden README's equal-weight expected example from 25/75 to 50/50. Keep placeholders unmistakably unfilled.

**Acceptance:** tests for missing file, empty list, missing case, duplicate ID, missing ticker, null/nonfinite values, missing screenshot and malformed fixture; none can produce overall PASS. A case-6 weight difference with valid improved momentum does not fail the bonus check. Run `pytest -q -rs` so missing-reference skips are visible. It is reasonable to separate reference tests from core tests; the submission gate must still fail on missing required evidence.

## R6 — Required evidence is incomplete

**Severity:** CRITICAL to declaring the submission complete, with an external-access dependency.

The assignment asks for each required scenario's **API response plus live-tool screenshot**, separately from screenshots of the API running for at least three strategies.

What exists:

- Actual local API JSON for cases **1, 2, 3, 5, 6** in `docs/reference/`.
- Actual Swagger screenshots for three strategies. This requirement has useful evidence already.
- A public repository. Do not recreate it.

What remains:

- **Case 4 API response** is missing and can be captured without live-tool access.
- No genuine live-tool comparison screenshots/weights are present. `tests/golden/scenarios.json` is absent.
- No actual Loom URL is present in the repo. Verify whether it has already been recorded/shared separately.

**Actions:**

- Save all six exact request/response pairs from the corrected running app. Distinguish local API responses from external reference outputs in names or an index; `live_case_*` currently means local live API, not reference-tool output.
- If access becomes available, capture all required live cases/settings/timestamps and case-6 Comparison. Complete R5, run the comparisons and report measured gaps.
- If signup remains blocked, preserve honest unverified status and document the access failure. Ask Ashraf to obtain access or authorize a clarification message through the known company contact if appropriate. Do not pretend tests satisfy the missing requirement, repeatedly create accounts, or fabricate captures. Continue all independent fixes.
- Check the actual 3–5 minute video link and permissions before submission. A script is not the deliverable.
- Use the company-provided submission channel; the assignment identifies an email for questions, not unambiguously the submission destination.

**Acceptance:** complete local request/response artifacts, actual reference comparisons or explicit unresolved access status, three-strategy API screenshots, and a verified recording/public-repo link. Without reference evidence, label the final state “core checked; reference comparison blocked,” not “fully verified.”

## R7 — Strengthen tests and distinguish solver failure from proven infeasibility

The suite contains useful tests, but several names/claims exceed their assertions:

- `tests/test_api.py:138`, `test_response_metrics_recompute_from_serialized_weights`, only checks the sum. It recomputes no metric.
- `tests/test_optimizers.py:45–53` uses the zero-covariance minimum-variance formula on a random sample whose empirical covariance is nonzero. A wide `.01` weight tolerance hides the discrepancy.
- `tests/test_constraints.py:85–91`, named as a solver-feasibility-failure check, never invokes or mocks a failing solver.
- `tests/test_factors.py:95–97` asserts the number of positive weights is no greater than the number of assets, which is always true and does not establish LP quality.
- `app/optimize.py:159–165` raises `ConstraintError` when every numerical attempt fails. `app/main.py:66–71` maps it to `infeasible_or_invalid_constraint` 422. The message acknowledges uncertainty, but the type/status still conflates solver failure with invalid constraints.

**Corrections:**

1. Recompute current and optimized metrics from returned weights and an independent small inline fixture; assert each reported metric, not just the sum.
2. For two assets use the exact sample-covariance solution `w_a=(var_b-cov_ab)/(var_a+var_b-2*cov_ab)`, clipped to the feasible interval. Use a nonzero-correlation case and justified numerical tolerance.
3. For unconstrained single-factor LP, compare achieved beta to the maximum available asset beta; test minimization, weighted multi-factor targets and binding constraints.
4. Introduce a separate numerical failure type/code (e.g. structured 500 `optimization_failed`) when a known-feasible problem has no accepted solver result. Keep 422 for validation, certified infeasibility and explicit strategy conflicts. Never call local search failure proof of impossibility.
5. Mock solver outputs to cover nonconvergence, missing optional metadata, nonfinite objectives/weights and constraint violations. No failed or invalid candidate may become a 200 response.
6. Reject nonfinite objective/constraint evaluations explicitly; NaN comparisons must not count as feasible. Use consistent documented tolerances for actual output checks, rather than loose tests that can mask a violation.

**Acceptance:** tests fail on the current defects and pass after correction. Do not add tests just to inflate the test count. Update README claims to match what is actually independently checked.

## R8 — Constant-return Sharpe can become a huge artificial value

**Location:** `app/metrics.py:51–54` uses `vol == 0.0`.

```python
sharpe_ratio(np.full(3, 0.01))   # None
sharpe_ratio(np.full(10, 0.01))  # 8.681430029724637e16
```

The mathematically constant stream is treated differently because floating-point standard deviation can be tiny rather than exactly zero. This violates the documented undefined-zero-variance policy and can distort Sharpe optimization on supplied data.

**Fix:** use a carefully justified constant/near-zero-risk check relative to numerical scale. Do not choose a broad arbitrary volatility cutoff that discards genuinely low but nonzero risk. Handle undefined-objective optimization explicitly rather than reporting a penalty-minimization result as a meaningful Sharpe optimum. Avoid inverse-volatility division by zero when constructing ERC seeds.

**Acceptance:** zero, positive-constant and negative-constant series behave consistently at multiple sample lengths; genuinely low but nonconstant variance still yields a valid ratio. API behavior is documented and structured when no meaningful Sharpe objective exists.

## R9 — Correct documentation, recording claims and artifact presentation

Make these edits after behavior stabilizes:

1. **Risk-parity explanation:** `README.md:179–184` and `docs/LOOM_TALKING_POINTS.md:67–68` incorrectly say two-asset ERC equals inverse volatility only with zero correlation. For two assets with positive volatility and positive portfolio variance, covariance cross terms cancel, giving `w1*sigma1 = w2*sigma2`; zero correlation is not required. Exclude a zero-variance portfolio at perfect anticorrelation, where fractional contributions are undefined. Say it generally differs for correlated portfolios with three or more assets. Uncorrelated multiasset ERC is another inverse-volatility case.
2. **Overclaims:** remove “every strategy's output independently re-verified” unless the tests actually provide that evidence. `docs/LOOM_SCRIPT.md:34` claims all strategies honor all constraints; it is false until R1 is fixed. Replace “no code changes needed” for reference capture until R5 is corrected. Do not describe local-search failure as a proof of infeasibility.
3. **Status:** `NEXT_STEPS.md` incorrectly says everything buildable is done, nothing else needs changing, and the public repo/screenshots still need creation. Replace with a current checklist. Preserve candid reference limitations, but do not claim they are the only remaining issue before fixes land.
4. **Units:** document that response `optimized_weight/current_weight/change` are percentages while `meta.metrics` CAGR/volatility/drawdown/yield and `/securities` yield are decimal fractions. Input limits are percentages. This existing mixed representation can remain if clearly documented; no broad response redesign is needed.
5. **Factor sample:** report or document the separate regression window ending 2026-05-22; current `meta.date_range` ends 2026-05-27 and describes portfolio metrics, not the regression sample. Prefer a small `meta.factor_date_range` with observations when returning betas.
6. **Screenshots:** the case-5 response screenshot cuts off before VEA/SPY and the yield metric, although surrounding text claims those binding values are demonstrated. Add a second real capture of the lower response or an easily readable genuine response artifact. Keep full-precision API numbers; do not solve presentation by rounding away binding-constraint correctness.
7. **Recording:** update counts/numbers only after the final test run. Mention the skipped reference check explicitly if still unresolved. Retain the actual code-path walkthrough and limitations. Add the real Loom link to the delivery checklist when available.
8. **Navigation:** put quickstart and a compact measured-status table before the large screenshot gallery. Link full evidence instead of making setup require scrolling through many large images. This is lower priority than correctness.

**Acceptance:** README, examples, screenshots and spoken claims all describe the same corrected commit. No statement that parity is measured unless actual reference evidence exists. Technical explanations are defensible in an interview.

## R10 — Small solver-quality/bookkeeping cleanup

**Locations:** `app/optimize.py:42–49`, `:143–158`.

The “corner” loop never uses `i`, so it generates the same point repeatedly (for two unbounded assets, the first three starts are all `[0.5,0.5]`). `iterations` is stored when the current best candidate is found and omits work done afterward.

Generate actual distinct feasible boundary starts or remove duplicates; keep the deterministic seed. Include a known feasible baseline when available and check the returned objective against it. Assign total iterations after the entire search, or label winner-only iteration metadata accurately. Do not add a larger random-search budget merely to hide repeated starts.

This is lower priority than R1–R8. Verify meaningful start coverage and bookkeeping with a small controlled solver fixture if changing the code.

## What should be preserved

- Small, readable modules; no unnecessary services or frontend.
- Supplied-return support and per-request common-date alignment.
- Initial-capital drawdown calculation.
- Explicit arithmetic Sharpe and risk-free-rate assumptions; do not arbitrarily change them without reference evidence.
- Dividend-yield linear feasibility check and documented GLD assumption.
- Factor regression linearity and LP for genuinely linear constraints.
- Real API screenshots, pinned working environment and candid missing-reference status.
- Existing useful analytic, synthetic-regression and drawdown-grid tests, improved where identified above.

## Final verification checklist

- [ ] R1–R4 reproductions now produce valid constrained results or structured errors, never ignored limits/plain 500s.
- [ ] Single-asset, fixed-weight and numerical-degeneracy cases covered across applicable strategies.
- [ ] R5 harness tests reject empty/incomplete evidence and evaluate factor bonus correctly.
- [ ] Tests strengthened per R7; no acceptance criterion was loosened to hide a failure.
- [ ] `python -m pytest -q -rs` passes core tests and clearly reports reference status.
- [ ] Clean checkout/environment installs and runs the documented HTTP examples.
- [ ] All six exact scenario request/response pairs saved, including missing case 4.
- [ ] `python scripts/compare_reference.py` reports genuine comparisons, or exits nonzero with the external evidence blocker visibly documented.
- [ ] At least three readable API-strategy screenshots; actual reference screenshots separately identified.
- [ ] README and Loom statements updated to corrected behavior, true test results and units.
- [ ] Actual 3–5 minute recording and public repository accessible from the delivery links.
- [ ] No unsupported claim of exact parity, global optimality, or guaranteed hiring outcome.

**Final assessment:** targeted fixes can materially improve this submission. The strongest remaining reason to select another candidate is not lack of features; it is that an accepted risk constraint can be ignored while the API returns success, and the present evidence checks do not reliably detect that. Fix those failures and complete the required evidence before cosmetic work.

---

## Remediation applied (2026-09-19, commits c8d196f through 43fe482)

Every R1-R10 finding above was reproduced first, then fixed, then covered
by a new regression test named for the specific defect. Test count went
71 -> 125 (99 after R1-R5, 114 after R8, 123 after R7, 125 after R10).
Verified clean at each step with a fresh Python 3.12 venv, `pip install -r
requirements.txt` only, and (for the final pass) a real HTTP round-trip
against a freshly booted server, not just TestClient.

| Finding | Status | Where |
| --- | --- | --- |
| R1 (constraint bypass, CRITICAL) | Fixed | `app/factors.py` routes through the shared constrained solver whenever a nonlinear limit is set; one final shared feasibility check on every path, including the LP path |
| R2a (fully-fixed-weights crash) | Fixed | `getattr(result, "nit", 0)` in `app/optimize.py` |
| R2b (single-asset covariance crash) | Fixed | `np.atleast_2d` in `app/metrics.py::covariance_matrix` |
| R3 (nonfinite/unknown-field bypass) | Fixed | `StrictModel` base (`extra="forbid"`, `allow_inf_nan=False`) across every request schema; per-security key collision check |
| R4 (invalid/duplicate dates) | Fixed | strict `YYYY-MM-DD` validator on `InlineReturn.date` before pandas ever sees it |
| R5 (harness false-PASS bugs) | Fixed | `scripts/reference_fixtures.py`, one shared validation module for both the CLI script and pytest; 12 dedicated unit tests |
| R6 (incomplete evidence) | Fixed except the live-tool capture itself | case 4 captured, all six unambiguously renamed `local_case_0N_*`; live-tool capture remains blocked by the account-creation error, documented as such throughout |
| R7 (weak tests, conflated failure semantics) | Fixed | 4 named tests strengthened; new `OptimizationFailedError` (500) distinct from `ConstraintError` (422); found and fixed an additional bug while mocking failures (`np.clip` laundering a nonfinite/wildly-out-of-bounds "success" into a false-valid weight vector) |
| R8 (Sharpe degeneracy) | Fixed | scale-aware near-zero-variance check in `sharpe_ratio`; ERC seed's `1/sqrt(variance)` guarded against a zero-variance asset |
| R9 (documentation corrections) | Fixed | risk-parity claim corrected (and the fix verified by strengthening its test to a nonzero-correlation case, not just asserted in prose); overclaims removed; units table added; `meta.factor_date_range` added and documented; stale counts updated throughout; `NEXT_STEPS.md` rewritten to match reality |
| R10 (solver bookkeeping) | Fixed | genuinely distinct multi-start corners; iteration count reflects the full search, not just the winning candidate's position in it |

Not done, and out of this agent's control: the live-tool reference capture
itself (account creation on finominal.com fails with a generic client-side
error) and the actual Loom recording. Both are documented as open items in
`NEXT_STEPS.md`.
