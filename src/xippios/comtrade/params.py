"""Packaged reference data for UN Comtrade and the checks run before a call (conventions §3).

Small, stable upstream lists and tables ship inside the package under ``reference/`` so
lookups and checks need no network call; ``scripts/refresh_reference.py`` writes them,
never by hand. ``reference/README.md`` carries the provenance of every file. Each is a
packaged-list file,
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

Several values of one filter are one argument, one code or a list of codes, and a text with
a comma is refused; ``joined`` writes a list as the comma-separated text UN Comtrade takes
(conventions §2, sdk-core ADR-0061, decision 1). Each check refuses the first problem that it
finds and says that nothing was sent after its first sentence (conventions §5, sdk-core
ADR-0061, decision 7): a code of a packaged list or table by core's ``check`` of its
declaration in ``codes.py``, in core's words, and a period, a product code and a day by their
shape, in the package's.
"""

import functools
import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import Any

from xippios.core import (
    InvalidRequestError,
    PackagedCodes,
    PackagedList,
    UpstreamModel,
    closest,
    nearest,
)

from xippios.comtrade._client import SOURCE
from xippios.comtrade.codes import (
    AGGREGATE_BY,
    BREAKDOWN_MODES,
    CATEGORIES,
    CL_CODES,
    CUSTOMS_CODES,
    FLOW_CODES,
    FREQ_CODES,
    MOT_CODES,
    PACKAGE,
    PARTNERS,
    REPORTERS,
    TYPE_CODES,
)
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
    "Codes",
    "TextCodes",
    "classification_files",
    "joined",
    "validate_bilateral_data",
    "validate_classification_file",
    "validate_code_list",
    "validate_datasets",
    "validate_get",
    "validate_reference_category",
    "validate_trade_balance",
    "validate_world_share",
]

Codes = str | int | Sequence[str | int]
"""One area code or period, or a list of them: ``"757"``, ``757``, ``[757, 842]``, ``"2023"``."""

TextCodes = str | Sequence[str]
"""One text code, or a list of them: ``"X"``, ``["M", "X"]``, ``["C00", "C01"]``."""

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


_DIGITS = re.compile(r"\d+")
"""A text of digits, which ``int`` reads, those outside ASCII among them."""
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
also takes ``TOTAL``, which the spec's example answer holds, and the aggregation levels
``AG1`` to ``AG6``, as 0.3.0 did: ``AG2`` and ``AG4`` stand in recorded HS queries that
upstream answered, ``AG6`` in the example answer of the async ``getDa`` in
``apidocs/comtradeAsync.json``, and ``AG1``, ``AG3`` and ``AG5`` in no page of the snapshot
and no recording, though no page rules them out. A trailing ``*`` or
``?`` is a wildcard (``help/how-do-i-use-wildcards-to-query-data.md``;
``tests/fixtures/get/count_cmd_code_wildcard.json`` counts 113 records for ``27??``).
"""


def _family(cl_code: str) -> str:
    if cl_code.startswith("EB"):
        return "services"
    if cl_code == "SS" or re.fullmatch(r"S\d", cl_code):
        return "sitc"
    return "goods"


_UNSENT = "Nothing was sent."
"""The sentence after the first of each refusal before a request (conventions §5)."""


def _refused(first: str, rest: str = "") -> InvalidRequestError:
    """A refusal of the package's own: its first sentence, that nothing was sent, the rest."""
    return InvalidRequestError(f"{first}. {_UNSENT}{' ' + rest if rest else ''}", source=SOURCE)


def _members(argument: str, value: Codes) -> list[str | int]:
    """The codes of ``value``, one code or a list of them, in the caller's order and form.

    Raises:
        InvalidRequestError: ``value`` is a text with a comma, which names the list to pass,
            a list without a code, or no sequence, such as a set, which ``joined`` would send
            as given.
    """
    held: object = value  # a caller outside the types, a set among them, reaches this check
    if not isinstance(held, str | int | Sequence):
        raise _refused(
            f"{argument} takes one code or a list of codes, not a {type(held).__name__}, {held!r}"
        )
    given: list[str | int] = [value] if isinstance(value, str | int) else list(value)
    if any(isinstance(code, str) and "," in code for code in given):
        listed = [part.strip() for code in given for part in str(code).split(",") if part.strip()]
        if listed:
            raise _refused(
                f"{argument} takes several codes as a list, {json.dumps(listed)}, not a text "
                f"with commas, {value!r}"
            )
        given = []
    if not given:
        raise _refused(
            f"{argument} lists no code: give one code or a list of codes, or leave {argument} out"
        )
    return given


