# What's left

Status as of the last update: the code is done, including a full pass fixing
every issue raised in `SUBMISSION_REVIEW.md` (R1-R10 - a critical constraint-
bypass bug, two valid-request crashes, validation gaps, a Sharpe-ratio
degeneracy, a broken reference-comparison harness, several weak tests, and
solver bookkeeping issues). 125 tests pass. Public repo is live and pushed:
https://github.com/AshrafAhmed9/finominal-portfolio-optimizer-api. Four
Swagger screenshots covering equal weights, constrained maximize_sharpe, and
the factor-exposure bonus are committed and embedded in the README.

This is what's actually left, in order:

## 1. Record the Loom (3-5 min)
Script is in `docs/LOOM_SCRIPT.md` (verbatim lines, screen cues, and a
caption track). Loom's own recorder is free up to 5 minutes per video and
avoids their upload paywall; OBS + a shared Google Drive link is the
documented fallback if you'd rather edit it yourself - either is fine, see
the earlier conversation for the tradeoffs.

**Before recording, re-run the demo once against the current code** - some
of the numbers referenced in the script may have shifted slightly from the
R1-R10 fixes (in particular, the factor-exposure strategy now actually
enforces every constraint type, not just dividend yield, and the response
includes a new `meta.factor_date_range` field). Nothing observed so far
changed the specific numbers already in the script (Sharpe 0.82→0.90,
momentum beta 0.13→0.19), but confirm on camera rather than trusting stale
numbers.

## 2. Optional: one more attempt at live-tool reference capture (~10 min cap)
If the account-creation error from before is still blocking you, don't
spend more time on it - the README already documents this honestly and the
test suite is the correctness evidence in its place. If you do get in, the
six scenarios and the exact validation this needs to satisfy are described
in `tests/golden/README.md`; `scripts/compare_reference.py` and
`tests/test_reference.py` share one validation module
(`scripts/reference_fixtures.py`) so a malformed or incomplete capture
cannot silently report a false pass.

## 3. Fill out the Submission Form
https://docs.google.com/forms/d/e/1FAIpQLSfJr12o6Owh3U492Pws-LK4PeQZnxxFC956HJKsTDxCDDyjhw/viewform
- Email, name
- GitHub link: https://github.com/AshrafAhmed9/finominal-portfolio-optimizer-api
- Loom (or Drive) video link

## 4. Optional: reply to Kaushik about the signup error
Not required for submission, but worth sending whenever - see the draft
from earlier in the conversation.

## If you get stuck
- Server won't start: check `Data.xlsx` is present at the repo root, or set
  `FINOMINAL_DATA_PATH` env var.
- `pytest -q -rs` should show 125 passed, 1 skipped (the skip is the
  reference-fixtures test, expected until `tests/golden/scenarios.json`
  exists).
- A live-tool case doesn't match, if you do get reference access: check
  `meta.conventions` and `meta.date_range` in that case's response first -
  most mismatches trace to a convention difference (annualization, rf) or a
  different data window, not a bug. The README's Methodology section
  explains every convention choice and where to change it.
