# Hardware cross-check

Runs the same PIO scenarios on the emulator and on a real Pico 2, observed with an Analog
Discovery (via [dwfpy](https://dwfpy.readthedocs.io)), and compares per-cycle pin traces.

- `cases/*.json` - scenarios as data: the program as PIO assembly source (wrap and side-set come
  from its directives), state machine config, FIFO input and stimulus.
- `assembler.py` - assembles a case with `adafruit_pioasm` (dev dependency) into opcodes plus the
  settings implied by the directives.
- `golden/*.json` - expected pin traces. `source` is `hardware` (captured from the Pico 2) or
  `hand-derived` (worked out from the instruction semantics, to be replaced by a capture).
- `emulator.py` - runs a case with pioemu and produces a `Trace`.
- `analog_discovery.py` - `capture()` records the logic analyzer, `samples_to_trace()` reduces
  the raw samples to one value per state machine cycle.
- `test_golden_traces.py` - the emulator must reproduce every golden trace. No hardware needed.

```
python -m pytest crosscheck
```

Wiring and equipment are described in [HARDWARE.md](HARDWARE.md).

Tests marked `hardware` are skipped unless you pass `--hardware`:

```
python -m pytest crosscheck --hardware             # flashes MicroPython if the board lacks it
python -m pytest crosscheck --hardware --no-flash  # fail instead of flashing
```

At the start of a hardware run the `pico_port` fixture (`firmware.py`) looks for the board's
MicroPython serial port and asks what it runs. If MicroPython at least as new as
`flash_micropython.PINNED_VERSION` is there, nothing is flashed. Otherwise the pinned version is
flashed through the Debug Probe, overwriting whatever the board ran, so use a board dedicated
to this. A busy serial port, or a board that is not a Pico 2, stops the run without flashing.

## Not done yet

- The MicroPython runner that loads a case, configures the state machine and runs it. The
  firmware check and the serial (raw REPL) client exist, but have only been tested against fakes.
- A capture script tying the firmware and `capture()` together to write `source: hardware`
  golden traces, including calibration of `first_cycle_sample`.
- `capture()` has not been run against a real Analog Discovery.
- RP2350 differs slightly from RP2040 in PIO; only use cases within the common subset.
