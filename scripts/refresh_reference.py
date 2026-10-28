"""Refresh the packaged reference data from upstream (``/refresh-reference-data``).

Fetches every list in ``LISTS`` and table in ``TABLES``, reads every list in
``SPEC_LISTS``, and only then writes each to ``reference/<name>.json`` with
``PackagedList.write`` (conventions §3, ADR-0022): the list's name, the upstream
operation it came from, the UTC time of the fetch to the second, upstream's records under
upstream's field names and a ``note`` with its provenance in words. The time is the
``retrieved_at`` the wrapper returns: a file the client's cache answers, as it answers
``ListofReferences.json`` for the table after the ``clCode`` list fetched it, carries the
time its entry was stored, when it was fetched (conventions §4). A list's record holds
the value under the upstream parameter's name and, beside it, the fields upstream gives
the value a text in (``text``; ``qtyAbbr`` and ``qtyDescription``; ``variable`` and
``description``), under upstream's names; a value without one is a record of one field.
Every record is checked against its list's model, ``params.PACKAGED_LISTS``. Then
``enums.py`` is regenerated from the packaged files by one
``xippios.core.reference.render_enums`` call, one ``StrEnum`` per list, its members the
values, each class naming the day its list was fetched, and formatted with ``ruff format``
and ``ruff check --fix``, as it is committed (ADR-0008).

- ``LISTS`` come from UN Comtrade's public reference files, fetched through the layer-1
  wrapper ``api.reference_rows`` (no key needed or sent): the ``id`` and ``text`` of
  ``tradeRegimes.json``, ``ModeOfTransportCodes.json``, ``CustomsCodes.json`` and
  ``ModeOfSupply.json``, the ``qtyCode`` values of ``QuantityUnits.json`` (the codes
  ``qtyUnitCode`` carries) with their ``qtyAbbr`` and ``qtyDescription``, and the
  ``clCode`` values as the ``cmd:<clCode>`` categories of ``ListofReferences.json`` with
  their ``variable`` and ``description``. A key the row model does not know stops the
  script.
- ``TABLES`` are reference files that are tables rather than value lists:
  ``Reporters.json``, ``partnerAreas.json``, ``TradeDataItems.json``,
  ``ListofReferences.json`` (the index of the reference files) and
  ``country_area_code_iso.json``. The last is not in ``ListofReferences.json``; it is the
  table the official ``comtradeapicall`` package (1.3.2, ``convertCountryIso3ToCode``)
  reads to map ISO alpha-3 codes to UN Comtrade's. Each row is parsed with its row model
  (``params.PACKAGED_TABLES``) and written by ``dump_upstream``, with the keys upstream
  sent and no other: a key upstream leaves out of a row stays out, and a key the model
  does not know stops the script.
- ``SUPPLEMENTS`` reconcile two of those with the spec, where the two disagree. The
  values the spec documents for ``flowCode`` are all added (``MIF`` and ``XIF`` are
  missing from ``tradeRegimes.json``). For ``clCode``, a value of the spec's enum is added
  only when a recorded answer shows upstream accepting it, and any value a recorded
  answer shows refused is left out. ``EVIDENCE`` names those recordings, and the list's
  ``note`` names each exception, one sentence per value: the decision and the evidence.
- ``SPEC_LISTS`` have no reference file. They are read from the snapshot of the spec,
  ``docs/upstream/apidocs/comtrade.json``, operation ``get``: the ``typeCode``,
  ``freqCode`` and ``breakdownMode`` enums, each value with the wording the parameter's
  description gives it as ``text`` ("C for commodities" gives ``C`` the text
  ``commodities``; ``breakdownMode``'s gives none), and the names ``aggregateBy``'s
  description lists, without wording. Their ``endpoint`` is the URL path upstream serves
  the spec at, their ``fetched`` the snapshot's, from ``docs/upstream/FETCHED.md``.

Run from the repository root; no API key is needed::

    uv run python scripts/refresh_reference.py

``--render-only`` regenerates ``enums.py`` from the packaged ``reference/*.json`` alone,
without a request: after a core release changes the renderer (conventions §15, item 6),
it changes ``enums.py`` and nothing else.
"""

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Coroutine, Sequence
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

from xippios.core import PackagedList, UpstreamModel, parse, sync
from xippios.core.reference import render_enums

