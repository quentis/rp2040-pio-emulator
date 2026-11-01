"""
Makes sure the Pico 2 runs a suitable MicroPython, flashing it through the debug probe if not.

The board is assumed to be dedicated to this cross-check: when it does not answer as
MicroPython, whatever it ran is overwritten.
"""
import logging
import subprocess
import time
import urllib.error
from typing import Callable

from . import flash_micropython
from .pico import (
    FirmwareInfo,
    PicoError,
    PortBusyError,
    find_port,
    query_firmware,
)

LOGGER = logging.getLogger(__name__)

MINIMUM_VERSION = flash_micropython.PINNED_VERSION


class FirmwareMissing(PicoError):
    """No suitable MicroPython and flashing was not allowed."""


class WrongBoard(PicoError):
    """The board runs MicroPython but is not a Pico 2."""


class FlashError(PicoError):
    """Flashing failed or did not produce a working MicroPython."""


def _version_text(version: tuple[int, int, int]) -> str:
    return ".".join(map(str, version))


def flash_firmware() -> None:
    """Flashes the pinned MicroPython build through the debug probe."""
    try:
        flash_micropython.main([])
    except subprocess.CalledProcessError as error:
        raise FlashError(
            "flashing with pyOCD failed; is the Debug Probe connected and pyocd installed? "
            "(try `pyocd list`)"
        ) from error
    except (urllib.error.URLError, ValueError) as error:
        raise FlashError(f"could not obtain the firmware: {error}") from error


def _inspect(find: Callable, query: Callable) -> tuple[str | None, FirmwareInfo | None, str]:
    """Returns (port, info, reason); info is None when no usable MicroPython answers."""
    try:
        port = find()
        return port, query(port), ""
    except PortBusyError:
        raise  # somebody is using the board; flashing would not help
    except PicoError as error:
        return None, None, str(error)


def ensure_micropython(
    *,
    allow_flash: bool = True,
    find: Callable[[], str] = find_port,
    query: Callable[[str], FirmwareInfo] = query_firmware,
    flash: Callable[[], None] = flash_firmware,
    sleep: Callable[[float], None] = time.sleep,
    timeout: float = 30.0,
) -> str:
    """
    Returns the serial port of a board running MicroPython of at least MINIMUM_VERSION,
    flashing the pinned version first if there is none (unless allow_flash is False).
    """
    port, info, reason = _inspect(find, query)

    if info is not None:
        if "RP2350" not in info.machine.upper():
            raise WrongBoard(f"the board is not a Pico 2 (it reports {info.machine!r})")

        if info.version >= MINIMUM_VERSION:
            return port

        reason = (
            f"MicroPython {_version_text(info.version)} is older than "
            f"the required {_version_text(MINIMUM_VERSION)}"
        )
    else:
        reason = f"no usable MicroPython on the board ({reason})"

    if not allow_flash:
        raise FirmwareMissing(
            f"{reason}. Run `python -m crosscheck.flash_micropython` or drop --no-flash."
        )

    LOGGER.warning(
        "%s; flashing MicroPython %s, which overwrites the board's firmware",
        reason,
        _version_text(flash_micropython.PINNED_VERSION),
    )
    flash()

    # The board reboots and its USB serial port re-enumerates.
    interval = 0.5
    for _ in range(int(timeout / interval)):
        sleep(interval)
        port, info, reason = _inspect(find, query)
        if info is not None and info.version >= MINIMUM_VERSION:
            return port

    raise FlashError(f"MicroPython did not come up after flashing ({reason or 'too old'})")
