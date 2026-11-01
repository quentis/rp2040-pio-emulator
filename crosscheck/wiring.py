"""
Checks the connections between the Pico 2 and the Analog Discovery (see HARDWARE.md).

Every wire is driven on its own and everything on the other side is read back, so a missing wire,
a wire on the wrong pin, two wires shorted together and a pin stuck high each give their own
message. GP0 - GP7 are driven by the Analog Discovery, GP8 - GP15 by the Pico.
"""
import time
from typing import Callable, Sequence

from .hardware import MARKER_PIN, OBSERVABLE_PINS, STIMULUS_PINS
from .pico import RawRepl

INPUT_PINS = list(STIMULUS_PINS)  # the Analog Discovery drives, the Pico reads
OUTPUT_PINS = [*OBSERVABLE_PINS, MARKER_PIN]  # the Pico drives, the Analog Discovery reads

SETTLE_TIME = 0.005  # seconds between driving a wire and reading it back


def _names(prefix: str, mask: int, pins: Sequence[int]) -> str:
    return ", ".join(f"{prefix}{pin}" for pin in pins if (mask >> pin) & 1)


def check_wires(
    pins: Sequence[int],
    drive: Callable[[int], None],
    read: Callable[[], int],
    source: str,
    sink: str,
) -> list[str]:
    """
    Drives the wires one at a time and reports what is wrong with them.

    `drive` sets the source pins from a bit mask (bit n is pin n) and `read` returns the sink pins
    as a bit mask. `source` and `sink` are the names the two sides call a pin (for example "DIO"
    and "GP"); pin n on one side is meant to be wired to pin n on the other.
    """
    mask = sum(1 << pin for pin in pins)
    problems = []

    drive(0)
    stuck = read() & mask
    if stuck:
        problems.append(
            f"{_names(sink, stuck, pins)} read high while every {source} pin is low "
            "(stuck high, or shorted to a supply)"
        )

    for pin in pins:
        drive(1 << pin)
        seen = read() & mask

        if not (seen >> pin) & 1:
            problems.append(
                f"{sink}{pin} does not follow {source}{pin} (not connected, or connected to "
                "another pin)"
            )

        others = seen & ~(1 << pin)
        if others:
            problems.append(
                f"{_names(sink, others, pins)} read high when only {source}{pin} is high "
                "(wires shorted or crossed)"
            )

    drive(0)
    return problems


def check_wiring(port: str) -> list[str]:
    """Checks all the wires of the setup; returns the problems found (none if it is right)."""
    import dwfpy

    problems = []

    with RawRepl.open(port) as repl, dwfpy.Device() as device:
        repl.exec("import machine")

        io = device.digital_io
        io.reset()

        # Analog Discovery -> Pico: GP0 - GP7
        io.output_enable = sum(1 << pin for pin in INPUT_PINS)

        def drive_analog_discovery(mask: int) -> None:
            io.output_state = mask
            io.configure()
            time.sleep(SETTLE_TIME)

        def read_pico() -> int:
            answer = repl.exec(
                "print(sum(machine.Pin(n, machine.Pin.IN, machine.Pin.PULL_DOWN).value() << n "
                f"for n in range({INPUT_PINS[0]}, {INPUT_PINS[-1] + 1})))"
            )
            return int(answer.strip())

        problems += check_wires(INPUT_PINS, drive_analog_discovery, read_pico, "DIO", "GP")

        # Pico -> Analog Discovery: GP8 - GP15
        drive_analog_discovery(0)

        def drive_pico(mask: int) -> None:
            repl.exec(
                f"for n in range({OUTPUT_PINS[0]}, {OUTPUT_PINS[-1] + 1}): "
                f"machine.Pin(n, machine.Pin.OUT, value=(({mask} >> n) & 1))"
            )
            time.sleep(SETTLE_TIME)

        def read_analog_discovery() -> int:
            io.read_status()
            return io.input_state

        problems += check_wires(OUTPUT_PINS, drive_pico, read_analog_discovery, "GP", "DIO")

    return problems
