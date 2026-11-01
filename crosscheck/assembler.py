from dataclasses import dataclass

import adafruit_pioasm

from .case import Case


@dataclass(frozen=True)
class AssembledProgram:
    opcodes: list[int]
    # State machine settings given by the program's directives, as emulate() keyword arguments.
    config: dict[str, int | bool]


def assemble(case: Case) -> AssembledProgram:
    """Assembles the case's program and extracts the settings its directives imply."""
    program = adafruit_pioasm.Program(case.source)
    settings = program.pio_kwargs

    # Without wrap directives the program wraps from its last instruction to its first.
    config: dict[str, int | bool] = {
        "wrap_target": settings.get("wrap_target", 0),
        "wrap_top": settings.get("wrap", len(program.assembled) - 1),
    }

    side_set_count = settings.get("sideset_pin_count", 0)
    if side_set_count:
        config["side_set_count"] = side_set_count
        config["side_set_opt"] = bool(settings.get("sideset_enable", False))

    return AssembledProgram(list(program.assembled), config)
