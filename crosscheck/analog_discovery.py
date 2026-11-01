"""
Analog Discovery side of the hardware cross-check.

capture() needs a connected device and the WaveForms runtime and has not been exercised
against real hardware yet; samples_to_trace() is pure and covered by unit tests.
"""
import time
from typing import Callable, Sequence

from .trace import Trace


def samples_to_trace(
    samples: Sequence[int],
    *,
    sample_rate: float,
    cycle_rate: float,
    first_cycle_sample: float,
    cycles: int,
    pins: Sequence[int],
) -> Trace:
    """
    Reduces raw logic analyzer samples to one value per state machine cycle.

    Parameters
    ----------
    samples : Sequence[int]
        One word per analyzer sample; bit n is the level of analyzer channel n.
    sample_rate : float
        Analyzer sample rate in Hz.
    cycle_rate : float
        State machine clock frequency in Hz.
    first_cycle_sample : float
        Sample index at which the effect of the instruction executed in cycle 0 becomes
        visible. Typically derived from the trigger position or a calibration marker.
    cycles : int
        Number of cycles to extract.
    pins : Sequence[int]
        Analyzer channels to extract; bit j of each result is channel pins[j].
    """
    samples_per_cycle = sample_rate / cycle_rate
    if samples_per_cycle < 2:
        raise ValueError("sample_rate must be at least twice the cycle_rate")

    values = []
    for cycle in range(cycles):
        # Sample in the middle of the cycle, away from the edges where pins change.
        index = int(first_cycle_sample + (cycle + 0.5) * samples_per_cycle)
        if not 0 <= index < len(samples):
            raise ValueError(f"capture too short: cycle {cycle} needs sample {index}")

        word = samples[index]
        values.append(sum(((word >> pin) & 1) << j for j, pin in enumerate(pins)))

    return Trace(tuple(pins), tuple(values))


def capture(
    *,
    trigger_pin: int,
    sample_rate: float,
    sample_count: int,
    start: Callable[[], None],
    prefill: int = 16,
    timeout: float = 5.0,
) -> list[int]:
    """
    Arms the logic analyzer, calls `start` (which makes the Pico produce the trigger edge),
    waits for a rising edge on trigger_pin and returns the samples.

    The trigger sample sits at index `prefill` of the result.
    """
    import dwfpy

    with dwfpy.Device() as device:
        logic = device.digital_input
        logic.reset()

        if sample_count > logic.buffer_size_max:
            raise ValueError(
                f"capture of {sample_count} samples exceeds the analyzer buffer "
                f"({logic.buffer_size_max}); run fewer cycles or sample more slowly"
            )

        logic.sample_rate = sample_rate
        logic.sample_format = 16
        logic.buffer_size = sample_count
        logic.setup_edge_trigger(trigger_pin, "rising")
        logic.setup_trigger(position=sample_count - prefill, prefill=prefill)
        logic.configure(start=True)

        start()

        deadline = time.monotonic() + timeout
        while logic.read_status(read_data=True) != dwfpy.Status.DONE:
            if time.monotonic() > deadline:
                raise TimeoutError("logic analyzer was not triggered in time")
            time.sleep(0.001)

        raw = logic.get_data()

    return [int(word) for word in raw]
