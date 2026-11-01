# Copyright 2025 Nathan Young
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from collections import deque

import pytest

from pioemu import State, clock_cycles_reached, emulate
from pioemu.shift_register import ShiftRegister

from ..opcodes import Opcodes
from ..support import instruction_param


# fmt: off
@pytest.mark.parametrize(
    "opcode, initial_state, expected_state",
    [
        # Test PIO stalls when auto-pull threshold reached with empty FIFO
        instruction_param(
            "out pins, 32",
            0x6000,
            State(pin_values=0xFFFF_FFFF, transmit_fifo=deque(), output_shift_register=ShiftRegister(0, 32)),
            State(pin_values=0xFFFF_FFFF, transmit_fifo=deque(), output_shift_register=ShiftRegister(0, 32)),
            expected_program_counter=0,  # Should stall when threshold reached
        ),

        # Test PIO stalls when auto-pull threshold reached with non-empty FIFO
        instruction_param(
            "out pins, 32",
            0x6000,
            State(pin_values=0xFFFF_FFFF, transmit_fifo=deque([0xAAAA_AAAA]), output_shift_register=ShiftRegister(0, 32)),
            State(pin_values=0xFFFF_FFFF, transmit_fifo=deque(), output_shift_register=ShiftRegister(0xAAAA_AAAA, 0)),
            expected_program_counter=0,  # Should stall when threshold reached
        ),

        # Test OSR is empty, and not yet refilled, after the last bits are shifted out
        instruction_param(
            "out pins, 8",
            0x6008,
            State(pin_values=0xFFFF_FFFF, transmit_fifo=deque([0xAAAA_AAAA]), output_shift_register=ShiftRegister(0xFF, 24)),
            State(pin_values=0x0000_00FF, transmit_fifo=deque([0xAAAA_AAAA]), output_shift_register=ShiftRegister(0, 32)),
        ),

        # Test PULL is a no-op while the OSR is full
        instruction_param(
            "pull block",
            0x80A0,
            State(transmit_fifo=deque([0xBB]), output_shift_register=ShiftRegister(0xAA, 0)),
            State(transmit_fifo=deque([0xBB]), output_shift_register=ShiftRegister(0xAA, 0)),
        ),

        # Test the no-op PULL does not stall when the FIFO is empty
        instruction_param(
            "pull block",
            0x80A0,
            State(transmit_fifo=deque(), output_shift_register=ShiftRegister(0xAA, 0)),
            State(transmit_fifo=deque(), output_shift_register=ShiftRegister(0xAA, 0)),
        ),

        # Test PULL replaces the OSR once any bit has been shifted out of it
        instruction_param(
            "pull block",
            0x80A0,
            State(transmit_fifo=deque([0xBB]), output_shift_register=ShiftRegister(0xAA, 3)),
            State(transmit_fifo=deque(), output_shift_register=ShiftRegister(0xBB, 0)),
        ),
    ]
)
# fmt: on
def test_auto_pull(opcode: int, initial_state: State, expected_state: State):
    _, new_state = next(
        emulate(
            [opcode, Opcodes.nop()],
            initial_state=initial_state,
            stop_when=clock_cycles_reached(1),
            auto_pull=True,
        )
    )

    assert new_state == expected_state


def test_auto_pull_refills_the_osr_in_the_cycle_after_it_empties():
    # The second OUT finds the OSR empty and stalls for the cycle in which it is refilled.
    out_pins_8 = 0x6008

    states = [
        state
        for _, state in emulate(
            [out_pins_8, out_pins_8],
            initial_state=State(
                transmit_fifo=deque([0xAAAA_AAAA]),
                output_shift_register=ShiftRegister(0xFF, 24),
            ),
            stop_when=clock_cycles_reached(3),
            auto_pull=True,
        )
    ]

    assert [(state.program_counter, state.output_shift_register) for state in states] == [
        (1, ShiftRegister(0, 32)),
        (1, ShiftRegister(0xAAAA_AAAA, 0)),
        (0, ShiftRegister(0x00AA_AAAA, 8)),
    ]
    assert states[2].pin_values == 0xAA


def test_auto_pull_refills_the_osr_during_a_cycle_that_does_not_use_it():
    _, new_state = next(
        emulate(
            [Opcodes.nop(), Opcodes.nop()],
            initial_state=State(transmit_fifo=deque([0xCC]), output_shift_register=ShiftRegister(0, 32)),
            stop_when=clock_cycles_reached(1),
            auto_pull=True,
        )
    )

    assert new_state.output_shift_register == ShiftRegister(0xCC, 0)
    assert new_state.transmit_fifo == deque()


def test_auto_pull_does_not_refill_the_osr_a_second_time_when_the_instruction_pulls():
    pull_block = 0x80A0

    _, new_state = next(
        emulate(
            [pull_block, Opcodes.nop()],
            initial_state=State(transmit_fifo=deque([1, 2]), output_shift_register=ShiftRegister(0, 32)),
            stop_when=clock_cycles_reached(1),
            auto_pull=True,
        )
    )

    assert new_state.output_shift_register == ShiftRegister(1, 0)
    assert new_state.transmit_fifo == deque([2])


def test_jmp_not_osre_sees_an_osr_that_is_about_to_be_refilled_as_not_empty():
    out_null_8 = 0x6068
    jmp_not_osre_3 = 0x00E3

    states = [
        state
        for _, state in emulate(
            [out_null_8, jmp_not_osre_3, Opcodes.nop(), Opcodes.nop()],
            initial_state=State(transmit_fifo=deque([1]), output_shift_register=ShiftRegister(0xFF, 0)),
            stop_when=clock_cycles_reached(2),
            auto_pull=True,
            pull_threshold=8,
        )
    ]

    assert [state.program_counter for state in states] == [1, 3]


def test_jmp_not_osre_sees_an_empty_osr_as_empty_when_there_is_nothing_to_refill_it():
    out_null_8 = 0x6068
    jmp_not_osre_3 = 0x00E3

    states = [
        state
        for _, state in emulate(
            [out_null_8, jmp_not_osre_3, Opcodes.nop(), Opcodes.nop()],
            initial_state=State(transmit_fifo=deque(), output_shift_register=ShiftRegister(0xFF, 0)),
            stop_when=clock_cycles_reached(2),
            auto_pull=True,
            pull_threshold=8,
        )
    ]

    assert [state.program_counter for state in states] == [1, 2]
