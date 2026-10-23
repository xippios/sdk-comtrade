"""Packaged reference data for UN Comtrade and the checks run before a call (conventions §3).

Small, stable upstream lists and tables ship inside the package under ``reference/`` so
lookups and checks need no network call; ``scripts/refresh_reference.py`` writes them and
the matching ``StrEnum`` classes in ``enums.py``, never by hand. ``reference/README.md``
carries the provenance of every file. Value lists are ``<name>.json``
(``packaged_values``); tables are ``<name>.csv`` with upstream's columns
(``packaged_table``), their origin and fetch date in ``tables.json``. ``validate_get``
checks the arguments of a ``data/v1/get`` call against them, and the free-form ones by
shape, before anything is sent (ADR-0007); ``validate_datasets`` does the same for
``data/v1/getDa`` and ``data/v1/getMetadata``.
"""

import difflib
import functools
import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, cast

from pydantic import Field
from xippios.core import InvalidRequestError, UpstreamModel, load_json, load_table

from xippios.comtrade._client import SOURCE
from xippios.comtrade.errors import MAX_PERIODS
from xippios.comtrade.models import CountryAreaCodeIso, PartnerArea, Reporter, TradeDataItem

__all__ = [
    "PACKAGED_LISTS",
    "PACKAGED_TABLES",
    "ListException",
    "PackagedTable",
    "PackagedValues",
    "classification_files",
    "packaged_table",
    "packaged_table_info",
    "packaged_values",
    "validate_classification_file",
    "validate_datasets",
    "validate_get",
]

PACKAGE = "xippios.comtrade"

PACKAGED_LISTS: tuple[str, ...] = (
    "typeCode",
    "freqCode",
    "clCode",
    "flowCode",
    "customsCode",
    "motCode",
    "aggregateBy",
    "breakdownMode",
    "mosCode",
    "qtyUnitCode",
)
"""Names of the lists that ship inside the package; keep in step with the refresh script."""

PACKAGED_TABLES: Mapping[str, type[UpstreamModel]] = {
    "Reporters": Reporter,
    "partnerAreas": PartnerArea,
    "country_area_code_iso": CountryAreaCodeIso,
    "TradeDataItems": TradeDataItem,
}
"""Tables that ship as ``reference/<name>.csv``, named after the upstream file, and their row
model; keep in step with the refresh script."""

TABLES_INDEX = "tables.json"


class ListException(UpstreamModel):
    """A value where a packaged list departs from its reference file, with the evidence.

    Attributes:
        value: The value.
        decision: ``"added"``, ``"left out"``, ``"removed"`` or ``"kept"``.
        evidence: Where the value is documented and what upstream answered to it.
    """

    value: str
    decision: str
    evidence: str


class PackagedValues(UpstreamModel):
    """One packaged value list: ``reference/<name>.json``.

    Attributes:
        param: The upstream parameter the values belong to.
        fetched: Day the list was fetched (for lists read from the spec, the day the
            snapshot was fetched).
        origin: The reference file or snapshot entry the values come from.
        note: What the values are and are not, where the list needs saying so.
        exceptions: Values the refresh script reconciled with the spec, with evidence.
        values: The values, as upstream lists them, reconciled values last.
    """

    param: str
    fetched: date
    origin: str | None = None
    note: str | None = None
    exceptions: list[ListException] = Field(default_factory=list)
    values: list[str]


class PackagedTable(UpstreamModel):
    """Provenance of one packaged table: an entry of ``reference/tables.json``.

    Attributes:
        file: The CSV file under ``reference/``, e.g. ``"Reporters.csv"``.
        origin: The upstream file it was written from.
        fetched: Day it was fetched.
        rows: Rows it holds.
    """

    file: str
    origin: str
    fetched: date
    rows: int


def packaged_values(name: str) -> PackagedValues | None:
    """The packaged list ``name``, or ``None`` when it is not packaged."""
    if name not in PACKAGED_LISTS:
        return None
    return PackagedValues.model_validate(load_json(PACKAGE, f"{name}.json"))


def packaged_table_info(name: str) -> PackagedTable | None:
    """Provenance of the packaged table ``name``, or ``None`` when it is not packaged."""
    if name not in PACKAGED_TABLES:
        return None
    return PackagedTable.model_validate(load_json(PACKAGE, TABLES_INDEX)[name])


@functools.cache
def _table(name: str) -> tuple[UpstreamModel, ...]:
    return tuple(load_table(PACKAGE, f"{name}.csv", PACKAGED_TABLES[name]))


