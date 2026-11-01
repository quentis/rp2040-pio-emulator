"""
Talking to MicroPython on the Pico 2 over its USB serial port, using the raw REPL protocol.

pyserial is imported lazily so that the rest of the framework works without the 'hardware'
dependency group.
"""
import re
import time
from dataclasses import dataclass
from typing import Callable

_CHUNK = 256
_CHUNK_PAUSE = 0.01

# USB vendor and product ID of MicroPython's serial port on the Pico. The Debug Probe's UART
# bridge and the bootloader use other product IDs and are not matched.
MICROPYTHON_USB_ID = (0x2E8A, 0x0005)

_QUERY = """\
import sys, os
print(sys.implementation.name)
print(sys.implementation.version[:3])
print(os.uname().machine)
"""


class PicoError(RuntimeError):
    """Something went wrong talking to the board."""


class NoPortError(PicoError):
    """No MicroPython serial port is present."""


class PortBusyError(PicoError):
    """The port exists but cannot be opened, typically because another program holds it."""


@dataclass(frozen=True)
class FirmwareInfo:
    name: str
    version: tuple[int, int, int]
    machine: str


def find_port(comports: Callable | None = None) -> str:
    """Returns the device name of the one MicroPython serial port that is connected."""
    if comports is None:
        from serial.tools import list_ports

        comports = list_ports.comports

    devices = [p.device for p in comports() if (p.vid, p.pid) == MICROPYTHON_USB_ID]

    if not devices:
        raise NoPortError("no MicroPython serial port found (USB ID 2e8a:0005)")

    if len(devices) > 1:
        raise PicoError(f"several MicroPython serial ports found: {sorted(devices)}")

    return devices[0]


class RawRepl:
    """A minimal client for MicroPython's raw REPL, over any stream with write/read_until."""

    def __init__(self, stream):
        self._stream = stream

    @classmethod
    def open(cls, port: str, timeout: float = 5.0) -> "RawRepl":
        import serial

        try:
            return cls(serial.Serial(port, 115200, timeout=timeout))
        except serial.SerialException as error:
            raise PortBusyError(
                f"cannot open {port}: {error} (is another program using it?)"
            ) from error

    def __enter__(self) -> "RawRepl":
        self._enter_raw_repl()
        return self

    def __exit__(self, *_) -> None:
        try:
            self._stream.write(b"\x02")  # back to the friendly REPL
        finally:
            self._stream.close()

    def _expect(self, terminator: bytes) -> bytes:
        data = self._stream.read_until(terminator)
        if not data.endswith(terminator):
            raise PicoError(f"timed out waiting for {terminator!r}, received {data!r}")

        return data[: -len(terminator)]

    def _enter_raw_repl(self) -> None:
        self._stream.write(b"\r\x03\x03")  # interrupt whatever is running
        self._stream.write(b"\r\x01")
        self._expect(b"raw REPL; CTRL-B to exit\r\n>")

    def exec(self, code: str) -> str:
        """Runs code on the board and returns what it printed."""
        # The board has a small input buffer, so send in chunks (as MicroPython's pyboard.py does).
        data = code.encode()
        for offset in range(0, len(data), _CHUNK):
            self._stream.write(data[offset : offset + _CHUNK])
            time.sleep(_CHUNK_PAUSE)
        self._stream.write(b"\x04")

        self._expect(b"OK")
        output = self._expect(b"\x04")
        errors = self._expect(b"\x04>")

        if errors:
            raise PicoError(f"the board reported an error:\n{errors.decode(errors='replace')}")

        return output.decode(errors="replace")


def parse_info(output: str) -> FirmwareInfo:
    lines = output.strip().splitlines()
    if len(lines) != 3:
        raise PicoError(f"unexpected answer from the board: {output!r}")

    numbers = re.findall(r"\d+", lines[1])
    if len(numbers) != 3:
        raise PicoError(f"unexpected version from the board: {lines[1]!r}")

    major, minor, patch = map(int, numbers)
    return FirmwareInfo(lines[0].strip(), (major, minor, patch), lines[2].strip())


def query_firmware(port: str, open_repl: Callable[[str], RawRepl] = RawRepl.open) -> FirmwareInfo:
    """Asks the board what it runs."""
    with open_repl(port) as repl:
        return parse_info(repl.exec(_QUERY))