def joined(request: Mapping[str, Any]) -> dict[str, Any]:
    """The arguments as a wrapper sends them: a list of codes as UN Comtrade's text.

    UN Comtrade takes several values of one parameter separated by commas ("Multi value
    input should be in the form of csv", ``docs/upstream/apidocs/comtrade.json``), so a
    list ``[757, 842]`` is sent as ``757,842``; every other value is passed on as given.
    """
    return {
        name: (
            ",".join(str(code) for code in value)
            if isinstance(value, Sequence) and not isinstance(value, str)
            else value
        )
        for name, value in request.items()
    }


_SPEC_LIST = (
    "UN Comtrade's spec lists every value of {param}, so the package refuses another before "
    "the call. list_codes({param!r}) lists them {tool}."
)
"""``UnknownCode``'s reason for a value of a list read from the spec."""

_REFUSED_UPSTREAM = (
    "UN Comtrade refuses a {param} it does not have with HTTP 400, so the package refuses it "
    "before the call. list_codes({param!r}) lists every code {tool}."
)
"""``UnknownCode``'s reason for a ``clCode`` or ``flowCode`` value: upstream's HTTP 400.

``tests/fixtures/get/count_cl_code_be5.json`` and ``count_flow_code_unknown.json``.
"""

_UNKNOWN_DIMENSION = (
    "UN Comtrade's answer to a customs or transport code it does not have is not recorded, "
    "so the package refuses it before the call, as it does an unknown area. "
    "list_codes({param!r}) lists every code {tool}."
)
"""``UnknownCode``'s reason for a customs or transport code, whose upstream answer is unseen."""


def _reason_of(reason: str, param: str) -> str:
    return reason.format(param=param, tool=over_mcp("list_codes"))


_LISTS: Mapping[str, tuple[PackagedCodes, str]] = {
    "typeCode": (TYPE_CODES, _reason_of(_SPEC_LIST, "typeCode")),
    "freqCode": (FREQ_CODES, _reason_of(_SPEC_LIST, "freqCode")),
    "clCode": (CL_CODES, _reason_of(_REFUSED_UPSTREAM, "clCode")),
    "flowCode": (FLOW_CODES, _reason_of(_REFUSED_UPSTREAM, "flowCode")),
    "customsCode": (CUSTOMS_CODES, _reason_of(_UNKNOWN_DIMENSION, "customsCode")),
    "motCode": (MOT_CODES, _reason_of(_UNKNOWN_DIMENSION, "motCode")),
    "aggregateBy": (AGGREGATE_BY, _reason_of(_SPEC_LIST, "aggregateBy")),
    "breakdownMode": (BREAKDOWN_MODES, _reason_of(_SPEC_LIST, "breakdownMode")),
}
"""Each packaged list an argument is checked against, by upstream's parameter, and the reason
its refusal gives."""


def _check_list(argument: str, value: TextCodes | None, upstream: str) -> None:
    """Refuse the first code of ``value`` that the packaged list ``upstream`` lacks."""
    if value is None:
        return
    listed, reason = _LISTS[upstream]
    listed.check(argument, _members(argument, value), reason=reason)


_AREA_TABLES: dict[str, tuple[PackagedCodes, str]] = {
    "reporter": (REPORTERS, "list_reporters"),
    "partner": (PARTNERS, "list_partners"),
}
"""Kind of area code: (the table's codes, the task that lists them)."""


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


def _reason(kind: str) -> str:
    """The reason of the refusal of an area code, with the task that lists the codes."""
    _, task = _AREA_TABLES[kind]
    return f"{_UNKNOWN_CODE} {task} lists every code {over_mcp(task)}."


def _same_area(member: str, kind: str) -> str | None:
    """The code of ``kind`` with the ISO alpha-3 of the area code ``member``, if any.

    ``country_area_code_iso.json`` gives the ISO alpha-3 of every reporter and partner code,
    and a code of the table with the same alpha-3 is the same area: 756, Switzerland as a
    partner, is 757 among the reporters.
    """
    alpha3 = _iso3().get(member)
    same = [code for code, (_, iso3) in _areas(kind).items() if alpha3 and iso3 == alpha3]
    return same[0] if same else None


