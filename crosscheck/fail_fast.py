"""
Makes the wiring test run first and stops the whole run if it fails: with wrong connections
nothing else that needs the hardware means anything.
"""

STOP_MESSAGE = (
    "the wiring test failed: fix the connections (see crosscheck/HARDWARE.md) before running "
    "anything else"
)


def wiring_first(items: list) -> None:
    """Moves the tests marked 'wiring' to the front, keeping the order of all the others."""
    items.sort(key=lambda item: "wiring" not in item.keywords)


def stop_after_failed_wiring(item, report) -> None:
    """Stops the session once a test marked 'wiring' has failed (in any phase of the test)."""
    if report.failed and "wiring" in item.keywords:
        item.session.shouldfail = STOP_MESSAGE
