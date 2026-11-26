"""Packaged reference data for UN Comtrade and the checks run before a call (conventions §3).

Small, stable upstream lists and tables ship inside the package under ``reference/`` so
lookups and checks need no network call; ``scripts/refresh_reference.py`` writes them and
the matching ``StrEnum`` classes in ``enums.py``, never by hand. ``reference/README.md``
carries the provenance of every file. Each is a packaged-list file,
``reference/<name>.json``, read with ``xippios.core.PackagedList.load(PACKAGE, name)``
(sdk-core ADR-0041): a list's records carry the value under the parameter's name and the
fields upstream words it in, under upstream's names, parsed into the list's model
(``PACKAGED_LISTS``), a table's records upstream's columns, parsed into its row model
(``PACKAGED_TABLES``). ``validate_get`` checks the arguments of a ``data/v1/get`` call
against them, and the free-form ones by shape, before anything is sent (sdk-core ADR-0007);
``validate_datasets`` does the same for ``data/v1/getDa`` and ``data/v1/getMetadata``,
``validate_trade_balance`` and ``validate_bilateral_data`` for the Tools operations
``tools/v1/getTradeBalance`` and ``tools/v1/getBilateralData``, ``validate_world_share``
for ``public/v1/getWorldShare``.
"""

import difflib
import functools
import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from xippios.core import InvalidRequestError, PackagedList, UnknownCode, UpstreamModel, closest

from xippios.comtrade._client import SOURCE
from xippios.comtrade.errors import MAX_PERIODS, over_mcp
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
    "RECENT",
    "TOOLS_FLOW_CODES",
    "classification_files",
    "validate_bilateral_data",
    "validate_classification_file",
    "validate_code_list",
    "validate_datasets",
    "validate_get",
    "validate_reference_category",
    "validate_trade_balance",
    "validate_world_share",
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
        if upstream in _DIMENSIONS:
            raise UnknownCode(
                argument,
                member,
                list_name=upstream,
                fetched=PackagedList.load(PACKAGE, upstream).fetched,
                closest=_closest_texts(member, upstream),
                reason=(
                    f"{_UNKNOWN_DIMENSION} list_codes({upstream!r}) lists every code "
                    f"{over_mcp('list_codes')}."
                ),
                source=SOURCE,
            )
        near = _closest(member, allowed)
        hint = f"; closest: {near!r}" if near else ""
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