from xippios.comtrade import api
from xippios.comtrade._client import SOURCE
from xippios.comtrade.models import QuantityUnit, Reference, ReferenceCode
from xippios.comtrade.params import PACKAGED_LISTS, PACKAGED_TABLES

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "src/xippios/comtrade"
REFERENCE = PACKAGE_DIR / "reference"
ENUMS = PACKAGE_DIR / "enums.py"
GENERATOR = "scripts/refresh_reference.py"
SPEC = ROOT / "docs/upstream/apidocs/comtrade.json"
SPEC_NAME = "apidocs/comtrade.json"
SPEC_ENDPOINT = "files/v1/app/apim/comtrade.json"
"""The URL path upstream serves the spec at: ``endpoint`` of the lists read from it."""
FETCHED = ROOT / "docs/upstream/FETCHED.md"
FILES = "files/v1/app/reference/"
OPERATION = "/get/{typeCode}/{freqCode}/{clCode}"
FIXTURES = ROOT / "tests/fixtures/get"

Records = list[dict[str, str]]
"""A list's records: the value under the parameter's name, upstream's text fields beside it."""

Fetcher = Callable[[], Coroutine[Any, Any, tuple[Records, datetime]]]
"""An async fetcher of a list's records through ``api/``, with the file's ``retrieved_at``."""


async def _rows[M: UpstreamModel](file: str, model: type[M]) -> tuple[list[M], datetime]:
    """The rows of the reference file ``file`` as ``model`` and when the file was retrieved.

    A key the model does not know stops the script.
    """
    endpoint = f"{FILES}{file}"
    answer = await api.reference_rows(file)
    rows: list[M] = []
    for row in answer.rows:
        parsed = parse(model, row, source=SOURCE, endpoint=endpoint)
        unknown = sorted(set(row) - set(parsed.dump_upstream()))
        if unknown:
            raise SystemExit(f"{file}: keys {unknown} are not in {model.__name__}")
        rows.append(parsed)
    return rows, answer.retrieved_at


async def _coded(file: str, name: str) -> tuple[Records, datetime]:
    """The ``id`` of each row of ``file`` under the name ``name``, with its ``text``."""
    rows, retrieved_at = await _rows(file, ReferenceCode)
    return [{name: row.id, "text": row.text} for row in rows], retrieved_at


async def _cl_codes() -> tuple[Records, datetime]:
    prefix = "cmd:"
    references, retrieved_at = await _rows("ListofReferences.json", Reference)
    records = [
        {
            "clCode": ref.category.removeprefix(prefix),
            "variable": ref.variable,
            "description": ref.description,
        }
        for ref in references
        if ref.category.startswith(prefix)
    ]
    return records, retrieved_at


async def _qty_codes() -> tuple[Records, datetime]:
    units, retrieved_at = await _rows("QuantityUnits.json", QuantityUnit)
    records = [
        {
            "qtyUnitCode": str(unit.qty_code),
            "qtyAbbr": unit.qty_abbr,
            "qtyDescription": unit.qty_description,
        }
        for unit in units
    ]
    return records, retrieved_at


LISTS: dict[str, tuple[str, str, Fetcher]] = {
    "clCode": (
        "ListofReferences.json",
        "The cmd:<clCode> categories of ListofReferences.json with their variable and "
        "description (neither for a value added from the spec)",
        _cl_codes,
    ),
    "flowCode": (
        "tradeRegimes.json",
        "The ids of tradeRegimes.json with their text (none for a value added from the spec)",
        lambda: _coded("tradeRegimes.json", "flowCode"),
    ),
    "customsCode": (
        "CustomsCodes.json",
        "The ids of CustomsCodes.json with their text",
        lambda: _coded("CustomsCodes.json", "customsCode"),
    ),
    "motCode": (
        "ModeOfTransportCodes.json",
        "The ids of ModeOfTransportCodes.json with their text",
        lambda: _coded("ModeOfTransportCodes.json", "motCode"),
    ),
    "mosCode": (
        "ModeOfSupply.json",
        "The ids of ModeOfSupply.json with their text, not proven parameter values: "
        "data/v1/get, which takes mosCode though the spec does not list it, refused 'Mode 1' "
        "(HTTP 400, tests/fixtures/get/count_services_eb10_mos_code_mode_1.json) and accepted "
        "'0' and '1' (count_services_eb10_mos_code_0.json, count_services_eb10_mos_code_1.json). "
        "mosCode is not a parameter of the tasks; trade rows carry it as mos_code",
        lambda: _coded("ModeOfSupply.json", "mosCode"),
    ),
    "qtyUnitCode": (
        "QuantityUnits.json",
        "The qtyCode values of QuantityUnits.json with their qtyAbbr and qtyDescription, the "
        "codes qtyUnitCode and altQtyUnitCode carry on trade rows",
        _qty_codes,
    ),
}
"""Lists from reference files: name to (the file, what the list is, fetcher through ``api/``).

What the list is opens its packaged file's ``note``.
"""

