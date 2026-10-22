"""Refresh the packaged reference data from upstream (``/refresh-reference-data``).

For every list in ``LISTS`` this writes ``reference/<name>.json`` with the values and
the fetch date, then regenerates ``enums.py`` with one ``StrEnum`` per list through
``xippios.core.reference.render_str_enums``. Fetch through the layer-1 wrappers in
``api/``, never through a task that might answer from the package. Run from the
repository root with the API key in the environment::

    uv run python scripts/refresh_reference.py
"""

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from xippios.core import sync
from xippios.core.reference import render_str_enums

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "src/xippios/comtrade"
REFERENCE = PACKAGE_DIR / "reference"
ENUMS = PACKAGE_DIR / "enums.py"

LISTS: dict[str, Callable[[], Awaitable[list[str]]]] = {
    # name of the list, as upstream calls it, to an async fetcher through api/, e.g.
    # "country_code": lambda: api.list_countries(),
}
"""The packaged value lists; keep ``params.PACKAGED_LISTS`` in step with the keys."""


def main() -> None:
    """Fetch every list, write its file and regenerate ``enums.py``."""
    today = datetime.now(UTC).date().isoformat()
    lists: dict[str, list[str]] = {}
    REFERENCE.mkdir(exist_ok=True)
    for name, fetch in LISTS.items():
        values = sync(fetch)()
        lists[name] = values
        path = REFERENCE / f"{name}.json"
        payload = {"param": name, "fetched": today, "values": values}
        path.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"{path.name}: {len(values)} values")  # noqa: T201
    source = render_str_enums(lists, fetched=today, generator="scripts/refresh_reference.py")
    ENUMS.write_text(source)
    print(f"{ENUMS.name}: {len(lists)} enums")  # noqa: T201


if __name__ == "__main__":
    main()
