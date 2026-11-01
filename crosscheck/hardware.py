"""
Runs a case on the Pico 2 and records its pin trace with the Analog Discovery.

Wiring (see HARDWARE.md): GPn is connected to DIOn. The case drives and observes GP8 - GP14;
GP15 carries a marker edge that triggers the capture and marks the start of cycle 0.
"""
from pathlib import Path
from typing import Callable

from . import analog_discovery
from .assembler import AssembledProgram, assemble
from .case import Case
from .pico import RawRepl
from .trace import Trace

FREQ = 5_000_000  # state machine clock in Hz
SAMPLE_RATE = 50e6  # logic analyzer sample rate in Hz: ten samples per state machine cycle
PREFILL = 16  # analyzer samples kept from before the trigger
TAIL_CYCLES = 2  # cycles captured beyond the end of the case

OBSERVABLE_PINS = range(8, 15)  # GP8 - GP14 are wired to DIO8 - DIO14, analyzer inputs
MARKER_PIN = 15
MAX_TX_FIFO_WORDS = 4

# Marker program: "set pins, 1" in cycle 0, then spin. It starts on the same clock as the case.
_MARKER_OPCODES = [0xE001, 0x0001]
_PIN_OUTPUT = 0b10  # entry of a pin initialisation list: bit 1 direction, bit 0 level


def _pin_initialisation(case: Case, base: int, count: int) -> list[int]:
    return [((case.pin_directions >> (base + i)) & 1) << 1 for i in range(count)]


def _check_pins(case: Case, name: str, base: int, count: int) -> None:
    if base not in OBSERVABLE_PINS or base + count - 1 not in OBSERVABLE_PINS:
        raise ValueError(
            f"case {case.name!r}: {name} pins {base}..{base + count - 1} must lie within "
            f"GP{OBSERVABLE_PINS[0]} - GP{OBSERVABLE_PINS[-1]}"
        )


def validate(case: Case) -> None:
    """Raises ValueError if the case cannot be run on the wired hardware."""
    if case.stimulus:
        raise ValueError(f"case {case.name!r}: stimulus is not supported on hardware yet")

    if len(case.tx_fifo) > MAX_TX_FIFO_WORDS:
        raise ValueError(f"case {case.name!r}: at most {MAX_TX_FIFO_WORDS} TX FIFO words")

    for pin in case.observed_pins:
        _check_pins(case, "observed", pin, 1)

    directions = case.pin_directions
    for pin in range(32):
        if directions >> pin & 1 and pin not in OBSERVABLE_PINS:
            raise ValueError(f"case {case.name!r}: GP{pin} cannot be an output on this wiring")


def build_spec(case: Case, program: AssembledProgram | None = None) -> dict:
    """
    Describes the case for device_runner.setup(): plain ints, lists and dicts only.

    Pin groups (OUT, SET, side-set) are configured only when the case names their base pin;
    unlike the emulator there are no defaults, and hardware needs every pin to be wired.
    """
    validate(case)
    program = program or assemble(case)
    settings = {**program.config, **case.config}

    def flag(key: str, default: bool) -> int:
        return int(settings.get(key, default))

    pins: dict[str, int] = {}
    inits = {"out_init": [0], "set_init": [0], "sideset_init": [0]}  # unused unless a base is set

    for group, init in (("out", "out_init"), ("set", "set_init")):
        if f"{group}_base" in settings:
            if f"{group}_count" not in settings:
                raise ValueError(f"case {case.name!r}: {group}_base needs {group}_count")

            base, count = settings[f"{group}_base"], settings[f"{group}_count"]
            _check_pins(case, group, base, count)
            pins[f"{group}_base"] = base
            inits[init] = _pin_initialisation(case, base, count)

    if settings.get("side_set_count"):
        base, count = settings["side_set_base"], settings["side_set_count"]
        _check_pins(case, "side-set", base, count)
        pins["sideset_base"] = base
        inits["sideset_init"] = _pin_initialisation(case, base, count)

    if "jmp_pin" in settings:
        pins["jmp_pin"] = settings["jmp_pin"]

    # EXECCTRL (RP2350 layout): SIDE_EN (30), WRAP_TOP (16:12), WRAP_BOTTOM (11:7), STATUS_SEL
    # (6:5), STATUS_N (4:0). The side-set pin count and the pins' initial state come from the pin
    # lists, the load offset is added on the board.
    execctrl = (
        flag("side_set_opt", False) << 30
        | settings["wrap_top"] << 12
        | settings["wrap_target"] << 7
        | settings.get("status_sel", 0) << 5
        | settings.get("status_n", 0)
    )

    # SHIFTCTRL: thresholds (32 is encoded as 0), shift directions (1 = right), auto-pull/push.
    shiftctrl = (
        (settings.get("pull_threshold", 32) & 0x1F) << 25
        | (settings.get("push_threshold", 32) & 0x1F) << 20
        | flag("shift_osr_right", True) << 19
        | flag("shift_isr_right", True) << 18
        | flag("auto_pull", False) << 17
        | flag("auto_push", False) << 16
    )

    return {
        "freq": FREQ,
        "tx_fifo": list(case.tx_fifo),
        "case": {
            "opcodes": program.opcodes,
            "execctrl": execctrl,
            "shiftctrl": shiftctrl,
            "pins": pins,
            **inits,
        },
        "marker": {
            "opcodes": _MARKER_OPCODES,
            "execctrl": 1 << 12,  # wrap top 1, wrap bottom 0
            "shiftctrl": 0,
            "pins": {"set_base": MARKER_PIN},
            "out_init": [0],
            "set_init": [_PIN_OUTPUT],
            "sideset_init": [0],
        },
    }


def device_runner_source() -> str:
    return Path(__file__).with_name("device_runner.py").read_text(encoding="utf-8")


def run_on_hardware(
    case: Case,
    port: str,
    *,
    open_repl: Callable[[str], RawRepl] = RawRepl.open,
    capture: Callable[..., list[int]] = analog_discovery.capture,
) -> Trace:
    """Runs the case on the board at `port` and returns the pin trace seen by the analyzer."""
    spec = build_spec(case)

    samples_per_cycle = SAMPLE_RATE / FREQ
    sample_count = PREFILL + int((case.cycles + TAIL_CYCLES) * samples_per_cycle)

    with open_repl(port) as repl:
        repl.exec(device_runner_source())
        repl.exec(f"setup({spec!r})")

        try:
            samples = capture(
                trigger_pin=MARKER_PIN,
                sample_rate=SAMPLE_RATE,
                sample_count=sample_count,
                prefill=PREFILL,
                start=lambda: repl.exec("start()"),
            )
        finally:
            repl.exec("stop()")

    # The marker edge and the effect of cycle 0 appear on the same clock edge. The edge is
    # looked up in the data: the analyzer's trigger sample is not exactly at the prefill index.
    return analog_discovery.samples_to_trace(
        samples,
        sample_rate=SAMPLE_RATE,
        cycle_rate=FREQ,
        first_cycle_sample=analog_discovery.find_rising_edge(samples, MARKER_PIN),
        cycles=case.cycles,
        pins=case.observed_pins,
    )
