# Loom recording script

One file: what to say, what's on screen, and the caption track. Total runtime
target is 4:00-4:15. Read the script in your own voice, it's written to be
spoken, not read verbatim like a robot, so if a line doesn't feel like you,
say it your way. The numbers and facts in it are all pulled straight from
your actual test run and API responses; don't improvise different ones on
camera.

Before recording: have `uvicorn app.main:app --reload` running, the Swagger
UI open at `/docs`, a terminal with the repo open, and `examples/case_05_constrained_sharpe.json`
and the case 6 body from `screenshots/04a_case6_factor_exposure_request.png`
ready to paste.

---

## 0:00-0:15 - Open with the honest headline

**Say:**
> "Hey, I'm Ashraf. This is my submission for the Finominal backend take-home, a REST API that replicates their portfolio optimizer. Five required strategies, plus the factor-exposure bonus. One thing up front: I couldn't validate against your live tool because account creation kept failing on my end, so I'll show you what I used instead."

**Screen:**
- 0:00-0:08 - Your face on camera, or the repo's GitHub page open (`https://github.com/AshrafAhmed9/finominal-portfolio-optimizer-api`) as a static opening shot.
- 0:08-0:15 - Cut to the README, scrolled to the top "Reference match status" paragraph.

**Caption:**
> Finominal Portfolio Optimizer API: take-home submission walkthrough.

---

## 0:15-0:45 - What's built, in one breath

**Say:**
> "It's a FastAPI app: equal weights, risk parity, minimize drawdown, minimize volatility, maximize Sharpe, and factor exposure for the bonus. Every strategy takes bounds, dividend yield floors, CAGR and drawdown limits, and a volatility range. All of it's covered by 71 tests, and I'll show a few of those running live."

**Screen:**
- Terminal, `tree app/` or a quick scroll through the `app/` folder in an editor, just enough to show the module layout (`data.py`, `metrics.py`, `constraints.py`, `optimize.py`, `factors.py`, `main.py`), not a slow read-through.

**Caption:**
> 5 required strategies + factor-exposure bonus. 71 passing tests.

---

## 0:45-1:45 - Live constrained request (case 5)

**Say:**
> "Here's a live one: five funds, equal-weighted to start, maximizing Sharpe with a 2.5% minimum dividend yield and each position capped between 5 and 40 percent."
>
> *(after clicking Execute)*
>
> "So the optimizer pushes AGG up to the 40% ceiling, pulls VEA down to the 5% floor, and the achieved yield lands at exactly 2.5%, the constraint's actually binding, not just technically satisfied. Sharpe goes from 0.82 to 0.90, volatility drops from about 11% to 9%."

**Screen:**
- 0:45-1:00 - Swagger UI, `POST /optimize` expanded, paste the case 5 request body.
- 1:00-1:05 - Click Execute.
- 1:05-1:45 - Response body on screen, scroll slowly so `allocation_changes` and `meta.metrics` are both readable. Optionally circle or point at VEA (5.0) and AGG (40.0) and the `dividend_yield: 0.025` line if your recording tool supports annotation, otherwise just pause the scroll there for a beat.

**Caption:**
> Case 5: maximize Sharpe, min yield 2.5%, weights bounded 5-40%.
> Constraints hit exactly, not just satisfied. Binding.

---

## 1:45-2:30 - One code path, briefly

**Say:**
> "Quickly, how a request actually flows: it comes into `/optimize`, gets checked against the known tickers, then the return histories get lined up on their common date range. That matters because IEFA only goes back to 2012 while SPY goes back to '93, so which funds you ask for changes how much history you're working with. After that it's a feasibility check on the bounds, then the strategy runs, and the response comes back with the weights plus a `meta` block: date range used, the conventions applied, and the solver's status. None of it's a black box."

**Screen:**
- Editor open to `app/main.py`, scrolled to the `/optimize` function. Scroll through it at a pace that roughly matches the narration, don't linger on every line, just let it track past as you talk about the shape of it.

**Caption:**
> Request, validation, date alignment, feasibility check, strategy, response.

---

## 2:30-3:05 - Tests, live

**Say:**
> "Here's the test suite running: 71 passing. A few of these are worth calling out. This one's a closed-form two-asset minimum-variance check, so it's not just 'the code runs,' it's checked against a known correct answer. Same idea for risk parity: there's a case where it should mathematically reduce to inverse-volatility weighting, and it does. And this one fits the factor regression against returns I generated from betas I already know, just to confirm it actually recovers them."

**Screen:**
- Terminal: run `pytest -q`, let it finish and show `71 passed, 1 skipped`.
- Cut briefly to `tests/test_optimizers.py`, scrolled to `test_min_volatility_matches_analytic_two_asset_solution` and `test_risk_parity_two_asset_equals_inverse_volatility`.

**Caption:**
> 71 tests: analytic fixtures, not just "it runs."
> Includes closed-form checks and a synthetic-coefficient recovery test.

---

## 3:05-3:35 - Infeasible request, handled properly

**Say:**
> "One more thing I wanted to show: what happens when a constraint can't be met. If I ask for a 50% minimum dividend yield, the API doesn't just fail silently or return garbage weights. It tells you the actual maximum achievable yield under your bounds, so you know exactly why it failed."

**Screen:**
- Swagger UI, `POST /optimize` with `{"securities":[{"ticker":"SPY","weight":50},{"ticker":"AGG","weight":50}],"strategy":"maximize_sharpe","constraints":{"min_dividend_yield":50}}`. Execute, show the 422 response with the specific error message.

**Caption:**
> Infeasible constraints return a specific reason, not a generic failure.

---

## 3:35-3:55 - The bonus: factor exposure

**Say:**
> "For the bonus, maximizing momentum exposure, the optimized portfolio's momentum beta goes from 0.13 to 0.19 compared to the current equal-weight portfolio. The assignment's clear that this case doesn't need to match your live tool's exact weights, since it only uses three factors against your broader model. The bar here is that the exposure actually increases, and it does."

**Screen:**
- Case 6 response already on screen (or re-run it live), scrolled to the `factor_betas` block.

**Caption:**
> Bonus: factor exposure. Momentum beta 0.13 to 0.19.

---

## 3:55-4:15 - Honest limitations, close

**Say:**
> "Two things I'd flag. One, the risk-free rate is a stated default of zero percent. The assignment allows that, but I didn't get to test it against your actual tool's convention. Two, minimize drawdown is a non-convex problem, so there's no global-optimum guarantee. I cross-checked it against a grid search on a synthetic case, but a full global search was out of scope for the time I had. That's it, thanks for reading this far, and I'm around if you've got questions."

**Screen:**
- Back to README, scrolled to "Known limitations."

**Caption:**
> Known limitations, stated plainly. See README for details.

---

## Full caption track (paste-ready, in order)

```
Finominal Portfolio Optimizer API: take-home submission walkthrough.
5 required strategies + factor-exposure bonus. 71 passing tests.
Case 5: maximize Sharpe, min yield 2.5%, weights bounded 5-40%.
Constraints hit exactly, not just satisfied. Binding.
Request, validation, date alignment, feasibility check, strategy, response.
71 tests: analytic fixtures, not just "it runs."
Includes closed-form checks and a synthetic-coefficient recovery test.
Infeasible constraints return a specific reason, not a generic failure.
Bonus: factor exposure. Momentum beta 0.13 to 0.19.
Known limitations, stated plainly. See README for details.
```
