# Loom talking points (outline, not a script — say it in your own words)

Target: 3-5 minutes. Structure follows `IMPLEMENTATION_PLAN.md` §11.

## 0:00–0:25 — What it does, and the honest headline
- "REST API replicating Finominal's portfolio optimizer: 5 required strategies
  plus the factor-exposure bonus."
- State the actual measured result once you've run `scripts/compare_reference.py`
  — e.g. "N of 5 required cases matched the live tool within 0.1 points; here's
  the one that didn't and why." **Do not claim a number you haven't measured.**

## 0:25–1:15 — Live constrained request
- Run case 5 (`examples/case_05_constrained_sharpe.json`) against the running
  API. Point out in the response: the weights, the achieved dividend yield
  sitting right at the 2.5% floor, and that all weights are within 5–40%.

## 1:15–2:00 — One code path, briefly
- Walk `/optimize` in `app/main.py`: request → ticker validation → date
  alignment (`app/data.py` — mention IEFA vs SPY's very different histories
  and why that matters) → bounds/feasibility check → strategy dispatch →
  response. Keep it to the shape of the pipeline, not a line-by-line read.
- Mention units convention: percentages at the API boundary, fractions
  internally — this trips people up if unstated.

## 2:00–2:45 — Tests and reference comparison
- Run `pytest -q` live, show it green.
- Run `python scripts/compare_reference.py`, show the actual comparison
  table. If any case is out of tolerance, say so and give your best
  explanation (data snapshot vs. live tool, a convention difference, etc.)
  rather than hiding it.
- Mention the dedicated `minimize_drawdown` correctness check (dense grid
  cross-check on a synthetic two-asset fixture) since there's no required
  scenario that exercises it directly.

## 2:45–3:15 — Infeasible request + supplied returns
- Hit an infeasible constraint (e.g. `min_dividend_yield: 50`) and show the
  clear 422 naming the max achievable yield, not a generic failure.
- Show `examples/inline_returns_request.json` — supplied returns actually
  change the output, not just accepted and ignored.

## 3:15–4:00 — Factor bonus, limitations, what's next
- Case 6: optimized momentum beta exceeds current — note the assignment
  explicitly does NOT require weight parity here (only 3 factors vs. the
  live tool's broader model).
- One or two honest limitations: risk-free rate is a stated default (0%),
  not solved from live-tool evidence yet; minimize_drawdown has no global-
  optimum guarantee (non-convex problem, multi-start SLSQP).
- What you'd do with more time.

## Things to actually be able to explain if asked
- Why date intersection matters (IEFA starts 2012, SPY starts 1993).
- ERC risk parity vs. naive inverse-volatility (they coincide only in the
  two-asset, zero-correlation case).
- Arithmetic vs. geometric (CAGR) return conventions, and where each is used.
- Why max drawdown reflects starting capital (a -10%/+10% sequence is NOT
  back to 0% drawdown at the trough).
- Local vs. global optimum for the non-convex minimize_drawdown strategy.
- The linear-regression shortcut for factor betas (see `app/factors.py`
  docstring) and why it's mathematically valid, not just faster.

Avoid: a folder tour, claiming the tool's "true" risk-free rate was
identified from a handful of weight comparisons, reading code line by line.
