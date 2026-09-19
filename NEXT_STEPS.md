# What's left (everything below genuinely needs you)

Everything buildable without live-tool access or a human is done: API, all 6
strategies, 71 passing tests, error handling, README, example requests, a
fresh-checkout verification. This is what remains, in order.

## 1. Try once more to capture the live tool's reference outputs (~10 min cap)
Account creation was failing with a generic error as of the last update. Try
once more (incognito window, different browser, different email) — if it
works, go to https://finominal.com/portfolio-optimizer/US and run the 6
scenarios from `IMPLEMENTATION_PLAN.md` §4 / the assignment doc:
- Screenshot the Review Results tab (and Comparison tab for case 6) into
  `docs/reference/` (e.g. `case_01_equal_weights.png`).
- Copy `tests/golden/scenarios.template.json` to `tests/golden/scenarios.json`
  and fill in each `expected_weights` value from what the tool shows.
- Then run:
  ```bash
  source .venv/bin/activate
  python scripts/compare_reference.py
  pytest tests/test_reference.py -v
  ```
  If something's out of tolerance, try the risk-free rate first — see README
  "Methodology" and `ANNUAL_RISK_FREE_RATE` in `app/metrics.py`.
- Then update the README's status paragraph at the top with the real result.

**If it's still broken, don't burn more time on it** — email
kaushik@finominal.com about the signup error (legitimate, worth flagging),
and move on. The README already documents this fallback honestly: the 71
tests (analytic fixtures, feasible-baseline checks, synthetic-coefficient
recovery for the factor regression) are the correctness evidence in place
of a live-tool match. Nothing else needs to change.

## 2. Screenshots for the submission
At least 3 strategies, showing the running API returning correct output.
`docs/reference/live_case_*.json` already has 5 real captured responses from
curl if you want a starting point — but the deliverable wants screenshots
(e.g. of the terminal or Swagger UI at `/docs`), not raw JSON files.

## 3. Record the Loom (3-5 min)
Outline in `docs/LOOM_TALKING_POINTS.md`. Say it in your own words.

## 4. Push and submit
- Create a public GitHub repo, push this code.
- Send: repo link, screenshots, Loom link, to kaushik@finominal.com within
  the 12-hour window (check how much you have left).

## If you get stuck
- Server won't start: check `Data.xlsx` is present at the repo root, or set
  `FINOMINAL_DATA_PATH` env var.
- A live-tool case doesn't match: check `meta.conventions` and
  `meta.date_range` in that case's response first — most mismatches trace to
  a convention difference (annualization, rf) or a different data window,
  not a bug. The README's Methodology section explains every convention
  choice and where to change it.