TABLES: dict[str, str] = {
    "Reporters": "Reporters.json",
    "partnerAreas": "partnerAreas.json",
    "country_area_code_iso": "country_area_code_iso.json",
    "TradeDataItems": "TradeDataItems.json",
    "ListofReferences": "ListofReferences.json",
}
"""Tables from reference files: name of the packaged list (``params.PACKAGED_TABLES``) to file."""

TABLE_NOTES: dict[str, str] = {
    "country_area_code_iso": (
        "Not in ListofReferences.json: the table the official comtradeapicall package "
        "(1.3.2, convertCountryIso3ToCode) reads to map ISO alpha-3 codes to UN Comtrade's."
    ),
}
"""A table's provenance in words, where its file alone does not say it."""


def _parameter(spec: dict[str, Any], name: str) -> dict[str, Any]:
    for parameter in spec["paths"][OPERATION]["get"]["parameters"]:
        if parameter["name"] == name:
            return dict(parameter)
    raise SystemExit(f"{SPEC_NAME}: operation get has no parameter {name!r}")


def _enum(spec: dict[str, Any], name: str) -> list[str]:
    return [str(value) for value in _parameter(spec, name)["schema"]["enum"]]


_WORDING = re.compile(r"(\S+) for (.+?)(?= and |, |$)")
"""One value's wording in a parameter's description: ``C for commodities``."""


def _enum_records(spec: dict[str, Any], name: str) -> tuple[str, Records]:
    """The enum of parameter ``name``, each value with the wording its description gives it.

    The description lists the wording after a colon ("Type of trade: C for commodities and
    S for service"); a value it does not word is a record of one field. A worded value the
    enum lacks stops the script.
    """
    values = _enum(spec, name)
    description = str(_parameter(spec, name)["description"])
    _, colon, listing = description.partition(":")
    wording = dict(_WORDING.findall(listing.strip())) if colon else {}
    unknown = sorted(set(wording) - set(values))
    if unknown:
        raise SystemExit(f"{SPEC_NAME}: {name}'s description words {unknown}, not in its enum")
    records = [
        {name: value, "text": wording[value]} if value in wording else {name: value}
        for value in values
    ]
    said = (
        f'with the wording its description, "{description}", gives each value as text'
        if wording
        else f'whose description, "{description}", words no value'
    )
    return f"the {name} enum, {said}", records


def _aggregate_by(spec: dict[str, Any]) -> tuple[str, Records]:
    description = str(_parameter(spec, "aggregateBy")["description"])
    _, sep, names = description.partition("Comma-separated list of:")
    if not sep:
        raise SystemExit(f"{SPEC_NAME}: aggregateBy no longer lists its names: {description!r}")
    records = [{"aggregateBy": name.strip()} for name in names.split(",") if name.strip()]
    return "the names the aggregateBy description lists, without wording", records


SPEC_LISTS: dict[str, Callable[[dict[str, Any]], tuple[str, Records]]] = {
    "typeCode": lambda spec: _enum_records(spec, "typeCode"),
    "freqCode": lambda spec: _enum_records(spec, "freqCode"),
    "breakdownMode": lambda spec: _enum_records(spec, "breakdownMode"),
    "aggregateBy": _aggregate_by,
}
"""Lists from the spec snapshot, operation ``get``: name to its reader, which returns what
was read, in words for the ``note``, and the records."""


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

_H6 = (
    "count_cl_code_h6.json",
    "count_cl_code_h6_retried.json",
    "count_cl_code_h6_retried_later.json",
    "count_cl_code_h6_cmd_code_01.json",
    "count_cl_code_h6_usa.json",
)

EVIDENCE: dict[str, dict[str, tuple[str, ...]]] = {
    "flowCode": {
        "MIF": ("count_flow_code_mif.json",),
        "XIF": ("count_flow_code_xif.json",),
    },
    "clCode": {
        "BE": ("count_cl_code_be.json",),
        "BE5": ("count_cl_code_be5.json",),
        "TM": ("count_cl_code_tm.json",),
        "HS": ("count_ch_exports_2023.json",),
        "H6": _H6,
        **{
            value: (f"count_cl_code_{value.lower()}.json",)
            for value in [
                *("H0", "H1", "H2", "H3", "H4", "H5"),
                *("B4", "B5", "S1", "S2", "S3", "S4", "SS"),
                *("EB", "EB02", "EB10", "EB10S"),
            ]
        },
    },
}
"""Recorded ``data/v1/get`` counts under ``tests/fixtures/get/`` that try one value.

Every ``clCode`` value has at least one: the fixture query (757, partner 0, 2023, exports,
``TOTAL``) with ``countOnly``; the EBOPS ones with ``typeCode`` S and the services total
their files document (``200``, or ``S`` for EB10S). HTTP 200 means upstream accepted the
value, HTTP 400 that it refused it; anything else settles nothing. Where a value has several
recordings, one 200 settles it as accepted, else one 400 as refused.
"""


