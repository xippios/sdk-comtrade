"""Packaged reference data for UN Comtrade and the checks run before a call (conventions §3).

Small, stable upstream lists and tables ship inside the package under ``reference/`` so
lookups and checks need no network call; ``scripts/refresh_reference.py`` writes them and
the matching ``StrEnum`` classes in ``enums.py``, never by hand. ``reference/README.md``
carries the provenance of every file. Each is a packaged-list file,
``reference/<name>.json``, read with ``xippios.core.PackagedList.load(PACKAGE, name)``
(ADR-0022): a list's records carry the value under the parameter's name and the fields
upstream words it in, under upstream's names, parsed into the list's model
(``PACKAGED_LISTS``), a table's records upstream's columns, parsed into its row model
(``PACKAGED_TABLES``). ``validate_get`` checks the arguments of a ``data/v1/get`` call
against them, and the free-form ones by shape, before anything is sent (ADR-0007);
``validate_datasets`` does the same for ``data/v1/getDa`` and ``data/v1/getMetadata``;
``validate_slice`` resolves and checks the arguments of the task-shaped slices (an area as
a code or ISO alpha-3, periods of one format) into a ``data/v1/get`` request with
``SLICE_PINS``.
"""

import difflib
import functools
import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, NamedTuple

from xippios.core import InvalidRequestError, PackagedList, UnknownCode, UpstreamModel, closest

from xippios.comtrade._client import SOURCE
from xippios.comtrade.errors import MAX_PERIODS
from xippios.comtrade.models import (
    AggregateByValue,
    BreakdownModeValue,
    ClCodeValue,
    CodeValue,
    CountryAreaCodeIso,
    CustomsCodeValue,
    FlowCodeValue,
    FreqCodeValue,
    MosCodeValue,
    MotCodeValue,
    PartnerArea,
    QtyUnitCodeValue,
    Reference,
    Reporter,
    TradeDataItem,
    TypeCodeValue,
)

__all__ = [
    "CL_CODES_FROM_SPEC",
    "PACKAGE",
    "PACKAGED_LISTS",
    "PACKAGED_TABLES",
    "SLICE_PINS",
    "classification_files",
    "validate_classification_file",
    "validate_code_list",
    "validate_datasets",
    "validate_get",
    "validate_reference_category",
    "validate_slice",
]

PACKAGE = "xippios.comtrade"

PACKAGED_LISTS: Mapping[str, type[CodeValue]] = {
    "typeCode": TypeCodeValue,
    "freqCode": FreqCodeValue,
    "clCode": ClCodeValue,
    "flowCode": FlowCodeValue,
    "customsCode": CustomsCodeValue,
    "motCode": MotCodeValue,
    "aggregateBy": AggregateByValue,
    "breakdownMode": BreakdownModeValue,
    "mosCode": MosCodeValue,
    "qtyUnitCode": QtyUnitCodeValue,
}
"""Lists that ship as ``reference/<name>.json``, named after the upstream parameter, and the
model of their records; keep in step with the refresh script."""

PACKAGED_TABLES: Mapping[str, type[UpstreamModel]] = {
    "Reporters": Reporter,
    "partnerAreas": PartnerArea,
    "country_area_code_iso": CountryAreaCodeIso,
    "TradeDataItems": TradeDataItem,
    "ListofReferences": Reference,
}
"""Tables that ship as ``reference/<name>.json``, named after the upstream file, and their
row model; keep in step with the refresh script."""

CL_CODES_FROM_SPEC: tuple[str, ...] = ("BE", "TM")
"""The ``clCode`` values the packaged list takes from the spec, not from ``ListofReferences.json``.

The spec's ``clCode`` enum lists them and upstream accepted both on ``data/v1/get``
(``count_cl_code_be.json``, ``count_cl_code_tm.json``), so ``clCode.json`` adds them, as
its ``note`` records; upstream serves no classification file for them (``BE.json`` and
``TM.json`` answered HTTP 404 ``BlobNotFound`` on 2026-10-23,
``tests/fixtures/reference/be_absent.json``).
"""


def _rows[M: UpstreamModel](name: str, model: type[M]) -> list[M]:
    """The packaged table ``name`` parsed into ``model``, its row model in ``PACKAGED_TABLES``."""
    return PackagedList.load(PACKAGE, name).parse(model, source=SOURCE)


@functools.cache
def _allowed(name: str) -> tuple[str, ...]:
    """The values of the packaged list ``name``, in upstream order."""
    return tuple(str(record[name]) for record in PackagedList.load(PACKAGE, name).records)


@functools.cache
def _texts(name: str) -> dict[str, str]:
    """The values of the packaged list ``name`` that carry upstream's ``text``, to their text."""
    records = PackagedList.load(PACKAGE, name).records
    return {str(record[name]): record["text"] for record in records if "text" in record}


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


