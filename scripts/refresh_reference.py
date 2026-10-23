"""Refresh the packaged reference data from upstream (``/refresh-reference-data``).

Writes ``reference/<name>.json`` for every list in ``LISTS`` and ``SPEC_LISTS`` (values,
fetch date, origin), then regenerates ``enums.py`` with one ``StrEnum`` per list through
``xippios.core.reference.render_str_enums``. Names are the upstream parameter names.
Writes ``reference/<name>.csv`` for every table in ``TABLES`` and their origin and fetch
date to ``reference/tables.json``.

- ``LISTS`` come from UN Comtrade's public reference files, fetched through the layer-1
  wrapper ``api.reference`` (no key needed or sent): the codes of ``tradeRegimes.json``,
  ``ModeOfTransportCodes.json``, ``CustomsCodes.json`` and ``ModeOfSupply.json``, the
  ``qtyCode`` values of ``QuantityUnits.json`` (the codes ``qtyUnitCode`` carries), and the
  ``clCode`` values as the ``cmd:<clCode>`` categories of ``ListofReferences.json``.
- ``TABLES`` are reference files that are tables rather than value lists:
  ``Reporters.json``, ``partnerAreas.json``, ``TradeDataItems.json`` and
  ``country_area_code_iso.json``. The last is not in ``ListofReferences.json``; it is the
  table the official ``comtradeapicall`` package (1.3.2, ``convertCountryIso3ToCode``)
  reads to map ISO alpha-3 codes to UN Comtrade's. Each is written as CSV, one column per
  upstream key under its upstream name, in the row model's order (``params.PACKAGED_TABLES``);
  a key the model does not know, or an empty value (which the CSV could not tell from an
  absent key), stops the script. None of them has nested fields, so none stays JSON.
- ``SUPPLEMENTS`` reconcile two of those with the spec, where the two disagree. The
  values the spec documents for ``flowCode`` are all added (``MIF`` and ``XIF`` are
  missing from ``tradeRegimes.json``). For ``clCode``, a value of the spec's enum is added
  only when a recorded answer shows upstream accepting it, and any value a recorded
  answer shows refused is left out. ``EVIDENCE`` names those recordings, and each
  exception is written into the list's file with its evidence.
- ``SPEC_LISTS`` have no reference file. They are read from the snapshot of the spec,
  ``docs/upstream/apidocs/comtrade.json``, operation ``get``: the ``typeCode``,
  ``freqCode`` and ``breakdownMode`` enums and the names ``aggregateBy``'s description
  lists. The fetch date is the snapshot's, from ``docs/upstream/FETCHED.md``.

Each enum's docstring carries its list's ``fetched`` date. Run from the repository root;
no API key is needed. ``render_str_enums`` writes ``__all__`` on one line, so format the
result with ruff::

    uv run python scripts/refresh_reference.py
    uv run ruff format src/xippios/comtrade/enums.py
"""

import csv
import io
import json
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from xippios.core import UpstreamModel, parse, sync
from xippios.core.reference import render_str_enums

from xippios.comtrade import api
from xippios.comtrade._client import SOURCE
from xippios.comtrade.models import QuantityUnit, Reference, ReferenceCode
from xippios.comtrade.params import PACKAGED_LISTS, PACKAGED_TABLES, TABLES_INDEX

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "src/xippios/comtrade"
REFERENCE = PACKAGE_DIR / "reference"
ENUMS = PACKAGE_DIR / "enums.py"
SPEC = ROOT / "docs/upstream/apidocs/comtrade.json"
SPEC_NAME = "apidocs/comtrade.json"
FETCHED = ROOT / "docs/upstream/FETCHED.md"
FILES = "https://comtradeapi.un.org/files/v1/app/reference/"
OPERATION = "/get/{typeCode}/{freqCode}/{clCode}"
FIXTURES = ROOT / "tests/fixtures/get"


async def _codes(name: str) -> list[str]:
    return [entry.id for entry in await api.reference(name, ReferenceCode)]


async def _cl_codes() -> list[str]:
    references = await api.reference("ListofReferences.json", Reference)
    prefix = "cmd:"
    return [
        ref.category.removeprefix(prefix) for ref in references if ref.category.startswith(prefix)
    ]


async def _qty_codes() -> list[str]:
    return [str(unit.qty_code) for unit in await api.reference("QuantityUnits.json", QuantityUnit)]


