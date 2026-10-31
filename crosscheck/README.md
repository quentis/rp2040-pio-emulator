# Hardware cross-check

Runs the same PIO scenarios on the emulator and on a real Pico 2, observed with an Analog
Discovery (via [dwfpy](https://dwfpy.readthedocs.io)), and compares per-cycle pin traces.

- `cases/*.json` - scenarios as data (program, state machine config, FIFO input, stimulus).
- `golden/*.json` - expected pin traces. `source` is `hardware` (captured from the Pico 2) or
  `hand-derived` (worked out from the instruction semantics, to be replaced by a capture).
- `emulator.py` - runs a case with pioemu and produces a `Trace`.
- `analog_discovery.py` - `capture()` records the logic analyzer, `samples_to_trace()` reduces
  the raw samples to one value per state machine cycle.
- `test_golden_traces.py` - the emulator must reproduce every golden trace. No hardware needed.

```
python -m pytest crosscheck
```

## Not done yet

- Pico 2 firmware that loads a case over USB/UART, configures the state machine and runs it.
- A capture script tying the firmware and `capture()` together to write `source: hardware`
  golden traces, including calibration of `first_cycle_sample`.
- `capture()` has not been run against a real Analog Discovery.
- RP2350 differs slightly from RP2040 in PIO; only use cases within the common subset.
