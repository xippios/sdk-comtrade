"""Task-shaped functions for UN Comtrade.

The public API (ADR-0001, layer 2). A task composes endpoint wrappers from ``api/``,
resolves pagination and reference lookups, and returns ``Result[T]`` with full
``ResultMeta``. Write the async version, derive the sync one with ``xippios.core.sync``,
and list the sync name in ``__all__``: the MCP server and the HTTP router register
exactly what is named there.

Docstrings are read by agents: one sentence first, then ``Args:`` with examples of
valid values for every parameter. ``/add-endpoint`` walks through the whole recipe.

``meta.endpoint`` is the operation as the Help Center names it (``data/v1/get``) and
``meta.request`` the task's own arguments that were set, so ``get_data(**meta.request)``
repeats the call. ``meta.published_at`` stays empty: data rows carry no publication date.
Upstream publishes its release dates through ``getMetadata`` and ``getLiveUpdate``, which
are not wrapped yet; reading a date into a row's envelope from anywhere else would be a
guess.
"""

from typing import Any

from xippios.core import Result, ResultMeta, sync

from xippios.comtrade import api
from xippios.comtrade._client import SOURCE
from xippios.comtrade.api.get import ENDPOINT
from xippios.comtrade.errors import RECORD_LIMIT, QueryTooLarge
from xippios.comtrade.models import TradeDataRecord
from xippios.comtrade.params import validate_get

__all__ = ["get_counts", "get_data"]


def _meta(request: dict[str, Any]) -> ResultMeta:
    return ResultMeta(source=SOURCE, endpoint=ENDPOINT, request=request)


async def get_counts_async(
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
) -> Result[int]:
    """Count the UN Comtrade trade records a query would return, without fetching them.

    The same request as ``get_data`` with upstream's ``countOnly``. One call returns at
    most 100,000 records, so count first and split a larger query. A count of 0 means no
    data matches: an unreported period, a code that is not a reporter, a flow the
    reporter does not record. Every count costs one call of the key's daily quota (500
    on a free key). Arguments are checked before the call; an unknown code raises
    ``InvalidRequestError`` naming the closest valid one.

    Args:
        type_code: ``"C"`` goods or ``"S"`` services.
        freq_code: ``"A"`` annual or ``"M"`` monthly.
        cl_code: Product classification: ``"HS"`` (all HS editions; prefer it, a count on
            the edition ``"H6"`` failed upstream with HTTP 500 on 2026-10-23), an edition
            ``"H0"`` to ``"H6"``, SITC ``"SS"``, ``"S1"`` to ``"S4"``, BEC ``"B4"``,
            ``"B5"``, for services EBOPS ``"EB"``, ``"EB02"``, ``"EB10"``, ``"EB10S"``;
            also ``"BE"`` and ``"TM"``, which the spec lists and upstream accepts.
        reporter_code: Reporting areas as UN Comtrade's numeric codes, comma-separated,
            e.g. ``"757"`` Switzerland, ``"842"`` USA, ``"276"`` Germany, ``"156"`` China,
            ``"757,842"``. Some differ from ISO numeric codes: Switzerland is 757, not 756.
            Omit for every reporter.
        partner_code: Partner areas, comma-separated: ``"0"`` World (the total over all
            partners), ``"276"`` Germany. Omit for every partner, one row each.
        partner2_code: Second partner (consignment) areas, comma-separated; ``"0"`` is
            the total.
        period: Years ``"2023"`` (annual) or months ``"202305"`` (monthly), at most 12
            comma-separated, e.g. ``"2021,2022,2023"``.
        cmd_code: Product codes of ``cl_code``, comma-separated: ``"TOTAL"`` for all
            products, ``"AG2"``, ``"AG4"``, ``"AG6"`` for every code at that level, codes
            such as ``"0901"`` or ``"090111"``, wildcards such as ``"27??"`` (every
            four-digit code under 27) or ``"27*"``.
        flow_code: Trade flows, comma-separated: ``"X"`` exports, ``"M"`` imports,
            ``"RX"`` re-exports, ``"RM"`` re-imports, also ``"DX"``, ``"FM"``, ``"MIP"``,
            ``"MOP"``, ``"XIP"``, ``"XOP"``, ``"MIF"``, ``"XIF"``; e.g. ``"M,X"``.
        mot_code: Modes of transport, comma-separated: ``"0"`` the total, ``"1000"`` air,
            ``"2100"`` sea, ``"3100"`` railway, ``"3200"`` road, ``"9100"`` pipelines and
            cables. Omit for every mode, one row each.
        customs_code: Customs procedures, comma-separated: ``"C00"`` the total, ``"C01"``
            clearance for home use, ``"C03"`` outright exportation. Omit for every
            procedure, one row each.
        aggregate_by: Upstream parameters to aggregate the results over, comma-separated
            from ``cmdCode``, ``period``, ``partnerCode``, ``partner2Code``,
            ``reporterCode``, ``customsCode``, ``motCode``; e.g. ``"period"``.
        breakdown_mode: Upstream's breakdown mode, ``"classic"`` or ``"plus"``.
        include_desc: Upstream's ``includeDesc``, "Include descriptions of data
            variables" (the ``*_desc`` fields of ``get_data`` rows); sent on as given.
    """
    request = validate_get(
        type_code,
        freq_code,
        cl_code,
        reporter_code=reporter_code,
        partner_code=partner_code,
        partner2_code=partner2_code,
        period=period,
        cmd_code=cmd_code,
        flow_code=flow_code,
        mot_code=mot_code,
        customs_code=customs_code,
        aggregate_by=aggregate_by,
        breakdown_mode=breakdown_mode,
        include_desc=include_desc,
    )
    response = await api.get_count_only(**request)
    return Result(data=response.count, meta=_meta(request))


