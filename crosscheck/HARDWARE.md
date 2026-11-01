# Hardware setup

Equipment: a Raspberry Pi Pico 2 (RP2350) and a Digilent Analog Discovery (first generation,
16 digital I/O lines). Both are 3.3 V logic and compatible with each other.

## Wiring

GPn is connected to DIOn for every wire, so a case's GPIO numbers are also the analyzer
channels. The low eight lines are driven by the Analog Discovery, the high eight by the Pico.

| Pico 2 | Analog Discovery | Driven by | Purpose |
|---|---|---|---|
| GP0 - GP7 | DIO 0 - DIO 7 | Analog Discovery (pattern generator) | Stimulus read by the PIO program |
| GP8 - GP14 | DIO 8 - DIO 14 | Pico | Observed pins, recorded by the logic analyzer |
| GP15 | DIO 15 | Pico | Marker: its edge triggers the capture and aligns cycle 0 |
| GND (for example pin 3) | Ground | | Common reference |

```
Pico 2                         Analog Discovery
GP0..GP7   <------------------ DIO 0..7    (AD drives, Pico reads)
GP8..GP14  ------------------> DIO 8..14   (Pico drives, AD records)
GP15       ------------------> DIO 15      (marker / trigger)
GND        ------------------- GND
USB        ---> PC             USB ---> PC
```

Every wire has exactly one driver. A case must therefore keep GP0 - GP7 as inputs on the Pico
and GP8 - GP15 as outputs or unused. Stimulus that the Pico generates itself (a second state
machine) also goes on GP8 and above.

An optional 330 ohm - 1 kohm resistor in series with each wire protects against wiring mistakes.

## Checking the wiring

`python -m pytest crosscheck --hardware` starts with a wiring test (`test_wiring.py`, marked
`wiring`), which runs before every other test. It drives each of the sixteen wires on its own,
DIO0 - DIO7 from the Analog Discovery and GP8 - GP15 from the Pico, and reads the other side
back. A wire that is missing, on the wrong pin, shorted to another one, or stuck high each gives
a message of its own, for example `GP5 does not follow DIO5`. If the wiring test fails the whole
run stops, because nothing that follows would mean anything. Ground is checked implicitly: without
it the readings are not stable.

## Power

- Power the Pico from its own USB cable; that cable is also the serial link to the PC.
- Do not power the Pico from the Analog Discovery's supply while USB is connected.
- The Analog Discovery connects to the PC with its own USB cable for WaveForms and dwfpy.
- Connect at least one ground wire between the boards.

## Software

- Install the WaveForms runtime from Digilent; dwfpy only wraps it.
- `pip install dwfpy` (the `hardware` dependency group in `pyproject.toml`).
- Pico 2 runs MicroPython or other firmware that implements the case runner (not written yet).

## Flashing MicroPython with the Debug Probe

Connect the Raspberry Pi Debug Probe's SWD port to the Pico 2's three-pin DEBUG header
(SWCLK, GND, SWDIO) and keep the Pico powered over USB. Then:

```
python -m crosscheck.flash_micropython --dry-run   # show what would be done
python -m crosscheck.flash_micropython             # download, flash, reset
```

The script downloads the newest stable (non-RISC-V) Pico 2 build from micropython.org, converts
the UF2 to a flat binary and flashes it at 0x10000000 with [pyOCD](https://pyocd.io)
(`pip install pyocd`, in the `hardware` dependency group), which resets the board afterwards.
pyOCD only drives CMSIS-DAP, ST-Link and J-Link probes, so it never picks up the Analog
Discovery. With several probes connected, choose one with `--probe <unique id>` (see
`pyocd list`). Use `--file` for a UF2 you already have.

## Capture timing

- Run the state machine slowly, for example 10 MHz, so the analyzer takes several samples per
  state machine cycle. `analog_discovery.samples_to_trace()` needs at least two samples per
  cycle and samples in the middle of each cycle.
- The marker edge on GP15 triggers the capture. A second state machine in the same PIO block
  drives it, and `device_runner.start()` enables both state machines with one write to the PIO0
  control register so that they start on the same clock. The marker rises in cycle 0, so the
  trigger sample is taken to be the sample at which the effect of cycle 0 appears.
- The analyzer buffer limits the capture length: check `digital_input.buffer_size_max` for your
  device and keep `cycles * sample_rate / cycle_rate` below it.
- Stimulus: the pattern generator plays one bit per analyzer sample on DIO0 - DIO7. It is
  triggered by the analyzer's detector on the marker edge and starts a constant 9 samples
  (`PATTERN_LATENCY`, 180 ns) later. A stimulus change "from cycle N" is an edge half a cycle
  before cycle N starts, so the state machine sees it in cycle N and not in the cycle before.
  The analyzer records the driven pins as well, so every run checks that each edge landed within
  two samples of where it belongs and fails with a `StimulusTimingError` if it did not. The
  earliest cycle at which the stimulus can change is 2; an entry at cycle 0 gives the initial
  level.
- The pads of an RP2350 are isolated until a function is selected for them, and an isolated pad
  reads as low to the PIO. The runner therefore enables GP0 - GP7 as inputs with a pull-down, so
  a pin that nothing drives reads as low.

## Measured on this hardware

- The first-generation Analog Discovery's logic analyzer buffer holds 4096 samples; at 10 samples
  per state machine cycle a capture can cover roughly 400 cycles.
- The pattern generator reaches the pins 9 samples after the marker edge, every time.
- Both state machines start on the same clock (checked on the raw samples).
