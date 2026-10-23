"""Packaged reference data for UN Comtrade and the checks run before a call (conventions §3).

Small, stable upstream lists and tables ship inside the package under ``reference/`` so
lookups and checks need no network call; ``scripts/refresh_reference.py`` writes them and
the matching ``StrEnum`` classes in ``enums.py``, never by hand. ``reference/README.md``
carries the provenance of every file. Value lists are ``<name>.json``
(``packaged_values``); tables are ``<name>.csv`` with upstream's columns
(``packaged_table``), their origin and fetch date in ``tables.json``. ``validate_get``
checks the arguments of a ``data/v1/get`` call against them, and the free-form ones by
shape, before anything is sent (ADR-0007); ``validate_datasets`` does the same for
``data/v1/getDa`` and ``data/v1/getMetadata``; ``validate_slice`` resolves and checks the
arguments of the task-shaped slices (an area as a code or ISO alpha-3, periods of one
format) into a ``data/v1/get`` request with ``SLICE_PINS``.
"""

import difflib
import functools
import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, NamedTuple, cast

from pydantic import Field
from xippios.core import InvalidRequestError, UpstreamModel, load_json, load_table

from xippios.comtrade._client import SOURCE
from xippios.comtrade.errors import MAX_PERIODS
from xippios.comtrade.models import CountryAreaCodeIso, PartnerArea, Reporter, TradeDataItem

