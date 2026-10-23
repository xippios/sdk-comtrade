"""Refresh the packaged reference data from upstream (``/refresh-reference-data``).

Writes ``reference/<name>.json`` for every list in ``LISTS`` and ``SPEC_LISTS`` (values,
fetch date, origin), then regenerates ``enums.py`` with one ``StrEnum`` per list through
``xippios.core.reference.render_str_enums``. Names are the upstream parameter names.

- ``LISTS`` come from UN Comtrade's public reference files, fetched through the layer-1
  wrapper ``api.reference`` (no key needed or sent): the codes of ``tradeRegimes.json``,
  ``ModeOfTransportCodes.json`` and ``CustomsCodes.json``, and the ``clCode`` values as the
  ``cmd:<clCode>`` categories of ``ListofReferences.json``.
- ``SPEC_LISTS`` have no reference file. They are read from the snapshot of the spec,
  ``docs/upstream/apidocs/comtrade.json``, operation ``get``: the ``typeCode``,
  ``freqCode`` and ``breakdownMode`` enums and the names ``aggregateBy``'s description
  lists. The fetch date is the snapshot's, from ``docs/upstream/FETCHED.md``.

Run from the repository root; no API key is needed. ``render_str_enums`` writes
``__all__`` on one line, so format the result with ruff::

    uv run python scripts/refresh_reference.py
    uv run ruff format src/xippios/comtrade/enums.py
"""

import json
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xippios.core import sync
from xippios.core.reference import render_str_enums

from xippios.comtrade import api
from xippios.comtrade.models import Reference, ReferenceCode
from xippios.comtrade.params import PACKAGED_LISTS

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "src/xippios/comtrade"
REFERENCE = PACKAGE_DIR / "reference"
ENUMS = PACKAGE_DIR / "enums.py"
SPEC = ROOT / "docs/upstream/apidocs/comtrade.json"
SPEC_NAME = "apidocs/comtrade.json"
FETCHED = ROOT / "docs/upstream/FETCHED.md"
FILES = "https://comtradeapi.un.org/files/v1/app/reference/"
OPERATION = "/get/{typeCode}/{freqCode}/{clCode}"


async def _codes(name: str) -> list[str]:
    return [entry.id for entry in await api.reference(name, ReferenceCode)]


async def _cl_codes() -> list[str]:
    references = await api.reference("ListofReferences.json", Reference)
    prefix = "cmd:"
    return [
        ref.category.removeprefix(prefix) for ref in references if ref.category.startswith(prefix)
    ]


LISTS: dict[str, tuple[str, Callable[[], Awaitable[list[str]]]]] = {
    "clCode": (
        f"{FILES}ListofReferences.json, the cmd:<clCode> categories",
        _cl_codes,
    ),
    "flowCode": (f"{FILES}tradeRegimes.json", lambda: _codes("tradeRegimes.json")),
    "customsCode": (f"{FILES}CustomsCodes.json", lambda: _codes("CustomsCodes.json")),
    "motCode": (f"{FILES}ModeOfTransportCodes.json", lambda: _codes("ModeOfTransportCodes.json")),
}
"""Lists from reference files: name to (origin, fetcher through ``api/``)."""


def _parameter(spec: dict[str, Any], name: str) -> dict[str, Any]:
    for parameter in spec["paths"][OPERATION]["get"]["parameters"]:
        if parameter["name"] == name:
            return dict(parameter)
    raise SystemExit(f"{SPEC_NAME}: operation get has no parameter {name!r}")


def _enum(spec: dict[str, Any], name: str) -> list[str]:
    return [str(value) for value in _parameter(spec, name)["schema"]["enum"]]


def _aggregate_by(spec: dict[str, Any]) -> list[str]:
    description = str(_parameter(spec, "aggregateBy")["description"])
    _, sep, names = description.partition("Comma-separated list of:")
    if not sep:
        raise SystemExit(f"{SPEC_NAME}: aggregateBy no longer lists its names: {description!r}")
    return [name.strip() for name in names.split(",") if name.strip()]


SPEC_LISTS: dict[str, tuple[str, Callable[[dict[str, Any]], list[str]]]] = {
    "typeCode": (f"{SPEC_NAME}, get, typeCode enum", lambda spec: _enum(spec, "typeCode")),
    "freqCode": (f"{SPEC_NAME}, get, freqCode enum", lambda spec: _enum(spec, "freqCode")),
    "breakdownMode": (
        f"{SPEC_NAME}, get, breakdownMode enum",
        lambda spec: _enum(spec, "breakdownMode"),
    ),
    "aggregateBy": (f"{SPEC_NAME}, get, aggregateBy description", _aggregate_by),
}
"""Lists from the spec snapshot: name to (origin, reader)."""


def _snapshot_date() -> str:
    match = re.search(
        rf"^\| {re.escape(SPEC_NAME)} \| \S+ \| (\d{{4}}-\d{{2}}-\d{{2}}) \|",
        FETCHED.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if match is None:
        raise SystemExit(f"{FETCHED} has no row for {SPEC_NAME}")
    return match.group(1)


def _write(name: str, fetched: str, origin: str, values: list[str]) -> None:
    payload = {"param": name, "fetched": fetched, "origin": origin, "values": values}
    path = REFERENCE / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"{path.name}: {len(values)} values from {origin}")  # noqa: T201


def main() -> None:
    """Fetch and derive every list, write its file and regenerate ``enums.py``."""
    names = [*LISTS, *SPEC_LISTS]
    if sorted(names) != sorted(PACKAGED_LISTS):
        raise SystemExit(f"params.PACKAGED_LISTS {PACKAGED_LISTS} does not match {names}")
    today = datetime.now(UTC).date().isoformat()
    REFERENCE.mkdir(exist_ok=True)
    lists: dict[str, list[str]] = {}
    for name, (origin, fetch) in LISTS.items():
        lists[name] = sync(fetch)()
        _write(name, today, origin, lists[name])
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    snapshot = _snapshot_date()
    for name, (origin, read) in SPEC_LISTS.items():
        lists[name] = read(spec)
        _write(name, snapshot, f"docs/upstream/{origin} (snapshot of {snapshot})", lists[name])
    # Classes in name order, so the generated __all__ is sorted as ruff wants it.
    class_names = {name: name[0].upper() + name[1:] for name in lists}
    ordered = {name: lists[name] for name in sorted(lists, key=class_names.__getitem__)}
    source = render_str_enums(
        ordered,
        class_names=class_names,
        fetched=today,
        generator="scripts/refresh_reference.py",
    )
    ENUMS.write_text(source, encoding="utf-8")
    print(f"{ENUMS.name}: {len(ordered)} enums")  # noqa: T201


if __name__ == "__main__":
    main()
