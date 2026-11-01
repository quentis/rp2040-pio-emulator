"""
Runs on the Pico 2 under MicroPython; sent to the board by crosscheck.hardware, never imported
on the PC (except by the unit tests, which substitute fake `rp2` and `machine` modules).

setup() takes a plain-data description of the state machines (built by crosscheck.hardware),
start() enables the case's state machine and a marker state machine, and restarts their clock
dividers, with one register write so that they begin on the same clock; stop() disables them.
"""
import machine
import rp2
from array import array

PIO0_CTRL = 0x50200000  # PIO0 CTRL register; SM_ENABLE is bits 3:0
CASE_SM = 0
MARKER_SM = 1

_machines = []


def _state_machine(sm_id, description, freq):
    program = [
        array("H", description["opcodes"]),
        -1,  # load offsets in PIO0, PIO1 and PIO2: not loaded yet
        -1,
        -1,
        description["execctrl"],
        description["shiftctrl"],
        description["out_init"],
        description["set_init"],
        description["sideset_init"],
    ]
    return rp2.StateMachine(sm_id, program, freq=freq, **description["pins"])


def setup(spec):
    stop()
    rp2.PIO(0).remove_program()

    case_sm = _state_machine(CASE_SM, spec["case"], spec["freq"])
    marker_sm = _state_machine(MARKER_SM, spec["marker"], spec["freq"])

    for word in spec["tx_fifo"]:
        case_sm.put(word)

    _machines[:] = [case_sm, marker_sm]


def start():
    # One write enables both state machines and restarts both clock dividers (CTRL bits 11:8).
    # The dividers free-run, so without the restart the two would start up to a cycle apart.
    enable = (1 << CASE_SM) | (1 << MARKER_SM)
    machine.mem32[PIO0_CTRL] = machine.mem32[PIO0_CTRL] | enable | (enable << 8)


def stop():
    for sm in _machines:
        sm.active(0)
