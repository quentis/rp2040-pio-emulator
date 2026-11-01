"""The emulator must reproduce every committed golden trace; runs without hardware."""
from pathlib import Path

import pytest

from .case import load_cases
from .emulator import run_on_emulator
from .golden import golden_path, load_golden
from .trace import compare, format_mismatches

HERE = Path(__file__).parent
CASES = load_cases(HERE / "cases")


def test_every_case_has_a_golden_trace_and_vice_versa():
    case_names = {case.name for case in CASES}
    golden_names = {path.stem for path in (HERE / "golden").glob("*.json")}

    assert case_names == golden_names


def _expect_failure_if_known(case):
    marks = []
    if case.known_emulator_difference:
        marks.append(pytest.mark.xfail(strict=True, reason=case.known_emulator_difference))

    return pytest.param(case, id=case.name, marks=marks)


@pytest.mark.parametrize("case", [_expect_failure_if_known(case) for case in CASES])
def test_emulator_reproduces_golden_trace(case):
    golden = load_golden(golden_path(HERE / "golden", case.name))
    assert golden.case == case.name

    actual = run_on_emulator(case)

    mismatches = compare(golden.trace, actual)
    assert not mismatches, (
        f"emulator differs from {golden.source} golden trace\n"
        + format_mismatches(golden.trace, mismatches)
    )
