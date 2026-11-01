"""
Downloads a pinned, stable MicroPython firmware for the Pico 2 and flashes it through a
Raspberry Pi Debug Probe (CMSIS-DAP, SWD) with pyOCD.

    python -m crosscheck.flash_micropython             # download, flash, reset
    python -m crosscheck.flash_micropython --dry-run   # show what would be done
    python -m crosscheck.flash_micropython --file fw.uf2

Requires pyocd (the 'hardware' dependency group). micropython.org publishes no checksums, so the
download is only as trustworthy as the HTTPS connection. pyOCD resets the board after
programming; this script does not read the image back for an extra verification.
"""
import argparse
import re
import struct
import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

DOWNLOAD_PAGE = "https://micropython.org/download/RPI_PICO2/"
TARGET = "rp2350"  # pyOCD built-in target

# The firmware the hardware cross-check runs against. Golden traces captured on hardware should
# be reproducible, so this is raised deliberately rather than following the latest release.
PINNED_VERSION = (1, 29, 0)

UF2_MAGIC_START0 = 0x0A324655
UF2_MAGIC_START1 = 0x9E5D5157
UF2_MAGIC_END = 0x0AB16F30
UF2_FLAG_FAMILY_ID = 0x00002000
UF2_BLOCK_SIZE = 512
RP2350_ARM_SECURE = 0xE48BFF59  # family of the blocks that make up the flash image
MAX_IMAGE_SIZE = 32 * 1024 * 1024

# Stable builds only: no RISC-V variant ("RPI_PICO2-RISCV-...") and no previews ("-v1.30.0-preview...").
_FIRMWARE_LINK = re.compile(
    r'href="([^"]*/resources/firmware/RPI_PICO2-(\d{8})-v(\d+)\.(\d+)\.(\d+)\.uf2)"'
)


def find_firmware(
    html: str, version: tuple[int, int, int] | None = None, page_url: str = DOWNLOAD_PAGE
) -> str:
    """
    Returns the absolute URL of a stable firmware build linked from the download page: the one
    with the given version, or the newest if no version is given.
    """
    candidates = [
        ((int(major), int(minor), int(patch), date), href)
        for href, date, major, minor, patch in _FIRMWARE_LINK.findall(html)
    ]
    if version is not None:
        candidates = [c for c in candidates if c[0][:3] == version]

    if not candidates:
        wanted = "v" + ".".join(map(str, version)) if version else "any stable version"
        raise ValueError(f"no firmware link for {wanted} found on the download page")

    return urljoin(page_url, max(candidates)[1])


def parse_version(text: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", text.strip())
    if not match:
        raise ValueError(f"not a version of the form X.Y.Z: {text!r}")

    return tuple(map(int, match.groups()))  # type: ignore[return-value]


def uf2_to_bin(data: bytes, family_id: int = RP2350_ARM_SECURE) -> tuple[int, bytes]:
    """
    Converts a UF2 image to a flat binary.

    Returns (base address, image). Blocks of other families, such as the RP2350 'absolute'
    blocks that only the USB bootloader needs, are skipped; gaps are filled with 0xFF.
    """
    if len(data) % UF2_BLOCK_SIZE:
        raise ValueError("not a UF2 file: size is not a multiple of 512 bytes")

    chunks: list[tuple[int, bytes]] = []
    for offset in range(0, len(data), UF2_BLOCK_SIZE):
        block = data[offset : offset + UF2_BLOCK_SIZE]
        magic0, magic1, flags, address, size, _, _, family = struct.unpack_from("<8I", block)
        (magic_end,) = struct.unpack_from("<I", block, UF2_BLOCK_SIZE - 4)

        if (magic0, magic1, magic_end) != (UF2_MAGIC_START0, UF2_MAGIC_START1, UF2_MAGIC_END):
            raise ValueError(f"not a UF2 file: bad magic in block at offset {offset}")

        if not flags & UF2_FLAG_FAMILY_ID or family != family_id:
            continue

        if size > 476:
            raise ValueError(f"bad UF2 payload size {size} in block at offset {offset}")

        chunks.append((address, block[32 : 32 + size]))

    if not chunks:
        raise ValueError(f"no UF2 blocks for family 0x{family_id:08X}")

    base = min(address for address, _ in chunks)
    end = max(address + len(payload) for address, payload in chunks)
    if end - base > MAX_IMAGE_SIZE:
        raise ValueError(f"UF2 image spans {end - base} bytes, which is implausible")

    image = bytearray(b"\xff" * (end - base))
    for address, payload in chunks:
        image[address - base : address - base + len(payload)] = payload

    return base, bytes(image)


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def fetch_firmware(cache_dir: Path, version: tuple[int, int, int] | None) -> Path:
    """Downloads the firmware (newest stable if no version) into cache_dir unless cached."""
    url = find_firmware(_download(DOWNLOAD_PAGE).decode("utf-8", "replace"), version)
    path = cache_dir / url.rsplit("/", 1)[1]

    if path.exists():
        print(f"using cached {path}")
        return path

    print(f"downloading {url}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".part")
    temporary.write_bytes(_download(url))
    temporary.replace(path)
    return path


def flash_command(binary: Path, base: int, *, target: str, probe: str | None) -> list[str]:
    """The pyOCD command that programs the binary at `base` and resets the board."""
    return [
        sys.executable, "-m", "pyocd", "load", str(binary),
        "--target", target,
        "--format", "bin",
        "--base-address", f"0x{base:08X}",
        "--no-wait",  # fail at once if no probe is connected
        *(["--uid", probe] if probe else []),
    ]  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--file", type=Path, help="flash this UF2 instead of downloading")
    parser.add_argument(
        "--version",
        default=".".join(map(str, PINNED_VERSION)),
        help="MicroPython version to flash, or 'latest' (default: %(default)s)",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "pioemu-crosscheck",
        help="where downloaded firmware is kept (default: %(default)s)",
    )
    parser.add_argument(
        "--probe",
        help="pyOCD probe unique ID (see 'pyocd list'); needed when several probes are connected",
    )
    parser.add_argument("--target", default=TARGET, help="pyOCD target (default: %(default)s)")
    parser.add_argument("--dry-run", action="store_true", help="print the command, flash nothing")
    args = parser.parse_args(argv)

    version = None if args.version == "latest" else parse_version(args.version)
    uf2 = args.file or fetch_firmware(args.cache_dir, version)
    base, image = uf2_to_bin(uf2.read_bytes())
    print(f"{uf2.name}: {len(image)} bytes at 0x{base:08X}")

    binary = uf2.with_suffix(".bin")
    binary.write_bytes(image)

    command = flash_command(binary, base, target=args.target, probe=args.probe)
    print("$", " ".join(command))
    if not args.dry_run:
        subprocess.run(command, check=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
