import pytest

from .firmware import (
    MINIMUM_VERSION,
    FirmwareMissing,
    FlashError,
    WrongBoard,
    ensure_micropython,
)
from .pico import FirmwareInfo, NoPortError, PicoError, PortBusyError

PICO2 = "Raspberry Pi Pico 2 with RP2350"


def info(version=MINIMUM_VERSION, machine=PICO2) -> FirmwareInfo:
    return FirmwareInfo("micropython", version, machine)


class Board:
    """Fake board and flasher: what the board answers changes once it has been flashed."""

    def __init__(self, before, after=None):
        self.state = before  # FirmwareInfo, or an exception to raise from find()
        self.after = after if after is not None else info()
        self.flashed = 0

    def find(self) -> str:
        if isinstance(self.state, Exception):
            raise self.state
        return "COM7"

    def query(self, _port: str) -> FirmwareInfo:
        return self.state

    def flash(self) -> None:
        self.flashed += 1
        self.state = self.after

    def ensure(self, **kwargs) -> str:
        return ensure_micropython(
            find=self.find, query=self.query, flash=self.flash, sleep=lambda _: None, **kwargs
        )


def test_suitable_firmware_is_left_alone():
    board = Board(info())

    assert board.ensure() == "COM7"
    assert board.flashed == 0


def test_newer_firmware_is_accepted():
    board = Board(info(version=(MINIMUM_VERSION[0] + 1, 0, 0)))

    board.ensure()

    assert board.flashed == 0


def test_older_firmware_is_replaced():
    board = Board(info(version=(1, 0, 0)))

    assert board.ensure() == "COM7"
    assert board.flashed == 1


def test_board_without_micropython_port_is_flashed():
    board = Board(NoPortError("no port"))

    assert board.ensure() == "COM7"
    assert board.flashed == 1


def test_board_that_does_not_answer_is_flashed():
    board = Board(PicoError("timed out"))

    board.ensure()

    assert board.flashed == 1


def test_flashing_can_be_forbidden():
    board = Board(NoPortError("no port"))

    with pytest.raises(FirmwareMissing, match="no usable MicroPython"):
        board.ensure(allow_flash=False)

    assert board.flashed == 0


def test_old_firmware_with_flashing_forbidden_is_reported():
    board = Board(info(version=(1, 0, 0)))

    with pytest.raises(FirmwareMissing, match="older than"):
        board.ensure(allow_flash=False)


def test_other_boards_are_not_flashed():
    board = Board(info(machine="Raspberry Pi Pico with RP2040"))

    with pytest.raises(WrongBoard):
        board.ensure()

    assert board.flashed == 0


def test_busy_port_is_not_mistaken_for_missing_firmware():
    board = Board(PortBusyError("COM7 is in use"))

    with pytest.raises(PortBusyError):
        board.ensure()

    assert board.flashed == 0


def test_failure_to_come_up_after_flashing_is_reported():
    board = Board(NoPortError("no port"), after=NoPortError("still no port"))

    with pytest.raises(FlashError, match="did not come up"):
        board.ensure()
