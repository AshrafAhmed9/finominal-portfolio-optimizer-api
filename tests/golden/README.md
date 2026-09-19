# Golden reference fixtures

This directory holds the live tool's captured outputs for the six required
scenarios (see `IMPLEMENTATION_PLAN.md` §4 and §9). **Not yet populated** -
capturing them requires a human running the live tool at
https://finominal.com/portfolio-optimizer/US, which this build could not do.

Expected file: `scenarios.json`, a list of:

```json
{
  "id": 1,
  "name": "equal_weights_2asset",
  "request": { "securities": [{"ticker": "IEFA", "weight": 25}, {"ticker": "SPY", "weight": 75}], "strategy": "equal_weights", "constraints": null },
  "expected_weights": { "IEFA": 50.00, "SPY": 50.00 },
  "tolerance_pp": 0.1,
  "reference_screenshot": "docs/reference/case_01_equal_weights.png"
}
```

Note `expected_weights` here is 50/50, not the request's starting 25/75:
equal weights always outputs 1/n regardless of the starting allocation. The
starting weights only matter for the `change` column in the response, not
for what "equal" means.

**Requirements enforced by `scripts/reference_fixtures.py`** (shared by both
`scripts/compare_reference.py` and `tests/test_reference.py`, so the two can
never silently disagree):

- Exactly one fixture for each of case IDs 1-5, matching the assignment's
  specified request for that case exactly (tickers, weights, strategy,
  constraints). Missing, duplicate, or mismatched-request cases fail loudly.
- `expected_weights` must cover every ticker in the request, every value
  finite, and the values themselves must sum to 100 (a malformed reference
  capture is caught before it's even compared against).
- `tolerance_pp` cannot be widened past 0.1 - that number comes from the
  assignment brief, not from this script's runtime input.
- The referenced screenshot file must actually exist on disk.
- Case 6 is validated separately and is **not** gated on weight parity with
  the live tool - the assignment explicitly exempts it from that (see the
  assignment doc's "Factor Exposure Validation" section). What's checked
  instead: the optimized momentum beta exceeds the current portfolio's, and
  every constraint in the request is respected by the returned weights.
  `expected_weights` for case 6 is optional and, if present, is shown only
  as an informal comparison, never enforced as a pass/fail gate.
- An empty fixture list, or a list missing any of cases 1-5, is a hard
  failure, not a vacuous pass.

Once populated, `tests/test_reference.py` asserts every case against it
(currently the module skips with an explicit reason when this file is
missing - it never silently passes), and `scripts/compare_reference.py`
prints a full comparison table. Both exit/fail loudly on missing, empty, or
malformed evidence - see `scripts/reference_fixtures.py` for the shared
validation logic.
