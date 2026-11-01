"""
Runs cases on the Pico 2 and compares what the Analog Discovery saw with the committed golden
traces; with --write the captured traces replace the golden files (source: hardware).

    python -m crosscheck.capture_golden                  # check all cases against their goldens
    python -m crosscheck.capture_golden set_pins_toggle  # check one case
    python -m crosscheck.capture_golden --write          # record hardware traces as goldens

The board is flashed with MicroPython first if it has none (see firmware.py); --no-flash
forbids that.
"""
import argparse
import sys
from pathlib import Path

from . import hardware
from .case import load_cases
from .emulator import run_on_emulator
from .firmware import ensure_micropython
from .golden import Golden, golden_path, load_golden, save_golden
from .pico import query_firmware
from .trace import compare, format_mismatches

HERE = Path(__file__).parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("cases", nargs="*", help="names of the cases to run (default: all)")
    parser.add_argument("--write", action="store_true", help="save the captured traces as goldens")
    parser.add_argument("--no-flash", action="store_true", help="never flash the board")
    args = parser.parse_args(argv)

    cases = load_cases(HERE / "cases")
    if args.cases:
        unknown = set(args.cases) - {case.name for case in cases}
        if unknown:
            parser.error(f"unknown cases: {sorted(unknown)}")
        cases = [case for case in cases if case.name in args.cases]

    port = ensure_micropython(allow_flash=not args.no_flash)
    firmware = query_firmware(port)
    notes = (
        f"Captured on {firmware.machine}, MicroPython {'.'.join(map(str, firmware.version))}; "
        f"state machine at {hardware.FREQ} Hz, analyzer at {hardware.SAMPLE_RATE:.0f} Hz."
    )

    differences = 0
    for case in cases:
        trace = hardware.run_on_hardware(case, port)
        path = golden_path(HERE / "golden", case.name)

        if not path.exists():
            if not args.write:
                print(f"{case.name}: no golden trace yet (use --write)")
                differences += 1
                continue

            against_golden = []
        else:
            against_golden = compare(load_golden(path).trace, trace)
        try:
            against_emulator = compare(run_on_emulator(case), trace)
            emulator_status = "emulator agrees" if not against_emulator else "emulator differs"
        except RuntimeError as error:  # the emulation ended early
            emulator_status = f"emulator failed ({error})"

        golden_status = (
            "matches golden" if not against_golden else f"{len(against_golden)} cycles differ from golden"
        )
        print(f"{case.name}: {golden_status}; {emulator_status}")
        if against_golden:
            print(format_mismatches(trace, against_golden))
            differences += 1

        if args.write:
            save_golden(path, Golden(case.name, "hardware", trace, notes))
            print(f"  wrote {path.name}")

    return 1 if differences and not args.write else 0


if __name__ == "__main__":
    sys.exit(main())
