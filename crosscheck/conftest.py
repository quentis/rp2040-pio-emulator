import pytest

from .fail_fast import stop_after_failed_wiring, wiring_first
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
    config.addinivalue_line(
        "markers", "wiring: checks the connections; runs first and stops the run if it fails"
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--hardware"):
        wiring_first(items)
        return

    skip = pytest.mark.skip(reason="needs hardware: run with --hardware")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def pico_port(request) -> str:
    """Serial port of a Pico 2 running a suitable MicroPython; flashes it if required."""
    return ensure_micropython(allow_flash=not request.config.getoption("--no-flash"))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    stop_after_failed_wiring(item, outcome.get_result())

