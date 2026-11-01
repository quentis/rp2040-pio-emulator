"""Tests of the stimulus support, with fake boards and analyzer captures."""
import pytest

from . import hardware
from .case import Case
from .hardware import (
    FIRST_STIMULUS_CYCLE,
    PATTERN_LATENCY,
    StimulusTimingError,
    check_stimulus_timing,
    run_on_hardware,
    stimulus_drive,
    validate,
)
from .pico import RawRepl
from .test_hardware_runner import BANNER, FakeStream, make_case

SAMPLES_PER_CYCLE = int(hardware.SAMPLE_RATE / hardware.FREQ)
HALF = SAMPLES_PER_CYCLE // 2


def stimulus_case(stimulus) -> Case:
    return make_case(stimulus=stimulus, cycles=20)


class SilentRepl(RawRepl):
    """A raw REPL that accepts any code and prints nothing."""

    def exec(self, code: str) -> str:
        return ""


def silent_repl(_port: str) -> RawRepl:
    return SilentRepl(FakeStream(BANNER))


class TestValidation:
    @pytest.mark.parametrize(
        "stimulus",
        [
            [[FIRST_STIMULUS_CYCLE, 1]],
            [[0, 0b11], [FIRST_STIMULUS_CYCLE, 0], [9, 0xFF]],
        ],
    )
    def test_accepts_stimulus_on_the_wired_input_pins(self, stimulus):
        validate(stimulus_case(stimulus))

    @pytest.mark.parametrize(
        "stimulus",
        [
            [[3, 0x100]],  # GP8 is an output
            [[3, 1], [3, 0]],  # not strictly increasing
            [[5, 1], [4, 0]],
            [[1, 1]],  # too early for the pattern generator
        ],
    )
    def test_rejects_stimulus_that_cannot_be_produced(self, stimulus):
        with pytest.raises(ValueError):
            validate(stimulus_case(stimulus))


class TestStimulusDrive:
    def test_drives_all_the_input_pins(self):
        drive = stimulus_drive(stimulus_case([[4, 1]]), length=60)

        assert sorted(drive) == list(range(8))
        assert all(len(bits) == 60 for _, bits in drive.values())

    def test_a_pin_without_changes_stays_at_its_initial_level(self):
        drive = stimulus_drive(stimulus_case([[0, 0b10], [4, 0b10]]), length=60)

        assert drive[0] == (0, [0] * 60)
        assert drive[1] == (1, [1] * 60)

    def test_an_edge_for_cycle_n_is_half_a_cycle_before_the_cycle_starts(self):
        cycle = 6
        drive = stimulus_drive(stimulus_case([[cycle, 1]]), length=100)

        idle_level, bits = drive[0]
        first_high = bits.index(1)

        # The pattern starts PATTERN_LATENCY samples after the marker edge
        assert idle_level == 0
        assert first_high + PATTERN_LATENCY == cycle * SAMPLES_PER_CYCLE - HALF

    def test_a_falling_edge_is_placed_the_same_way(self):
        drive = stimulus_drive(stimulus_case([[0, 1], [9, 0]]), length=120)

        idle_level, bits = drive[0]

        assert idle_level == 1
        assert bits.index(0) + PATTERN_LATENCY == 9 * SAMPLES_PER_CYCLE - HALF


def capture_with_edges(case: Case, marker_edge: int, offset: int = 0) -> list[int]:
    """What the analyzer would record if the pattern generator played the case's stimulus."""
    length = marker_edge + (case.cycles + 3) * SAMPLES_PER_CYCLE
    samples = [0] * length

    for index in range(length):
        word = 1 << hardware.MARKER_PIN if index >= marker_edge else 0
        for pin in range(8):
            cycle = (index - marker_edge - offset + HALF) // SAMPLES_PER_CYCLE
            word |= hardware._stimulus_level(case, pin, cycle) << pin
        samples[index] = word

    return samples


class TestStimulusTiming:
    def test_accepts_edges_where_they_belong(self):
        case = stimulus_case([[6, 1], [11, 0]])

        check_stimulus_timing(capture_with_edges(case, marker_edge=14), 14, case)

    def test_accepts_a_small_deviation(self):
        case = stimulus_case([[6, 1]])

        check_stimulus_timing(capture_with_edges(case, 14, offset=hardware.STIMULUS_TOLERANCE), 14, case)

    def test_rejects_edges_that_are_too_late(self):
        case = stimulus_case([[6, 1]])
        late = capture_with_edges(case, 14, offset=HALF)

        with pytest.raises(StimulusTimingError, match="GP0"):
            check_stimulus_timing(late, 14, case)

    def test_rejects_edges_that_never_appear(self):
        case = stimulus_case([[6, 1]])

        with pytest.raises(StimulusTimingError, match="no sample"):
            check_stimulus_timing([1 << hardware.MARKER_PIN] * 200, 14, case)

    def test_cases_without_changes_need_no_edges(self):
        case = stimulus_case([[0, 0b101]])

        check_stimulus_timing(capture_with_edges(case, 14), 14, case)


class TestRunWithStimulus:
    def test_hands_the_pattern_to_the_analyzer_and_checks_the_edges(self):
        case = stimulus_case([[6, 1]])
        passed = {}

        def capture(*, sample_count, drive=None, **_):
            passed["drive"] = drive
            return capture_with_edges(case, 14)

        trace = run_on_hardware(
            case, "COM7", open_repl=silent_repl, capture=capture
        )

        assert sorted(passed["drive"]) == list(range(8))
        assert len(trace.values) == case.cycles

    def test_fails_when_the_edges_are_misplaced(self):
        case = stimulus_case([[6, 1]])

        def capture(**_):
            return capture_with_edges(case, 14, offset=HALF)

        with pytest.raises(StimulusTimingError):
            run_on_hardware(
                case, "COM7", open_repl=silent_repl, capture=capture
            )

    def test_cases_without_stimulus_leave_the_pattern_generator_alone(self):
        passed = {}

        def capture(*, sample_count, prefill, **options):
            passed.update(options)
            return [0] * prefill + [1 << hardware.MARKER_PIN] * (sample_count - prefill)

        run_on_hardware(
            make_case(), "COM7", open_repl=silent_repl, capture=capture
        )

        assert "drive" not in passed
