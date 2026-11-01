import pytest

from .wiring import check_wiring

pytestmark = [pytest.mark.hardware, pytest.mark.wiring]


def test_pico_and_analog_discovery_are_wired_as_documented(pico_port):
    """Runs before every other hardware test; if it fails the run stops (see fail_fast.py)."""
    problems = check_wiring(pico_port)

    assert not problems, "wiring problems (see crosscheck/HARDWARE.md):\n  " + "\n  ".join(problems)