_DIMENSIONS = frozenset({"customsCode", "motCode"})
"""Packaged lists whose unknown member raises ``UnknownCode`` (conventions §5).

Dimension codes of the data rows, like the areas; upstream's answer to a code it does not
have is not recorded for them. The other lists stay gathered problems: upstream answers
an unknown ``clCode`` and ``flowCode`` with HTTP 400 (``count_cl_code_be5.json``,
``count_flow_code_unknown.json``), and the spec's enums are its own.
"""

_UNKNOWN_DIMENSION = (
    "UN Comtrade's answer to a customs or transport code it does not have is not recorded, "
    "so the package refuses it before the call, as it does an unknown area."
)
"""``UnknownCode``'s reason for a member of a ``_DIMENSIONS`` list."""


def _closest_texts(member: str, upstream: str) -> list[tuple[str, str]]:
    """The codes of ``upstream`` close to ``member``, with upstream's text, best first.

    Core's ``closest``, by code and then by text (``"air"`` finds ``1000`` Air); where it
    finds none, the one most similar code, as for an unknown area (``"9"`` finds
    ``9900``).
    """
    texts = _texts(upstream)
    near = closest(member, texts)
    if near:
        return near
    code = _closest(member, list(texts))
    return [(code, texts[code])] if code else []


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
        if upstream in _DIMENSIONS:
            raise UnknownCode(
                argument,
                member,
                list_name=upstream,
                fetched=PackagedList.load(PACKAGE, upstream).fetched,
                closest=_closest_texts(member, upstream),
                reason=f"{_UNKNOWN_DIMENSION} list_codes({upstream!r}) lists every code.",
                source=SOURCE,
            )
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
            for row in _rows("Reporters", Reporter)
        }
    return {
        str(row.partner_code): (row.partner_desc.strip(), row.partner_code_iso_alpha3)
        for row in _rows("partnerAreas", PartnerArea)
    }


@functools.cache
def _iso3() -> dict[str, str]:
    return {
        str(row.country_area_code): row.iso3
        for row in _rows("country_area_code_iso", CountryAreaCodeIso)
    }


_UNKNOWN_CODE = (
    "UN Comtrade answers a code it does not have with count 0, so the package refuses it "
    "before the call."
)
"""``UnknownCode``'s reason for an area code (conventions §5): 756, no reporter, counted 0.

``tests/fixtures/get/count_not_a_reporter_756.json``.
"""

_UNKNOWN_ALPHA3 = (
    "The package resolves an ISO alpha-3 code to UN Comtrade's numeric code through this list."
)
"""``UnknownCode``'s reason for an ISO alpha-3 code no area of the list carries."""


def _unknown_area(
    argument: str,
    value: str,
    kind: str,
    *,
    closest: Sequence[tuple[str, str]] = (),
    hint: str | None = None,
    reason: str = _UNKNOWN_CODE,
) -> UnknownCode:
    """The refusal of an area ``value`` the packaged reporter or partner table lacks."""
    list_name, _, task = _AREA_TABLES[kind]
    return UnknownCode(
        argument,
        value,
        list_name=list_name,
        fetched=PackagedList.load(PACKAGE, list_name).fetched,
        closest=closest,
        hint=hint,
        reason=f"{reason} {task} lists every code.",
        source=SOURCE,
    )


def _unknown_code(argument: str, member: str, kind: str) -> UnknownCode:
    """``UnknownCode`` for a numeric ``member`` that is no code of ``kind``.

    Comtrade's own strategy for the closest code (conventions §5):
    ``country_area_code_iso.json`` gives the ISO alpha-3 of every reporter and partner code,
    and a code of the table with the same alpha-3 is the same area: 756, Switzerland as a
    partner, is 757 among the reporters. Failing that, a code of the other table is named
    as such (0 World is a partner only), and anything else gets the most similar code of
    the table.
    """
    areas = _areas(kind)
    alpha3 = _iso3().get(member)
    same = [code for code, (_, iso3) in areas.items() if alpha3 and iso3 == alpha3]
    if same:
        return _unknown_area(argument, member, kind, closest=[(same[0], areas[same[0]][0])])
    other = "partner" if kind == "reporter" else "reporter"
    if member in _areas(other):
        hint = f"{member!r} ({_areas(other)[member][0]}) is a {other} code only."
        return _unknown_area(argument, member, kind, hint=hint)
    closest = _closest(member, list(areas))
    near = [(closest, areas[closest][0])] if closest else []
    return _unknown_area(argument, member, kind, closest=near)