def _closest_area(kind: str) -> Callable[[Any, Mapping[Any, str]], list[tuple[int, str]]]:
    """Comtrade's own strategy for the closest code of ``kind``: ``check``'s ``closest``.

    The code of the same area by its ISO alpha-3 (conventions §5), else core's ``nearest``
    codes by number; none for a text, which core then names by name.
    """

    def strategy(member: Any, names: Mapping[Any, str]) -> list[tuple[int, str]]:
        if isinstance(member, bool) or not isinstance(member, int):
            return []
        same = _same_area(str(member), kind)
        if same is not None:
            return [(int(same), _areas(kind)[same][0])]
        return list(nearest(member, names))

    return strategy


@functools.cache
def _other_table(kind: str) -> dict[str, str]:
    """``check``'s hints for the codes of the other table alone: 0 World is a partner only.

    A code of the other table whose area this table holds under another code is left to
    ``_closest_area``, which names that code.
    """
    other = "partner" if kind == "reporter" else "reporter"
    return {
        code: f"{code} ({desc}) is a {other} code only."
        for code, (desc, _) in _areas(other).items()
        if code not in _areas(kind) and _same_area(code, kind) is None
    }


def _check_areas(argument: str, value: Codes | None, kind: str) -> None:
    """Refuse the first area code of ``value`` that the reporter or partner table lacks.

    The table's codes are integers, so a text of digits that is its integer's own text,
    ``"757"``, is checked as that integer, by one call of core's ``check`` (sdk-core
    ADR-0045), and the value is sent as given. A text whose digits are not its integer's
    own, ``"0757"`` or digits outside ASCII, which ``int`` reads as 757, is checked as its
    text, which the table lacks, with a hint that names the code as UN Comtrade writes it,
    and core's check refuses any other text in its own words.
    """
    if value is None:
        return
    codes: list[str | int] = []
    written: dict[str, str] = {}
    for code in _members(argument, value):
        if isinstance(code, str) and _DIGITS.fullmatch(code):
            number = int(code)
            if str(number) == code:
                codes.append(number)
                continue
            written[code] = (
                f"UN Comtrade writes this code {number}, in the digits 0 to 9 without a "
                "leading zero."
            )
        codes.append(code)
    listed, _ = _AREA_TABLES[kind]
    listed.check(
        argument,
        codes,
        hints={**_other_table(kind), **written},
        closest=_closest_area(kind),
        reason=_reason(kind),
    )


def _check_period(
    value: Codes | None, *, max_periods: int | None = MAX_PERIODS, keyword: str | None = None
) -> None:
    if value is None or (keyword is not None and value == keyword):
        return
    alone = f", nor {keyword!r} alone" if keyword else ""
    members = _members("period", value)
    for member in members:
        if isinstance(member, bool) or not _PERIOD.fullmatch(str(member)):
            raise _refused(
                f"period {member!r} is neither a year (YYYY, e.g. '2023') nor a month "
                f"(YYYYMM, e.g. '202305'){alone}"
            )
    if max_periods is not None and len(members) > max_periods:
        raise _refused(
            f"period lists {len(members)} periods; UN Comtrade takes at most {MAX_PERIODS} per "
            "call, so split the query by period"
        )


def _check_cmd_code(value: TextCodes | None, cl_code: str) -> None:
    if value is None:
        return
    shape, example = _CMD_SHAPES[_family(cl_code)]
    for member in _members("cmd_code", value):
        if not isinstance(member, str) or not (
            _KEYWORD.fullmatch(member) or shape.fullmatch(member)
        ):
            raise _refused(
                f"cmd_code {member!r} is not a {cl_code} product code: use 'TOTAL', 'AG2', "
                f"'AG4', 'AG6' or codes made of {example}"
            )


def _set(**arguments: Any) -> dict[str, Any]:
    """The arguments that are set, as the caller gave them, in the order given."""
    return {name: value for name, value in arguments.items() if value is not None}


