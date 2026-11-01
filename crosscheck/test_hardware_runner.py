"""Tests of the hardware run, with fake board, serial port and analyzer."""
import importlib.util
import sys
from pathlib import Path

import pytest

from . import hardware
from .case import Case, load_cases
from .hardware import build_spec, run_on_hardware, validate
from .pico import RawRepl
from .test_pico import BANNER, FakeStream

HERE = Path(__file__).parent


def make_case(**overrides) -> Case:
    fields = dict(
        name="c",
        program=["set pins, 1"],
        cycles=4,
        observed_pins=[8],
        pin_directions=1 << 8,
        config={"set_base": 8, "set_count": 1},
    )
    fields.update(overrides)
    return Case(**fields)


class TestBuildSpec:
    def test_describes_program_and_pins(self):
        spec = build_spec(make_case())

        assert spec["case"]["opcodes"] == [0xE001]
        assert spec["case"]["pins"] == {"set_base": 8}
        assert spec["case"]["set_init"] == [0b10]  # output, low
        assert spec["freq"] == hardware.FREQ

    def test_pin_direction_follows_the_case(self):
        case = make_case(config={"set_base": 8, "set_count": 2}, pin_directions=1 << 9)

        assert build_spec(case)["case"]["set_init"] == [0b00, 0b10]

    def test_wrap_goes_into_execctrl(self):
        case = make_case(program=["nop", ".wrap_target", "nop", "nop", ".wrap"])

        execctrl = build_spec(case)["case"]["execctrl"]

        assert (execctrl >> 12) & 0x1F == 2  # wrap top
        assert (execctrl >> 7) & 0x1F == 1  # wrap bottom

    def test_side_set_goes_into_pins_and_execctrl(self):
        case = make_case(
            program=[".side_set 1 opt", "nop side 1"],
            config={"side_set_base": 9},
            pin_directions=1 << 9,
            observed_pins=[9],
        )

        spec = build_spec(case)["case"]

        assert spec["pins"] == {"sideset_base": 9}
        assert spec["sideset_init"] == [0b10]
        assert spec["execctrl"] >> 30 & 1 == 1

    def test_shift_settings_go_into_shiftctrl(self):
        case = make_case(
            config={
                "set_base": 8,
                "set_count": 1,
                "auto_pull": True,
                "pull_threshold": 8,
                "push_threshold": 32,
                "shift_osr_right": False,
            }
        )

        shiftctrl = build_spec(case)["case"]["shiftctrl"]

        assert (shiftctrl >> 25) & 0x1F == 8  # pull threshold
        assert (shiftctrl >> 20) & 0x1F == 0  # push threshold 32 is encoded as 0
        assert (shiftctrl >> 19) & 1 == 0  # OSR shifts left
        assert (shiftctrl >> 18) & 1 == 1  # ISR shifts right (default)
        assert (shiftctrl >> 17) & 1 == 1  # autopull
        assert (shiftctrl >> 16) & 1 == 0  # no autopush

    def test_marker_state_machine_uses_the_marker_pin(self):
        marker = build_spec(make_case())["marker"]

        assert marker["pins"] == {"set_base": hardware.MARKER_PIN}
        assert marker["set_init"] == [0b10]

    @pytest.mark.parametrize(
        "overrides",
        [
            {"stimulus": [[1, 1]]},
            {"tx_fifo": [1, 2, 3, 4, 5]},
            {"observed_pins": [0]},
            {"observed_pins": [15]},
            {"pin_directions": 1},
            {"config": {"set_base": 14, "set_count": 2}},
            {"config": {"set_base": 8}},
        ],
    )
    def test_rejects_cases_that_cannot_run_on_this_wiring(self, overrides):
        with pytest.raises(ValueError):
            build_spec(make_case(**overrides))

    def test_every_committed_case_can_run_on_hardware(self):
        for case in load_cases(HERE / "cases"):
            validate(case)
            build_spec(case)


