import pytest

from .firmware import ensure_micropython


def pytest_addoption(parser):
    group = parser.getgroup("crosscheck")
    group.addoption(
        "--hardware",
        action="store_true",
        help="run the tests that need a Pico 2 (and flash MicroPython onto it if necessary)",
    )
    group.addoption(
        "--no-flash",
        action="store_true",
        help="never flash the Pico 2; fail if it does not already run a suitable MicroPython",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "hardware: needs a Pico 2 and an Analog Discovery")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--hardware"):
        return

    skip = pytest.mark.skip(reason="needs hardware: run with --hardware")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def pico_port(request) -> str:
    """Serial port of a Pico 2 running a suitable MicroPython; flashes it if required."""
    return ensure_micropython(allow_flash=not request.config.getoption("--no-flash"))
