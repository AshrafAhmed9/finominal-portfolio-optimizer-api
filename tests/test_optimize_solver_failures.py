"""R7 regression: mocks SciPy's minimize() to exercise failure paths that
are rare or hard to hit with real data - total nonconvergence, missing
optional result metadata, nonfinite objective/weight values, and a
converged-but-constraint-violating result. No failed or invalid candidate
may ever become a returned OptimizationResult.
"""
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from app.constraints import Bounds, ConstraintError, build_portfolio_limits
from app.optimize import OptimizationFailedError, _run_multistart

NO_LIMITS = build_portfolio_limits(None, None, None, None)


def _bounds(n=2):
    return Bounds(lower=np.zeros(n), upper=np.ones(n))


def _return_matrix(n_assets=2, n_obs=50):
    return np.random.default_rng(0).normal(0, 0.01, (n_obs, n_assets))


def _fake_result(success, x=None, message="mock", **extra):
    ns = SimpleNamespace(success=success, x=x if x is not None else np.array([0.5, 0.5]), message=message)
    for k, v in extra.items():
        setattr(ns, k, v)
    return ns


def test_total_nonconvergence_raises_optimization_failed_not_constraint_error():
    # Every single mocked call reports success=False: this is a solver
    # failure, and must be reported as one (OptimizationFailedError / 500),
    # never as ConstraintError / 422, which would claim the problem itself
    # is impossible rather than admitting the search didn't work.
    with patch("app.optimize.minimize", return_value=_fake_result(success=False, x=np.array([np.nan, np.nan]))):
        with pytest.raises(OptimizationFailedError):
            _run_multistart(lambda w: float(w @ w), _bounds(), _return_matrix(), np.zeros(2), NO_LIMITS)


def test_missing_nit_attribute_does_not_crash():
    # Real SciPy omits `nit` entirely (not zero) when every variable is
    # pinned by equal bounds - this reproduces that shape directly rather
    # than relying on triggering it through real bounds.
    good = _fake_result(success=True, x=np.array([0.5, 0.5]))  # deliberately no .nit attribute
    with patch("app.optimize.minimize", return_value=good):
        result = _run_multistart(lambda w: float(w @ w), _bounds(), _return_matrix(), np.zeros(2), NO_LIMITS)
    assert result.iterations == 0
    assert np.allclose(result.weights, [0.5, 0.5])


def test_nonfinite_objective_never_wins_even_as_first_candidate():
    # A pathological objective that returns NaN for every input. Must never
    # be accepted as "best" - not even as the first candidate examined,
    # where `best is None or ...` would otherwise short-circuit past the
    # NaN comparison and accept it unconditionally.
    def nan_objective(w):
        return float("nan")

    with patch("app.optimize.minimize", return_value=_fake_result(success=True, x=np.array([0.5, 0.5]))):
        with pytest.raises(ConstraintError):
            _run_multistart(nan_objective, _bounds(), _return_matrix(), np.zeros(2), NO_LIMITS)


def test_nonfinite_weights_from_solver_are_rejected():
    # SciPy claiming success=True while returning [inf, -inf] is itself a
    # solver malfunction, not evidence the constraints are infeasible - this
    # must never be silently clipped into a false-valid [1, 0] and accepted.
    with patch("app.optimize.minimize", return_value=_fake_result(success=True, x=np.array([np.inf, -np.inf]))):
        with pytest.raises(OptimizationFailedError):
            _run_multistart(lambda w: float(w @ w), _bounds(), _return_matrix(), np.zeros(2), NO_LIMITS)


def test_converged_but_wildly_out_of_bounds_result_is_rejected_not_clipped():
    # SciPy reports success=True, but the returned x is wildly outside the
    # given bounds (a real, if rare, solver edge case). np.clip would
    # otherwise silently launder this into a plausible-looking [1.0, 0.0]
    # and accept it. Treated as a solver malfunction (500), not a false
    # infeasibility certificate (422) - SciPy's own "success" claim was
    # wrong, that says nothing about whether a real solution exists.
    out_of_bounds = _fake_result(success=True, x=np.array([5.0, -4.0]))  # sums to 1 but wildly out of [0,1]
    with patch("app.optimize.minimize", return_value=out_of_bounds):
        with pytest.raises(OptimizationFailedError):
            _run_multistart(lambda w: float(w @ w), _bounds(), _return_matrix(), np.zeros(2), NO_LIMITS)


def test_feasible_starts_are_genuinely_distinct_corners():
    # R10 regression: the corner-generation loop used to ignore its own
    # loop index and produce the identical [0.5, 0.5] point n times for an
    # unbounded 2-asset problem, instead of distinct corners toward each
    # asset's own upper bound.
    from app.optimize import _feasible_starts

    starts = _feasible_starts(_bounds(2))
    corner_candidates = [tuple(np.round(s, 6)) for s in starts]
    assert (1.0, 0.0) in corner_candidates
    assert (0.0, 1.0) in corner_candidates
    # not every start need be unique (the equal-weight start and a random
    # Dirichlet draw could in principle coincide), but the two asset-biased
    # corners specifically must differ from each other and from equal-weight
    assert corner_candidates[1] != corner_candidates[2]


def test_reported_iterations_reflect_the_full_search_not_just_the_winner():
    # R10 regression: iterations used to be captured at the moment a new
    # best candidate was found, undercounting work done by later starts in
    # the same search. Now it's the true total across every start tried.
    call_log = []

    def side_effect(*args, **kwargs):
        call_log.append(1)
        # first call "wins" (lowest objective value achievable here), later
        # calls still report real iteration counts that must be included
        x = np.array([0.9, 0.1]) if len(call_log) == 1 else np.array([0.5, 0.5])
        return _fake_result(success=True, x=x, nit=7)

    with patch("app.optimize.minimize", side_effect=side_effect):
        result = _run_multistart(lambda w: -float(w[0]), _bounds(), _return_matrix(), np.zeros(2), NO_LIMITS)
    total_starts = len(call_log)
    assert result.iterations == 7 * total_starts


def test_mixed_success_and_failure_returns_the_successful_candidate():
    # A realistic case: most starts fail to converge, one succeeds cleanly.
    # The successful one must still be returned rather than treated as an
    # overall failure just because other starts didn't converge.
    calls = {"n": 0}

    def side_effect(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 5:
            return _fake_result(success=False, x=np.array([np.nan, np.nan]))
        return _fake_result(success=True, x=np.array([0.3, 0.7]), nit=12)

    with patch("app.optimize.minimize", side_effect=side_effect):
        result = _run_multistart(lambda w: float(w @ w), _bounds(), _return_matrix(), np.zeros(2), NO_LIMITS)
    assert np.allclose(result.weights, [0.3, 0.7])