class TestRunOnHardware:
    def make_repl(self, executed: list[str]):
        class Repl(RawRepl):
            def exec(self, code: str) -> str:
                executed.append(code)
                return ""

        return lambda _port: Repl(FakeStream(BANNER))

    def test_sets_up_starts_and_stops_the_board_around_the_capture(self):
        executed: list[str] = []
        case = make_case(cycles=2)

        def capture(*, start, sample_count, **_):
            executed.append("<capture begins>")
            start()
            executed.append("<capture ends>")
            return [0b1 << 8] * sample_count

        trace = run_on_hardware(case, "COM7", open_repl=self.make_repl(executed), capture=capture)

        assert [e for e in executed if e.startswith("<") or e in ("start()", "stop()")] == [
            "<capture begins>",
            "start()",
            "<capture ends>",
            "stop()",
        ]
        assert "def setup" in executed[0]
        assert executed[1].startswith("setup({")
        assert trace.observed_pins == (8,)
        assert trace.values == (1, 1)

    def test_stops_the_board_even_if_the_capture_fails(self):
        executed: list[str] = []

        def capture(**_):
            raise TimeoutError("not triggered")

        with pytest.raises(TimeoutError):
            run_on_hardware(
                make_case(), "COM7", open_repl=self.make_repl(executed), capture=capture
            )

        assert executed[-1] == "stop()"

    def test_requests_enough_samples_for_the_case(self):
        requested = {}

        def capture(*, sample_count, prefill, **_):
            requested.update(sample_count=sample_count, prefill=prefill)
            return [0] * sample_count

        run_on_hardware(
            make_case(cycles=10), "COM7", open_repl=self.make_repl([]), capture=capture
        )

        per_cycle = hardware.SAMPLE_RATE / hardware.FREQ
        assert requested["sample_count"] >= requested["prefill"] + 10 * per_cycle


class FakeStateMachine:
    def __init__(self, sm_id, program, freq, **pins):
        self.sm_id, self.program, self.freq, self.pins = sm_id, program, freq, pins
        self.fifo: list[int] = []
        self.enabled = None

    def put(self, word):
        self.fifo.append(word)

    def active(self, value):
        self.enabled = value


class FakePio:
    removed = 0

    def __init__(self, index):
        assert index == 0

    def remove_program(self):
        FakePio.removed += 1


class FakeMem32(dict):
    def __missing__(self, key):
        return 0


@pytest.fixture
def device_runner(monkeypatch):
    """Imports device_runner.py against fake rp2 and machine modules."""
    from types import SimpleNamespace

    FakePio.removed = 0
    fake_machine = SimpleNamespace(mem32=FakeMem32())
    fake_rp2 = SimpleNamespace(StateMachine=FakeStateMachine, PIO=FakePio)
    monkeypatch.setitem(sys.modules, "machine", fake_machine)
    monkeypatch.setitem(sys.modules, "rp2", fake_rp2)

    spec = importlib.util.spec_from_file_location("device_runner", HERE / "device_runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, fake_machine


class TestDeviceRunner:
    def test_setup_creates_both_state_machines_and_fills_the_fifo(self, device_runner):
        module, _ = device_runner

        module.setup(build_spec(make_case(tx_fifo=[7, 9])))

        case_sm, marker_sm = module._machines
        assert (case_sm.sm_id, marker_sm.sm_id) == (0, 1)
        assert list(case_sm.program[0]) == [0xE001]
        assert case_sm.program[1:4] == [-1, -1, -1]
        assert case_sm.pins == {"set_base": 8}
        assert case_sm.fifo == [7, 9]
        assert marker_sm.pins == {"set_base": 15}
        assert case_sm.freq == marker_sm.freq == hardware.FREQ
        assert FakePio.removed == 1

    def test_start_enables_both_state_machines_with_one_write(self, device_runner):
        module, fake_machine = device_runner

        module.start()

        assert fake_machine.mem32[module.PIO0_CTRL] == 0b11

    def test_start_keeps_other_enabled_state_machines(self, device_runner):
        module, fake_machine = device_runner
        fake_machine.mem32[module.PIO0_CTRL] = 0b1000

        module.start()

        assert fake_machine.mem32[module.PIO0_CTRL] == 0b1011

    def test_stop_deactivates_the_state_machines(self, device_runner):
        module, _ = device_runner
        module.setup(build_spec(make_case()))

        module.stop()

        assert [sm.enabled for sm in module._machines] == [0, 0]
