"""Packaged value lists for UN Comtrade and the checks run before a data call (conventions §3).

Small, stable upstream lists ship inside the package under ``reference/`` so lookups and
checks need no network call; ``scripts/refresh_reference.py`` writes them and the matching
``StrEnum`` classes in ``enums.py``, never by hand. ``reference/README.md`` carries the
provenance of every file. ``validate_get`` checks the arguments of a ``data/v1/get`` call
against them, and the free-form ones by shape, before anything is sent (ADR-0007).
"""

import difflib
import functools
import re
from collections.abc import Sequence
from datetime import date
from typing import Any

from xippios.core import InvalidRequestError, UpstreamModel, load_json

from xippios.comtrade._client import SOURCE
from xippios.comtrade.errors import MAX_PERIODS

__all__ = ["PACKAGED_LISTS", "PackagedValues", "packaged_values", "validate_get"]

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
)
"""Names of the lists that ship inside the package; keep in step with the refresh script."""


class PackagedValues(UpstreamModel):
    """One packaged value list: ``reference/<name>.json``.

    Attributes:
        param: The upstream parameter the values belong to.
        fetched: Day the list was fetched (for lists read from the spec, the day the
            snapshot was fetched).
        origin: The reference file or snapshot entry the values come from.
        values: The values, as upstream lists them.
    """

    param: str
    fetched: date
    origin: str | None = None
    values: list[str]


def packaged_values(name: str) -> PackagedValues | None:
    """The packaged list ``name``, or ``None`` when it is not packaged."""
    if name not in PACKAGED_LISTS:
        return None
    return PackagedValues.model_validate(load_json(PACKAGE, f"{name}.json"))


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


def _check_areas(argument: str, value: str | None, problems: list[str]) -> None:
    if value is None:
        return
    for member in _members(argument, value, problems):
        if not _AREA.fullmatch(member):
            problems.append(
                f"{argument} {member!r} is not a numeric UN Comtrade area code; use codes "
                "such as '757' (Switzerland) or '0' (World), separated by commas"
            )


def _check_period(value: str | None, problems: list[str]) -> None:
    if value is None:
        return
    members = _members("period", value, problems)
    for member in members:
        if not _PERIOD.fullmatch(member):
            problems.append(
                f"period {member!r} is neither a year (YYYY, e.g. '2023') nor a month "
                "(YYYYMM, e.g. '202305')"
            )
    if len(members) > MAX_PERIODS:
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

    Coded parameters are checked against the packaged lists; area codes, periods and
    product codes by shape only (membership is not checked). Values are never rewritten.

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
    _check_areas("reporter_code", reporter_code, problems)
    _check_areas("partner_code", partner_code, problems)
    _check_areas("partner2_code", partner2_code, problems)
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