def _verdict(name: str, value: str) -> tuple[str, str] | None:
    fixtures = EVIDENCE.get(name, {}).get(value)
    if not fixtures:
        return None
    statuses = [
        json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))["response"]["status"]
        for fixture in fixtures
    ]
    if 200 in statuses:
        outcome = "accepted it"
    elif 400 in statuses:
        outcome = "refused it"
    else:
        outcome = "answered without settling it"
    cited = "; ".join(
        f"tests/fixtures/get/{fixture}, HTTP {status}"
        for fixture, status in zip(fixtures, statuses, strict=True)
    )
    return outcome, cited


def _reconcile(name: str, base: list[str], spec: dict[str, Any]) -> tuple[list[str], list[str]]:
    """``base`` with the spec's extra values added or left out, refused ones removed.

    Returns the values and one sentence per exception, ``"<value> <decision>: <evidence>."``,
    the decision ``added``, ``left out``, ``removed`` or ``kept``.
    """
    origin, read, add_unexercised = SUPPLEMENTS[name]
    values = list(base)
    exceptions: list[str] = []
    for value in read(spec):
        if value in base:
            continue
        verdict = _verdict(name, value)
        accepted = verdict[0] == "accepted it" if verdict else add_unexercised
        if accepted:
            values.append(value)
        seen = f"upstream {verdict[0]} ({verdict[1]})" if verdict else "not tried upstream"
        decision = "added" if accepted else "left out"
        exceptions.append(f"{value} {decision}: listed in {origin}; {seen}.")
    for value in base:
        verdict = _verdict(name, value)
        if verdict is None:
            continue
        refused = verdict[0] == "refused it"
        if refused:
            values.remove(value)
        decision = "removed" if refused else "kept"
        exceptions.append(
            f"{value} {decision}: in the reference file; upstream {verdict[0]} ({verdict[1]})."
        )
    return values, exceptions


