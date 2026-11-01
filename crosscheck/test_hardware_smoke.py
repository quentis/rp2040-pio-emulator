import pytest

from .firmware import MINIMUM_VERSION
from .pico import query_firmware

pytestmark = pytest.mark.hardware


def test_board_runs_a_suitable_micropython(pico_port):
    info = query_firmware(pico_port)

    assert info.name == "micropython"
    assert info.version >= MINIMUM_VERSION
    assert "RP2350" in info.machine.upper()
