from collections import deque

from pioemu import State, clock_cycles_reached, emulate

from .case import Case
from .trace import Trace


def _stimulus_input_source(case: Case):
    changes = sorted(case.stimulus)

    def input_source(state: State) -> int:
        value = 0
        for cycle, pin_values in changes:
            if cycle > state.clock:
                break
            value = pin_values
        return value

    return input_source


def run_on_emulator(case: Case) -> Trace:
    """Runs the case with pioemu and returns the observed pin trace."""
    mask = case.observed_mask
    pins = case.observed_pins

    def compress(pin_values: int) -> int:
        masked = pin_values & mask
        return sum(((masked >> pin) & 1) << i for i, pin in enumerate(pins))

    run = emulate(
        case.opcodes,
        stop_when=clock_cycles_reached(case.cycles),
        initial_state=State(
            pin_directions=case.pin_directions, transmit_fifo=deque(case.tx_fifo)
        ),
        input_source=_stimulus_input_source(case) if case.stimulus else None,
        **case.config,
    )

    values: list[int] = []
    for _, state in run:
        # An instruction with delay occupies several cycles; the pins hold their new value.
        # The last instruction may overshoot the requested length, hence the cap below.
        values.extend([compress(state.pin_values)] * (state.clock - len(values)))

    if len(values) < case.cycles:
        raise RuntimeError(
            f"emulation of {case.name!r} ended after {len(values)} of {case.cycles} cycles"
        )

    return Trace(tuple(pins), tuple(values[: case.cycles]))
