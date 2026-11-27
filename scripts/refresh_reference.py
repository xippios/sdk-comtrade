"""Refresh the packaged reference data from upstream (``/refresh-reference-data``).

The script declares UN Comtrade's fifteen packaged lists and tables in one ``Lists``,
``LISTS``, and hands it to core's ``run`` (sdk-core ADR-0062), which fetches every list
through the declared fetch, the package's client with one attempt per request, each
counted, then writes each to ``reference/<name>.json`` with ``PackagedList.write``
(conventions §3, sdk-core ADR-0041) and the provenance rows of ``reference/README.md`` with
the origins of ``ORIGINS``, and no ``enums.py``, since no list declares an enum. Each file
holds the list's name, the upstream operation it came from, the UTC time of the fetch to the
second, upstream's records under upstream's field names and a ``note`` with its provenance
in words. The time is the ``retrieved_at`` the wrapper returns: a file the client's cache
answers, as it answers ``ListofReferences.json`` for the table after the ``clCode`` list
fetched it, carries the time its entry was stored, when it was fetched (conventions §4). A
list's record holds the value under the upstream parameter's name and, beside it, the
fields upstream gives the value a text in (``text``; ``qtyAbbr`` and ``qtyDescription``;
``variable`` and ``description``), under upstream's names; a value without one is a record
of one field. Every record is checked against its list's model, ``params.PACKAGED_LISTS``.
What the fetches declare is UN Comtrade's:

- ``LISTS_FROM_FILES`` come from UN Comtrade's public reference files, fetched through the
  layer-1 wrapper ``api.reference_rows`` (no key needed or sent): the ``id`` and ``text`` of
  ``tradeRegimes.json``, ``ModeOfTransportCodes.json``, ``CustomsCodes.json``,
  ``ModeOfSupply.json`` and ``Frequency.json``, the ``qtyCode`` values of
  ``QuantityUnits.json`` (the codes ``qtyUnitCode`` carries) with their ``qtyAbbr`` and
  ``qtyDescription``, and the ``clCode`` values as the ``cmd:<clCode>`` categories of
  ``ListofReferences.json`` with their ``variable`` and ``description``. A row the row
  model does not read, or a key it does not know, stops the script.
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
- ``WITHIN_ENUM`` cuts ``freqCode`` to the values of the spec's enum of the same name,
  ``A`` and ``M``, which every task takes: a value that ``Frequency.json`` holds no row of
  stops the script before it writes, and a row whose id the enum does not list, ``Q``, is
  left out, the list's ``note`` naming it with its text, one sentence per row.
- ``SPEC_LISTS`` have no reference file. They are read from the snapshot of the spec,
  ``docs/upstream/apidocs/comtrade.json``, operation ``get``: the ``typeCode`` and
  ``breakdownMode`` enums and the names ``aggregateBy``'s description lists, each value
  alone. A label names a code in upstream's own words, from upstream's own list (sdk-core
  ``docs/conventions.md``, §14, sentence 3), and a parameter's description is none, so no
  value of these lists carries words, though ``typeCode``'s description words its two.
  Their ``endpoint`` is the URL path upstream serves the spec at, their ``fetched`` the
  snapshot's, from ``docs/upstream/FETCHED.md``.

UN Comtrade reports no quota in a header: its ``x-ratelimit-*`` headers describe the
per-second pace, not the daily 500, so ``quota_header`` is ``None``. Run from the
repository root; no API key is needed or sent::

    uv run python scripts/refresh_reference.py                  # fetch every list
    uv run python scripts/refresh_reference.py --only motCode   # one list, the rest kept
    uv run python scripts/refresh_reference.py --render-only    # no request

A run sends eleven requests, one per reference file, ``Frequency.json`` among them, the
client's cache answering the ``ListofReferences`` table from the ``clCode`` list's fetch;
the three spec lists send none.
"""

import functools
import json
import re
from collections.abc import Callable, Coroutine, Sequence
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

from xippios.core import PackagedList, UpstreamModel, parse, sync
from xippios.core.refresh import Listed, Lists, run

