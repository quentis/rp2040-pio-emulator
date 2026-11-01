# Copyright 2021, 2022, 2023 Nathan Young
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

from pioemu import ShiftRegister, State, clock_cycles_reached, emulate

from ..support import emulate_single_instruction, instruction_param

# fmt: off
instructions_to_test = [
    instruction_param(
        "mov pins null",
        0xA003,
        State(),
        State(pin_values=0x0000_0000),
    ),
    instruction_param(
        "mov x ~ osr",
        0xA02F,
        State(output_shift_register=ShiftRegister(0xFFFF_FFFF, 0)),
        State(output_shift_register=ShiftRegister(0xFFFF_FFFF, 0), x_register=0x0000_0000),
    ),
    instruction_param(
        "mov y y",
        0xA042,
        State(y_register=0xFFFF_FFFF),
        State(y_register=0xFFFF_FFFF),
    ),
    instruction_param(
        "mov osr x",
        0xA0E1,
        State(x_register=0xFFFF_FFFF),
        State(x_register=0xFFFF_FFFF, output_shift_register=ShiftRegister(0xFFFF_FFFF, 0)),
    ),
    instruction_param(
        "mov isr ~ pins",
        0xA0C8,
        State(pin_values=0x1_0000_0000),
        State(pin_values=0x1_0000_0000, input_shift_register=ShiftRegister(0xFFFF_FFFF, 0)),
    ),
    instruction_param(
        "mov pins ~ isr",
        0xA00E,
        State(input_shift_register=ShiftRegister(0xFFFF_FFFF, 0)),
        State(input_shift_register=ShiftRegister(0xFFFF_FFFF, 0), pin_values=0x0000_0000),
    ),
    instruction_param(
        "mov x pins",
        0xA020,
        State(pin_values=0x1_0000_0000),
        State(pin_values=0x1_0000_0000, x_register=0x0000_0000),
    ),
    instruction_param(
        "mov y ~ pins",
        0xA048,
        State(pin_values=0xFFFF_FFFF),
        State(pin_values=0xFFFF_FFFF, y_register=0x0000_0000),
    ),
    instruction_param(
        "mov osr ~ pins",
        0xA0E8,
        State(pin_values=0x1_0000_0000),
        State(pin_values=0x1_0000_0000, output_shift_register=ShiftRegister(0xFFFF_FFFF, 0)),
    ),
    instruction_param(
        "mov isr ~ x",
        0xA0C9,
        State(x_register=0xFFFF_FFFF),
        State(x_register=0xFFFF_FFFF, input_shift_register=ShiftRegister(0x0000_0000, 0)),
    ),
    instruction_param(
        "mov pins ~ y",
        0xA00A,
        State(y_register=0x1_0000_0000),
        State(y_register=0x1_0000_0000, pin_values=0xFFFF_FFFF),
    ),
    instruction_param(
        "mov x ~ null",
        0xA02B,
        State(),
        State(x_register=0xFFFF_FFFF),
    ),
    instruction_param(
        "mov x isr",
        0xA026,
        State(input_shift_register=ShiftRegister(0x1_0000_0000, 0)),
        State(input_shift_register=ShiftRegister(0x1_0000_0000, 0), x_register=0x0000_0000),
    ),
    instruction_param(
        "mov pins osr",
        0xA007,
        State(output_shift_register=ShiftRegister(0x1_0000_0000, 0)),
        State(output_shift_register=ShiftRegister(0x1_0000_0000, 0), pin_values=0x0000_0000),
    ),
    instruction_param(
        "mov x :: y",
        0xA032,
        State(y_register=0x0000_0001),
        State(y_register=0x0000_0001, x_register=0x8000_0000),
    ),
    instruction_param(
        "mov osr :: isr",
        0xA0F6,
        State(input_shift_register=ShiftRegister(0x0000_00F3, 0)),
        State(input_shift_register=ShiftRegister(0x0000_00F3, 0), output_shift_register=ShiftRegister(0xCF00_0000, 0)),
    ),
    instruction_param(
        "mov y ~ x",
        0xA049,
        State(x_register=0x1_0000_0000),
        State(x_register=0x1_0000_0000, y_register=0xFFFF_FFFF),
    ),
    instruction_param(
        "mov isr osr",
        0xA0C7,
        State(output_shift_register=ShiftRegister(0xFFFF_FFFF, 0)),
        State(output_shift_register=ShiftRegister(0xFFFF_FFFF, 0), input_shift_register=ShiftRegister(0xFFFF_FFFF, 0)),
    ),
    instruction_param(
        "mov osr ~ osr",
        0xA0EF,
        State(output_shift_register=ShiftRegister(0x1_0000_0000, 0)),
        State(output_shift_register=ShiftRegister(0xFFFF_FFFF, 0)),
    ),
    instruction_param(
        "mov y osr",
        0xA047,
        State(output_shift_register=ShiftRegister(0xFFFF_FFFF, 0)),
        State(output_shift_register=ShiftRegister(0xFFFF_FFFF, 0), y_register=0xFFFF_FFFF),
    ),
    instruction_param(
        "mov osr ~ isr",
        0xA0EE,
        State(input_shift_register=ShiftRegister(0x1_0000_0000, 0)),
        State(input_shift_register=ShiftRegister(0x1_0000_0000, 0), output_shift_register=ShiftRegister(0xFFFF_FFFF, 0)),
    ),
    instruction_param(
        "mov isr ~ isr",
        0xA0CE,
        State(input_shift_register=ShiftRegister(0xFFFF_FFFF, 0)),
        State(input_shift_register=ShiftRegister(0x0000_0000, 0)),
    ),
    instruction_param(
        "mov isr ~ y",
        0xA0CA,
        State(y_register=0xFFFF_FFFF),
        State(y_register=0xFFFF_FFFF, input_shift_register=ShiftRegister(0x0000_0000, 0)),
    ),
    instruction_param(
        "mov isr ~ null",
        0xA0CB,
        State(),
        State(input_shift_register=ShiftRegister(0xFFFF_FFFF, 0)),
    ),
    instruction_param(
        "mov pins ~ pins",
        0xA008,
        State(pin_values=0x1_0000_0000),
        State(pin_values=0xFFFF_FFFF),
    ),
    instruction_param(
        "mov x y",
        0xA022,
        State(y_register=0x1_0000_0000),
        State(y_register=0x1_0000_0000, x_register=0x0000_0000),
    ),
    instruction_param(
        "mov y null",
        0xA043,
        State(),
        State(y_register=0x0000_0000),
    ),
    instruction_param(
        "mov osr ~ null",
        0xA0EB,
        State(),
        State(output_shift_register=ShiftRegister(0xFFFF_FFFF, 0)),
    ),
    instruction_param(
        "mov pins ~ x",
        0xA009,
        State(x_register=0xFFFF_FFFF),
        State(x_register=0xFFFF_FFFF, pin_values=0x0000_0000),
    ),
    instruction_param(
        "mov x x",
        0xA021,
        State(x_register=0xFFFF_FFFF),
        State(x_register=0xFFFF_FFFF),
    ),
    instruction_param(
        "mov x ~ pc",
        0xA0A9,
        State(x_register=29),
        State(x_register=29),
        expected_program_counter=2,
    ),
    instruction_param(
        "mov y isr",
        0xA046,
        State(input_shift_register=ShiftRegister(0xFFFF_FFFF, 0)),
        State(input_shift_register=ShiftRegister(0xFFFF_FFFF, 0), y_register=0xFFFF_FFFF),
    ),
    instruction_param(
        "mov osr ~ y",
        0xA0EA,
        State(y_register=0x1_0000_0000),
        State(y_register=0x1_0000_0000, output_shift_register=ShiftRegister(0xFFFF_FFFF, 0)),
    ),
]
# fmt: on


