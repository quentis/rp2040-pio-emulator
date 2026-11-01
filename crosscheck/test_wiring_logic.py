"""The logic of the wiring check, against simulated wiring faults; needs no hardware."""
from .wiring import INPUT_PINS, OUTPUT_PINS, check_wires


class SimulatedWires:
    """Drive pins on one side, sink pins on the other, joined by `connections`."""

    def __init__(self, pins, connections=None, stuck_high=0):
        self.connections = connections or {pin: {pin} for pin in pins}
        self.stuck_high = stuck_high
        self.driven = 0

    def drive(self, mask):
        self.driven = mask

    def read(self):
        seen = self.stuck_high
        for pin, sinks in self.connections.items():
            if (self.driven >> pin) & 1:
                seen |= sum(1 << sink for sink in sinks)

        return seen


def check(wires: SimulatedWires, pins=INPUT_PINS, source="DIO", sink="GP") -> list[str]:
    return check_wires(pins, wires.drive, wires.read, source, sink)


def test_correct_wiring_has_no_problems():
    assert check(SimulatedWires(INPUT_PINS)) == []
    assert check(SimulatedWires(OUTPUT_PINS), OUTPUT_PINS, "GP", "DIO") == []


def test_a_missing_wire_is_named():
    wires = SimulatedWires(INPUT_PINS)
    wires.connections[5] = set()

    assert check(wires) == ["GP5 does not follow DIO5 (not connected, or connected to another pin)"]


def test_every_missing_wire_is_reported():
    wires = SimulatedWires(INPUT_PINS)
    wires.connections[1] = set()
    wires.connections[6] = set()

    problems = check(wires)

    assert [p.split(" ")[0] for p in problems] == ["GP1", "GP6"]


def test_two_wires_shorted_together_are_reported_from_both_sides():
    wires = SimulatedWires(INPUT_PINS)
    wires.connections[2] = {2, 3}
    wires.connections[3] = {2, 3}

    problems = check(wires)

    assert "GP3 read high when only DIO2 is high (wires shorted or crossed)" in problems
    assert "GP2 read high when only DIO3 is high (wires shorted or crossed)" in problems
    assert len(problems) == 2


def test_crossed_wires_do_not_follow_and_light_the_other_pin():
    wires = SimulatedWires(INPUT_PINS)
    wires.connections[0] = {1}
    wires.connections[1] = {0}

    problems = check(wires)

    assert any("GP0 does not follow DIO0" in problem for problem in problems)
    assert any("GP1 does not follow DIO1" in problem for problem in problems)
    assert any("GP1 read high when only DIO0 is high" in problem for problem in problems)


def test_a_pin_that_is_stuck_high_is_reported_once_and_for_the_idle_state():
    wires = SimulatedWires(INPUT_PINS, stuck_high=1 << 4)

    problems = check(wires)

    assert problems[0] == (
        "GP4 read high while every DIO pin is low (stuck high, or shorted to a supply)"
    )


def test_names_follow_the_direction_of_the_wire():
    wires = SimulatedWires(OUTPUT_PINS)
    wires.connections[11] = set()

    problems = check(wires, OUTPUT_PINS, "GP", "DIO")

    assert problems == ["DIO11 does not follow GP11 (not connected, or connected to another pin)"]


def test_the_sources_are_left_low_afterwards():
    wires = SimulatedWires(INPUT_PINS)

    check(wires)

    assert wires.driven == 0


def test_pins_outside_the_checked_group_are_ignored():
    wires = SimulatedWires(INPUT_PINS, stuck_high=1 << 12)

    assert check(wires) == []


def test_the_pin_groups_match_the_wiring_document():
    assert INPUT_PINS == list(range(0, 8))
    assert OUTPUT_PINS == list(range(8, 16))