def _unknown_area(
    argument: str,
    value: str,
    kind: str,
    *,
    closest: Sequence[tuple[str, str]] = (),
    hint: str | None = None,
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
        reason=f"{_UNKNOWN_CODE} {task} lists every code {over_mcp(task)}.",
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
    value: str | None,
    problems: list[str],
    *,
    max_periods: int | None = MAX_PERIODS,
    keyword: str | None = None,
) -> None:
    if value is None or value == keyword:
        return
    alone = f", nor {keyword!r} alone" if keyword else ""
    members = _members("period", value, problems)
    for member in members:
        if not _PERIOD.fullmatch(member):
            problems.append(
                f"period {member!r} is neither a year (YYYY, e.g. '2023') nor a month "
                f"(YYYYMM, e.g. '202305'){alone}"
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


TOOLS_FLOW_CODES: tuple[str, ...] = ("M", "X")
"""The ``flowCode`` values ``tools/v1/getBilateralData`` takes, one per call: the spec's enum.

``docs/upstream/apidocs/comtradeTools.json`` gives ``flowCode`` the enum ``M``/``X`` and
the description "Multi value input should be in the form of csv"; upstream refused
``M,X`` with HTTP 400 "The field flowCode is invalid"
(``tests/fixtures/get_bilateral_data/ch_us_2023_flow_code_m_x.json``), so one flow per
call. The packaged ``flowCode`` list holds the twelve flows of ``data/v1/get``.
"""

_UNBOUNDED = (
    "{task} needs reporter_code or partner_code, and cmd_code: UN Comtrade's Tools "
    "operations give no count to check a query's size before the call (countOnly "
    "answered 0 for a query of 48 rows), so the package bounds a query by its arguments; "
    "e.g. reporter_code='757', partner_code='0', cmd_code='TOTAL'"
)
"""The refusal of a Tools query that names neither area nor a product code.

``tests/fixtures/get_trade_balance/count_only_ch_world_2023.json`` (``count`` 0) and
``ch_world_2023_include_desc.json`` (48 rows); ``getBilateralData`` ignores ``countOnly``
(``tests/fixtures/get_bilateral_data/count_only_ch_us_exports_2023.json``).
"""


def _check_bounded(
    task: str,
    reporter_code: str | None,
    partner_code: str | None,
    cmd_code: str | None,
    problems: list[str],
) -> None:
    if (reporter_code is None and partner_code is None) or cmd_code is None:
        problems.append(_UNBOUNDED.format(task=task))


def _check_tools_flow(value: str | None, problems: list[str]) -> None:
    if value is None or value in TOOLS_FLOW_CODES:
        return
    if "," in value:
        problems.append(
            f"flow_code {value!r} must be one flow, 'M' or 'X': getBilateralData refuses "
            "several in one call (HTTP 400), so call it once per flow"
        )
        return
    closest = _closest(value, TOOLS_FLOW_CODES)
    hint = f"; closest: {closest!r}" if closest else ""
    problems.append(
        f"flow_code {value!r} is not a flowCode getBilateralData takes{hint}. "
        f"Valid values: {', '.join(TOOLS_FLOW_CODES)}"
    )


def validate_trade_balance(
    type_code: str,
    freq_code: str,
    cl_code: str,
    *,
    reporter_code: str | None = None,
    period: str | None = None,
    partner_code: str | None = None,
    partner2_code: str | None = None,
    cmd_code: str | None = None,
    customs_code: str | None = None,
    mot_code: str | None = None,
    aggregate_by: str | None = None,
    breakdown_mode: str | None = None,
    include_desc: bool | None = None,
) -> dict[str, Any]:
    """Check the arguments of a ``tools/v1/getTradeBalance`` call before anything is sent.

    ``validate_get``'s checks for the parameters the two share, the same packaged lists:
    the Tools spec lists the same ``typeCode``, ``freqCode``, ``customsCode``,
    ``motCode``, ``aggregateBy`` and ``breakdownMode`` values; ``clCode`` is checked
    against the packaged list, reconciled by ``data/v1/get``'s recorded answers, not the
    Tools spec's enum. At most 12 periods: upstream refused 13 with HTTP 400
    (``tests/fixtures/get_trade_balance/ch_world_13_periods.json``). The query must name
    ``reporter_code`` or ``partner_code``, and ``cmd_code``, since upstream gives no count
    to check its size first (``_UNBOUNDED``). Values are never rewritten.

    Returns:
        The arguments that are set, under the task's parameter names, in signature order.

    Raises:
        UnknownCode: A reporter, partner or second-partner code the packaged table lacks,
            or a ``customs_code`` or ``mot_code`` the packaged list lacks (conventions
            §5); the first one found ends the checks.
        InvalidRequestError: Naming every problem found, with the closest valid value
            where there is one.
    """
    problems: list[str] = []
    _check_bounded("get_trade_balance", reporter_code, partner_code, cmd_code, problems)
    _check_list("type_code", type_code, "typeCode", problems)
    _check_list("freq_code", freq_code, "freqCode", problems)
    _check_list("cl_code", cl_code, "clCode", problems)
    _check_areas("reporter_code", reporter_code, "reporter", problems)
    _check_areas("partner_code", partner_code, "partner", problems)
    _check_areas("partner2_code", partner2_code, "partner", problems)
    _check_period(period, problems)
    if cl_code in _allowed("clCode"):
        _check_cmd_code(cmd_code, cl_code, problems)
    # customsCode's pattern in the Tools spec, as in comtrade.json, accepts c and C.
    _check_list(
        "customs_code", customs_code, "customsCode", problems, multi=True, case_insensitive=True
    )
    _check_list("mot_code", mot_code, "motCode", problems, multi=True)
    _check_list("aggregate_by", aggregate_by, "aggregateBy", problems, multi=True)
    _check_list("breakdown_mode", breakdown_mode, "breakdownMode", problems)
    if problems:
        raise InvalidRequestError("; ".join(problems) + ".", source=SOURCE)
    arguments: dict[str, Any] = {
        "type_code": type_code,
        "freq_code": freq_code,
        "cl_code": cl_code,
        "reporter_code": reporter_code,
        "period": period,
        "partner_code": partner_code,
        "partner2_code": partner2_code,
        "cmd_code": cmd_code,
        "customs_code": customs_code,
        "mot_code": mot_code,
        "aggregate_by": aggregate_by,
        "breakdown_mode": breakdown_mode,
        "include_desc": include_desc,
    }
    return {name: value for name, value in arguments.items() if value is not None}


def validate_bilateral_data(
    type_code: str,
    freq_code: str,
    cl_code: str,
    *,
    reporter_code: str | None = None,
    period: str | None = None,
    partner_code: str | None = None,
    cmd_code: str | None = None,
    flow_code: str | None = None,
    include_desc: bool | None = None,
) -> dict[str, Any]:
    """Check the arguments of a ``tools/v1/getBilateralData`` call before anything is sent.

    ``validate_get``'s checks for the parameters the two share, except that ``period``
    takes more than 12 values (13 answered 13 rows,
    ``tests/fixtures/get_bilateral_data/ch_us_exports_13_periods.json``) and
    ``flow_code`` is one of ``TOOLS_FLOW_CODES``. The query must name ``reporter_code`` or
    ``partner_code``, and ``cmd_code``, since upstream gives no count to check its size
    first (``_UNBOUNDED``). Values are never rewritten.

    Returns:
        The arguments that are set, under the task's parameter names, in signature order.

    Raises:
        UnknownCode: A reporter or partner code the packaged table lacks (conventions
            §5); the first one found ends the checks.
        InvalidRequestError: Naming every problem found, with the closest valid value
            where there is one.
    """
    problems: list[str] = []
    _check_bounded("get_bilateral_data", reporter_code, partner_code, cmd_code, problems)
    _check_list("type_code", type_code, "typeCode", problems)
    _check_list("freq_code", freq_code, "freqCode", problems)
    _check_list("cl_code", cl_code, "clCode", problems)
    _check_areas("reporter_code", reporter_code, "reporter", problems)
    _check_areas("partner_code", partner_code, "partner", problems)
    _check_period(period, problems, max_periods=None)
    if cl_code in _allowed("clCode"):
        _check_cmd_code(cmd_code, cl_code, problems)
    _check_tools_flow(flow_code, problems)
    if problems:
        raise InvalidRequestError("; ".join(problems) + ".", source=SOURCE)
    arguments: dict[str, Any] = {
        "type_code": type_code,
        "freq_code": freq_code,
        "cl_code": cl_code,
        "reporter_code": reporter_code,
        "period": period,
        "partner_code": partner_code,
        "cmd_code": cmd_code,
        "flow_code": flow_code,
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


RECENT = "recent"
"""The one word ``getWorldShare``'s ``period`` takes besides periods (``public.json``).

Its pattern, ``^((\\d{4}|\\d{6})(,(\\d{4}|\\d{6}))*$|recent\\b)``, ends the word with
``\\b`` and no ``$``, so it would pass ``recent,2023``; the description reads
"comma-separated, or 'recent'", and the package takes the word alone, as the description
writes it.
"""


def validate_world_share(
    type_code: str,
    freq_code: str,
    *,
    period: str | None = None,
    reporter_code: str | None = None,
) -> dict[str, Any]:
    """Check the arguments of a ``public/v1/getWorldShare`` call before anything is sent.

    ``type_code`` and ``freq_code`` against the packaged lists; ``period`` by shape, each
    comma-separated member a year or a month as ``validate_get`` checks them, any number
    of them (the spec states no limit), or ``RECENT`` alone; ``reporter_code`` against
    ``Reporters.json``, each member of a comma-separated list. Values are never rewritten.

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
    _check_period(period, problems, max_periods=None, keyword=RECENT)
    _check_areas("reporter_code", reporter_code, "reporter", problems)
    if problems:
        raise InvalidRequestError("; ".join(problems) + ".", source=SOURCE)
    arguments: dict[str, Any] = {
        "type_code": type_code,
        "freq_code": freq_code,
        "period": period,
        "reporter_code": reporter_code,
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
