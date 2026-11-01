import struct
from pathlib import Path

import pytest

from .flash_micropython import (
    RP2350_ARM_SECURE,
    find_latest_firmware,
    flash_commands,
    main,
    uf2_to_bin,
)

PAGE = """
<a href="/resources/firmware/RPI_PICO2-20260824-v1.29.0.uf2">v1.29.0 (2026-08-24) .uf2</a>
<a href="/resources/firmware/RPI_PICO2-RISCV-20260824-v1.29.0.uf2">v1.29.0 RISC-V</a>
<a href="/resources/firmware/RPI_PICO2-20261030-v1.30.0-preview.206.g8ee4798dc2.uf2">preview</a>
<a href="/resources/firmware/RPI_PICO2-20250809-v1.26.0.uf2">v1.26.0 (2025-08-09) .uf2</a>
<a href="/resources/firmware/RPI_PICO2-20260101-v1.9.10.uf2">older, longer date string</a>
"""


def uf2_block(address: int, payload: bytes, family: int | None = RP2350_ARM_SECURE) -> bytes:
    flags = 0x2000 if family is not None else 0
    header = struct.pack(
        "<8I", 0x0A324655, 0x9E5D5157, flags, address, len(payload), 0, 1, family or 0
    )
    return header + payload.ljust(476, b"\0") + struct.pack("<I", 0x0AB16F30)


class TestFindLatestFirmware:
    def test_picks_the_newest_stable_standard_build(self):
        assert (
            find_latest_firmware(PAGE)
            == "https://micropython.org/resources/firmware/RPI_PICO2-20260824-v1.29.0.uf2"
        )

    def test_compares_versions_numerically(self):
        page = (
            '<a href="/resources/firmware/RPI_PICO2-20240101-v1.9.0.uf2"></a>'
            '<a href="/resources/firmware/RPI_PICO2-20230101-v1.10.0.uf2"></a>'
        )

        assert find_latest_firmware(page).endswith("v1.10.0.uf2")

    def test_fails_without_a_stable_link(self):
        with pytest.raises(ValueError):
            find_latest_firmware("<html>nothing here</html>")


class TestUf2ToBin:
    def test_joins_blocks_and_fills_gaps_with_ff(self):
        uf2 = uf2_block(0x1000_0000, b"\x01\x02") + uf2_block(0x1000_0004, b"\x03")

        base, image = uf2_to_bin(uf2)

        assert base == 0x1000_0000
        assert image == b"\x01\x02\xff\xff\x03"

    def test_blocks_may_come_in_any_order(self):
        uf2 = uf2_block(0x1000_0001, b"\x02") + uf2_block(0x1000_0000, b"\x01")

        assert uf2_to_bin(uf2) == (0x1000_0000, b"\x01\x02")

    def test_skips_other_families_and_blocks_without_a_family(self):
        uf2 = (
            uf2_block(0x1000_0000, b"\x01")
            + uf2_block(0x10FF_FF00, b"\xaa", family=0xE48BFF57)
            + uf2_block(0x2000_0000, b"\xbb", family=None)
        )

        assert uf2_to_bin(uf2) == (0x1000_0000, b"\x01")

    def test_rejects_data_that_is_not_uf2(self):
        with pytest.raises(ValueError):
            uf2_to_bin(b"\0" * 512)

        with pytest.raises(ValueError):
            uf2_to_bin(b"\0" * 100)

    def test_rejects_a_file_without_blocks_for_the_family(self):
        with pytest.raises(ValueError):
            uf2_to_bin(uf2_block(0x1000_0000, b"\x01", family=0x1234))


def test_flash_commands_download_then_reset():
    download, reset = flash_commands(
        Path("fw.bin"), 0x1000_0000, chip="RP235x", probe="2e8a:000c", verify=True
    )

    assert download[:2] == ["probe-rs", "download"]
    assert "--verify" in download
    assert download[download.index("--base-address") + 1] == "0x10000000"
    assert download[download.index("--probe") + 1] == "2e8a:000c"
    assert reset[:2] == ["probe-rs", "reset"]


def test_dry_run_converts_but_does_not_flash(tmp_path, capsys):
    uf2 = tmp_path / "fw.uf2"
    uf2.write_bytes(uf2_block(0x1000_0000, b"\x01\x02\x03"))

    assert main(["--file", str(uf2), "--dry-run"]) == 0

    assert (tmp_path / "fw.bin").read_bytes() == b"\x01\x02\x03"
    assert "$ probe-rs download" in capsys.readouterr().out
