"""The wiring test runs first and a failure of it stops the run; needs no hardware."""
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from .fail_fast import STOP_MESSAGE, stop_after_failed_wiring, wiring_first

REPOSITORY = Path(__file__).parent.parent


def item(name: str, *keywords: str) -> SimpleNamespace:
    return SimpleNamespace(name=name, keywords=set(keywords), session=SimpleNamespace(shouldfail=False))


class TestWiringFirst:
    def test_moves_the_wiring_test_to_the_front_and_keeps_the_rest_in_order(self):
        items = [item("a"), item("b", "hardware"), item("w", "hardware", "wiring"), item("c")]

        wiring_first(items)

        assert [i.name for i in items] == ["w", "a", "b", "c"]

    def test_leaves_the_order_alone_without_a_wiring_test(self):
        items = [item("b"), item("a")]

        wiring_first(items)

        assert [i.name for i in items] == ["b", "a"]


class TestStopAfterFailedWiring:
    def test_a_failed_wiring_test_stops_the_session(self):
        wiring = item("w", "wiring")

        stop_after_failed_wiring(wiring, SimpleNamespace(failed=True))

        assert wiring.session.shouldfail == STOP_MESSAGE

    @pytest.mark.parametrize(
        "test, failed",
        [
            pytest.param(item("w", "wiring"), False, id="wiring test that passed"),
            pytest.param(item("t", "hardware"), True, id="other test that failed"),
        ],
    )
    def test_nothing_else_stops_the_session(self, test, failed):
        stop_after_failed_wiring(test, SimpleNamespace(failed=failed))

        assert test.session.shouldfail is False


CONFTEST = """
import sys

import pytest

sys.path.insert(0, {repository!r})

from crosscheck.fail_fast import stop_after_failed_wiring, wiring_first


def pytest_configure(config):
    config.addinivalue_line("markers", "wiring: the wiring test")


def pytest_collection_modifyitems(items):
    wiring_first(items)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    stop_after_failed_wiring(item, outcome.get_result())
"""


def run_pytest(directory: Path, wiring_passes: bool) -> subprocess.CompletedProcess:
    (directory / "conftest.py").write_text(CONFTEST.format(repository=str(REPOSITORY)))
    (directory / "test_a_before.py").write_text("def test_before():\n    pass\n")
    (directory / "test_m_wiring.py").write_text(
        "import pytest\n\n"
        "@pytest.mark.wiring\n"
        f"def test_wiring():\n    assert {wiring_passes}\n"
    )
    (directory / "test_z_after.py").write_text("def test_after():\n    pass\n")

    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-v"],
        cwd=directory,
        capture_output=True,
        text=True,
    )


def test_a_failing_wiring_test_runs_first_and_stops_the_run(tmp_path):
    result = run_pytest(tmp_path, wiring_passes=False)

    assert result.returncode != 0
    assert "test_wiring FAILED" in result.stdout
    assert "test_before" not in result.stdout.replace("collected", "")
    assert "test_after" not in result.stdout
    assert "the wiring test failed" in result.stdout


def test_a_passing_wiring_test_lets_everything_else_run(tmp_path):
    result = run_pytest(tmp_path, wiring_passes=True)

    assert result.returncode == 0
    assert result.stdout.index("test_wiring") < result.stdout.index("test_before")
    assert "3 passed" in result.stdout