def validate_get(
    type_code: str,
    freq_code: str,
    cl_code: str,
    *,
    reporter_code: Codes | None = None,
    period: Codes | None = None,
    partner_code: Codes | None = None,
    partner2_code: Codes | None = None,
    cmd_code: TextCodes | None = None,
    flow_code: TextCodes | None = None,
    customs_code: TextCodes | None = None,
    mot_code: TextCodes | None = None,
    aggregate_by: TextCodes | None = None,
    breakdown_mode: str | None = None,
    include_desc: bool | None = None,
) -> dict[str, Any]:
    """Check the arguments of a ``data/v1/get`` call before anything is sent.

    Coded parameters are checked against the packaged lists, reporter codes against
    ``Reporters.json`` and partner and second-partner codes against ``partnerAreas.json``,
    each code of a list; periods and product codes by shape only. Values are never
    rewritten. The checks run in the order of the arguments and the first problem ends them.

    Returns:
        The arguments that are set, under the task's parameter names, in signature order,
        as given: ``joined`` writes them as upstream takes them.

    Raises:
        UnknownCode: A code that its packaged list or table lacks, naming the list, its
            fetch date and the closest codes (conventions §5); an ``InvalidRequestError``.
        InvalidRequestError: Any other first problem, a text with a comma among them, and
            that nothing was sent.
    """
    _check_list("type_code", type_code, "typeCode")
    _check_list("freq_code", freq_code, "freqCode")
    _check_list("cl_code", cl_code, "clCode")
    _check_areas("reporter_code", reporter_code, "reporter")
    _check_period(period)
    _check_areas("partner_code", partner_code, "partner")
    _check_areas("partner2_code", partner2_code, "partner")
    _check_cmd_code(cmd_code, cl_code)
    _check_list("flow_code", flow_code, "flowCode")
    _check_list("customs_code", customs_code, "customsCode")
    _check_list("mot_code", mot_code, "motCode")
    _check_list("aggregate_by", aggregate_by, "aggregateBy")
    _check_list("breakdown_mode", breakdown_mode, "breakdownMode")
    return _set(
        type_code=type_code,
        freq_code=freq_code,
        cl_code=cl_code,
        reporter_code=reporter_code,
        period=period,
        partner_code=partner_code,
        partner2_code=partner2_code,
        cmd_code=cmd_code,
        flow_code=flow_code,
        customs_code=customs_code,
        mot_code=mot_code,
        aggregate_by=aggregate_by,
        breakdown_mode=breakdown_mode,
        include_desc=include_desc,
    )


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
    task: str, reporter_code: object, partner_code: object, cmd_code: object
) -> None:
    if (reporter_code is None and partner_code is None) or cmd_code is None:
        raise _refused(_UNBOUNDED.format(task=task))


def _check_tools_flow(value: str | None) -> None:
    if value is None:
        return
    if not isinstance(value, str) or "," in value:
        raise _refused(
            f"flow_code {value!r} must be one flow, 'M' or 'X': getBilateralData refuses "
            "several in one call (HTTP 400), so call it once per flow"
        )
    if value not in TOOLS_FLOW_CODES:
        raise _refused(
            f"flow_code {value!r} is not a flowCode getBilateralData takes: it takes "
            f"{' or '.join(repr(code) for code in TOOLS_FLOW_CODES)}"
        )


