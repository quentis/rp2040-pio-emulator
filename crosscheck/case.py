import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# The subset of emulate() keyword arguments a case may configure. They map one-to-one onto the
# state machine configuration that the hardware runner has to apply.
CONFIG_KEYS = frozenset(
    {
        "auto_pull",
        "auto_push",
        "pull_threshold",
        "push_threshold",
        "shift_isr_right",
        "shift_osr_right",
        "out_base",
        "out_count",
        "set_base",
        "set_count",
        "side_set_base",
        "side_set_count",
        "side_set_opt",
        "jmp_pin",
        "status_sel",
        "status_n",
        "wrap_target",
        "wrap_top",
    }
)

# Settings that the assembler derives from the program's directives.
PROGRAM_KEYS = frozenset({"side_set_count", "side_set_opt", "wrap_target", "wrap_top"})


@dataclass(frozen=True)
class Case:
    """
    A single PIO scenario, described as data so that the emulator and the hardware runner
    execute exactly the same thing.

    Attributes
    ----------
    name : str
        Unique identifier; also the file stem of the case and its golden trace.
    program : list[str]
        The PIO program as assembly source, one line per entry. Wrap and side-set settings
        come from its directives (.wrap_target, .wrap, .side_set), not from `config`.
    cycles : int
        Number of state machine clock cycles to run and record.
    observed_pins : list[int]
        GPIO numbers recorded in the trace (bit i of a trace value is observed_pins[i]).
    pin_directions : int
        Initial pin directions (bit set = output), as a GPIO bit mask.
    config : dict
        State machine configuration, restricted to CONFIG_KEYS.
    tx_fifo : list[int]
        Words pushed into the TX FIFO before the state machine starts.
    stimulus : list[list[int]]
        [cycle, pin_values] pairs: from the given cycle onwards the externally driven pins
        take the given GPIO bit mask value. Empty if nothing drives the pins externally.
    known_emulator_difference : str
        Non-empty if pioemu is known not to reproduce the golden trace; says why. The golden
        test then expects the emulator to fail (strictly: it fails once the emulator is fixed,
        as the cue to remove this note).
    """

    name: str
    program: list[str]
    cycles: int
    observed_pins: list[int]
    description: str = ""
    pin_directions: int = 0
    config: dict[str, int | bool] = field(default_factory=dict)
    tx_fifo: list[int] = field(default_factory=list)
    stimulus: list[list[int]] = field(default_factory=list)
    known_emulator_difference: str = ""

    def __post_init__(self):
        unknown = set(self.config) - CONFIG_KEYS
        if unknown:
            raise ValueError(f"unknown config keys in case {self.name!r}: {sorted(unknown)}")

        from_program = set(self.config) & PROGRAM_KEYS
        if from_program:
            raise ValueError(
                f"case {self.name!r} sets {sorted(from_program)} in config; "
                "use the program's directives instead"
            )

        if self.cycles < 1:
            raise ValueError(f"case {self.name!r} must run at least one cycle")

        if not self.observed_pins or any(not 0 <= p <= 31 for p in self.observed_pins):
            raise ValueError(f"case {self.name!r} has invalid observed_pins")

        if len(set(self.observed_pins)) != len(self.observed_pins):
            raise ValueError(f"case {self.name!r} observes a pin twice")

    @property
    def source(self) -> str:
        return "\n".join(self.program) + "\n"

    @property
    def observed_mask(self) -> int:
        return sum(1 << pin for pin in self.observed_pins)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Case":
        return cls(**data)


def load_case(path: Path) -> Case:
    return Case.from_dict(json.loads(path.read_text(encoding="utf-8")))


def load_cases(directory: Path) -> list[Case]:
    cases = [load_case(path) for path in sorted(directory.glob("*.json"))]

    names = [case.name for case in cases]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate case names in {directory}")

    return cases
