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
STIMULUS_PINS = range(0, 8)  # GP0 - GP7 are wired to DIO0 - DIO7, pattern generator outputs
MARKER_PIN = 15
MAX_TX_FIFO_WORDS = 4

# The pattern generator starts this many samples after the marker edge that triggers it. The
# analyzer sees the pattern, and run_on_hardware() checks that the edges land where they belong.
PATTERN_LATENCY = 9
# A stimulus edge is placed half a cycle before the cycle in which the state machine is to see
# it, and must be seen within this many samples of that point.
STIMULUS_TOLERANCE = 2
# The earliest cycle at which the stimulus can change: its edge has to follow the marker edge by
# at least the pattern generator's latency.
FIRST_STIMULUS_CYCLE = 2

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
    _check_stimulus(case)

    if len(case.tx_fifo) > MAX_TX_FIFO_WORDS:
        raise ValueError(f"case {case.name!r}: at most {MAX_TX_FIFO_WORDS} TX FIFO words")

    for pin in case.observed_pins:
        _check_pins(case, "observed", pin, 1)

    directions = case.pin_directions
    for pin in range(32):
        if directions >> pin & 1 and pin not in OBSERVABLE_PINS:
            raise ValueError(f"case {case.name!r}: GP{pin} cannot be an output on this wiring")


class StimulusTimingError(RuntimeError):
    """The pattern generator did not produce the stimulus where the case needs it."""


def _check_stimulus(case: Case) -> None:
    previous_cycle = None
    for cycle, pin_values in case.stimulus:
        if pin_values & ~0xFF:
            raise ValueError(
                f"case {case.name!r}: stimulus can only drive GP0 - GP7, not 0x{pin_values:X}"
            )

        if previous_cycle is not None and cycle <= previous_cycle:
            raise ValueError(f"case {case.name!r}: stimulus cycles must be strictly increasing")

        if 0 < cycle < FIRST_STIMULUS_CYCLE:
            raise ValueError(
                f"case {case.name!r}: stimulus can change from cycle {FIRST_STIMULUS_CYCLE} at "
                "the earliest (cycle 0 gives the initial level)"
            )

        previous_cycle = cycle


def _stimulus_level(case: Case, pin: int, cycle: int) -> int:
    """The level that the stimulus gives a pin from the given cycle onwards."""
    level = 0
    for change_cycle, pin_values in case.stimulus:
        if change_cycle <= cycle:
            level = (pin_values >> pin) & 1

    return level


def stimulus_drive(case: Case, length: int) -> dict[int, tuple[int, list[int]]]:
    """
    Describes what the pattern generator plays for the case: for each of GP0 - GP7 its idle level
    and `length` bits, one per analyzer sample from the start of the pattern.

    A stimulus change from cycle N is an edge half a cycle before cycle N starts, that is
    PATTERN_LATENCY samples after the pattern starts less that distance.
    """
    samples_per_cycle = int(SAMPLE_RATE / FREQ)
    half = samples_per_cycle // 2

    drive = {}
    for pin in STIMULUS_PINS:
        bits = [
            _stimulus_level(case, pin, (index + PATTERN_LATENCY + half) // samples_per_cycle)
            for index in range(length)
        ]
        drive[pin] = (_stimulus_level(case, pin, 0), bits)

    return drive


def check_stimulus_timing(samples: list[int], marker_edge: int, case: Case) -> None:
    """
    Raises StimulusTimingError unless every stimulus edge was seen on the analyzer within
    STIMULUS_TOLERANCE samples of where it belongs, relative to the marker edge.
    """
    samples_per_cycle = int(SAMPLE_RATE / FREQ)
    search = 3 * STIMULUS_TOLERANCE

    for pin in STIMULUS_PINS:
        previous_level = _stimulus_level(case, pin, 0)
        for cycle, _ in case.stimulus:
            level = _stimulus_level(case, pin, cycle)
            if level == previous_level or cycle == 0:
                continue

            expected = marker_edge + cycle * samples_per_cycle - samples_per_cycle // 2
            seen = [
                index
                for index in range(max(1, expected - search), expected + search + 1)
                if index < len(samples)
                and (samples[index] >> pin) & 1 == level
                and (samples[index - 1] >> pin) & 1 != level
            ]

            if not seen or min(abs(index - expected) for index in seen) > STIMULUS_TOLERANCE:
                raise StimulusTimingError(
                    f"case {case.name!r}: the edge on GP{pin} for cycle {cycle} belongs at "
                    f"sample {expected} (marker edge at {marker_edge}) but was seen at "
                    f"{seen or 'no sample'}"
                )

            previous_level = level


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

    if "in_base" in settings:
        if not 0 <= settings["in_base"] <= OBSERVABLE_PINS[-1]:
            raise ValueError(f"case {case.name!r}: in_base must lie within GP0 - GP{OBSERVABLE_PINS[-1]}")

        pins["in_base"] = settings["in_base"]

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

    options = {}
    if case.stimulus:
        options["drive"] = stimulus_drive(case, sample_count)

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
                **options,
            )
        finally:
            repl.exec("stop()")

    # The marker edge and the effect of cycle 0 appear on the same clock edge. The edge is
    # looked up in the data: the analyzer's trigger sample is not exactly at the prefill index.
    marker_edge = analog_discovery.find_rising_edge(samples, MARKER_PIN)

    if case.stimulus:
        check_stimulus_timing(samples, marker_edge, case)

    return analog_discovery.samples_to_trace(
        samples,
        sample_rate=SAMPLE_RATE,
        cycle_rate=FREQ,
        first_cycle_sample=marker_edge,
        cycles=case.cycles,
        pins=case.observed_pins,
    )
