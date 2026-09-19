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
  "request": { "securities": [...], "strategy": "equal_weights", "constraints": null },
  "expected_weights": { "IEFA": 25.00, "SPY": 75.00 },
  "tolerance_pp": 0.1,
  "reference_screenshot": "docs/reference/case_01_equal_weights.png"
}
```

Once populated, `tests/test_reference.py` asserts every case against it
(currently the module skips with an explicit reason when this file is
missing - it never silently passes), and `scripts/compare_reference.py`
prints a full comparison table.