LISTS: dict[str, tuple[str, Callable[[], Awaitable[list[str]]]]] = {
    "clCode": (
        f"{FILES}ListofReferences.json, the cmd:<clCode> categories",
        _cl_codes,
    ),
    "flowCode": (f"{FILES}tradeRegimes.json", lambda: _codes("tradeRegimes.json")),
    "customsCode": (f"{FILES}CustomsCodes.json", lambda: _codes("CustomsCodes.json")),
    "motCode": (f"{FILES}ModeOfTransportCodes.json", lambda: _codes("ModeOfTransportCodes.json")),
    "mosCode": (f"{FILES}ModeOfSupply.json", lambda: _codes("ModeOfSupply.json")),
    "qtyUnitCode": (f"{FILES}QuantityUnits.json, the qtyCode values", _qty_codes),
}
"""Lists from reference files: name to (origin, fetcher through ``api/``)."""

TABLES: dict[str, str] = {
    "Reporters": "Reporters.json",
    "partnerAreas": "partnerAreas.json",
    "country_area_code_iso": "country_area_code_iso.json",
    "TradeDataItems": "TradeDataItems.json",
}
"""Tables from reference files: name of the packaged CSV (``params.PACKAGED_TABLES``) to file."""


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


def _flow_codes(spec: dict[str, Any]) -> list[str]:
    description = str(_parameter(spec, "flowCode")["description"])
    match = re.search(r"Allowed values \(case-insensitive\): ([^.]+)\.", description)
    if match is None:
        raise SystemExit(f"{SPEC_NAME}: flowCode no longer lists its values: {description!r}")
    return [value.strip() for value in match.group(1).split(",") if value.strip()]


SUPPLEMENTS: dict[str, tuple[str, Callable[[dict[str, Any]], list[str]], bool]] = {
    "flowCode": (
        f"docs/upstream/{SPEC_NAME}, operation get, parameter flowCode, description",
        _flow_codes,
        True,
    ),
    "clCode": (
        f"docs/upstream/{SPEC_NAME}, operation get, parameter clCode, enum",
        lambda spec: _enum(spec, "clCode"),
        False,
    ),
}
"""Spec values reconciled with a reference-file list: (origin, reader, add unexercised ones)."""

EVIDENCE: dict[str, dict[str, str]] = {
    "flowCode": {"MIF": "count_flow_code_mif.json"},
    "clCode": {
        "BE": "count_cl_code_be.json",
        "BE5": "count_cl_code_be5.json",
        "TM": "count_cl_code_tm.json",
        "H6": "count_cl_code_h6.json",
    },
}
"""Recorded ``data/v1/get`` counts under ``tests/fixtures/get/`` that try one value.

HTTP 200 means upstream accepted the value, HTTP 400 that it refused it; any other status
settles nothing.
"""


def _verdict(name: str, value: str) -> tuple[str, str] | None:
    fixture = EVIDENCE.get(name, {}).get(value)
    if fixture is None:
        return None
    status = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))["response"]["status"]
    outcome = {200: "accepted it", 400: "refused it"}.get(status, "answered without settling it")
    return outcome, f"tests/fixtures/get/{fixture}, HTTP {status}"


def _reconcile(
    name: str, base: list[str], spec: dict[str, Any]
) -> tuple[list[str], list[dict[str, str]]]:
    """``base`` with the spec's extra values added or left out, and refused ones removed."""
    origin, read, add_unexercised = SUPPLEMENTS[name]
    values = list(base)
    exceptions: list[dict[str, str]] = []
    for value in read(spec):
        if value in base:
            continue
        verdict = _verdict(name, value)
        accepted = verdict[0] == "accepted it" if verdict else add_unexercised
        if accepted:
            values.append(value)
        seen = f"upstream {verdict[0]} ({verdict[1]})" if verdict else "not tried upstream"
        exceptions.append(
            {
                "value": value,
                "decision": "added" if accepted else "left out",
                "evidence": f"listed in {origin}; {seen}",
            }
        )
    for value in base:
        verdict = _verdict(name, value)
        if verdict is None:
            continue
        refused = verdict[0] == "refused it"
        if refused:
            values.remove(value)
        exceptions.append(
            {
                "value": value,
                "decision": "removed" if refused else "kept",
                "evidence": f"in the reference file; upstream {verdict[0]} ({verdict[1]})",
            }
        )
    return values, exceptions