def packaged_table[M: UpstreamModel](name: str, model: type[M]) -> list[M]:
    """Rows of the packaged table ``name`` (``reference/<name>.csv``) as ``model`` instances.

    Args:
        name: A key of ``PACKAGED_TABLES``, e.g. ``"Reporters"``.
        model: Its row model, e.g. ``Reporter``.

    Raises:
        KeyError: When ``name`` is not packaged or ``model`` is not its row model.
    """
    if PACKAGED_TABLES.get(name) is not model:
        raise KeyError(f"{name!r} is not a packaged table of {model.__name__} rows")
    return list(cast(tuple[M, ...], _table(name)))


@functools.cache
def _allowed(name: str) -> tuple[str, ...]:
    packaged = packaged_values(name)
    if packaged is None:  # pragma: no cover - PACKAGED_LISTS and the files move together
        raise KeyError(name)
    return tuple(packaged.values)


_AREA = re.compile(r"\d+")
_PERIOD = re.compile(r"\d{4}(0[1-9]|1[0-2])?")
_KEYWORD = re.compile(r"TOTAL|AG[1-6]", re.IGNORECASE)
_WILDCARD = r"(\*|\?+)?"
_CMD_SHAPES: dict[str, tuple[re.Pattern[str], str]] = {
    "goods": (re.compile(r"\d+" + _WILDCARD), "digits, e.g. '0901' or '27??'"),
    "sitc": (re.compile(r"\d+X*" + _WILDCARD), "digits with optional trailing X, e.g. '001X'"),
    "services": (
        re.compile(r"[0-9A-Za-z]+(\.[0-9A-Za-z]+)*" + _WILDCARD),
        "letters, digits and dots, e.g. '205', 'SC1' or '10.1.1'",
    ),
}
"""Shapes of product codes, by family of ``clCode``.

Observed in the classification files ``ListofReferences.json`` links (fetched 2026-10-23):
HS and BEC codes are digit strings, SITC codes digits with trailing ``X`` (``0011X``),
EBOPS codes letters, digits and dots (``205X``, ``SC11z``, ``10.1.1.2``). Every family
also takes ``TOTAL`` and the aggregation levels ``AG1`` to ``AG6``. A trailing ``*`` or
``?`` is a wildcard (``help/how-do-i-use-wildcards-to-query-data.md``;
``tests/fixtures/get/count_cmd_code_wildcard.json`` counts 113 records for ``27??``).
"""


def _family(cl_code: str) -> str:
    if cl_code.startswith("EB"):
        return "services"
    if cl_code == "SS" or re.fullmatch(r"S\d", cl_code):
        return "sitc"
    return "goods"


def _closest(value: str, allowed: Sequence[str]) -> str | None:
    folded = {option.upper(): option for option in allowed}
    match = difflib.get_close_matches(value.upper(), list(folded), n=1, cutoff=0.3)
    return folded[match[0]] if match else None


def _members(argument: str, value: str, problems: list[str]) -> list[str]:
    members = value.split(",")
    if any(not member or member != member.strip() for member in members):
        problems.append(
            f"{argument} {value!r} must be values separated by commas, without spaces or "
            "empty entries"
        )
        return []
    return members


def _check_list(
    argument: str,
    value: str | None,
    upstream: str,
    problems: list[str],
    *,
    multi: bool = False,
    case_insensitive: bool = False,
) -> None:
    if value is None:
        return
    allowed = _allowed(upstream)
    members = _members(argument, value, problems) if multi else [value]
    known = {option.upper() for option in allowed} if case_insensitive else set(allowed)
    for member in members:
        if (member.upper() if case_insensitive else member) in known:
            continue
        closest = _closest(member, allowed)
        hint = f"; closest: {closest!r}" if closest else ""
        problems.append(
            f"{argument} {member!r} is not a UN Comtrade {upstream} value{hint}. "
            f"Valid values: {', '.join(allowed)}"
        )


_AREA_TABLES: dict[str, tuple[str, str, str]] = {
    "reporter": ("Reporters", "Reporters.json", "list_reporters"),
    "partner": ("partnerAreas", "partnerAreas.json", "list_partners"),
}
"""Kind of area code: (packaged table, upstream file, the task that lists the codes)."""


@functools.cache
def _areas(kind: str) -> dict[str, tuple[str, str]]:
    """Codes of the reporter or partner table: code to (description, ISO alpha-3)."""
    if kind == "reporter":
        return {
            str(row.reporter_code): (row.reporter_desc.strip(), row.reporter_code_iso_alpha3)
            for row in packaged_table("Reporters", Reporter)
        }
    return {
        str(row.partner_code): (row.partner_desc.strip(), row.partner_code_iso_alpha3)
        for row in packaged_table("partnerAreas", PartnerArea)
    }


