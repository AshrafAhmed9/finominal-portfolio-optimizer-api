"""Unit tests for scripts/reference_fixtures.py's validation logic, using
isolated temporary fixture files - never touching the repository's real
tests/golden/scenarios.json. These are the R5 acceptance tests: none of
these malformed inputs may produce an overall PASS.
"""
import json

import pytest

from scripts.reference_fixtures import (
    REQUIRED_REQUESTS,
    FixtureError,
    load_and_validate_fixtures,
)


def _write(tmp_path, data):
    path = tmp_path / "scenarios.json"
    path.write_text(json.dumps(data))
    return path


def _valid_case(case_id: int, expected: dict | None = None):
    request = REQUIRED_REQUESTS[case_id]
    tickers = [s["ticker"] for s in request["securities"]]
    return {
        "id": case_id,
        "name": f"case_{case_id}",
        "request": request,
        "expected_weights": expected if expected is not None else {t: 100.0 / len(tickers) for t in tickers},
        "tolerance_pp": 0.1,
    }


def _all_five_valid():
    return [_valid_case(i) for i in range(1, 6)]


def test_missing_file_raises(tmp_path):
    with pytest.raises(FixtureError):
        load_and_validate_fixtures(tmp_path / "does_not_exist.json")


def test_empty_list_raises(tmp_path):
    path = _write(tmp_path, [])
    with pytest.raises(FixtureError):
        load_and_validate_fixtures(path)


def test_missing_required_case_raises(tmp_path):
    cases = _all_five_valid()
    cases.pop()  # drop case 5
    path = _write(tmp_path, cases)
    with pytest.raises(FixtureError, match="missing required case"):
        load_and_validate_fixtures(path)


def test_duplicate_case_id_raises(tmp_path):
    cases = _all_five_valid()
    cases.append(_valid_case(1))
    path = _write(tmp_path, cases)
    with pytest.raises(FixtureError, match="duplicate fixture"):
        load_and_validate_fixtures(path)


def test_incomplete_expected_weights_ticker_set_raises(tmp_path):
    cases = _all_five_valid()
    cases[0]["expected_weights"] = {"IEFA": 100.0}  # missing SPY
    path = _write(tmp_path, cases)
    with pytest.raises(FixtureError, match="do not match"):
        load_and_validate_fixtures(path)


def test_nonfinite_expected_weight_raises(tmp_path):
    cases = _all_five_valid()
    cases[0]["expected_weights"] = {"IEFA": float("nan"), "SPY": 75.0}
    path = _write(tmp_path, cases)
    with pytest.raises(FixtureError):
        load_and_validate_fixtures(path)


def test_missing_screenshot_raises(tmp_path):
    cases = _all_five_valid()
    cases[0]["reference_screenshot"] = "docs/reference/definitely_does_not_exist.png"
    path = _write(tmp_path, cases)
    with pytest.raises(FixtureError, match="does not exist on disk"):
        load_and_validate_fixtures(path)


def test_widened_tolerance_raises(tmp_path):
    cases = _all_five_valid()
    cases[0]["tolerance_pp"] = 5.0  # far beyond the assignment's 0.1pp
    path = _write(tmp_path, cases)
    with pytest.raises(FixtureError, match="exceeds"):
        load_and_validate_fixtures(path)


def test_malformed_json_raises(tmp_path):
    path = tmp_path / "scenarios.json"
    path.write_text("{not valid json")
    with pytest.raises(FixtureError):
        load_and_validate_fixtures(path)


def test_case6_null_expected_weights_does_not_crash(tmp_path):
    # This used to raise a TypeError (subtracting None), not a FixtureError,
    # the exact defect named in SUBMISSION_REVIEW.md R5.
    cases = _all_five_valid()
    case6 = _valid_case(6)
    case6["expected_weights"] = None
    cases.append(case6)
    path = _write(tmp_path, cases)
    fixtures = load_and_validate_fixtures(path)  # must not raise
    case6_fixture = next(f for f in fixtures if f.id == 6)
    assert case6_fixture.expected_weights is None


def test_request_not_matching_assignment_spec_raises(tmp_path):
    cases = _all_five_valid()
    cases[0]["request"] = {
        "securities": [{"ticker": "IEFA", "weight": 50}, {"ticker": "SPY", "weight": 50}],  # wrong starting weights
        "strategy": "equal_weights",
    }
    path = _write(tmp_path, cases)
    with pytest.raises(FixtureError, match="does not match"):
        load_and_validate_fixtures(path)


def test_all_five_valid_loads_cleanly(tmp_path):
    path = _write(tmp_path, _all_five_valid())
    fixtures = load_and_validate_fixtures(path)
    assert {f.id for f in fixtures} == {1, 2, 3, 4, 5}