@pytest.mark.parametrize("opcode, initial_state, expected_state", instructions_to_test)
def test_mov_instruction(opcode: int, initial_state: State, expected_state: State):
    _, new_state = emulate_single_instruction(
        opcode, initial_state=initial_state, advance_program_counter=True
    )

    assert new_state == expected_state


def test_mov_with_the_reserved_operation_ends_the_emulation():
    opcode = 0xA03A  # mov x, <reserved operation 3> y

    assert list(emulate([opcode], stop_when=clock_cycles_reached(1))) == []


def test_mov_pins_writes_the_out_pin_group():
    opcode = 0xA001  # mov pins, x

    _, new_state = emulate_single_instruction(
        opcode,
        initial_state=State(x_register=0xFFFF_FFFD, pin_values=0x0000_0003),
        out_base=10,
        out_count=3,
    )

    assert new_state.pin_values == 0x0000_0003 | (0b101 << 10)


@pytest.mark.parametrize(
    "state, status_sel, status_n, expected_x_register",
    [
        pytest.param(State(), 0, 0, 0x0000_0000, id="never true when status_n is 0"),
        pytest.param(State(transmit_fifo=deque([1, 2])), 0, 3, 0xFFFF_FFFF, id="TX level below status_n"),
        pytest.param(State(transmit_fifo=deque([1, 2, 3])), 0, 3, 0x0000_0000, id="TX level equal to status_n"),
        pytest.param(State(receive_fifo=deque([1])), 1, 2, 0xFFFF_FFFF, id="RX level below status_n"),
        pytest.param(State(receive_fifo=deque([1, 2])), 1, 2, 0x0000_0000, id="RX level equal to status_n"),
        pytest.param(State(receive_fifo=deque([1, 2, 3])), 0, 2, 0xFFFF_FFFF, id="only the selected FIFO counts"),
    ],
)
def test_mov_x_status(state: State, status_sel: int, status_n: int, expected_x_register: int):
    opcode = 0xA025  # mov x, status

    _, new_state = next(
        emulate(
            [opcode],
            initial_state=state,
            stop_when=clock_cycles_reached(1),
            status_sel=status_sel,
            status_n=status_n,
        )
    )

    assert new_state.x_register == expected_x_register


@pytest.mark.parametrize(
    "keyword, value",
    [("status_sel", 2), ("status_sel", -1), ("status_n", 16), ("status_n", -1)],
)
def test_emulate_rejects_invalid_status_settings(keyword: str, value: int):
    with pytest.raises(ValueError, match=keyword):
        next(emulate([0xA042], stop_when=clock_cycles_reached(1), **{keyword: value}))


def test_mov_exec_executes_the_register_as_an_instruction_in_the_next_cycle():
    mov_exec_x = 0xA081
    set_pins_1 = 0xE001
    set_pins_2 = 0xE002

    states = [
        state
        for _, state in emulate(
            [mov_exec_x, set_pins_2, 0xA042],
            initial_state=State(x_register=set_pins_1),
            stop_when=clock_cycles_reached(3),
        )
    ]

    # The executed instruction does not advance the program counter
    assert [(state.program_counter, state.pin_values) for state in states] == [
        (1, 0),
        (1, 1),
        (2, 2),
    ]
    assert states[0].exec_opcode == set_pins_1


def test_mov_exec_uses_only_the_low_sixteen_bits():
    mov_exec_x = 0xA081
    set_pins_1 = 0xE001

    state = next(
        emulate(
            [mov_exec_x, 0xA042],
            initial_state=State(x_register=0xFFFF_0000 | set_pins_1),
            stop_when=clock_cycles_reached(1),
        )
    )[1]

    assert state.exec_opcode == set_pins_1