@functools.cache
def _iso3() -> dict[str, str]:
    return {
        str(row.country_area_code): row.iso3
        for row in packaged_table("country_area_code_iso", CountryAreaCodeIso)
    }


def _area_hint(member: str, kind: str) -> str:
    """Why ``member`` is not a code of ``kind``, and the code to use instead if there is one.

    ``country_area_code_iso.json`` gives the ISO alpha-3 of every reporter and partner
    code, and a code of the table with the same alpha-3 is the same area: 756, Switzerland
    as a partner, is 757 among the reporters. Failing that, a code of the other table is
    named as such (0 World is a partner only), and anything else gets the most similar
    code of the table.
    """
    areas = _areas(kind)
    alpha3 = _iso3().get(member)
    same = [code for code, (_, iso3) in areas.items() if alpha3 and iso3 == alpha3]
    if same:
        return f"; closest: {same[0]!r} ({areas[same[0]][0]})"
    other = "partner" if kind == "reporter" else "reporter"
    if member in _areas(other):
        return f"; {member!r} ({_areas(other)[member][0]}) is a {other} code only"
    closest = _closest(member, list(areas))
    return f"; closest: {closest!r} ({areas[closest][0]})" if closest else ""


def _check_areas(argument: str, value: str | None, kind: str, problems: list[str]) -> None:
    if value is None:
        return
    _, upstream_file, task = _AREA_TABLES[kind]
    for member in _members(argument, value, problems):
        if not _AREA.fullmatch(member):
            problems.append(
                f"{argument} {member!r} is not a numeric UN Comtrade area code; use codes "
                "such as '757' (Switzerland) or '0' (World), separated by commas"
            )
        elif member not in _areas(kind):
            problems.append(
                f"{argument} {member!r} is not a UN Comtrade {kind} code ({upstream_file})"
                f"{_area_hint(member, kind)}; {task} lists every code"
            )


def _check_period(
    value: str | None, problems: list[str], *, max_periods: int | None = MAX_PERIODS
) -> None:
    if value is None:
        return
    members = _members("period", value, problems)
    for member in members:
        if not _PERIOD.fullmatch(member):
            problems.append(
                f"period {member!r} is neither a year (YYYY, e.g. '2023') nor a month "
                "(YYYYMM, e.g. '202305')"
            )
    if max_periods is not None and len(members) > max_periods:
        problems.append(
            f"period has {len(members)} values; UN Comtrade takes at most {MAX_PERIODS} per "
            "call, so split the query by period"
        )


def _check_cmd_code(value: str | None, cl_code: str, problems: list[str]) -> None:
    if value is None:
        return
    shape, example = _CMD_SHAPES[_family(cl_code)]
    for member in _members("cmd_code", value, problems):
        if not (_KEYWORD.fullmatch(member) or shape.fullmatch(member)):
            problems.append(
                f"cmd_code {member!r} is not a {cl_code} product code: use 'TOTAL', 'AG2', "
                f"'AG4', 'AG6' or codes made of {example}"
            )


def validate_get(
    type_code: str,
    freq_code: str,
    cl_code: str,
    *,
    reporter_code: str | None = None,
    partner_code: str | None = None,
    partner2_code: str | None = None,
    period: str | None = None,
    cmd_code: str | None = None,
    flow_code: str | None = None,
    mot_code: str | None = None,
    customs_code: str | None = None,
    aggregate_by: str | None = None,
    breakdown_mode: str | None = None,
    include_desc: bool | None = None,
) -> dict[str, Any]:
    """Check the arguments of a ``data/v1/get`` call before anything is sent.

    Coded parameters are checked against the packaged lists, reporter codes against
    ``Reporters.json`` and partner and second-partner codes against ``partnerAreas.json``
    (each member of a comma-separated list); periods and product codes by shape only.
    Values are never rewritten.

    Returns:
        The arguments that are set, under the task's parameter names, in signature order.

    Raises:
        InvalidRequestError: Naming every problem, with the closest valid value where
            there is one.
    """
    problems: list[str] = []
    _check_list("type_code", type_code, "typeCode", problems)
    _check_list("freq_code", freq_code, "freqCode", problems)
    _check_list("cl_code", cl_code, "clCode", problems)
    _check_areas("reporter_code", reporter_code, "reporter", problems)
    _check_areas("partner_code", partner_code, "partner", problems)
    _check_areas("partner2_code", partner2_code, "partner", problems)
    _check_period(period, problems)
    if cl_code in _allowed("clCode"):
        _check_cmd_code(cmd_code, cl_code, problems)
    # flowCode is case-insensitive per the spec; customsCode's pattern accepts c and C.
    _check_list("flow_code", flow_code, "flowCode", problems, multi=True, case_insensitive=True)
    _check_list("mot_code", mot_code, "motCode", problems, multi=True)
    _check_list(
        "customs_code", customs_code, "customsCode", problems, multi=True, case_insensitive=True
    )
    _check_list("aggregate_by", aggregate_by, "aggregateBy", problems, multi=True)
    _check_list("breakdown_mode", breakdown_mode, "breakdownMode", problems)
    if problems:
        raise InvalidRequestError("; ".join(problems) + ".", source=SOURCE)
    arguments: dict[str, Any] = {
        "type_code": type_code,
        "freq_code": freq_code,
        "cl_code": cl_code,
        "reporter_code": reporter_code,
        "partner_code": partner_code,
        "partner2_code": partner2_code,
        "period": period,
        "cmd_code": cmd_code,
        "flow_code": flow_code,
        "mot_code": mot_code,
        "customs_code": customs_code,
        "aggregate_by": aggregate_by,
        "breakdown_mode": breakdown_mode,
        "include_desc": include_desc,
    }
    return {name: value for name, value in arguments.items() if value is not None}


