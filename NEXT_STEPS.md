# What's left (everything below genuinely needs you)

Everything buildable without live-tool access or a human is done: API, all 6
strategies, 71 passing tests, error handling, README, example requests, a
fresh-checkout verification. This is what remains, in order.

## 1. Capture the live tool's reference outputs (~30-45 min)
Go to https://finominal.com/portfolio-optimizer/US and run the 6 scenarios
from `IMPLEMENTATION_PLAN.md` §4 / the assignment doc. For each:
- Screenshot the Review Results tab (and Comparison tab for case 6) into
  `docs/reference/` (e.g. `case_01_equal_weights.png`).
- Copy `tests/golden/scenarios.template.json` to `tests/golden/scenarios.json`
  and fill in each `expected_weights` value from what the tool shows.

## 2. Run the comparison
```bash
source .venv/bin/activate
python scripts/compare_reference.py
pytest tests/test_reference.py -v
```
This prints the actual gap per case. If something's out of tolerance, the
likely first thing to try is the risk-free rate — see README "Methodology"
and `ANNUAL_RISK_FREE_RATE` in `app/metrics.py` (a prior public submission
of this same assignment reported 2% matched better than 0%; untested here).

## 3. Update the README's status line
Replace the "not yet measured" paragraph at the top of `README.md` with the
actual result once you have it (e.g. "5/5 required cases matched within
0.1pp; case detail below" or an honest accounting of what didn't match and
why).

## 4. Screenshots for the submission
At least 3 strategies, showing the running API returning correct output.
`docs/reference/live_case_*.json` already has 5 real captured responses from
curl if you want a starting point — but the deliverable wants screenshots
(e.g. of the terminal or Swagger UI at `/docs`), not raw JSON files.

## 5. Record the Loom (3-5 min)
Outline in `docs/LOOM_TALKING_POINTS.md`. Say it in your own words.

## 6. Push and submit
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
