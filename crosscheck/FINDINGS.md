# Findings from the hardware cross-check

Every case in `cases/` was run on a Raspberry Pi Pico 2 (RP2350, MicroPython 1.29.0, state machine
at 5 MHz, observed with an Analog Discovery at 50 MHz) and the traces are the golden files. The
numbers in the first column refer to the probe IDs of
[docs/pio_sim-cross-check.md](../docs/pio_sim-cross-check.md), which found these by reading the
code; the hardware confirms each of them and adds three more. Nothing was fixed: the cases that
expose a difference carry `known_emulator_difference` and the golden test expects them to fail
(strictly, so the test fails once the emulator is fixed and the note has to go).

The hardware is an RP2350. The datasheet behaviour of the PIO is the same as the RP2040's in
every case below as far as the RP2040 datasheet says, but a difference between the two chips
would not show up here.

## Where pioemu differs from the hardware

| ID  | Case | Hardware | pioemu |
| :-- | :--- | :------- | :----- |
| D1  | `mov_bit_reverse` | `mov x, ::y` reverses: the top seven bits of 0xC0000000 reach the pins | plain copy |
| D2  | `mov_pins_uses_out_mapping` | `mov pins, x` writes the OUT group (GP10 - GP12 for OUT_BASE 10, count 3) | writes 32 bits from GPIO 0 |
| D3  | `pull_ifempty_noop_keeps_delay` | the no-op `pull ifempty [3]` still takes 4 cycles | 1 cycle |
| D4  | `push_iffull_noop_keeps_delay` | the no-op `push iffull [3]` still takes 4 cycles | 1 cycle |
| D5  | `pull_with_autopull_osr_full` | `pull` with autopull and a full OSR does nothing: the first word stays | loads the second word |
| D6  | `jmp_not_osre_uses_pull_threshold` | 20 bits out with PULL_THRESH 16 means empty: not taken | taken (compares with 32) |
| D7  | `mov_x_status` | `mov x, status` runs | the emulation ends |
| D7  | `out_exec`, `mov_exec` | the shifted-out instruction runs in the next cycle, then execution continues after the `out`/`mov` | the emulation ends |
| D10 | `autopull_refills_in_background` | the OSR is refilled on a `nop` cycle: `jmp !osre` is taken | not taken (refills only on `out`) |
| new | `wrap_top_at_address_zero` | a wrap range ending at address 0 keeps the program on that instruction | continues with the next instruction: `emulate()` reads `wrap_top=0` as "not given" |
| new | `autopush_stalls_when_rx_full` | the `in` that reaches the threshold stalls on a full RX FIFO: the fifth never completes | the fifth completes, the sixth stalls |
| new | `autopull_across_threshold` | the `out` that crosses the autopull threshold is followed by one extra cycle for the refill | no extra cycle |

## Where pioemu agrees with the hardware

`SET`, `OUT`, `MOV` (invert, `OSR`/`ISR`/`X`/`Y` moves), `IN` (left shift, 32 bits), `JMP` (all
conditions, `X--`/`Y--` decrementing when not taken, delay on taken and not taken jumps, a taken
jump at the wrap top), `PULL` (block, noblock copying X, `ifempty`), `PUSH` (block stalls and
noblock discards on a full RX FIFO), `OUT X/Y/ISR/PC`, delays up to 31 cycles, side-set (plain,
optional, two pins, over `SET` and `MOV PINS`, applied while the instruction stalls), wrap
targets, `IRQ` set/clear/wait and `WAIT IRQ` (clearing, stalling, delay). See `cases/`.

## What could not be observed

- **Input synchroniser** (datasheet 3.5.6.3): it adds two *system* clocks, not two PIO cycles, so
  at a 5 MHz state machine clock a pin that was just set is seen by the very next instruction
  (`jmp_pin_sees_self_driven_pin_at_once`, `wait_pin_sees_self_driven_pin_at_once`). Seeing the
  latency needs the state machine at full speed and an analyzer sampling at several hundred MHz.
- **`IN_BASE`** (D9) and pin ranges that wrap after GPIO 31: the runner does not configure
  `IN_BASE` and the pins are wired only for GP8 - GP14.
- **Flags changed from outside while a program runs** (I3, I4), `IRQ PREV/NEXT` (RP2350 only),
  `MOV PINDIRS`, FIFO joining, `OUT_STICKY`, `INLINE_OUT_EN`, `SIDE_PINDIR`: not supported by the
  case format yet.
- **Register contents**: only pin levels are visible, so values reach the pins through `OUT PINS`.
