# Review of the original implementation plan

**Objective:** maximize the strength of the Finominal take-home within its 12-hour limit.
**Original verdict: BLOCK.** The original plan made required supplied-return support optional and promised a six-case match despite the assignment’s explicit factor exception. Several numerical and evidence claims also needed correction.

**Revised plan verdict: CLEAN.** Both independent reviewers reread the revision and found no material remaining mathematical or assignment-compliance issue. This verdict applies to the plan only. Bonus and nonlinear-validation time slots are ambitious checkpoints; implementation and evidence remain unverified.

Scope: the full original plan, every paragraph/table in the assignment DOCX, all three workbook sheets, the public reference page, the prior submission’s README, and official numerical-library documentation. Independent reviewers examined mathematical correctness and hiring/requirements risk. No application exists yet; no API tests or live optimization scenarios were run in this review.

## Material findings and corrections

| Severity | Original problem and consequence | Correction in revised plan |
| --- | --- | --- |
| CRITICAL | Section 9 treats supplied returns as optional scope; the brief requires accepting securities with return data | Concrete dated-return contract, all-inline or all-bundled mode, integration test proving supplied data is used |
| WARNING | Sections 4/8/10 promise six exact reference matches; case 6 explicitly need not match the broader live model | Five core comparisons and separate factor regression/improvement checks |
| WARNING | Drawdown in section 7 starts at first observed wealth, hiding initial losses; `[-10%, +10%]` incorrectly appears to have no drawdown | Include starting wealth 1 and hand-calculated first-day-loss test |
| WARNING | Section 7 mixes CAGR Sharpe with an inapplicable analytic tangency check, and annual drifting returns with constant-weight covariance formulas | Coherent objective conventions, valid analytic fixtures, explicit limits on covariance and beta shortcuts |
| WARNING | Sections 7/9 round and renormalize weights, which can break binding yield/bound constraints | Retain precision and independently validate actual serialized values |
| WARNING | Section 9 implies universal analytic feasibility checks; nonlinear search failure cannot establish infeasibility | Exact bounds/yield checks; separate nonlinear search failure; explicit equal-weight conflict behavior |
| WARNING | Sections 10/13 call random portfolios proof of optimum and add 20,000 samples to API responses | Remove per-request sampling and global claims; use independent analytic/grid tests |
| WARNING | Calibration before strategy implementation is circular; 1,024 candidate conventions waste time and include unidentifiable axes | Incremental implementation and bounded diagnostic calibration, held-out comparison when possible |
| WARNING | Six required scenarios contain no minimum-drawdown case; repeating its result tests determinism only | Dedicated drawdown correctness and objective-quality checks |
| WARNING | Exact matching may conflict with snapshot-data constraints, particularly case 5 | Measure reference weights against supplied yields; preserve validity and show any irreconcilable gap |
| WARNING | Opening summary emphasizes three API screenshots but understates per-case API responses plus reference screenshots | Explicit artifact checklist for all five required cases, bonus when attempted, and three API-strategy screenshots |
| WARNING | Sections 2/13 infer the reviewer, candidate pool and 80–85% advancement probability without evidence | Remove unsupported claims; ground decisions in the supplied rubric |
| WARNING | Loom allocates no clear actual code walkthrough despite the brief asking for one | Short request-to-solver explanation, working requests, evidence and tradeoffs |
| NOTE | Repeated OLS inside the bonus objective and many tiny modules add avoidable work | Shared-sample regression linearity plus linear programming; compact modules |

## What survived review

The original plan correctly prioritized reference validation, common-date alignment, explicit units, missing GLD yield handling, a small Python stack, tests, measured claims and a recording reserve. Those strengths remain.

## Remaining execution risks

The revised plan cannot establish live-tool parity without genuine outputs and settings. Data mismatch may limit achievable agreement. Nonsmooth drawdown and joint nonlinear constraints need actual numerical verification. Twelve hours is a tight budget, so required correctness and evidence take priority over optional polish. The precise deadline and any separate company instructions remain unconfirmed beyond “12hrs.”

The plan’s quality is not evidence that the submission is ready. Recheck the completed implementation, captured comparisons, screenshots, fresh setup and Loom before submission. No hiring outcome or percentile is guaranteed.
