# Cross-check against pio_sim

A comparison of this emulator (`pioemu`) with [pio_sim](https://github.com/ice458/pio_sim), a browser-based PIO
simulator, using the RP2040 datasheet as the tie-breaker. The focus is the `IRQ` instruction; the rest of the
functionality is covered afterwards.

|           |                                                                                                   |
| :-------- | :------------------------------------------------------------------------------------------------ |
| Date      | 2026-10-28                                                                                        |
| pioemu    | branch `dev` at `4dd5f12`: `upstream/main` (`abd90e0`) plus the IRQ, WAIT IRQ and disassembler commits |
| pio_sim   | `ice458/pio_sim` at `45e4a3d`                                                                     |
| Reference | RP2040 Datasheet (RP-008371-DS-1), chapter 3; section numbers below refer to it                   |

Legend: ✓ matches the datasheet · ✗ deviates from it or is unsupported · † judged from reading the source only

## Summary

The `IRQ` instruction itself behaves the same in the datasheet, pioemu and pio_sim: set and clear, `irq wait`,
the auto-clear of `wait 1 irq`, and REL on state machine 0. The differences are around it: who can change the
flags while a program runs, how PREV/NEXT and other unusual encodings are handled, and whether time advances per
instruction or per clock cycle.

Outside IRQ, several pioemu behaviours deviate from the datasheet (`MOV` bit-reverse, `MOV PINS` pin mapping,
delay after a no-op `PULL IFEMPTY`/`PUSH IFFULL`, `PULL` with autopull, `JMP !OSRE` threshold, background autopull,
`MOV STATUS`). pio_sim has its own deviations (side-set priority, `OUT_COUNT`, `wait ... irq prev|next`).

## How this was checked

- Both implementations were read in full and compared with the datasheet text.
- Rows marked with a probe ID (`I1`…, `D1`…) were reproduced by running pioemu; the programs are listed in the
  [appendix](#appendix-probe-programs).
- **pio_sim was not executed.** Everything attributed to it (†) comes from reading its source at the commit above.
- Only the RP2040 datasheet was consulted. RP2350-only behaviour (PREV/NEXT, JMPPIN, `mov rxfifo`, `MOV PINDIRS`)
  was not checked against the RP2350 datasheet.

## IRQ

| Behaviour                                                                                                     | pioemu                             | pio_sim †                                              |
| :------------------------------------------------------------------------------------------------------------ | :--------------------------------- | :----------------------------------------------------- |
| `irq set` / `irq clear`; Clear overrides Wait (§3.4.9.2)                                                      | ✓                                  | ✓                                                      |
| `irq wait` raises the flag once, stalls until it is lowered, delay cycles start afterwards (§3.4.9.2, §3.2.4) | ✓ — I1, I6                         | ✓                                                      |
| `wait 1 irq` clears the flag when satisfied, `wait 0 irq` leaves it alone (§3.4.3.2)                          | ✓ — I2                             | ✓                                                      |
| REL index (state machine ID added to the two low bits; same as direct for state machine 0)                    | ✓                                  | ✓ (the `rel` flag is parsed but not used)              |
| Flags changed from outside while the program runs, e.g. by another state machine or an interrupt handler (§3.2.6) | ✗ — see below                  | ✓ — flags can be toggled at any time (`main.js:116`)   |
| PREV/NEXT index modes (RP2350)                                                                                | ✗ — see below                      | partial — see below                                    |
| Time base                                                                                                     | one step per instruction; delay cycles advance `clock` in a single jump | one step per clock cycle |

### pioemu

- `irq_handler` is called only when an `IRQ` instruction executes
  ([instruction_decoder.py:263](../pioemu/instruction_decoder.py#L263)). A `wait 0 irq` or `wait 1 irq` that
  stalls therefore cannot be released from outside: the program stays on the `WAIT` and the handler is never
  called (I3). Flags can only be seeded through `State(irq_flags=...)` or changed by earlier instructions of the
  same program.
- When the instruction stalls, anything the handler changed other than `irq_flags` is discarded; it is kept only
  on the cycle that completes the instruction (I4).
- `WAIT IRQ` decoding ([instruction_decoder.py:415](../pioemu/instruction_decoder.py#L415)) masks the index with
  `0x0F`, but the field is three bits plus REL. `WAIT` source 3 is also routed into the IRQ branch
  ([instruction_decoder.py:402](../pioemu/instruction_decoder.py#L402)). RP2350 encodings (PREV, NEXT, JMPPIN) are
  therefore treated as flag 8–15 or flag 0 and stall forever (I5), whereas `irq` with PREV/NEXT stops the
  generator ([decoding/instruction_decoder.py:161](../pioemu/decoding/instruction_decoder.py#L161)).

### pio_sim †

- `irq prev|next <n>` sets and clears separate `irqPrev`/`irqNext` words that nothing else can reach
  (`pio_emulator.js:650-688`).
- `wait 1 irq prev 2` assembles silently as `wait 1 irq 2`: `parseWait` only recognises `rel`
  (`pio_assembler.js:295-303`), so the prev/next branches in `executeWait` (`pio_emulator.js:334-346`) are
  unreachable.

## Everything else

| Area                                                                  | pioemu                                                                                                                      | pio_sim †                                                                                                       | Datasheet                         |
| :-------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------- | :-------------------------------- |
| `MOV` bit-reverse (`::`)                                              | ✗ behaves as a plain copy, as does the reserved operation 3 ([instruction_decoder.py:301](../pioemu/instruction_decoder.py#L301)) — D1 | ✓                                                                                                               | §3.4.8.2                          |
| `MOV PINS` destination uses the OUT pin mapping                       | ✗ always from GPIO 0, 32 bits ([instruction_decoder.py:170](../pioemu/instruction_decoder.py#L170)) — D2                     | partial: starts at `OUT_BASE` but writes 32 bits                                                                | §3.4.8.2                          |
| Delay cycles after a `PULL IFEMPTY` / `PUSH IFFULL` that does nothing | ✗ delay skipped ([emulation.py:314](../pioemu/emulation.py#L314)) — D3, D4                                                   | ✓                                                                                                               | §3.2.4 (only a stall defers the delay) |
| `PULL` while autopull is on and the OSR is full                       | ✗ pulls anyway and overwrites the OSR ([instructions/pull.py](../pioemu/instructions/pull.py)) — D5                          | ✓ no-op (`pio_emulator.js:545-550`)                                                                             | §3.4.7.2 note, §3.5.4.2           |
| `JMP !OSRE` uses `PULL_THRESH`                                        | ✗ compares with 32 ([conditions.py:82](../pioemu/conditions.py#L82)) — D6                                                    | ✓ (`pio_emulator.js:315`)                                                                                       | §3.4.2.2                          |
| Autopull refills the OSR on non-OUT cycles                            | ✗ only when an `OUT` executes ([emulation.py:344-357](../pioemu/emulation.py#L344)) — D10                                    | ✓ (`backgroundAutopull`, `pio_emulator.js:100-105`)                                                             | §3.5.4.2                          |
| Side-set takes precedence over OUT/SET on the same pin                | ✓ — D8                                                                                                                      | ✗ side-set is applied before the instruction body, so SET/OUT overwrites it (`pio_emulator.js:196-218`, `262-264`) | §3.5.6                            |
| `PINCTRL_OUT_COUNT`                                                   | ✓                                                                                                                           | ✗ not modelled: `OUT PINS` writes exactly "bit count" pins, `MOV PINS` writes 32 (`pio_emulator.js:475-486`, `614-627`) | §3.4.5.2, §3.5.6                  |
| `IN_BASE` for `IN`, `MOV PINS` and `WAIT PIN`; pin ranges wrapping after GPIO 31 | ✗ (listed in the README) — D9                                                                                    | ✓                                                                                                               | §3.4.3.2, §3.4.4.2, §3.5.6        |
| `MOV x, STATUS` (`STATUS_SEL`, `STATUS_N`)                            | ✗ the generator ends without an error — D7                                                                                   | ✓                                                                                                               | §3.4.8.2                          |
| Side-set to pin directions (`SIDE_PINDIR`)                            | ✗                                                                                                                           | ✓                                                                                                               | §3.5.1                            |
| `OUT EXEC`, `MOV EXEC`                                                | ✗ the generator ends without an error — D7                                                                                   | ✗ reports "not supported"                                                                                       | §3.4.5.2, §3.4.8.2                |
| `IN STATUS`                                                           | rejected (the generator ends)                                                                                               | accepted, although IN source 5 is reserved (the pico-sdk's `pio_instructions.h` agrees)                         | §3.4.4.2                          |
| Input synchroniser (two extra cycles, engaged by default)             | not modelled                                                                                                                | optional per pin, bypassed by default (`pio_emulator.js:6-9`)                                                   | §3.5.6.3                          |

Not modelled by either simulator: FIFO joining (§3.5.3), clock dividers (§3.5.5), `OUT_STICKY`/`INLINE_OUT_EN`,
multiple state machines, and `MOV PINDIRS` (RP2350).

Only in pio_sim: an assembler, a GUI with a timing chart, and interactive editing of FIFOs, pins and IRQ flags.
Only in pioemu: a Python API suited to unit tests, `(before, after)` state pairs, and a disassembler.

## Disassembler

`pioemu/disassembly.py` (`disassemble`) has the following problems:

| Opcode                                          | Output           | Expected                                     |
| :---------------------------------------------- | :--------------- | :------------------------------------------- |
| `0xA032` (`mov x, ::y`)                         | `mov x, y`       | `mov x, ::y`                                 |
| `0xA081` (`mov exec, x`)                        | `mov None, x`    | `mov exec, x`                                |
| `0xE061` (`set` with reserved destination 3)    | `set None, 1`    | `ValueError`                                 |
| `0x20E0` (`wait` with source 3)                 | `IndexError`     | `ValueError`, like other undecodable opcodes |
| `0x20CA` (`wait 1 irq` with a PREV-coded index) | `wait 1 irq 10`  | rejected, or shown as PREV                   |

## Which findings are new code and which are old

- The `MOV`, delay, `PULL`/autopull, `JMP !OSRE`, background autopull and `MOV STATUS` findings are in code that the
  IRQ and disassembler commits did not touch (checked with `git diff upstream/main..dev`), so they also apply to
  `upstream/main`.
- The `WAIT IRQ` decoding, `irq_handler` behaviour and disassembler findings are in the new code.
- The README's "Known Limitations" already lists `IN_BASE`, pin wrapping, the `PULL IFEMPTY`/`PUSH IFFULL`
  thresholds, `OUT EXEC` and unimplemented `MOV` variants. It does not mention the `JMP !OSRE` threshold, which has
  the same cause.

## Appendix: probe programs

All probes ran on Python 3.12 against `4dd5f12` with this helper (`irq_handler` and `State` as described per row):

```python
from dataclasses import replace
from pioemu import State, emulate
from pioemu.shift_register import ShiftRegister


def run(opcodes, steps, **kwargs):
    generator = emulate(opcodes, stop_when=lambda *_: False, **kwargs)
    return [pair for _, pair in zip(range(steps), generator)]  # (before, after) states
```

| ID  | Opcodes (hex)                                   | Setup                                                                                       | Observed                                                                                          | Datasheet expects                                |
| :-- | :---------------------------------------------- | :------------------------------------------------------------------------------------------ | :------------------------------------------------------------------------------------------------ | :----------------------------------------------- |
| I1  | `C021 E027` (`irq wait 1`; `set x, 7`)          | handler lowers the flag on its second call                                                  | cycle 1 stalls with flags `0x02`; cycle 2 completes (pc 0→1, flags 0); `x` = 7 after cycle 3      | matches                                          |
| I2  | `20C2 E021` (`wait 1 irq 2`)                    | `irq_flags=0x04`                                                                            | completes in one cycle, flags → 0                                                                 | matches                                          |
| I3  | `2042` (`wait 0 irq 2`)                         | `irq_flags=0x04`; handler that lowers the flag                                              | stays at pc 0 for 6 cycles; the handler is called 0 times                                         | the wait ends when another agent lowers the flag |
| I4  | `C020 E021` (`irq wait 0`)                      | handler appends a word to the TX FIFO on every call and lowers the flag on its third call   | TX FIFO is `[]` after the two stall cycles and `[0x103]` after completion                         | —                                                |
| I5  | `20E0`, `20CA`, `20DA`, each followed by `E021` | `irq_flags=0x04`                                                                            | all three stall forever with the flag untouched; `20D2` (REL 2) completes and clears flag 2       | reserved / RP2350 encodings rejected             |
| I6  | `C320 E021` (`irq wait 0 [3]`; `set x, 1`)      | handler lowers the flag on its second call                                                  | clock 0→1 (stall), 1→5 (completion plus 3 delay cycles), 5→6 (`set`)                              | matches                                          |
| D1  | `E041 A032` (`set y, 1`; `mov x, ::y`)          |                                                                                             | `x` = `0x1`                                                                                       | `0x80000000`                                     |
| D2  | `E03F A001` (`set x, 31`; `mov pins, x`)        | `out_base=4, out_count=5`                                                                   | `pin_values` = `0x1f`                                                                             | `0x1f0`                                          |
| D3  | `83C0 E021` (`pull ifempty noblock [3]`)        | OSR = `ShiftRegister(0xAA, 0)`                                                              | clock is 1 after the first instruction                                                            | 4                                                |
| D4  | `8340 E021` (`push iffull noblock [3]`)         | empty ISR                                                                                   | clock is 1 after the first instruction (control `8380`, a `pull noblock [3]` that runs, gives 4)  | 4                                                |
| D5  | `80A0 E021` (`pull block`)                      | `auto_pull=True`; OSR = `ShiftRegister(0xAA, 0)`; TX FIFO = `[0xBB]`                        | OSR = `0xBB`, TX FIFO empty                                                                       | no-op: OSR stays `0xAA`, TX FIFO keeps `0xBB`    |
| D6  | `00E2 E021 E022` (`jmp !osre 2`)                | `pull_threshold=16`; OSR = `ShiftRegister(0xAA, 20)`                                        | jumps (pc 2)                                                                                      | falls through (pc 1): the OSR is empty           |
| D7  | `A025` (`mov x, status`); `60F0` (`out exec, 16`) | separate runs                                                                             | no states are yielded                                                                             | support, or an error                             |
| D8  | `F000` (`set pins, 0 side 1`)                   | `side_set_count=1, set_base=0, set_count=1`                                                 | `pin_values` = `0x1`                                                                              | `0x1` (side-set wins) — matches                  |
| D9  | `20A1 E021` (`wait 1 pin 1`)                    | input source returns `0b10`                                                                 | completes, i.e. waits on GPIO 1                                                                   | pin = `IN_BASE` + 1                              |
| D10 | `A042 00E3 E021 E022` (`nop`; `jmp !osre 3`)    | `auto_pull=True`; OSR = `ShiftRegister(0, 32)`; TX FIFO = `[0xCC]`                          | not taken (pc 2); OSR counter still 32; TX FIFO still `[0xCC]`                                    | taken (pc 3): the `nop` cycle refills the OSR    |
