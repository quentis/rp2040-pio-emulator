from dataclasses import dataclass


@dataclass(frozen=True)
class Trace:
    """
    Pin levels of one run, one entry per state machine clock cycle.

    values[i] holds the observed pins as they are once the instruction executed in cycle i has
    taken effect (and stays so through that instruction's delay cycles). Bit j of an entry is
    the level of observed_pins[j].
    """

    observed_pins: tuple[int, ...]
    values: tuple[int, ...]

    def to_dict(self) -> dict:
        return {"observed_pins": list(self.observed_pins), "values": list(self.values)}

    @classmethod
    def from_dict(cls, data: dict) -> "Trace":
        return cls(tuple(data["observed_pins"]), tuple(data["values"]))

    def pin_levels(self, pin: int) -> list[int]:
        bit = self.observed_pins.index(pin)
        return [(value >> bit) & 1 for value in self.values]


@dataclass(frozen=True)
class Mismatch:
    cycle: int
    expected: int
    actual: int


def compare(expected: Trace, actual: Trace) -> list[Mismatch]:
    """Returns every cycle at which the traces differ; a length difference counts too."""
    if expected.observed_pins != actual.observed_pins:
        raise ValueError("traces observe different pins")

    mismatches = [
        Mismatch(cycle, e, a)
        for cycle, (e, a) in enumerate(zip(expected.values, actual.values))
        if e != a
    ]

    # Missing cycles are reported with -1 on the side that lacks them.
    for cycle in range(len(actual.values), len(expected.values)):
        mismatches.append(Mismatch(cycle, expected.values[cycle], -1))
    for cycle in range(len(expected.values), len(actual.values)):
        mismatches.append(Mismatch(cycle, -1, actual.values[cycle]))

    return mismatches


def format_mismatches(trace: Trace, mismatches: list[Mismatch], limit: int = 10) -> str:
    width = len(trace.observed_pins)

    def bits(value: int) -> str:
        return "missing" if value < 0 else format(value, f"0{width}b")

    lines = [f"pins (msb first): {list(reversed(trace.observed_pins))}"]
    lines += [
        f"cycle {m.cycle}: expected {bits(m.expected)}, actual {bits(m.actual)}"
        for m in mismatches[:limit]
    ]
    if len(mismatches) > limit:
        lines.append(f"... and {len(mismatches) - limit} more")

    return "\n".join(lines)
