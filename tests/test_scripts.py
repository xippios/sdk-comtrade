"""The maintenance scripts under ``scripts/``, checked without a request or a key."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_refresh_reference_help_prints_usage_and_stops(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--help`` exits from the parser, before ``main`` fetches or writes anything.

    The script writes the packaged lists alone: it renders no ``enums.py``, so it takes no
    ``--render-only``.
    """
    script = _load("refresh_reference")
    with pytest.raises(SystemExit) as info:
        script.parse_args(["--help"])
    assert info.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("usage: refresh_reference.py [-h]\n")
    assert "Refresh the packaged reference data from upstream" in out
    assert "enums.py" not in out
    for unknown in (["--unknown"], ["--render-only"]):
        with pytest.raises(SystemExit):
            script.parse_args(unknown)
    assert vars(script.parse_args([])) == {}
    assert not hasattr(script, "render")
