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


def update_bits_32(value, new_value, bit_position=0, bit_count=32):
    """
    Updates an existing value with up to 32 bits from another value.

    A range that extends beyond bit 31 wraps around to bit 0, like pin ranges do.
    """

    bit_mask = ((1 << bit_count) - 1) << bit_position
    new_bits = (new_value << bit_position) & bit_mask

    wrapped_mask = (bit_mask & 0xFFFF_FFFF) | (bit_mask >> 32)
    wrapped_bits = (new_bits & 0xFFFF_FFFF) | (new_bits >> 32)

    return ((value & ~wrapped_mask) | wrapped_bits) & 0xFFFF_FFFF


def reverse_bits_32(value):
    """Reverses the order of the lowest 32 bits of a value."""

    return int(f"{value & 0xFFFF_FFFF:032b}"[::-1], 2)


def rotate_right_32(value, bit_count):
    """Rotates the lowest 32 bits of a value to the right."""

    value &= 0xFFFF_FFFF
    bit_count &= 31

    return ((value >> bit_count) | (value << (32 - bit_count))) & 0xFFFF_FFFF

