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

## Power

- Power the Pico from its own USB cable; that cable is also the serial link to the PC.
- Do not power the Pico from the Analog Discovery's supply while USB is connected.
- The Analog Discovery connects to the PC with its own USB cable for WaveForms and dwfpy.
- Connect at least one ground wire between the boards.

## Software

- Install the WaveForms runtime from Digilent; dwfpy only wraps it.
- `pip install dwfpy` (the `hardware` dependency group in `pyproject.toml`).
- Pico 2 runs MicroPython or other firmware that implements the case runner (not written yet).

## Capture timing

- Run the state machine slowly, for example 10 MHz, so the analyzer takes several samples per
  state machine cycle. `analog_discovery.samples_to_trace()` needs at least two samples per
  cycle and samples in the middle of each cycle.
- The marker edge on GP15 triggers the capture. Ideally a second state machine in the same
  PIO block drives it and both are enabled with one write to the PIO control register, so
  that they start on the same clock.
- The analyzer buffer limits the capture length: check `digital_input.buffer_size_max` for your
  device and keep `cycles * sample_rate / cycle_rate` below it.
- Stimulus from the pattern generator runs on the Analog Discovery's clock, which is
  asynchronous to the state machine. Starting it from a trigger on the marker edge should fix
  its timing relative to the capture; until that is verified, only use stimulus cases with
  generous timing margins.

## Not yet verified on this hardware

- Logic levels have been confirmed compatible by the user; nothing has been connected or captured.
- The sample rate and buffer depth of the first-generation Analog Discovery.
- `capture()` in `analog_discovery.py` against this device.
- Triggering the pattern generator from the marker edge.
