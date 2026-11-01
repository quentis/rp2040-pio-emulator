from types import SimpleNamespace

import pytest

from .pico import (
    FirmwareInfo,
    NoPortError,
    PicoError,
    RawRepl,
    find_port,
    parse_info,
    query_firmware,
)


def port(device: str, vid: int, pid: int):
    return SimpleNamespace(device=device, vid=vid, pid=pid)


class FakeStream:
    """Answers read_until from a scripted buffer, like a serial port that timed out at the end."""

    def __init__(self, incoming: bytes):
        self.incoming = bytearray(incoming)
        self.written = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.written += data

    def read_until(self, terminator: bytes) -> bytes:
        index = self.incoming.find(terminator)
        end = len(self.incoming) if index < 0 else index + len(terminator)
        data = bytes(self.incoming[:end])
        del self.incoming[:end]
        return data

    def close(self) -> None:
        self.closed = True


BANNER = b"MicroPython v1.29.0\r\n>>> raw REPL; CTRL-B to exit\r\n>"
ANSWER = b"OK" + b"micropython\r\n(1, 29, 0)\r\nRaspberry Pi Pico 2 with RP2350\r\n" + b"\x04\x04>"


class TestFindPort:
    def test_returns_the_micropython_port(self):
        ports = [port("COM1", 0x1234, 0x0005), port("COM7", 0x2E8A, 0x0005)]

        assert find_port(lambda: ports) == "COM7"

    def test_ignores_the_debug_probe_and_the_bootloader(self):
        ports = [port("COM3", 0x2E8A, 0x000C), port("COM4", 0x2E8A, 0x000F)]

        with pytest.raises(NoPortError):
            find_port(lambda: ports)

    def test_refuses_to_guess_between_several_boards(self):
        ports = [port("COM7", 0x2E8A, 0x0005), port("COM8", 0x2E8A, 0x0005)]

        with pytest.raises(PicoError, match="several"):
            find_port(lambda: ports)


class TestParseInfo:
    def test_parses_name_version_and_machine(self):
        info = parse_info("micropython\r\n(1, 29, 0)\r\nRaspberry Pi Pico 2 with RP2350\r\n")

        assert info == FirmwareInfo("micropython", (1, 29, 0), "Raspberry Pi Pico 2 with RP2350")

    @pytest.mark.parametrize("output", ["", "micropython\r\n(1, 29)\r\nboard", "a\r\nb"])
    def test_rejects_unexpected_answers(self, output):
        with pytest.raises(PicoError):
            parse_info(output)


class TestRawRepl:
    def test_enters_raw_repl_runs_code_and_leaves_again(self):
        stream = FakeStream(BANNER + ANSWER)

        with RawRepl(stream) as repl:
            output = repl.exec("print(1)")

        assert output.startswith("micropython")
        assert stream.written.startswith(b"\r\x03\x03\r\x01")
        assert b"print(1)\x04" in stream.written
        assert stream.written.endswith(b"\x02")
        assert stream.closed

    def test_reports_errors_from_the_board(self):
        stream = FakeStream(BANNER + b"OK" + b"\x04Traceback: boom\r\n\x04>")

        with RawRepl(stream) as repl:
            with pytest.raises(PicoError, match="boom"):
                repl.exec("1/0")

    def test_times_out_when_the_board_stays_silent(self):
        with pytest.raises(PicoError, match="timed out"):
            with RawRepl(FakeStream(b"")):
                pass

    def test_query_firmware(self):
        stream = FakeStream(BANNER + ANSWER)

        info = query_firmware("COM7", open_repl=lambda _: RawRepl(stream))

        assert info.version == (1, 29, 0)