from xippios.comtrade import api
from xippios.comtrade._client import SOURCE, client
from xippios.comtrade.models import QuantityUnit, Reference, ReferenceCode
from xippios.comtrade.params import PACKAGE, PACKAGED_LISTS, PACKAGED_TABLES

ROOT = Path(__file__).resolve().parents[1]
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
    for row in answer.payload:
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


LISTS_FROM_FILES: dict[str, tuple[str, str, Fetcher]] = {
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
    "freqCode": (
        "Frequency.json",
        "The ids of Frequency.json that the freqCode enum of "
        f"docs/upstream/{SPEC_NAME} (operation get) lists, with their text",
        lambda: _coded("Frequency.json", "freqCode"),
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


def _enum_values(spec: dict[str, Any], name: str) -> tuple[str, Records]:
    """The enum of parameter ``name``, each value a record of one field, without words.

    No reference file of UN Comtrade's lists the parameter, and the wording of its
    description is no list of upstream's, so a value takes none.
    """
    records = [{name: value} for value in _enum(spec, name)]
    return f"the {name} enum, values alone: no reference file of UN Comtrade's lists them", records


def _aggregate_by(spec: dict[str, Any]) -> tuple[str, Records]:
    description = str(_parameter(spec, "aggregateBy")["description"])
    _, sep, names = description.partition("Comma-separated list of:")
    if not sep:
        raise SystemExit(f"{SPEC_NAME}: aggregateBy no longer lists its names: {description!r}")
    records = [{"aggregateBy": name.strip()} for name in names.split(",") if name.strip()]
    return "the names the aggregateBy description lists, without wording", records


SPEC_LISTS: dict[str, Callable[[dict[str, Any]], tuple[str, Records]]] = {
    "typeCode": lambda spec: _enum_values(spec, "typeCode"),
    "breakdownMode": lambda spec: _enum_values(spec, "breakdownMode"),
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

WITHIN_ENUM: dict[str, str] = {
    "freqCode": f"the freqCode enum of docs/upstream/{SPEC_NAME} (operation get)",
}
"""Reference-file lists cut to the values of the spec's enum of their name: name to the enum.

``Frequency.json`` holds a row whose id the ``freqCode`` enum of no API document lists
("`Frequency.json` holds `Q`, which `getDA` refuses" in ``docs/upstream/OBSERVED.md``), so
the package offers ``A`` and ``M`` and the list's ``note`` names ``Q``, by the maintainer's
decision of 2026-11-27 (https://github.com/xippios/sdk-comtrade/issues/68).
"""


def _within_enum(name: str, file: str, records: Records) -> tuple[Records, list[str]]:
    """``records`` cut to the values of the spec's enum ``name``, and a sentence per row left out.

    Raises:
        SystemExit: A value of the enum has no row in ``file``, before anything is written:
            the reading follows the file's rows before the script runs again.
    """
    values = _enum(_spec(), name)
    held = {record[name] for record in records}
    if missing := [value for value in values if value not in held]:
        raise SystemExit(
            f"{file}: no row of {', '.join(missing)}, which {WITHIN_ENUM[name]} lists; "
            "nothing was written"
        )
    left_out = [
        f"{record[name]} ({record['text']}) left out: a row of {file} that the enum does not list."
        for record in records
        if record[name] not in values
    ]
    return [record for record in records if record[name] in values], left_out


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

    A bare date, as an older snapshot recorded it, reads as 00:00 UTC of that day.
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


@functools.cache
def _spec() -> dict[str, Any]:
    """The spec snapshot, read once for every list a run fetches."""
    return dict(json.loads(SPEC.read_text(encoding="utf-8")))


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


def from_file(name: str) -> PackagedList:
    """The reference-file list ``name``, fetched now and reconciled with the spec.

    ``fetched`` is the file's ``retrieved_at``. A list of ``WITHIN_ENUM`` keeps the rows of
    its enum's values alone. A value the reconciliation adds keeps its value alone, since the
    spec gives it no text; one it removes takes its record with it.
    """
    file, what, fetch = LISTS_FROM_FILES[name]
    records, fetched = sync(fetch)()
    note = f"{what}."
    if name in WITHIN_ENUM:
        records, left_out = _within_enum(name, file, records)
        note = " ".join([note, *left_out])
    if name in SUPPLEMENTS:
        values, exceptions = _reconcile(name, [record[name] for record in records], _spec())
        by_value = {record[name]: record for record in records}
        records = [by_value.get(value, {name: value}) for value in values]
        note = f"{what}, reconciled with {SUPPLEMENTS[name][0]}. {' '.join(exceptions)}"
    return _value_list(name, f"{FILES}{file}", fetched, note.rstrip(), records)


def from_spec(name: str) -> PackagedList:
    """The list ``name`` as the spec snapshot documents it, with the wording it gives."""
    what, records = SPEC_LISTS[name](_spec())
    fetched = _snapshot_fetched()
    note = (
        f"Read from docs/upstream/{SPEC_NAME}, the snapshot of {SPEC_ENDPOINT} fetched "
        f"{fetched:%Y-%m-%d}: operation get, {what}."
    )
    return _value_list(name, SPEC_ENDPOINT, fetched, note, records)


def table(name: str) -> PackagedList:
    """The table ``name``, fetched now: upstream's rows with the keys upstream sent.

    ``fetched`` is the file's ``retrieved_at``, the time its cache entry was stored where
    the client's cache answered.
    """
    file = TABLES[name]
    model = PACKAGED_TABLES[name]
    endpoint = f"{FILES}{file}"
    answer = sync(api.reference_rows)(file)
    records: list[dict[str, Any]] = []
    for row in answer.payload:
        dumped = parse(model, row, source=SOURCE, endpoint=endpoint).dump_upstream()
        unknown = sorted(set(row) - set(dumped))
        if unknown:
            raise SystemExit(f"{file}: keys {unknown} are not in {model.__name__}")
        records.append({key: value for key, value in dumped.items() if key in row})
    return PackagedList(
        param=name,
        endpoint=endpoint,
        fetched=answer.retrieved_at,
        note=TABLE_NOTES.get(name),
        records=records,
    )


def _rows_of(text: str) -> Callable[[PackagedList], str]:
    """A table's origin, its row count read from the list as written."""
    return lambda packaged: text.format(rows=f"{len(packaged.records):,}")


ORIGINS: dict[str, str | Callable[[PackagedList], str]] = {
    "aggregateBy": (
        "`docs/upstream/apidocs/comtrade.json`, operation `get`, the names `aggregateBy`'s "
        "description lists, values alone (same snapshot)"
    ),
    "breakdownMode": (
        "`docs/upstream/apidocs/comtrade.json`, operation `get`, the `breakdownMode` enum, "
        'values alone: the description ("Breakdown mode to choose from") words none (same '
        "snapshot)"
    ),
    "clCode": (
        "the `cmd:<clCode>` categories of "
        "https://comtradeapi.un.org/files/v1/app/reference/ListofReferences.json with their "
        "`variable` and `description`, plus `BE` and `TM`, values alone, from the `clCode` "
        "enum of `docs/upstream/apidocs/comtrade.json` (operation `get`), which upstream "
        "accepted (`tests/fixtures/get/count_cl_code_be.json`, `count_cl_code_tm.json`); the "
        "enum's `BE5` left out, refused (`count_cl_code_be5.json`). Every other value rests "
        "on a recorded count too (HTTP 200), except `H6`, which answered HTTP 500 to all five "
        "tries and stays, unsettled. Exceptions and evidence are in the file's `note`"
    ),
    "customsCode": (
        "`id` and `text` of https://comtradeapi.un.org/files/v1/app/reference/CustomsCodes.json"
    ),
    "flowCode": (
        "`id` and `text` of https://comtradeapi.un.org/files/v1/app/reference/tradeRegimes.json, "
        "plus `MIF` and `XIF`, values alone, from the `flowCode` description of "
        "`docs/upstream/apidocs/comtrade.json` (operation `get`), which lists values without "
        "wording; upstream accepted both (`tests/fixtures/get/count_flow_code_mif.json`, "
        "`count_flow_code_xif.json`, HTTP 200). Exceptions and evidence are in the file's "
        "`note`"
    ),
    "freqCode": (
        "`id` and `text` of https://comtradeapi.un.org/files/v1/app/reference/Frequency.json, "
        "which `ListofReferences.json` lists for the variable Frequency, the rows whose id the "
        "`freqCode` enum of `docs/upstream/apidocs/comtrade.json` (operation `get`) lists; the "
        "file's `Q` left out, as the file's `note` says"
    ),
    "mosCode": (
        "`id` and `text` of https://comtradeapi.un.org/files/v1/app/reference/ModeOfSupply.json. "
        "The file's ids (`0`, `Mode 1` to `Mode 4`), not proven parameter values: "
        "`data/v1/get` accepts `mosCode` though the spec does not list it, refused `Mode 1` "
        "and accepted `0` and `1` (`tests/fixtures/get/count_services_eb10_mos_code_*.json`). "
        "`mosCode` is not a task parameter; the file's `note` says the same"
    ),
    "motCode": (
        "`id` and `text` of "
        "https://comtradeapi.un.org/files/v1/app/reference/ModeOfTransportCodes.json"
    ),
    "qtyUnitCode": (
        "`qtyCode`, as text, with `qtyAbbr` and `qtyDescription`, of "
        "https://comtradeapi.un.org/files/v1/app/reference/QuantityUnits.json, the codes "
        "`qtyUnitCode` and `altQtyUnitCode` carry on trade rows"
    ),
    "typeCode": (
        "`docs/upstream/apidocs/comtrade.json`, operation `get`, the `typeCode` enum, values "
        "alone: no reference file of UN Comtrade's lists them (snapshot of "
        "https://comtradeapi.un.org/files/v1/app/apim/comtrade.json)"
    ),
    "Reporters": _rows_of(
        "https://comtradeapi.un.org/files/v1/app/reference/Reporters.json, every column "
        "({rows} rows)"
    ),
    "partnerAreas": _rows_of(
        "https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json, every column "
        "({rows} rows)"
    ),
    "country_area_code_iso": _rows_of(
        "https://comtradeapi.un.org/files/v1/app/reference/country_area_code_iso.json ({rows} "
        "rows). Not in `ListofReferences.json`; it is the table the official "
        "`comtradeapicall` package (1.3.2, `convertCountryIso3ToCode`) reads to map ISO "
        "alpha-3 codes to UN Comtrade's"
    ),
    "TradeDataItems": _rows_of(
        "https://comtradeapi.un.org/files/v1/app/reference/TradeDataItems.json, every column "
        "({rows} rows); also in the snapshot as `docs/upstream/reference/TradeDataItems.json`"
    ),
    "ListofReferences": _rows_of(
        "https://comtradeapi.un.org/files/v1/app/reference/ListofReferences.json, the index of "
        "the reference files, every column ({rows} rows: `category`, `variable`, "
        "`description`, `fileuri`); also in the snapshot as "
        "`docs/upstream/reference/ListofReferences.json`"
    ),
}
"""The Origin of each list's provenance row in ``reference/README.md``, as the README keeps it."""


def _listed(name: str, fetch: Callable[[str], PackagedList]) -> Listed:
    return Listed(name, functools.partial(fetch, name), origin=ORIGINS[name])


LISTS = Lists(
    package=PACKAGE,
    lists=(
        *(_listed(name, from_file) for name in LISTS_FROM_FILES),
        *(_listed(name, from_spec) for name in SPEC_LISTS),
        *(_listed(name, table) for name in TABLES),
    ),
    packaged=(*PACKAGED_LISTS, *PACKAGED_TABLES),
    client=client,
    quota_header=None,
)
"""The fifteen packaged lists and tables, the ``clCode`` list before the ``ListofReferences``
table, which the client's cache then answers; no enum."""


def main(argv: Sequence[str] | None = None) -> int:
    """Run core's frame on ``LISTS``: every list, some with ``--only``, or ``--render-only``."""
    return run(LISTS, argv)


if __name__ == "__main__":
    raise SystemExit(main())
