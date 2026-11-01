"""Cross-check: every case run on the Pico 2 must reproduce its golden trace."""
from pathlib import Path

import pytest

from .case import load_cases
from .golden import golden_path, load_golden
from .hardware import run_on_hardware
from .trace import compare, format_mismatches

HERE = Path(__file__).parent

pytestmark = pytest.mark.hardware


@pytest.mark.parametrize("case", load_cases(HERE / "cases"), ids=lambda case: case.name)
def test_hardware_reproduces_golden_trace(case, pico_port):
    golden = load_golden(golden_path(HERE / "golden", case.name))

    actual = run_on_hardware(case, pico_port)

    mismatches = compare(golden.trace, actual)
    assert not mismatches, (
        f"hardware differs from the {golden.source} golden trace\n"
        + format_mismatches(golden.trace, mismatches)
    )