def validate_trade_balance(
    type_code: str,
    freq_code: str,
    cl_code: str,
    *,
    reporter_code: Codes | None = None,
    period: Codes | None = None,
    partner_code: Codes | None = None,
    partner2_code: Codes | None = None,
    cmd_code: TextCodes | None = None,
    customs_code: TextCodes | None = None,
    mot_code: TextCodes | None = None,
    aggregate_by: TextCodes | None = None,
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
    to check its size first (``_UNBOUNDED``), and that is checked first. Values are never
    rewritten, and the first problem ends the checks.

    Returns:
        The arguments that are set, under the task's parameter names, in signature order.

    Raises:
        UnknownCode: A code that its packaged list or table lacks (conventions §5).
        InvalidRequestError: Any other first problem, and that nothing was sent.
    """
    _check_bounded("get_trade_balance", reporter_code, partner_code, cmd_code)
    _check_list("type_code", type_code, "typeCode")
    _check_list("freq_code", freq_code, "freqCode")
    _check_list("cl_code", cl_code, "clCode")
    _check_areas("reporter_code", reporter_code, "reporter")
    _check_period(period)
    _check_areas("partner_code", partner_code, "partner")
    _check_areas("partner2_code", partner2_code, "partner")
    _check_cmd_code(cmd_code, cl_code)
    _check_list("customs_code", customs_code, "customsCode")
    _check_list("mot_code", mot_code, "motCode")
    _check_list("aggregate_by", aggregate_by, "aggregateBy")
    _check_list("breakdown_mode", breakdown_mode, "breakdownMode")
    return _set(
        type_code=type_code,
        freq_code=freq_code,
        cl_code=cl_code,
        reporter_code=reporter_code,
        period=period,
        partner_code=partner_code,
        partner2_code=partner2_code,
        cmd_code=cmd_code,
        customs_code=customs_code,
        mot_code=mot_code,
        aggregate_by=aggregate_by,
        breakdown_mode=breakdown_mode,
        include_desc=include_desc,
    )


def validate_bilateral_data(
    type_code: str,
    freq_code: str,
    cl_code: str,
    *,
    reporter_code: Codes | None = None,
    period: Codes | None = None,
    partner_code: Codes | None = None,
    cmd_code: TextCodes | None = None,
    flow_code: str | None = None,
    include_desc: bool | None = None,
) -> dict[str, Any]:
    """Check the arguments of a ``tools/v1/getBilateralData`` call before anything is sent.

    ``validate_get``'s checks for the parameters the two share, except that ``period``
    takes more than 12 values (13 answered 13 rows,
    ``tests/fixtures/get_bilateral_data/ch_us_exports_13_periods.json``) and
    ``flow_code`` is one of ``TOOLS_FLOW_CODES``. The query must name ``reporter_code`` or
    ``partner_code``, and ``cmd_code``, since upstream gives no count to check its size
    first (``_UNBOUNDED``), and that is checked first. Values are never rewritten, and the
    first problem ends the checks.

    Returns:
        The arguments that are set, under the task's parameter names, in signature order.

    Raises:
        UnknownCode: A reporter or partner code the packaged table lacks (conventions §5).
        InvalidRequestError: Any other first problem, and that nothing was sent.
    """
    _check_bounded("get_bilateral_data", reporter_code, partner_code, cmd_code)
    _check_list("type_code", type_code, "typeCode")
    _check_list("freq_code", freq_code, "freqCode")
    _check_list("cl_code", cl_code, "clCode")
    _check_areas("reporter_code", reporter_code, "reporter")
    _check_period(period, max_periods=None)
    _check_areas("partner_code", partner_code, "partner")
    _check_cmd_code(cmd_code, cl_code)
    _check_tools_flow(flow_code)
    return _set(
        type_code=type_code,
        freq_code=freq_code,
        cl_code=cl_code,
        reporter_code=reporter_code,
        period=period,
        partner_code=partner_code,
        cmd_code=cmd_code,
        flow_code=flow_code,
        include_desc=include_desc,
    )


_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def _check_day(argument: str, value: str | None) -> None:
    if value is None:
        return
    try:
        valid = bool(_DAY.fullmatch(value)) and bool(date.fromisoformat(value))
    except ValueError:
        valid = False
    if not valid:
        raise _refused(f"{argument} {value!r} is not a day as YYYY-MM-DD, e.g. '2024-01-31'")


def validate_datasets(
    type_code: str,
    freq_code: str,
    cl_code: str,
    *,
    reporter_code: Codes | None = None,
    period: Codes | None = None,
    published_date_from: str | None = None,
    published_date_to: str | None = None,
) -> dict[str, Any]:
    """Check the arguments of a ``data/v1/getDa`` or ``data/v1/getMetadata`` call.

    The same checks as ``validate_get`` for the parameters the two share with it, except
    that ``period`` takes more than 12 values (``getDa`` answered 13,
    ``tests/fixtures/get_da/ch_13_periods.json``); the publication dates are checked as
    ``YYYY-MM-DD`` days. Values are never rewritten, and the first problem ends the checks.

    Returns:
        The arguments that are set, under the task's parameter names, in signature order.

    Raises:
        UnknownCode: A code that its packaged list or table lacks, naming the list, its
            fetch date and the closest codes (conventions §5); an ``InvalidRequestError``.
        InvalidRequestError: Any other first problem, and that nothing was sent.
    """
    _check_list("type_code", type_code, "typeCode")
    _check_list("freq_code", freq_code, "freqCode")
    _check_list("cl_code", cl_code, "clCode")
    _check_areas("reporter_code", reporter_code, "reporter")
    _check_period(period, max_periods=None)
    _check_day("published_date_from", published_date_from)
    _check_day("published_date_to", published_date_to)
    return _set(
        type_code=type_code,
        freq_code=freq_code,
        cl_code=cl_code,
        reporter_code=reporter_code,
        period=period,
        published_date_from=published_date_from,
        published_date_to=published_date_to,
    )


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
    reporter_code: Codes | None = None,
    period: Codes | None = None,
) -> dict[str, Any]:
    """Check the arguments of a ``public/v1/getWorldShare`` call before anything is sent.

    ``type_code`` and ``freq_code`` against the packaged lists; ``reporter_code`` against
    ``Reporters.json``, each code of a list; ``period`` by shape, each a year or a month
    as ``validate_get`` checks them, any number of them (the spec states no limit), or
    ``RECENT`` alone. Values are never rewritten, and the first problem ends the checks.

    Returns:
        The arguments that are set, under the task's parameter names, in signature order.

    Raises:
        UnknownCode: A code that its packaged list or table lacks, naming the list, its
            fetch date and the closest codes (conventions §5); an ``InvalidRequestError``.
        InvalidRequestError: Any other first problem, and that nothing was sent.
    """
    _check_list("type_code", type_code, "typeCode")
    _check_list("freq_code", freq_code, "freqCode")
    _check_areas("reporter_code", reporter_code, "reporter")
    _check_period(period, max_periods=None, keyword=RECENT)
    return _set(
        type_code=type_code, freq_code=freq_code, reporter_code=reporter_code, period=period
    )


def classification_files() -> tuple[str, ...]:
    """The ``clCode`` values with a classification file ``<clCode>.json`` upstream.

    The ``cmd:<clCode>`` categories of ``ListofReferences.json``: the packaged ``clCode``
    list without the values added from the spec, ``CL_CODES_FROM_SPEC``, for which
    upstream serves no file.
    """
    return tuple(
        str(record["clCode"])
        for record in CL_CODES.packaged.records
        if record["clCode"] not in CL_CODES_FROM_SPEC
    )


_FILES = (
    "list_classifications lists the classifications, the categories cmd:<clCode>, "
    f"{over_mcp('list_classifications')}."
)
"""``UnknownCode``'s reason for a classification the packaged ``clCode`` list lacks."""


def validate_classification_file(cl_code: str) -> dict[str, Any]:
    """Check that ``cl_code`` names a classification file before it is fetched.

    Core's check of the packaged ``clCode`` list first, then the values of the list that
    upstream serves no file for, ``CL_CODES_FROM_SPEC``.

    Returns:
        ``{"cl_code": cl_code}``, the arguments under the task's parameter names.

    Raises:
        UnknownCode: ``cl_code`` is no value of the packaged ``clCode`` list.
        InvalidRequestError: ``cl_code`` has no file, naming the classifications that do.
    """
    CL_CODES.check("cl_code", cl_code, reason=_FILES)
    if cl_code in CL_CODES_FROM_SPEC:
        raise _refused(
            f"cl_code {cl_code!r} has no classification file at UN Comtrade",
            f"The classifications with a file: {', '.join(classification_files())}.",
        )
    return {"cl_code": cl_code}


def validate_code_list(param: str) -> dict[str, Any]:
    """Check that ``param`` names a packaged list before it is read.

    Returns:
        ``{"param": param}``, the arguments under the task's parameter names.

    Raises:
        InvalidRequestError: Naming the closest lists by core's ``closest`` and every one
            the package carries.
    """
    if param not in PACKAGED_LISTS:
        rest = f"It carries: {', '.join(PACKAGED_LISTS)}."
        near = closest(param, {name: name for name in PACKAGED_LISTS})
        if near:
            rest = f"Did you mean {', '.join(name for name, _ in near)}? {rest}"
        raise _refused(f"param {param!r} is not a list the package carries", rest)
    return {"param": param}


_CATEGORY = (
    "The package answers from its copy of UN Comtrade's index of the reference files. "
    f"list_classifications lists every category {over_mcp('list_classifications')}."
)
"""``UnknownCode``'s reason for a category the packaged ``ListofReferences.json`` lacks."""


def validate_reference_category(category: str | None) -> dict[str, Any]:
    """Check that ``category`` is a category of the packaged ``ListofReferences.json``.

    Returns:
        ``{"category": category}``, or ``{}`` for ``None``, which keeps every row.

    Raises:
        UnknownCode: Naming the index, its fetch date and the closest categories.
    """
    if category is None:
        return {}
    CATEGORIES.check("category", category, reason=_CATEGORY)
    return {"category": category}