def _check_areas(argument: str, value: str | None, kind: str, problems: list[str]) -> None:
    """Gather a malformed area code; raise ``UnknownCode`` for the first one the table lacks."""
    if value is None:
        return
    for member in _members(argument, value, problems):
        if not _AREA.fullmatch(member):
            problems.append(
                f"{argument} {member!r} is not a numeric UN Comtrade area code; use codes "
                "such as '757' (Switzerland) or '0' (World), separated by commas"
            )
        elif member not in _areas(kind):
            raise _unknown_code(argument, member, kind)


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
        UnknownCode: A reporter, partner or second-partner code the packaged table lacks,
            or a ``customs_code`` or ``mot_code`` the packaged list lacks, naming the
            packaged list, its fetch date and the closest code (conventions §5); an
            ``InvalidRequestError``. The first one found ends the checks: other problems
            are reported once it is fixed.
        InvalidRequestError: Naming every problem found, with the closest valid value
            where there is one.
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
        UnknownCode: A reporter code the packaged table lacks, naming the packaged list,
            its fetch date and the closest area (conventions §5); an
            ``InvalidRequestError``. The first one found ends the checks: other problems
            are reported once it is fixed.
        InvalidRequestError: Naming every problem found, with the closest valid value
            where there is one.
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
    list without the values added from the spec, ``CL_CODES_FROM_SPEC``, for which
    upstream serves no file.
    """
    return tuple(value for value in _allowed("clCode") if value not in CL_CODES_FROM_SPEC)


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


def validate_code_list(param: str) -> dict[str, Any]:
    """Check that ``param`` names a packaged list before it is read.

    Returns:
        ``{"param": param}``, the arguments under the task's parameter names.

    Raises:
        InvalidRequestError: Naming the closest list and every one the package carries.
    """
    if param not in PACKAGED_LISTS:
        near = _closest(param, list(PACKAGED_LISTS))
        hint = f"; closest: {near!r}" if near else ""
        raise InvalidRequestError(
            f"param {param!r} is not a list the package carries{hint}. "
            f"Valid values: {', '.join(PACKAGED_LISTS)}.",
            source=SOURCE,
        )
    return {"param": param}


def validate_reference_category(category: str | None) -> dict[str, Any]:
    """Check that ``category`` is a category of the packaged ``ListofReferences.json``.

    Returns:
        ``{"category": category}``, or ``{}`` for ``None``, which keeps every row.

    Raises:
        InvalidRequestError: Naming the closest category and every one the index holds.
    """
    if category is None:
        return {}
    categories = [
        str(record["category"]) for record in PackagedList.load(PACKAGE, "ListofReferences").records
    ]
    if category not in categories:
        near = _closest(category, categories)
        hint = f"; closest: {near!r}" if near else ""
        raise InvalidRequestError(
            f"category {category!r} is not a category of UN Comtrade's "
            f"ListofReferences.json{hint}. Valid values: {', '.join(categories)}.",
            source=SOURCE,
        )
    return {"category": category}


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
            for row in _rows("Reporters", Reporter)
        )
    return tuple(
        _Area(
            code=str(row.partner_code),
            desc=row.partner_desc.strip(),
            iso3=row.partner_code_iso_alpha3.strip(),
            in_use=row.entry_expired_date is None,
        )
        for row in _rows("partnerAreas", PartnerArea)
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
    """The one code of ``kind`` behind an ISO alpha-3 code; ``UnknownCode`` for an unknown one.

    ``_by_iso3`` picks the code; an ambiguous alpha-3 code is a gathered problem, naming
    every candidate. An alpha-3 code no area of ``kind`` carries raises ``UnknownCode``,
    naming the code of the closest alpha-3 or name (842 USA among partners, not 840), or
    the other table where the area is one of its own (W00 World is a partner only).
    """
    wanted = value.upper()
    found = _by_iso3(wanted, kind)
    if len(found) == 1:
        return found[0].code
    _, upstream_file, _ = _AREA_TABLES[kind]
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
        hint = f"{value!r} ({elsewhere[0].code}, {elsewhere[0].desc}) is a {other} area only."
        raise _unknown_area(argument, value, kind, hint=hint, reason=_UNKNOWN_ALPHA3)
    rows = _area_rows(kind)
    options = {area.iso3: area.iso3 for area in rows} | {
        area.desc.upper(): area.iso3 for area in rows
    }
    closest = _closest(value, list(options))
    near = [(area.code, area.desc) for area in _by_iso3(options[closest], kind)] if closest else []
    raise _unknown_area(argument, value, kind, closest=near, reason=_UNKNOWN_ALPHA3)


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
        UnknownCode: A ``reporter`` or ``partner`` the packaged table lacks, as a code or
            an ISO alpha-3 code, naming the packaged list, its fetch date and the closest
            area (conventions §5); an ``InvalidRequestError``. It ends the checks: other
            problems are reported once it is fixed.
        InvalidRequestError: Naming every problem found, with the closest valid value
            where there is one.
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
