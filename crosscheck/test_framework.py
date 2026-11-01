"""Unit tests of the cross-check framework itself; no hardware needed."""
import pytest

from .analog_discovery import find_rising_edge, samples_to_trace
from .case import Case
from .emulator import run_on_emulator
from .golden import Golden, load_golden, save_golden
from .trace import Trace, compare, format_mismatches


def make_case(**overrides) -> Case:
    fields = dict(name="c", program=["nop"], cycles=3, observed_pins=[0])
    fields.update(overrides)
    return Case(**fields)


class TestCase:
    def test_round_trips_through_dict(self):
        case = make_case(config={"set_count": 1}, tx_fifo=[1, 2], stimulus=[[1, 1]])

        assert Case.from_dict(case.to_dict()) == case

    def test_observed_mask(self):
        assert make_case(observed_pins=[0, 3, 31]).observed_mask == 0x8000_0009

    def test_source_joins_program_lines(self):
        assert make_case(program=["nop", "nop"]).source == "nop\nnop\n"

    @pytest.mark.parametrize(
        "overrides",
        [
            {"config": {"bogus": 1}},
            {"config": {"wrap_top": 1}},
            {"config": {"side_set_count": 1}},
            {"cycles": 0},
            {"observed_pins": []},
            {"observed_pins": [32]},
            {"observed_pins": [1, 1]},
        ],
    )
    def test_rejects_invalid_definitions(self, overrides):
        with pytest.raises(ValueError):
            make_case(**overrides)


class TestTrace:
    def test_pin_levels(self):
        trace = Trace((4, 7), (0b00, 0b01, 0b10, 0b11))

        assert trace.pin_levels(4) == [0, 1, 0, 1]
        assert trace.pin_levels(7) == [0, 0, 1, 1]

    def test_identical_traces_match(self):
        trace = Trace((0,), (1, 0, 1))

        assert compare(trace, trace) == []

    def test_reports_each_differing_cycle(self):
        expected = Trace((0,), (1, 0, 1, 0))
        actual = Trace((0,), (1, 1, 1, 1))

        assert [(m.cycle, m.expected, m.actual) for m in compare(expected, actual)] == [
            (1, 0, 1),
            (3, 0, 1),
        ]

    def test_reports_missing_and_extra_cycles(self):
        short = Trace((0,), (1,))
        long = Trace((0,), (1, 0, 1))

        assert [(m.cycle, m.actual) for m in compare(long, short)] == [(1, -1), (2, -1)]
        assert [(m.cycle, m.expected) for m in compare(short, long)] == [(1, -1), (2, -1)]

    def test_refuses_to_compare_different_pins(self):
        with pytest.raises(ValueError):
            compare(Trace((0,), (0,)), Trace((1,), (0,)))

    def test_mismatch_report_is_readable(self):
        expected = Trace((0, 1), (0b01, 0b11))
        report = format_mismatches(expected, compare(expected, Trace((0, 1), (0b01, 0b10))))

        assert "cycle 1: expected 11, actual 10" in report


class TestGolden:
    def test_round_trips_through_file(self, tmp_path):
        golden = Golden("c", "hand-derived", Trace((0,), (1, 0)), notes="n")
        path = tmp_path / "c.json"

        save_golden(path, golden)

        assert load_golden(path) == golden

    def test_rejects_unknown_source(self):
        with pytest.raises(ValueError):
            Golden("c", "guess", Trace((0,), (0,)))


class TestEmulatorRunner:
    def test_trace_has_requested_length_even_when_delay_overshoots(self):
        # "set pins, 1 [31]" keeps the pin high far beyond the 4 requested cycles
        case = make_case(
            program=["set pins, 1 [31]"],
            cycles=4,
            pin_directions=1,
            config={"set_count": 1},
        )

        assert run_on_emulator(case).values == (1, 1, 1, 1)

    def test_observed_pins_are_packed_in_listed_order(self):
        # "set pins, 3" drives GPIO 2 and 3
        case = make_case(
            program=["set pins, 3"],
            cycles=1,
            observed_pins=[3, 2],
            pin_directions=0b1100,
            config={"set_base": 2, "set_count": 2},
        )

        assert run_on_emulator(case).values == (0b11,)

    def test_stimulus_drives_input_pins_from_the_given_cycle(self):
        case = make_case(
            program=["nop"],
            cycles=4,
            stimulus=[[2, 1]],
        )

        assert run_on_emulator(case).values == (0, 0, 1, 1)


class TestFindRisingEdge:
    def test_finds_the_first_low_to_high_transition(self):
        assert find_rising_edge([0, 0, 0b100, 0b100, 0, 0b100], 2) == 2

    def test_ignores_other_channels(self):
        assert find_rising_edge([0b001, 0b011, 0b111], 2) == 2

    def test_a_pin_that_is_high_from_the_start_has_no_edge(self):
        with pytest.raises(ValueError):
            find_rising_edge([1, 1, 1], 0)

    def test_fails_when_the_pin_never_rises(self):
        with pytest.raises(ValueError):
            find_rising_edge([0, 0, 0], 0)


class TestSamplesToTrace:
    def test_takes_the_middle_of_each_cycle(self):
        # 4 samples per cycle; cycle 0 is visible from sample 2
        samples = [0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1]

        trace = samples_to_trace(
            samples,
            sample_rate=40e6,
            cycle_rate=10e6,
            first_cycle_sample=2,
            cycles=2,
            pins=[0],
        )

        assert trace.values == (1, 0)

    def test_extracts_and_reorders_channels(self):
        samples = [0b0101] * 8

        trace = samples_to_trace(
            samples,
            sample_rate=20e6,
            cycle_rate=10e6,
            first_cycle_sample=0,
            cycles=1,
            pins=[2, 1, 0],
        )

        assert trace.values == (0b101,)

    def test_rejects_undersampling(self):
        with pytest.raises(ValueError):
            samples_to_trace(
                [0] * 8,
                sample_rate=10e6,
                cycle_rate=10e6,
                first_cycle_sample=0,
                cycles=1,
                pins=[0],
            )

    def test_rejects_capture_that_is_too_short(self):
        with pytest.raises(ValueError):
            samples_to_trace(
                [0] * 4,
                sample_rate=40e6,
                cycle_rate=10e6,
                first_cycle_sample=0,
                cycles=2,
                pins=[0],
            )
