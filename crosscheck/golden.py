import json
from dataclasses import dataclass
from pathlib import Path

from .trace import Trace

# Where a golden trace came from. Only 'hardware' traces are real cross-check references.
SOURCES = ("hardware", "hand-derived")


@dataclass(frozen=True)
class Golden:
    case: str
    source: str
    trace: Trace
    notes: str = ""

    def __post_init__(self):
        if self.source not in SOURCES:
            raise ValueError(f"golden source must be one of {SOURCES}, not {self.source!r}")


def golden_path(directory: Path, case_name: str) -> Path:
    return directory / f"{case_name}.json"


def load_golden(path: Path) -> Golden:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Golden(
        case=data["case"],
        source=data["source"],
        trace=Trace.from_dict(data["trace"]),
        notes=data.get("notes", ""),
    )


def save_golden(path: Path, golden: Golden) -> None:
    data = {
        "case": golden.case,
        "source": golden.source,
        "notes": golden.notes,
        "trace": golden.trace.to_dict(),
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
