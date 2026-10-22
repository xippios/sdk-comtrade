"""The namespace levels stay empty and the package ships its typing marker (ADR-0006)."""

from pathlib import Path

import xippios.comtrade as package

PACKAGE_DIR = Path(package.__file__ or "").parent


def test_namespace_levels_have_no_init() -> None:
    level = PACKAGE_DIR.parent
    while True:
        assert not (level / "__init__.py").exists(), f"{level} must stay a namespace portion"
        if level.name == "xippios":
            break
        level = level.parent


def test_py_typed_marker_ships() -> None:
    assert (PACKAGE_DIR / "py.typed").is_file()