__all__ = [
    "PACKAGED_LISTS",
    "PACKAGED_TABLES",
    "SLICE_PINS",
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
    "validate_slice",
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


SLICE_PINS: Mapping[str, Any] = {
    "type_code": "C",
    "partner2_code": "0",
    "mot_code": "0",
    "customs_code": "C00",
    "breakdown_mode": "classic",
    "include_desc": True,
}
"""What every task-shaped slice sends besides its own arguments: goods, the total row only.

``breakdownMode`` ``classic`` returns the total row alone, as pinning ``partner2Code`` 0,
``customsCode`` ``C00`` and ``motCode`` 0 does (under ``tests/fixtures/get/``:
``ch_exports_2023_breakdown_mode_classic.json``, ``ch_exports_2023_totals.json``), so
one row is one reporter, partner, product code, flow and period. ``includeDesc`` fills
the ``*_iso`` and ``*_desc`` fields (``ch_exports_2023_include_desc.json``).
"""

MAX_SERIES_PERIODS = 10 * MAX_PERIODS
"""Most periods one ``get_commodity_series`` call takes: 120, ten calls of 12.

Each chunk of 12 periods is a keyed call, and a Basic Individual key allows 500 calls a
day (``docs/upstream/help/subscriptions.md``), so the series is capped by calls rather
than records: ten years of months or a century of years per call.
"""

_SLICE_ORDER = (
    "type_code", "freq_code", "cl_code", "reporter_code", "partner_code", "partner2_code",
    "period", "cmd_code", "flow_code", "mot_code", "customs_code", "breakdown_mode",
    "include_desc",
)  # fmt: skip
"""``validate_get``'s order, so a slice's ``meta.request`` reads like ``get_data``'s."""


class _Area(NamedTuple):
    code: str
    desc: str
    iso3: str
    in_use: bool


@functools.cache
def _area_rows(kind: str) -> tuple[_Area, ...]:
    """The reporter or partner table as (code, description, ISO alpha-3, still in use)."""
    if kind == "reporter":
        return tuple(
            _Area(
                code=str(row.reporter_code),
                desc=row.reporter_desc.strip(),
                iso3=row.reporter_code_iso_alpha3.strip(),
                in_use=row.entry_expired_date is None,
            )
            for row in packaged_table("Reporters", Reporter)
        )
    return tuple(
        _Area(
            code=str(row.partner_code),
            desc=row.partner_desc.strip(),
            iso3=row.partner_code_iso_alpha3.strip(),
            in_use=row.entry_expired_date is None,
        )
        for row in packaged_table("partnerAreas", PartnerArea)
    )


def _by_iso3(iso3: str, kind: str) -> list[_Area]:
    """The codes of ``kind`` an ISO alpha-3 code resolves to: one, or several if ambiguous.

    Several codes can share an alpha-3 code: a code no longer used (``entry_expired_date``
    set, such as 280 Fed. Rep. of Germany until 1990 next to 276 Germany) gives way to the
    one in use; among partners, the code that is also a reporter code wins (757
    Switzerland, not 756; 842 USA, not 840): Switzerland's 2023 partner rows carry 842,
    251 France and 579 Norway, never 840, 250 or 578
    (``tests/fixtures/get/partners_ch_total_2023.json``). What is still ambiguous after
    that (A79: 473 LAIA, nes and 636 Rest of America, nes) stays several.
    """
    found = [area for area in _area_rows(kind) if area.iso3 == iso3]
    if len(found) > 1:
        found = [area for area in found if area.in_use] or found
    if len(found) > 1 and kind == "partner":
        reporters = {area.code for area in _area_rows("reporter")}
        found = [area for area in found if area.code in reporters] or found
    return found


def _resolve_iso3(argument: str, value: str, kind: str, problems: list[str]) -> str | None:
    """The one code of ``kind`` behind an ISO alpha-3 code, or a problem naming the closest.

    ``_by_iso3`` picks the code; an ambiguous alpha-3 code is refused, naming every
    candidate. The closest-value hint for an unknown one names the code that alpha-3 code
    resolves to (``'USA' (842, USA)`` among partners, not 840).
    """
    wanted = value.upper()
    found = _by_iso3(wanted, kind)
    if len(found) == 1:
        return found[0].code
    _, upstream_file, task = _AREA_TABLES[kind]
    if found:
        problems.append(
            f"{argument} {value!r} is the ISO alpha-3 code of several UN Comtrade {kind} codes "
            f"({upstream_file}): {', '.join(f'{a.code!r} ({a.desc})' for a in found)}; "
            "give the numeric code"
        )
        return None
    other = "partner" if kind == "reporter" else "reporter"
    elsewhere = _by_iso3(wanted, other)
    if elsewhere:
        problems.append(
            f"{argument} {value!r} ({elsewhere[0].code}, {elsewhere[0].desc}) is a {other} "
            f"area only, not a UN Comtrade {kind} ({upstream_file})"
        )
        return None
    rows = _area_rows(kind)
    options = {area.iso3: area.iso3 for area in rows} | {
        area.desc.upper(): area.iso3 for area in rows
    }
    closest = _closest(value, list(options))
    hint = ""
    if closest:
        iso3 = options[closest]
        named = " or ".join(f"{area.code}, {area.desc}" for area in _by_iso3(iso3, kind))
        hint = f"; closest: {iso3!r} ({named})"
    problems.append(
        f"{argument} {value!r} is neither a UN Comtrade {kind} code nor the ISO alpha-3 code "
        f"of one ({upstream_file}){hint}; {task} lists every code"
    )
    return None


def _resolve_area(argument: str, value: str | None, kind: str, problems: list[str]) -> str | None:
    """One reporter or partner, given as UN Comtrade's code or an ISO alpha-3 code, as the code."""
    if value is None:
        return None
    if "," in value:
        problems.append(f"{argument} {value!r} must be one area, e.g. '757' or 'CHE'")
        return None
    if _AREA.fullmatch(value):
        before = len(problems)
        _check_areas(argument, value, kind, problems)
        return value if len(problems) == before else None
    return _resolve_iso3(argument, value, kind, problems)


def _slice_periods(
    argument: str, value: str, problems: list[str], *, at_most: int
) -> tuple[str | None, list[str]]:
    """Periods of one format: the ``freqCode`` they imply (``A`` or ``M``) and the members."""
    members = _members(argument, value, problems)
    if not members:
        return None, []
    for member in members:
        if not _PERIOD.fullmatch(member):
            digits = re.sub(r"\D", "", member)
            hint = f"; closest: {digits!r}" if _PERIOD.fullmatch(digits) else ""
            problems.append(
                f"{argument} {member!r} is neither a year (YYYY, e.g. '2023') nor a month "
                f"(YYYYMM, e.g. '202305'){hint}"
            )
    valid = [member for member in members if _PERIOD.fullmatch(member)]
    if len(valid) < len(members):
        return None, []
    lengths = {len(member) for member in members}
    if len(lengths) > 1:
        years = [m for m in members if len(m) == 4]
        months = [m for m in members if len(m) == 6]
        problems.append(
            f"{argument} {value!r} mixes years ({', '.join(years)}) and months "
            f"({', '.join(months)}); the frequency follows from the format, so give years "
            f"only ('{','.join(years)}', annual) or months only ('{','.join(months)}', monthly)"
        )
        return None, []
    twice = sorted({member for member in members if members.count(member) > 1})
    if twice:
        problems.append(f"{argument} names {', '.join(map(repr, twice))} more than once")
    if at_most == 1 and len(members) > 1:
        problems.append(f"{argument} {value!r} must be one year or month, e.g. '2023' or '202305'")
    elif len(members) > at_most > MAX_PERIODS:
        problems.append(
            f"{argument} has {len(members)} values; get_commodity_series takes at most "
            f"{at_most}, {at_most // MAX_PERIODS} calls of {MAX_PERIODS}, against a daily "
            "quota of 500 calls on a free key; split the series"
        )
    elif len(members) > at_most:
        problems.append(
            f"{argument} has {len(members)} values; UN Comtrade takes at most {at_most} per "
            "call (get_commodity_series splits longer series)"
        )
    return ("A" if lengths == {4} else "M"), members


def _slice_commodities(
    argument: str, value: str, cl_code: str, problems: list[str], *, one: bool
) -> list[str]:
    """Product codes that each name one code, so the slice's rows are bounded by their number.

    ``TOTAL`` and codes of ``cl_code``'s shape pass, each once; the aggregation levels
    (``AG2``) and wildcards (``27??``) expand to an unknown number of codes upstream, so
    they are refused with a pointer to ``get_data``, which counts first.
    """
    if one and "," in value:
        problems.append(f"{argument} {value!r} must be one product code, e.g. 'TOTAL' or '27'")
        return []
    members = _members(argument, value, problems)
    folded = [member.upper() for member in members]
    twice = sorted({member for member in folded if folded.count(member) > 1})
    if twice:
        problems.append(f"{argument} names {', '.join(map(repr, twice))} more than once")
    shape, example = _CMD_SHAPES[_family(cl_code)]
    for member in members:
        if member.upper() == "TOTAL":
            continue
        if _KEYWORD.fullmatch(member) or member.endswith(("*", "?")):
            problems.append(
                f"{argument} {member!r} expands to many product codes; the slices take "
                "codes such as 'TOTAL', '27' or '2709' (get_data takes levels and wildcards "
                "and counts first)"
            )
        elif not shape.fullmatch(member):
            problems.append(
                f"{argument} {member!r} is not a {cl_code} product code: use 'TOTAL' or codes "
                f"made of {example}"
            )
    return members


def validate_slice(
    cl_code: str,
    flow: str,
    *,
    reporter: str | None = None,
    partner: str | None = None,
    commodity: str | None = None,
    commodities: str | None = None,
    period: str | None = None,
    periods: str | None = None,
    max_periods: int = MAX_PERIODS,
    n: int | None = None,
) -> dict[str, Any]:
    """Resolve and check the arguments of a task-shaped slice into a ``data/v1/get`` request.

    ``reporter`` and ``partner`` take one area, as UN Comtrade's code (``"757"``) or an ISO
    alpha-3 code (``"CHE"``, ``"W00"`` for World), checked against the packaged
    ``Reporters.json`` and ``partnerAreas.json``; ``None`` leaves the parameter out (every
    reporter or partner). ``commodity`` takes one product code, ``commodities`` several,
    comma-separated, each naming one code (``TOTAL``, ``27``, ``2709``). ``period`` takes
    one year or month, ``periods`` several of one format, at most ``max_periods`` (12, one
    call; ``MAX_SERIES_PERIODS`` for a series sent 12 at a time); the format sets
    ``freqCode``, ``A`` for ``YYYY`` and ``M`` for ``YYYYMM``. ``flow`` is one flow code.
    ``n``, how many rows a ranking keeps, is at least 1; it is not an upstream parameter,
    so it is not returned (the task records it in ``meta.request`` itself). Nothing is
    sent.

    Returns:
        The ``get_data`` arguments, ``SLICE_PINS`` included, in ``validate_get``'s order:
        the resolved codes, ``freq_code`` from the periods, ``period`` and ``cmd_code`` as
        given.

    Raises:
        InvalidRequestError: Naming every problem, with the closest valid value where
            there is one.
    """
    problems: list[str] = []
    _check_list("cl_code", cl_code, "clCode", problems)
    if "," in flow:
        problems.append(f"flow {flow!r} must be one flow code, e.g. 'X' or 'M'")
    else:
        _check_list("flow", flow, "flowCode", problems, case_insensitive=True)
    reporter_code = _resolve_area("reporter", reporter, "reporter", problems)
    partner_code = _resolve_area("partner", partner, "partner", problems)
    cmd_argument, cmd_value = (
        ("commodity", commodity) if commodity is not None else ("commodities", commodities)
    )
    if cmd_value is None:  # pragma: no cover - every slice names its product codes
        raise TypeError("validate_slice needs commodity or commodities")
    family = cl_code if cl_code in _allowed("clCode") else "HS"
    _slice_commodities(cmd_argument, cmd_value, family, problems, one=commodity is not None)
    period_argument, period_value = (
        ("period", period) if period is not None else ("periods", periods)
    )
    if period_value is None:  # pragma: no cover - every slice names its periods
        raise TypeError("validate_slice needs period or periods")
    at_most = 1 if period is not None else max_periods
    freq_code, _ = _slice_periods(period_argument, period_value, problems, at_most=at_most)
    if n is not None and n < 1:
        problems.append(f"n {n!r} must be at least 1; closest: 1")
    if problems:
        raise InvalidRequestError("; ".join(problems) + ".", source=SOURCE)
    arguments: dict[str, Any] = {
        **SLICE_PINS,
        "freq_code": freq_code,
        "cl_code": cl_code,
        "reporter_code": reporter_code,
        "partner_code": partner_code,
        "period": period_value,
        "cmd_code": cmd_value,
        "flow_code": flow,
    }
    return {name: arguments[name] for name in _SLICE_ORDER if arguments[name] is not None}