_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def _check_day(argument: str, value: str | None, problems: list[str]) -> None:
    if value is None:
        return
    try:
        valid = bool(_DAY.fullmatch(value)) and bool(date.fromisoformat(value))
    except ValueError:
        valid = False
    if not valid:
        problems.append(f"{argument} {value!r} is not a day as YYYY-MM-DD, e.g. '2024-01-31'")


def validate_datasets(
    type_code: str,
    freq_code: str,
    cl_code: str,
    *,
    reporter_code: str | None = None,
    period: str | None = None,
    published_date_from: str | None = None,
    published_date_to: str | None = None,
) -> dict[str, Any]:
    """Check the arguments of a ``data/v1/getDa`` or ``data/v1/getMetadata`` call.

    The same checks as ``validate_get`` for the parameters the two share with it, except
    that ``period`` takes more than 12 values (``getDa`` answered 13,
    ``tests/fixtures/get_da/ch_13_periods.json``); the publication dates are checked as
    ``YYYY-MM-DD`` days. Values are never rewritten.

    Returns:
        The arguments that are set, under the task's parameter names, in signature order.

    Raises:
        InvalidRequestError: Naming every problem, with the closest valid value where
            there is one.
    """
    problems: list[str] = []
    _check_list("type_code", type_code, "typeCode", problems)
    _check_list("freq_code", freq_code, "freqCode", problems)
    _check_list("cl_code", cl_code, "clCode", problems)
    _check_areas("reporter_code", reporter_code, "reporter", problems)
    _check_period(period, problems, max_periods=None)
    _check_day("published_date_from", published_date_from, problems)
    _check_day("published_date_to", published_date_to, problems)
    if problems:
        raise InvalidRequestError("; ".join(problems) + ".", source=SOURCE)
    arguments: dict[str, Any] = {
        "type_code": type_code,
        "freq_code": freq_code,
        "cl_code": cl_code,
        "reporter_code": reporter_code,
        "period": period,
        "published_date_from": published_date_from,
        "published_date_to": published_date_to,
    }
    return {name: value for name, value in arguments.items() if value is not None}


def classification_files() -> tuple[str, ...]:
    """The ``clCode`` values with a classification file ``<clCode>.json`` upstream.

    The ``cmd:<clCode>`` categories of ``ListofReferences.json``: the packaged ``clCode``
    list without the values added from the spec (``BE`` and ``TM``), for which upstream
    serves no file (``BE.json`` and ``TM.json`` answered HTTP 404 ``BlobNotFound`` on
    2026-10-23, ``tests/fixtures/reference/be_absent.json``).
    """
    packaged = packaged_values("clCode")
    if packaged is None:  # pragma: no cover - clCode is always packaged
        raise KeyError("clCode")
    added = {item.value for item in packaged.exceptions if item.decision == "added"}
    return tuple(value for value in packaged.values if value not in added)


def validate_classification_file(cl_code: str) -> dict[str, Any]:
    """Check that ``cl_code`` names a classification file before it is fetched.

    Returns:
        ``{"cl_code": cl_code}``, the arguments under the task's parameter names.

    Raises:
        InvalidRequestError: Naming the closest valid value and every valid one.
    """
    files = classification_files()
    if cl_code not in files:
        closest = _closest(cl_code, files)
        hint = f"; closest: {closest!r}" if closest else ""
        raise InvalidRequestError(
            f"cl_code {cl_code!r} has no classification file at UN Comtrade{hint}. "
            f"Valid values: {', '.join(files)}.",
            source=SOURCE,
        )
    return {"cl_code": cl_code}