def _snapshot_fetched() -> datetime:
    """When the spec snapshot was fetched, from its row in ``docs/upstream/FETCHED.md``.

    A bare date, as the snapshot of 2026-10-23 recorded it, reads as 00:00 UTC of that day.
    """
    match = re.search(
        rf"^\| {re.escape(SPEC_NAME)} \| \S+ \| (\d{{4}}-\d{{2}}-\d{{2}}(?:T[0-9:]+Z)?) \|",
        FETCHED.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if match is None:
        raise SystemExit(f"{FETCHED} has no row for {SPEC_NAME}")
    text = match.group(1)
    if "T" in text:
        return datetime.fromisoformat(text).astimezone(UTC)
    return datetime.combine(date.fromisoformat(text), time(), UTC)


def _value_list(
    name: str, endpoint: str, fetched: datetime, note: str, records: Records
) -> PackagedList:
    """The packaged list ``name``; a record its model in ``PACKAGED_LISTS`` refuses stops it."""
    model = PACKAGED_LISTS[name]
    for record in records:
        dumped = parse(model, record, source=SOURCE, endpoint=endpoint).dump_upstream()
        if {key: dumped.get(key) for key in record} != record:
            raise SystemExit(f"{name}: a record does not fit {model.__name__}: {record}")
    return PackagedList(param=name, endpoint=endpoint, fetched=fetched, note=note, records=records)


def _list(name: str, spec: dict[str, Any]) -> PackagedList:
    """The reference-file list ``name``, fetched now and reconciled with the spec.

    ``fetched`` is the file's ``retrieved_at``. A value the reconciliation adds keeps its
    value alone, since the spec gives it no text; one it removes takes its record with it.
    """
    file, what, fetch = LISTS[name]
    records, fetched = sync(fetch)()
    note = f"{what}."
    if name in SUPPLEMENTS:
        values, exceptions = _reconcile(name, [record[name] for record in records], spec)
        by_value = {record[name]: record for record in records}
        records = [by_value.get(value, {name: value}) for value in values]
        note = f"{what}, reconciled with {SUPPLEMENTS[name][0]}. {' '.join(exceptions)}"
    return _value_list(name, f"{FILES}{file}", fetched, note.rstrip(), records)


def _spec_list(name: str, spec: dict[str, Any], fetched: datetime) -> PackagedList:
    """The list ``name`` as the spec snapshot documents it, with the wording it gives."""
    what, records = SPEC_LISTS[name](spec)
    note = (
        f"Read from docs/upstream/{SPEC_NAME}, the snapshot of {SPEC_ENDPOINT} fetched "
        f"{fetched:%Y-%m-%d}: operation get, {what}."
    )
    return _value_list(name, SPEC_ENDPOINT, fetched, note, records)


def _table(name: str) -> PackagedList:
    """The table ``name``, fetched now: upstream's rows with the keys upstream sent.

    ``fetched`` is the file's ``retrieved_at``, the time its cache entry was stored where
    the client's cache answered.
    """
    file = TABLES[name]
    model = PACKAGED_TABLES[name]
    endpoint = f"{FILES}{file}"
    rows, fetched = sync(api.reference_rows)(file)
    records: list[dict[str, Any]] = []
    for row in rows:
        dumped = parse(model, row, source=SOURCE, endpoint=endpoint).dump_upstream()
        unknown = sorted(set(row) - set(dumped))
        if unknown:
            raise SystemExit(f"{file}: keys {unknown} are not in {model.__name__}")
        records.append({key: value for key, value in dumped.items() if key in row})
    return PackagedList(
        param=name, endpoint=endpoint, fetched=fetched, note=TABLE_NOTES.get(name), records=records
    )


def read(name: str) -> PackagedList:
    """The packaged ``reference/<name>.json``, read from the file as it is now."""
    path = REFERENCE / f"{name}.json"
    if not path.is_file():
        raise SystemExit(f"{path.name} is not packaged yet: run the script without --render-only")
    return PackagedList.model_validate_json(path.read_text(encoding="utf-8"))


def render() -> None:
    """Regenerate ``enums.py`` from the packaged value lists and format it as committed."""
    lists: dict[str, Sequence[str]] = {}
    fetched: dict[str, str] = {}
    # Classes in the order of their names, as enums.py has always listed them.
    class_names = {name: name[0].upper() + name[1:] for name in PACKAGED_LISTS}
    for name in sorted(PACKAGED_LISTS, key=class_names.__getitem__):
        packaged = read(name)
        lists[name] = [str(record[name]) for record in packaged.records]
        fetched[name] = f"{packaged.fetched:%Y-%m-%d}"
    module = render_enums(lists, fetched=fetched, class_names=class_names, generator=GENERATOR)
    ENUMS.write_text(module, encoding="utf-8")
    sys.stdout.flush()
    for command in (["format"], ["check", "--fix"]):
        run = subprocess.run([sys.executable, "-m", "ruff", *command, str(ENUMS)], cwd=ROOT)
        if run.returncode:
            raise SystemExit(f"ruff {' '.join(command)} left {ENUMS.name} failing")
    print(f"{ENUMS.name}: {len(lists)} enums")  # noqa: T201


def refresh() -> None:
    """Fetch every list and table, then write their files, then regenerate ``enums.py``."""
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    snapshot = _snapshot_fetched()
    packaged = [
        *(_list(name, spec) for name in LISTS),
        *(_spec_list(name, spec, snapshot) for name in SPEC_LISTS),
        *(_table(name) for name in TABLES),
    ]
    REFERENCE.mkdir(exist_ok=True)
    for fetched in packaged:
        path = REFERENCE / f"{fetched.param}.json"
        fetched.write(path)
        print(f"{path.name}: {len(fetched.records)} records from {fetched.endpoint}")  # noqa: T201
    render()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """The command line: ``--render-only``; ``--help`` exits before any fetch."""
    summary, _, details = (__doc__ or "").partition("\n\n")
    parser = argparse.ArgumentParser(
        prog="refresh_reference.py",
        description=summary,
        epilog=details,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="regenerate enums.py from the packaged reference/*.json, without a request",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    """Refresh from upstream, or with ``--render-only`` regenerate ``enums.py`` alone."""
    args = parse_args(argv)
    names = [*LISTS, *SPEC_LISTS]
    if sorted(names) != sorted(PACKAGED_LISTS):
        raise SystemExit(f"params.PACKAGED_LISTS {list(PACKAGED_LISTS)} does not match {names}")
    if sorted(TABLES) != sorted(PACKAGED_TABLES):
        raise SystemExit(f"params.PACKAGED_TABLES {list(PACKAGED_TABLES)} does not match {TABLES}")
    if args.render_only:
        render()
    else:
        refresh()


if __name__ == "__main__":
    main()
