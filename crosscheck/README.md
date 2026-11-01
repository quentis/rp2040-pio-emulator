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
- `hardware.py` - runs a case on the Pico 2: `build_spec()` turns the assembled case into
  plain data (EXECCTRL/SHIFTCTRL words, pin lists), `run_on_hardware()` sends it to the board
  and records the pins.
- `device_runner.py` - the MicroPython code that runs on the board. It loads the case on one
  state machine and a marker program on another, and enables both with a single write to the
  PIO control register so they start on the same clock.
- `capture_golden.py` - checks cases on hardware against their golden traces, or records them.
- `pico.py`, `firmware.py`, `flash_micropython.py` - serial link, firmware check, flashing.

A case whose golden trace pioemu does not reproduce can carry `known_emulator_difference` with the
reason; the golden test then expects it to fail, strictly. No case needs it at the moment.
[FINDINGS.md](FINDINGS.md) lists the differences the cases found, all since fixed, and what
they cover.

Cases that run on hardware must observe and drive GP8 - GP14 (see HARDWARE.md), configure their
OUT/SET/side-set pin groups explicitly, and use no stimulus yet.

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

To compare the board with the committed goldens, or to record hardware goldens:

```
python -m crosscheck.capture_golden            # check
python -m crosscheck.capture_golden --write    # record
```

## Not verified on hardware

Everything on the hardware side has so far been tested only against fakes:

- the raw REPL client, the firmware check and the flashing;
- that the board's PIO accepts the program lists `build_spec()` produces (the layout follows
  MicroPython's `rp2` module: instructions, three load offsets, EXECCTRL, SHIFTCTRL, pin lists);
- `capture()` on the first-generation Analog Discovery, including how its trigger position
  relates to `first_cycle_sample` (assumed: the trigger sample is the one where cycle 0 takes
  effect) and the size of its buffer;
- that the case and marker state machines really start on the same clock.

Not implemented: pin stimulus from the Analog Discovery's pattern generator, reading back
FIFO and register state, and the `IN` instruction (`in_base` is not a case setting). RP2350
differs slightly from RP2040 in PIO; only use cases within the common subset.