async def get_data_async(
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
) -> Result[list[TradeDataRecord]]:
    """Fetch UN Comtrade final trade data for one query, up to 100,000 records.

    Counts first (one extra call, as ``get_counts``): a count of 0 returns an empty list
    without fetching, since no matching data is an answer, not an error; a count above
    100,000 raises ``QueryTooLarge`` with the count before anything is fetched, because
    upstream would cut the answer at 100,000 rows without saying so. Each row carries
    every field of upstream's ``TradeDataRecord`` under its snake_case name;
    ``primary_value`` is upstream's primary trade value (taken from the CIF or FOB value,
    in ``cifvalue``/``fobvalue``). Leaving out ``partner2_code``,
    ``customs_code`` and ``mot_code`` returns every breakdown upstream holds (32 rows for
    Switzerland's 2023 exports to the World); the row with ``partner2_code`` 0,
    ``customs_code`` ``"C00"`` and ``mot_code`` 0 is the total. Arguments are checked
    before any call; an unknown code raises ``InvalidRequestError`` naming the closest
    valid one.

    Args:
        type_code: ``"C"`` goods or ``"S"`` services.
        freq_code: ``"A"`` annual or ``"M"`` monthly.
        cl_code: Product classification: ``"HS"`` (all HS editions; prefer it, a count on
            the edition ``"H6"`` failed upstream with HTTP 500 on 2026-10-23), an edition
            ``"H0"`` to ``"H6"``, SITC ``"SS"``, ``"S1"`` to ``"S4"``, BEC ``"B4"``,
            ``"B5"``, for services EBOPS ``"EB"``, ``"EB02"``, ``"EB10"``, ``"EB10S"``;
            also ``"BE"`` and ``"TM"``, which the spec lists and upstream accepts.
        reporter_code: Reporting areas as UN Comtrade's numeric codes, comma-separated,
            e.g. ``"757"`` Switzerland, ``"842"`` USA, ``"276"`` Germany, ``"156"`` China,
            ``"757,842"``. Some differ from ISO numeric codes: Switzerland is 757, not 756.
            Omit for every reporter.
        partner_code: Partner areas, comma-separated: ``"0"`` World (the total over all
            partners), ``"276"`` Germany. Omit for every partner, one row each.
        partner2_code: Second partner (consignment) areas, comma-separated; ``"0"`` is
            the total.
        period: Years ``"2023"`` (annual) or months ``"202305"`` (monthly), at most 12
            comma-separated, e.g. ``"2021,2022,2023"``.
        cmd_code: Product codes of ``cl_code``, comma-separated: ``"TOTAL"`` for all
            products, ``"AG2"``, ``"AG4"``, ``"AG6"`` for every code at that level, codes
            such as ``"0901"`` or ``"090111"``, wildcards such as ``"27??"`` (every
            four-digit code under 27) or ``"27*"``.
        flow_code: Trade flows, comma-separated: ``"X"`` exports, ``"M"`` imports,
            ``"RX"`` re-exports, ``"RM"`` re-imports, also ``"DX"``, ``"FM"``, ``"MIP"``,
            ``"MOP"``, ``"XIP"``, ``"XOP"``, ``"MIF"``, ``"XIF"``; e.g. ``"M,X"``.
        mot_code: Modes of transport, comma-separated: ``"0"`` the total, ``"1000"`` air,
            ``"2100"`` sea, ``"3100"`` railway, ``"3200"`` road, ``"9100"`` pipelines and
            cables. Omit for every mode, one row each.
        customs_code: Customs procedures, comma-separated: ``"C00"`` the total, ``"C01"``
            clearance for home use, ``"C03"`` outright exportation. Omit for every
            procedure, one row each.
        aggregate_by: Upstream parameters to aggregate the results over, comma-separated
            from ``cmdCode``, ``period``, ``partnerCode``, ``partner2Code``,
            ``reporterCode``, ``customsCode``, ``motCode``; e.g. ``"period"``.
        breakdown_mode: Upstream's breakdown mode, ``"classic"`` or ``"plus"``.
        include_desc: Upstream's ``includeDesc``, "Include descriptions of data
            variables" (the ``*_desc`` fields such as ``reporter_desc``); without it they
            are ``None``.
    """
    request = validate_get(
        type_code,
        freq_code,
        cl_code,
        reporter_code=reporter_code,
        partner_code=partner_code,
        partner2_code=partner2_code,
        period=period,
        cmd_code=cmd_code,
        flow_code=flow_code,
        mot_code=mot_code,
        customs_code=customs_code,
        aggregate_by=aggregate_by,
        breakdown_mode=breakdown_mode,
        include_desc=include_desc,
    )
    count = (await api.get_count_only(**request)).count
    if count == 0:
        return Result(data=[], meta=_meta(request))
    if count > RECORD_LIMIT:
        raise QueryTooLarge(count)
    response = await api.get(**request)
    return Result(data=response.data, meta=_meta(request))


get_counts = sync(get_counts_async)
get_data = sync(get_data_async)