def _snapshot_date() -> str:
    match = re.search(
        rf"^\| {re.escape(SPEC_NAME)} \| \S+ \| (\d{{4}}-\d{{2}}-\d{{2}}) \|",
        FETCHED.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if match is None:
        raise SystemExit(f"{FETCHED} has no row for {SPEC_NAME}")
    return match.group(1)


def _write(
    name: str,
    fetched: str,
    origin: str,
    values: list[str],
    exceptions: list[dict[str, str]] | None = None,
) -> None:
    payload: dict[str, Any] = {"param": name, "fetched": fetched, "origin": origin}
    if exceptions:
        payload["exceptions"] = exceptions
    payload["values"] = values
    path = REFERENCE / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"{path.name}: {len(values)} values from {origin}")  # noqa: T201
    for exception in exceptions or []:
        print(f"  {exception['value']}: {exception['decision']}, {exception['evidence']}")  # noqa: T201


def _columns(model: type[UpstreamModel]) -> list[str]:
    """The upstream keys of a row model, in field order."""
    return [
        field.validation_alias if isinstance(field.validation_alias, str) else name
        for name, field in model.model_fields.items()
    ]


def _cell(value: object) -> str:
    return value if isinstance(value, str) else json.dumps(value)


def _write_table(name: str, file: str, today: str) -> dict[str, Any]:
    model = PACKAGED_TABLES[name]
    origin = f"{FILES}{file}"
    rows = sync(api.reference_rows)(file)
    columns = _columns(model)
    for row in rows:
        unknown = sorted(set(row) - set(columns))
        if unknown:
            raise SystemExit(f"{file}: columns {unknown} are not in {model.__name__}")
        if any(value in ("", None) for value in row.values()):
            raise SystemExit(f"{file}: an empty value cannot be told from an absent key: {row}")
        parse(model, row, source=SOURCE, endpoint=f"files/v1/app/reference/{file}")
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows({key: _cell(value) for key, value in row.items()} for row in rows)
    path = REFERENCE / f"{name}.csv"
    path.write_text(buffer.getvalue(), encoding="utf-8")
    print(f"{path.name}: {len(rows)} rows from {origin}")  # noqa: T201
    return {"file": path.name, "origin": origin, "fetched": today, "rows": len(rows)}


def main() -> None:
    """Fetch and derive every list and table, write their files and regenerate ``enums.py``."""
    names = [*LISTS, *SPEC_LISTS]
    if sorted(names) != sorted(PACKAGED_LISTS):
        raise SystemExit(f"params.PACKAGED_LISTS {PACKAGED_LISTS} does not match {names}")
    if sorted(TABLES) != sorted(PACKAGED_TABLES):
        raise SystemExit(f"params.PACKAGED_TABLES {list(PACKAGED_TABLES)} does not match {TABLES}")
    today = datetime.now(UTC).date().isoformat()
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    snapshot = _snapshot_date()
    REFERENCE.mkdir(exist_ok=True)
    lists: dict[str, list[str]] = {}
    dates: dict[str, str] = {}
    for name, (origin, fetch) in LISTS.items():
        values = sync(fetch)()
        exceptions: list[dict[str, str]] = []
        if name in SUPPLEMENTS:
            values, exceptions = _reconcile(name, values, spec)
            origin += f", reconciled with {SUPPLEMENTS[name][0]} (see exceptions)"
        lists[name], dates[name] = values, today
        _write(name, today, origin, values, exceptions)
    for name, (origin, read) in SPEC_LISTS.items():
        lists[name], dates[name] = read(spec), snapshot
        _write(name, snapshot, f"docs/upstream/{origin} (snapshot of {snapshot})", lists[name])
    # Classes in name order, so the generated __all__ is sorted as ruff wants it.
    class_names = {name: name[0].upper() + name[1:] for name in lists}
    ordered = {name: lists[name] for name in sorted(lists, key=class_names.__getitem__)}
    source = render_str_enums(
        ordered, class_names=class_names, generator="scripts/refresh_reference.py"
    )
    for name in ordered:
        # Each class carries its own list's date, so lists read from the snapshot keep theirs.
        plain = f'"""Values of ``{name}``."""'
        if source.count(plain) != 1:
            raise SystemExit(f"render_str_enums changed its docstrings; cannot date {name}")
        source = source.replace(plain, f'"""Values of ``{name}`` (fetched {dates[name]})."""')
    ENUMS.write_text(source, encoding="utf-8")
    print(f"{ENUMS.name}: {len(ordered)} enums")  # noqa: T201
    index = {name: _write_table(name, file, today) for name, file in TABLES.items()}
    (REFERENCE / TABLES_INDEX).write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"{TABLES_INDEX}: {len(index)} tables")  # noqa: T201


if __name__ == "__main__":
    main()
