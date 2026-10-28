"""Task functions, the public API: the adapters serve ``__all__`` (conventions §2).

``/add-endpoint`` adds them.

``meta.endpoint`` is the operation as the Help Center names it (``data/v1/get``), or as
the Tools spec's server path and summary do (``tools/v1/getTradeBalance``), or the
reference file a list comes from (``files/v1/app/reference/Reporters.json``), and
``meta.request`` the task's own arguments that were set, so ``get_data(**meta.request)``
repeats the call. The task-shaped slices (``get_bilateral_flows``,
``get_commodity_series``, ``get_world_trade``, ``get_top_partners``) put the resolved
``get_data`` arguments there instead, pins included (``params.SLICE_PINS``); a commodity
series lists every period, though it sent them 12 per call, and ``get_top_partners``
adds ``n``.

``meta.published_at`` stays ``None`` on every task. Data rows carry no publication date,
and where upstream does publish release dates it publishes one per reporter and period
(``getDa``, ``getMetadata``, ``getLiveUpdate``); a single value for a whole result would
be a guess. The lists packaged with this version (``list_reporters``, ``list_partners``)
carry the time the package fetched them as ``meta.retrieved_at``, and ``meta.vintage``
stays ``None``: upstream gives the files no release identifier (ADR-0022, rule 1).
"""

from collections.abc import Mapping
from typing import Any

from xippios.core import PackagedList, Result, ResultCap, ResultMeta, matches, sync

from xippios.comtrade import api
from xippios.comtrade._client import SOURCE
from xippios.comtrade.api.get import ENDPOINT
from xippios.comtrade.api.get_bilateral_data import ENDPOINT as GET_BILATERAL_DATA
from xippios.comtrade.api.get_da import ENDPOINT as GET_DA
from xippios.comtrade.api.get_live_update import ENDPOINT as GET_LIVE_UPDATE
from xippios.comtrade.api.get_metadata import ENDPOINT as GET_METADATA
from xippios.comtrade.api.get_trade_balance import ENDPOINT as GET_TRADE_BALANCE
from xippios.comtrade.errors import MAX_PERIODS, RECORD_LIMIT, QueryTooLarge
from xippios.comtrade.models import (
    BilateralData,
    Commodity,
    DataAvailability,
    LiveUpdateRecord,
    MetadataDataset,
    PartnerArea,
    Reporter,
    TradeBalanceRecord,
    TradeDataRecord,
    TradeFlowRecord,
)
from xippios.comtrade.params import (
    MAX_SERIES_PERIODS,
    PACKAGE,
    validate_bilateral_data,
    validate_classification_file,
    validate_datasets,
    validate_get,
    validate_slice,
    validate_trade_balance,
)

__all__ = [
    "get_bilateral_data",
    "get_bilateral_flows",
    "get_commodity_series",
    "get_counts",
    "get_data",
    "get_data_availability",
    "get_live_update",
    "get_metadata",
    "get_top_partners",
    "get_trade_balance",
    "get_world_trade",
    "list_commodities",
    "list_partners",
    "list_reporters",
]

# A task named here is Python-only: no tool, no route; the adapters skip it (ADR-0019 decision 4).
BULK_TASKS: frozenset[str] = frozenset()

# Result caps of their own, keyed by the task function's name (conventions §8, ADR-0016):
# the reporter (255) and partner (310) tables reach an agent whole; a classification file
# (8,262 HS codes) cannot, and its note tells the agent to search.
MCP_CAPS: Mapping[str, ResultCap] = {
    "list_reporters": ResultCap(max_rows=400, max_bytes=100_000),
    "list_partners": ResultCap(max_rows=400, max_bytes=100_000),
    "list_commodities": ResultCap(
        max_rows=400,
        max_bytes=100_000,
        note='search by code or text, e.g. search="0901" or search="coffee", to see the rest',
    ),
}

REFERENCE = "files/v1/app/reference"
"""Where upstream serves the reference files; ``meta.endpoint`` of the list tasks."""


def _meta(request: dict[str, Any]) -> ResultMeta:
    return ResultMeta(source=SOURCE, endpoint=ENDPOINT, request=request)


def _bounded(bound: int) -> None:
    """Refuse a slice whose rows could exceed the per-call limit, before any call."""
    if bound > RECORD_LIMIT:
        raise QueryTooLarge(bound, bound=True)


async def _flows(request: dict[str, Any]) -> list[TradeFlowRecord]:
    """One ``data/v1/get`` call of a slice, its rows projected; no count first."""
    response = await api.get(**request)
    return [TradeFlowRecord.project(record) for record in response.data]


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
    on a free key). Arguments are checked before the call, reporter, partner, customs and
    transport codes against the packaged lists: an unknown one raises ``UnknownCode``, an
    ``InvalidRequestError`` naming the packaged list, its fetch date and the closest code
    (756 names 757, Switzerland); another mistake raises ``InvalidRequestError`` naming
    the closest valid value.

    Args:
        type_code: ``"C"`` goods or ``"S"`` services.
        freq_code: ``"A"`` annual or ``"M"`` monthly.
        cl_code: Product classification: ``"HS"`` (all HS editions as reported; prefer
            it), an edition ``"H0"`` to ``"H5"``, SITC ``"SS"``, ``"S1"`` to ``"S4"``, BEC
            ``"B4"``, ``"B5"``, for services EBOPS ``"EB"``, ``"EB02"``, ``"EB10"``,
            ``"EB10S"``; also ``"BE"`` and ``"TM"``, which the spec lists and upstream
            accepts. ``"H6"`` is valid but upstream answered HTTP 500 to all five tries on
            2026-10-23 (two reporters, two product codes); ``"HS"`` rows carry the edition
            the reporter used, e.g. ``classification_code`` ``"H6"`` for Switzerland 2023.
        reporter_code: Reporting areas as UN Comtrade's numeric codes, comma-separated,
            e.g. ``"757"`` Switzerland, ``"842"`` USA, ``"276"`` Germany, ``"156"`` China,
            ``"757,842"``, as ``list_reporters`` lists them. Some differ from ISO numeric
            codes: Switzerland is 757, not 756. Omit for every reporter.
        partner_code: Partner areas, comma-separated, as ``list_partners`` lists them:
            ``"0"`` World (the total over all partners), ``"276"`` Germany. Omit for every
            partner, one row each.
        partner2_code: Second partner (consignment) areas, comma-separated, codes of
            ``list_partners``; ``"0"`` is the total.
        period: Years ``"2023"`` (annual) or months ``"202305"`` (monthly), at most 12
            comma-separated, e.g. ``"2021,2022,2023"``.
        cmd_code: Product codes of ``cl_code``, comma-separated, as
            ``list_commodities(cl_code)`` lists them: ``"TOTAL"`` for all goods,
            ``"AG2"``, ``"AG4"``, ``"AG6"`` for every code at that level, codes such as
            ``"0901"`` or ``"090111"``, wildcards such as ``"27??"`` (every four-digit code
            under 27) or ``"27*"``. For services the classification files name ``"200"``
            (EB, EB02, EB10) or ``"S"`` (EB10S) as the total; recorded counts confirm
            ``"200"`` on EB10 and EB02, where ``"TOTAL"`` counted 0 (EB10). A code
            upstream does not have counts 0 too, so a 0 does not prove that a code exists.
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
            ``reporterCode``, ``customsCode``, ``motCode``; e.g. ``"cmdCode"`` sums the
            products of ``"AG2"`` into one row per remaining breakdown. The aggregated
            parameters come back as ``-2`` (``cmd_code`` ``"-2"``, ``partner_code`` -2)
            with ``classification_code`` ``"GG"``; the count matches the rows.
        breakdown_mode: ``"plus"``, upstream's default (omitting it gives the same rows):
            every customs procedure, mode of transport and second partner;
            ``"classic"``: only the total row (``partner2_code`` 0, ``customs_code``
            ``"C00"``, ``mot_code`` 0).
        include_desc: Upstream's ``includeDesc``, "Include descriptions of data
            variables": fills the ``*_iso`` and ``*_desc`` fields of ``get_data`` rows;
            sent on as given.
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
    ``customs_code`` ``"C00"`` and ``mot_code`` 0 is the total, and pinning those three
    (or ``breakdown_mode="classic"``) returns that row alone. Arguments are checked
    before any call; an unknown reporter, partner, customs or transport code raises
    ``UnknownCode``, an ``InvalidRequestError`` naming the packaged list and the closest
    code, another mistake ``InvalidRequestError`` naming the closest valid value.

    Args:
        type_code: ``"C"`` goods or ``"S"`` services.
        freq_code: ``"A"`` annual or ``"M"`` monthly.
        cl_code: Product classification: ``"HS"`` (all HS editions as reported; prefer
            it), an edition ``"H0"`` to ``"H5"``, SITC ``"SS"``, ``"S1"`` to ``"S4"``, BEC
            ``"B4"``, ``"B5"``, for services EBOPS ``"EB"``, ``"EB02"``, ``"EB10"``,
            ``"EB10S"``; also ``"BE"`` and ``"TM"``, which the spec lists and upstream
            accepts. ``"H6"`` is valid but upstream answered HTTP 500 to all five tries on
            2026-10-23 (two reporters, two product codes); ``"HS"`` rows carry the edition
            the reporter used, e.g. ``classification_code`` ``"H6"`` for Switzerland 2023.
        reporter_code: Reporting areas as UN Comtrade's numeric codes, comma-separated,
            e.g. ``"757"`` Switzerland, ``"842"`` USA, ``"276"`` Germany, ``"156"`` China,
            ``"757,842"``, as ``list_reporters`` lists them. Some differ from ISO numeric
            codes: Switzerland is 757, not 756. Omit for every reporter.
        partner_code: Partner areas, comma-separated, as ``list_partners`` lists them:
            ``"0"`` World (the total over all partners), ``"276"`` Germany. Omit for every
            partner, one row each.
        partner2_code: Second partner (consignment) areas, comma-separated, codes of
            ``list_partners``; ``"0"`` is the total.
        period: Years ``"2023"`` (annual) or months ``"202305"`` (monthly), at most 12
            comma-separated, e.g. ``"2021,2022,2023"``.
        cmd_code: Product codes of ``cl_code``, comma-separated, as
            ``list_commodities(cl_code)`` lists them: ``"TOTAL"`` for all goods,
            ``"AG2"``, ``"AG4"``, ``"AG6"`` for every code at that level, codes such as
            ``"0901"`` or ``"090111"``, wildcards such as ``"27??"`` (every four-digit code
            under 27) or ``"27*"``. For services the classification files name ``"200"``
            (EB, EB02, EB10) or ``"S"`` (EB10S) as the total; recorded counts confirm
            ``"200"`` on EB10 and EB02, where ``"TOTAL"`` counted 0 (EB10). A code
            upstream does not have counts 0 too, so a 0 does not prove that a code exists.
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
            ``reporterCode``, ``customsCode``, ``motCode``; e.g. ``"cmdCode"`` sums the
            products of ``"AG2"`` into one row per remaining breakdown. The aggregated
            parameters come back as ``-2`` (``cmd_code`` ``"-2"``, ``partner_code`` -2)
            with ``classification_code`` ``"GG"``; the count matches the rows.
        breakdown_mode: ``"plus"``, upstream's default (omitting it gives the same rows):
            every customs procedure, mode of transport and second partner;
            ``"classic"``: only the total row (``partner2_code`` 0, ``customs_code``
            ``"C00"``, ``mot_code`` 0).
        include_desc: Upstream's ``includeDesc``, "Include descriptions of data
            variables": fills ``reporter_iso``/``reporter_desc``, the partner and second
            partner ones, ``flow_desc``, ``cmd_desc``, ``customs_desc``, ``mot_desc``, the
            quantity unit abbreviations, ``aggr_level`` and ``is_leaf``; without it they
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


async def get_data_availability_async(
    type_code: str,
    freq_code: str,
    cl_code: str,
    *,
    reporter_code: str | None = None,
    period: str | None = None,
    published_date_from: str | None = None,
    published_date_to: str | None = None,
) -> Result[list[DataAvailability]]:
    """List the UN Comtrade datasets a query covers, per reporter and period, with release dates.

    Upstream's ``getDa``: which reporters have published data for which periods, in which
    classification, how many records each dataset holds and when it was first and last
    released (``first_released``, ``last_released``, naive datetimes as upstream sends
    them). One call. A period nobody reported returns an empty list. Arguments are checked
    before the call; an unknown reporter code raises ``UnknownCode``, an
    ``InvalidRequestError`` naming the packaged list and the closest area, another
    mistake ``InvalidRequestError`` naming the closest valid value.

    Args:
        type_code: ``"C"`` goods or ``"S"`` services.
        freq_code: ``"A"`` annual or ``"M"`` monthly.
        cl_code: Classification: ``"HS"`` for the data as reported (Switzerland 2023 is
            an ``"H6"`` dataset), an HS edition ``"H0"`` to ``"H6"``, SITC ``"S1"`` to
            ``"S4"``, ``"BE"``, for services ``"EB"``, ``"EB02"``, ``"EB10"``.
        reporter_code: Reporters, comma-separated, as ``list_reporters`` lists them:
            ``"757"`` Switzerland, ``"842"`` USA, ``"276"`` Germany, ``"156"`` China,
            ``"757,842"``. Omit for every reporter (169 datasets for 2023, annual HS).
        period: Years ``"2023"`` or months ``"202305"``, comma-separated, e.g.
            ``"2021,2022,2023"``; unlike ``get_data``, more than 12 are accepted.
        published_date_from: Upstream's ``publishedDateFrom``, a day ``"2024-01-01"``:
            datasets published from then on. A dataset revised in the range counts
            (Switzerland 2022, first released 2023-02-01, revised 2024-04-29, is in 2024).
        published_date_to: Upstream's ``publishedDateTo``, a day ``"2024-12-31"``.
    """
    request = validate_datasets(
        type_code,
        freq_code,
        cl_code,
        reporter_code=reporter_code,
        period=period,
        published_date_from=published_date_from,
        published_date_to=published_date_to,
    )
    response = await api.get_da(**request)
    return Result(
        data=response.data,
        meta=ResultMeta(source=SOURCE, endpoint=GET_DA, request=request),
    )


async def get_metadata_async(
    type_code: str,
    freq_code: str,
    cl_code: str,
    *,
    reporter_code: str | None = None,
    period: str | None = None,
) -> Result[list[MetadataDataset]]:
    """List UN Comtrade's publication notes for a reporter's datasets, one per publication.

    Upstream's ``getMetadata``: per dataset (reporter and period), a note for its first
    publication ("New Data") and one for each revision ("Revised Data"), each with its
    ``publication_date`` and what the reporter's data rests on: ``currency``, the import
    and export conversion factors (``Decimal``), ``trade_system`` (``"General"`` or
    ``"Special"``), the valuation (``"CIF"``, ``"FOB"``) and partner attribution. One call.
    ``reporter_code`` and ``period`` are not in upstream's spec, but upstream honours them
    as the official ``comtradeapicall`` package sends them; without ``reporter_code`` the
    answer holds every reporter's notes, so name one.

    Args:
        type_code: ``"C"`` goods or ``"S"`` services.
        freq_code: ``"A"`` annual or ``"M"`` monthly.
        cl_code: Classification: ``"HS"`` (``"H6"`` is answered the same), SITC
            ``"SS"`` or ``"S1"`` to ``"S4"``, ``"BE"``, ``"TM"``, for services ``"EB"``,
            ``"EB02"``, ``"EB10"``.
        reporter_code: Reporters, comma-separated, as ``list_reporters`` lists them:
            ``"757"`` Switzerland (38 annual datasets, 1988 onwards), ``"842"`` USA,
            ``"276"`` Germany, ``"156"`` China.
        period: Years ``"2023"`` or months ``"202305"``, comma-separated. Omit for every
            period.
    """
    request = validate_datasets(
        type_code, freq_code, cl_code, reporter_code=reporter_code, period=period
    )
    response = await api.get_metadata(**request)
    meta = ResultMeta(source=SOURCE, endpoint=GET_METADATA, request=request)
    return Result(data=response.data, meta=meta)


async def get_live_update_async() -> Result[list[LiveUpdateRecord]]:
    """List the 50 most recent releases in UN Comtrade's release pipeline, newest first.

    Upstream's ``getLiveUpdate``: for each release the reporter (``reporter_code``, a
    string here, e.g. ``"842"``), ``type_code``, ``freq_code``, ``classification_code``,
    ``period``, file ``size``, ``status`` and ``release_status`` (e.g. ``"Released"``),
    and four times: ``started_at`` and ``completed_at`` (UTC), ``last_updated`` (a day)
    and ``queued_at`` (no zone given, kept naive). There is no publication date field;
    ``get_data_availability`` and ``get_metadata`` carry those per dataset. One call, no
    arguments. Upstream's ``count`` (174 when recorded) is not the number of rows, so it
    is not returned.
    """
    response = await api.get_live_update()
    meta = ResultMeta(source=SOURCE, endpoint=GET_LIVE_UPDATE)
    return Result(data=response.data, meta=meta)


async def get_trade_balance_async(
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
) -> Result[list[TradeBalanceRecord]]:
    """Fetch UN Comtrade trade data with a reporter's exports and imports side by side.

    Upstream's ``getTradeBalance``, which its spec marks "EXPERIMENTAL - USE SPARINGLY":
    one keyed call, no count first. Each row, a ``TradeBalanceRecord``, holds a reporter's
    exports (``*_x``: ``primary_value_x``, ``qty_x``, ``net_wgt_x``, ...) and imports
    (``*_m``) with one partner, second partner, product code, customs procedure, mode of
    transport and period, and ``primary_value_bal``, which the spec defines as "X - M":
    upstream's value, passed through (``54550055814.504944`` for Switzerland and the World
    in 2023). Without ``breakdown_mode`` upstream answers every breakdown (48 rows for
    Switzerland and the World, 2023, all goods); ``breakdown_mode="classic"`` returns the
    total row alone. A query nothing matches returns an empty list. ``meta.total`` is
    upstream's ``count``. The query must name ``reporter_code`` or ``partner_code``, and
    ``cmd_code``: upstream offers no count to check a query's size before the call
    (``countOnly`` answered 0 for those 48 rows), so a broader query is refused before it
    is sent. Arguments are checked before the call; an unknown reporter, partner, customs
    or transport code raises ``UnknownCode``, an ``InvalidRequestError`` naming the
    packaged list and the closest code, another mistake ``InvalidRequestError`` naming the
    closest valid value. The spec says a free-tier key that is not on UN Comtrade's
    allow-list is refused with HTTP 403 "User not allowed" (``AuthError``); the key the
    package was recorded with was answered (2026-10-28).

    Args:
        type_code: ``"C"`` goods or ``"S"`` services.
        freq_code: ``"A"`` annual or ``"M"`` monthly.
        cl_code: Product classification, checked against the package's list: ``"HS"``
            (all HS editions as reported, the one recorded here; rows name the edition in
            ``classification_code``, e.g. ``"H6"``), an edition ``"H0"`` to ``"H6"``,
            SITC ``"SS"``, ``"S1"`` to ``"S4"``, BEC ``"B4"``, ``"B5"``, ``"BE"``,
            ``"TM"``, for services EBOPS ``"EB"``, ``"EB02"``, ``"EB10"``, ``"EB10S"``.
            The Tools spec lists ``HS``, ``S1`` to ``S4``, ``BE4``, ``BE5``, ``EB``,
            ``EB02``, ``EB10`` and ``EBSDMX``; ``BE4``, ``BE5`` and ``EBSDMX`` are not in
            the package's list (upstream refused ``BE5`` on ``data/v1/get`` and
            ``EBSDMX`` on ``getDa``) and are refused before the call.
        reporter_code: Reporting areas as UN Comtrade's numeric codes, comma-separated,
            e.g. ``"757"`` Switzerland, ``"842"`` USA, ``"276"`` Germany, ``"156"`` China,
            ``"757,842"``, as ``list_reporters`` lists them. Some differ from ISO numeric
            codes: Switzerland is 757, not 756. Required unless ``partner_code`` is given.
        period: Years ``"2023"`` (annual) or months ``"202305"`` (monthly), at most 12
            comma-separated, e.g. ``"2021,2022,2023"``.
        partner_code: Partner areas, comma-separated, as ``list_partners`` lists them:
            ``"0"`` World (the total over all partners), ``"276"`` Germany. Required
            unless ``reporter_code`` is given; omitted, upstream's default applies, which
            on ``get_data`` is every partner, one row each.
        partner2_code: Second partner (consignment) areas, comma-separated, codes of
            ``list_partners``; ``"0"`` is the total.
        cmd_code: Product codes of ``cl_code``, comma-separated, as
            ``list_commodities(cl_code)`` lists them: ``"TOTAL"`` for all goods,
            ``"AG2"`` for every chapter, codes such as ``"27"``, ``"0901"`` or
            ``"090111"``, wildcards such as ``"27??"``.
        customs_code: Customs procedures, comma-separated: ``"C00"`` the total, ``"C01"``
            clearance for home use, ``"C03"`` outright exportation. Omit for every
            procedure, one row each.
        mot_code: Modes of transport, comma-separated: ``"0"`` the total, ``"1000"`` air,
            ``"2100"`` sea, ``"3100"`` railway, ``"3200"`` road, ``"9100"`` pipelines and
            cables. Omit for every mode, one row each.
        aggregate_by: Upstream parameters to aggregate the results over, comma-separated
            from ``cmdCode``, ``period``, ``partnerCode``, ``partner2Code``,
            ``reporterCode``, ``customsCode``, ``motCode``, e.g. ``"cmdCode"``; sent on as
            given (not recorded on this operation; on ``get_data`` the aggregated
            parameters come back as ``-2``).
        breakdown_mode: Omitted, upstream's default: every customs procedure, mode of
            transport and second partner, one row each. ``"classic"``: the total row only
            (``customs_code`` ``"C00"``, ``mot_code`` 0, ``partner2_code`` 0). ``"plus"``,
            the spec's other value, gives every breakdown on ``get_data``.
        include_desc: Upstream's ``includeDesc``, "Include descriptions of data
            variables": with it the recorded rows have ``reporter_iso``/``reporter_desc``,
            the partner and second partner ones, ``cmd_desc``, ``customs_desc``,
            ``mot_desc``, the quantity unit abbreviations, ``aggr_level`` and ``is_leaf``
            filled; no answer with rows was recorded without it.
    """
    request = validate_trade_balance(
        type_code,
        freq_code,
        cl_code,
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
    response = await api.get_trade_balance(**request)
    meta = ResultMeta(
        source=SOURCE, endpoint=GET_TRADE_BALANCE, request=request, total=response.count
    )
    return Result(data=response.data, meta=meta)


async def get_bilateral_data_async(
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
) -> Result[BilateralData]:
    """Compare a reporter's trade figures with its partners' mirror figures, row by row.

    Upstream's ``getBilateralData``, which its spec marks "EXPERIMENTAL - USE SPARINGLY":
    one keyed call, "basic trade data joined with mirror partner data", useful to analyse
    bilateral trade asymmetries. It is the one task whose result is not a list: ``data`` is
    a ``BilateralData`` holding upstream's ``note``, its ``timestamp_requested`` and the
    rows, ``data.data``, because the note qualifies the mirror values. It counts the
    partners with a data gap and gives their share of world trade without naming them ("a
    data gap for 2 partner(s) ... approximately 0.015% of the accumulated world's share").
    Each row, a ``BilateralDataRecord``, is one reporter, partner, product code, flow and
    period at the total of every breakdown (``customs_code`` ``"C00"``, ``mot_code`` 0): the
    reporter's figures (``primary_value``, ``qty``, ``net_wgt``, ...) beside the mirror
    (``mirror_primary_value``, ``mirror_qty``, ...), for a reporter's exports "the import
    data reported by" its partners, as UN Comtrade's Help Center puts it. It warns that "the
    outcome of the mirror data depends on the availability of other reporters rather than
    no-trade": a mirror of 0 is no evidence of no trade. For Switzerland's 2023 exports
    Afghanistan's mirror of 0 showed which partner the gap was, inferred from the counts
    (DPRK alone: 1, the USA alone: none, the three together: 2), not stated. That is no
    general rule: the note speaks of a gap "during specific periods" and says "the
    calculation of mirror data may be incomplete", and a mirror of 0 can also be a partner
    that reported no such imports. ``primary_value_disc`` is upstream's, its meaning not
    stated; in every recorded row it equals ``(mirror_primary_value - primary_value) /
    primary_value``, a relative difference (``-0.16`` for Switzerland's 2023 exports to the
    USA, ``-1.0`` where the mirror is 0). The ``mirror2_*`` fields are not described
    upstream and were ``None`` or 0 in every recorded row. A pair upstream holds nothing for
    has no row. ``meta.total`` is upstream's ``count``. Over MCP the rows are not cut to the
    result cap one by one: an answer above it (about 40 rows) comes as a preview of its
    text, so name a few partners or periods per call. The query must name ``reporter_code``
    or ``partner_code``, and ``cmd_code``: upstream offers no count to check a query's size
    before the call (it ignores ``countOnly``), so a broader query is refused before it is
    sent. Arguments are checked before the call; an unknown reporter or partner code raises
    ``UnknownCode``, an ``InvalidRequestError`` naming the packaged list and the closest
    area, another mistake ``InvalidRequestError`` naming the closest valid value.

    Args:
        type_code: ``"C"`` goods or ``"S"`` services.
        freq_code: ``"A"`` annual or ``"M"`` monthly.
        cl_code: Product classification, checked against the package's list: ``"HS"``
            (all HS editions as reported, the one recorded here; rows name the edition in
            ``classification_code``, e.g. ``"H6"``), an edition ``"H0"`` to ``"H6"``,
            SITC ``"SS"``, ``"S1"`` to ``"S4"``, BEC ``"B4"``, ``"B5"``, ``"BE"``,
            ``"TM"``, for services EBOPS ``"EB"``, ``"EB02"``, ``"EB10"``, ``"EB10S"``.
            The Tools spec lists ``HS``, ``S1`` to ``S4``, ``BE4``, ``BE5``, ``EB``,
            ``EB02``, ``EB10`` and ``EBSDMX``; ``BE4``, ``BE5`` and ``EBSDMX`` are not in
            the package's list (upstream refused ``BE5`` on ``data/v1/get`` and
            ``EBSDMX`` on ``getDa``) and are refused before the call.
        reporter_code: Reporting areas as UN Comtrade's numeric codes, comma-separated,
            e.g. ``"757"`` Switzerland, ``"842"`` USA, ``"276"`` Germany, ``"156"`` China,
            ``"757,842"``, as ``list_reporters`` lists them. Some differ from ISO numeric
            codes: Switzerland is 757, not 756. Required unless ``partner_code`` is given.
        period: Years ``"2023"`` (annual) or months ``"202305"`` (monthly),
            comma-separated, e.g. ``"2021,2022,2023"``; unlike ``get_data``, more than 12
            are accepted (13 answered 13 rows).
        partner_code: Partner areas, comma-separated, as ``list_partners`` lists them:
            ``"842"`` USA, ``"276"`` Germany, ``"842,276"``, one row each. Required
            unless ``reporter_code`` is given.
        cmd_code: Product codes of ``cl_code``, comma-separated, as
            ``list_commodities(cl_code)`` lists them: ``"TOTAL"`` for all goods,
            ``"AG2"`` for every chapter, codes such as ``"27"``, ``"0901"`` or
            ``"090111"``, wildcards such as ``"27??"``.
        flow_code: One trade flow: ``"X"`` exports or ``"M"`` imports; upstream refuses
            both in one call (``"M,X"``), so call once per flow.
        include_desc: Upstream's ``includeDesc``, sent on as given: the recorded answers
            carry no descriptions with or without it (the ``*_iso`` and ``*_desc`` fields
            stay ``None``); ``list_reporters`` and ``list_partners`` name the codes.
    """
    request = validate_bilateral_data(
        type_code,
        freq_code,
        cl_code,
        reporter_code=reporter_code,
        period=period,
        partner_code=partner_code,
        cmd_code=cmd_code,
        flow_code=flow_code,
        include_desc=include_desc,
    )
    response = await api.get_bilateral_data(**request)
    meta = ResultMeta(
        source=SOURCE, endpoint=GET_BILATERAL_DATA, request=request, total=response.count
    )
    return Result(data=BilateralData.project(response), meta=meta)


async def get_bilateral_flows_async(
    reporter: str,
    partner: str,
    commodities: str,
    periods: str,
    flow: str,
    *,
    cl_code: str = "HS",
) -> Result[list[TradeFlowRecord]]:
    """Trade between one reporter and one partner, one row per product code and period.

    One ``data/v1/get`` call for goods (``typeCode`` C), pinned to the total of every
    breakdown (``partner2Code`` 0, ``customsCode`` C00, ``motCode`` 0, ``breakdownMode``
    classic) and with descriptions (``includeDesc``), so each row is UN Comtrade's figure
    for the reporter's side of the trade in one product code and period. At ``TOTAL``
    and chapter level these are mostly UNSD aggregates (``is_aggregate`` true,
    ``is_reported`` false) with no quantity (``qty`` 0, ``qty_unit_abbr`` ``"N/A"``,
    ``net_wgt`` 0 or ``None``): read the trade values. Rows are ``TradeFlowRecord``,
    sorted by period, then product code; a code or period upstream holds nothing for has
    no row. Bounded by construction at product codes times periods rows (at most 12
    periods), so there is no count call; a bound above 100,000 raises ``QueryTooLarge``
    before the call. Arguments are resolved and checked before the call; an unknown area
    raises ``UnknownCode``, an ``InvalidRequestError`` naming the packaged list and the
    closest area, another mistake ``InvalidRequestError`` naming the closest valid value.
    ``meta.request`` holds the ``get_data`` arguments that were sent, codes resolved.

    Args:
        reporter: The reporting area, as UN Comtrade's code or its ISO alpha-3 code:
            ``"757"`` or ``"CHE"`` Switzerland, ``"842"`` or ``"USA"``, ``"276"`` or ``"DEU"``
            Germany, ``"156"`` or ``"CHN"`` China; ``list_reporters(search=...)`` finds them.
            Codes are UN Comtrade's, not ISO numeric (Switzerland is 757, not 756). An
            alpha-3 code that several codes share resolves to the one still in use
            (``"DEU"`` is 276, not 280 Fed. Rep. of Germany until 1990).
        partner: The partner area, as code or ISO alpha-3 code: ``"842"`` or ``"USA"``
            (842, the code the USA reports under, not 840), ``"276"`` or ``"DEU"``, ``"0"``
            or ``"W00"`` World, the total over all partners; ``list_partners(search=...)``
            finds them.
        commodities: Product codes of ``cl_code``, comma-separated, each naming one code:
            ``"TOTAL"`` all goods, an HS chapter ``"27"``, heading ``"2709"`` or subheading
            ``"270900"``, e.g. ``"TOTAL,27"``. Levels such as ``"AG2"`` and wildcards such
            as ``"27??"`` are for ``get_data``. ``list_commodities("HS", search="crude")``
            finds codes.
        periods: Years ``"2022,2023"`` (annual data) or months ``"202301,202302"`` (monthly
            data), comma-separated, at most 12, one format: the format sets ``freqCode``.
        flow: One trade flow: ``"X"`` exports, ``"M"`` imports, ``"RX"`` re-exports,
            ``"RM"`` re-imports.
        cl_code: Product classification, ``"HS"`` by default: all HS editions as each
            reporter reported them (rows name the edition in ``classification_code``, e.g.
            ``"H6"``); an edition ``"H0"`` to ``"H5"``, SITC ``"SS"`` or ``"S1"`` to ``"S4"``,
            BEC ``"B4"``, ``"B5"`` also work. ``"H6"`` is valid but upstream answered HTTP 500
            to every try on 2026-10-23, so ``"HS"`` stays the default. EBOPS ``"EB"``,
            ``"EB02"``, ``"EB10"``, ``"EB10S"`` (services), ``"BE"`` and ``"TM"`` are
            accepted but untested with the pinned ``typeCode`` C.
    """
    request = validate_slice(
        cl_code, flow, reporter=reporter, partner=partner, commodities=commodities,
        periods=periods,
    )  # fmt: skip
    _bounded(len(request["cmd_code"].split(",")) * len(request["period"].split(",")))
    rows = await _flows(request)
    rows.sort(key=lambda row: (row.period or "", row.cmd_code or ""))
    return Result(data=rows, meta=_meta(request))


async def get_commodity_series_async(
    reporter: str,
    commodity: str,
    flow: str,
    periods: str,
    *,
    cl_code: str = "HS",
) -> Result[list[TradeFlowRecord]]:
    """A reporter's trade in one product with the World over many periods, oldest first.

    ``data/v1/get`` for goods (``typeCode`` C) with partner 0, World (the total over all
    partners), pinned to the total of every breakdown (``partner2Code`` 0, ``customsCode``
    C00, ``motCode`` 0, ``breakdownMode`` classic), with descriptions (``includeDesc``).
    Upstream takes at most 12 periods per call, so the periods are sent in chunks of 12,
    one call after the other in the order given (14 periods: two calls, 1.5 s apart), and
    the rows are joined and sorted by period; a period upstream holds nothing for has no
    row. A period the reporter has not released yet has no row either, which cannot be
    told from a period without trade; ``get_data_availability`` names the periods a
    reporter has released. One row per period at most, so there is no count call. Every
    chunk is a keyed call and a free key allows 500 calls a day, so one series takes at
    most 120 periods (ten calls); more raise ``InvalidRequestError`` before any call:
    split the series. Arguments are resolved and checked before any call; an unknown
    reporter raises ``UnknownCode``, an ``InvalidRequestError`` naming the packaged list
    and the closest area, another mistake ``InvalidRequestError`` naming the closest valid
    value. ``meta.request`` holds the ``get_data`` arguments with every period; they were
    sent 12 at a time.

    Args:
        reporter: The reporting area, as UN Comtrade's code or its ISO alpha-3 code:
            ``"757"`` or ``"CHE"`` Switzerland, ``"842"`` or ``"USA"``, ``"276"`` or ``"DEU"``
            Germany, ``"156"`` or ``"CHN"`` China; ``list_reporters(search=...)`` finds them.
            Codes are UN Comtrade's, not ISO numeric (Switzerland is 757, not 756). An
            alpha-3 code that several codes share resolves to the one still in use
            (``"DEU"`` is 276, not 280 Fed. Rep. of Germany until 1990).
        commodity: One product code of ``cl_code``: ``"TOTAL"`` all goods, an HS chapter
            ``"27"``, heading ``"0901"`` or subheading ``"090111"``.
            ``list_commodities("HS", search="coffee")`` finds codes.
        flow: One trade flow: ``"X"`` exports, ``"M"`` imports, ``"RX"`` re-exports,
            ``"RM"`` re-imports.
        periods: Years (annual data) or months (monthly data), comma-separated, one
            format, each once, at most 120: ``"2018,2019,2020,2021,2022,2023"``,
            ``"202201,202202,202203"``; every year from 2010 to 2023 is 14 periods, two
            calls.
        cl_code: Product classification, ``"HS"`` by default: all HS editions as each
            reporter reported them (rows name the edition in ``classification_code``, e.g.
            ``"H6"``); an edition ``"H0"`` to ``"H5"``, SITC ``"SS"`` or ``"S1"`` to ``"S4"``,
            BEC ``"B4"``, ``"B5"`` also work. ``"H6"`` is valid but upstream answered HTTP 500
            to every try on 2026-10-23, so ``"HS"`` stays the default. EBOPS ``"EB"``,
            ``"EB02"``, ``"EB10"``, ``"EB10S"`` (services), ``"BE"`` and ``"TM"`` are
            accepted but untested with the pinned ``typeCode`` C.
    """
    request = validate_slice(
        cl_code, flow, reporter=reporter, partner="0", commodity=commodity, periods=periods,
        max_periods=MAX_SERIES_PERIODS,
    )  # fmt: skip
    members = request["period"].split(",")
    rows: list[TradeFlowRecord] = []
    for start in range(0, len(members), MAX_PERIODS):
        chunk = ",".join(members[start : start + MAX_PERIODS])
        rows += await _flows({**request, "period": chunk})
    rows.sort(key=lambda row: row.period or "")
    return Result(data=rows, meta=_meta(request))


async def get_world_trade_async(
    commodity: str,
    period: str,
    flow: str,
    *,
    cl_code: str = "HS",
) -> Result[list[TradeFlowRecord]]:
    """Every reporter's trade in one product with the World for one period, largest first.

    One ``data/v1/get`` call for goods (``typeCode`` C) without ``reporterCode`` (every
    reporter) and with partner 0, World, pinned to the total of every breakdown
    (``partner2Code`` 0, ``customsCode`` C00, ``motCode`` 0, ``breakdownMode`` classic),
    with descriptions (``includeDesc``): one row per reporter that reported the period
    (167 for 2023 imports of HS chapter 27 when recorded), sorted by ``primary_value``,
    largest first. Bounded by construction at one row per reporter (255 in the packaged
    ``Reporters.json``), so there is no count call. Arguments are checked before the
    call; a mistake raises ``InvalidRequestError`` naming the closest valid value.
    ``meta.request`` holds the ``get_data`` arguments that were sent.

    Args:
        commodity: One product code of ``cl_code``: ``"TOTAL"`` all goods, an HS chapter
            ``"27"``, heading ``"2709"`` or subheading ``"270900"``.
            ``list_commodities("HS", search="crude")`` finds codes.
        period: One year ``"2023"`` (annual data) or month ``"202305"`` (monthly data).
            Recent periods fill as reporters publish; ``get_data_availability`` tells who
            has.
        flow: One trade flow: ``"X"`` exports, ``"M"`` imports, ``"RX"`` re-exports,
            ``"RM"`` re-imports.
        cl_code: Product classification, ``"HS"`` by default: all HS editions as each
            reporter reported them (rows name the edition in ``classification_code``, e.g.
            ``"H6"``); an edition ``"H0"`` to ``"H5"``, SITC ``"SS"`` or ``"S1"`` to ``"S4"``,
            BEC ``"B4"``, ``"B5"`` also work. ``"H6"`` is valid but upstream answered HTTP 500
            to every try on 2026-10-23, so ``"HS"`` stays the default. EBOPS ``"EB"``,
            ``"EB02"``, ``"EB10"``, ``"EB10S"`` (services), ``"BE"`` and ``"TM"`` are
            accepted but untested with the pinned ``typeCode`` C.
    """
    request = validate_slice(cl_code, flow, partner="0", commodity=commodity, period=period)
    _bounded(len(PackagedList.load(PACKAGE, "Reporters").records))
    rows = await _flows(request)
    rows.sort(key=lambda row: (-row.primary_value, row.reporter_code))
    return Result(data=rows, meta=_meta(request))


async def get_top_partners_async(
    reporter: str,
    commodity: str,
    period: str,
    flow: str,
    n: int,
    *,
    cl_code: str = "HS",
) -> Result[list[TradeFlowRecord]]:
    """A reporter's ``n`` largest partners in one product and period, by primary value.

    One ``data/v1/get`` call for goods (``typeCode`` C) without ``partnerCode`` (every
    partner), pinned to the total of every breakdown (``partner2Code`` 0, ``customsCode``
    C00, ``motCode`` 0, ``breakdownMode`` classic), with descriptions (``includeDesc``).
    The rows are sorted by ``primary_value``, largest first, here rather than upstream;
    partner 0, World, is dropped because it is the total over all partners, not a
    partner; the first ``n`` rows are returned and nothing else is changed. Areas that
    are not countries, such as 490 "Other Asia, nes", stay in the ranking where the
    reporter reported them. Bounded by construction at one row per partner (310 in the
    packaged ``partnerAreas.json``), so there is no count call. Arguments are resolved and
    checked before the call; an unknown reporter raises ``UnknownCode``, an
    ``InvalidRequestError`` naming the packaged list and the closest area, another
    mistake ``InvalidRequestError`` naming the closest valid value. ``meta.request`` holds
    the ``get_data`` arguments that were sent, and ``n``.

    Args:
        reporter: The reporting area, as UN Comtrade's code or its ISO alpha-3 code:
            ``"757"`` or ``"CHE"`` Switzerland, ``"842"`` or ``"USA"``, ``"276"`` or ``"DEU"``
            Germany, ``"156"`` or ``"CHN"`` China; ``list_reporters(search=...)`` finds them.
            Codes are UN Comtrade's, not ISO numeric (Switzerland is 757, not 756). An
            alpha-3 code that several codes share resolves to the one still in use
            (``"DEU"`` is 276, not 280 Fed. Rep. of Germany until 1990).
        commodity: One product code of ``cl_code``: ``"TOTAL"`` all goods, an HS chapter
            ``"27"``, heading ``"3004"`` or subheading ``"300490"``.
            ``list_commodities("HS", search="medicament")`` finds codes.
        period: One year ``"2023"`` (annual data) or month ``"202305"`` (monthly data).
        flow: One trade flow: ``"X"`` exports, ``"M"`` imports, ``"RX"`` re-exports,
            ``"RM"`` re-imports.
        n: How many partners, at least 1, e.g. ``10``; fewer come back when fewer
            partners have a row.
        cl_code: Product classification, ``"HS"`` by default: all HS editions as each
            reporter reported them (rows name the edition in ``classification_code``, e.g.
            ``"H6"``); an edition ``"H0"`` to ``"H5"``, SITC ``"SS"`` or ``"S1"`` to ``"S4"``,
            BEC ``"B4"``, ``"B5"`` also work. ``"H6"`` is valid but upstream answered HTTP 500
            to every try on 2026-10-23, so ``"HS"`` stays the default. EBOPS ``"EB"``,
            ``"EB02"``, ``"EB10"``, ``"EB10S"`` (services), ``"BE"`` and ``"TM"`` are
            accepted but untested with the pinned ``typeCode`` C.
    """
    request = validate_slice(
        cl_code, flow, reporter=reporter, commodity=commodity, period=period, n=n
    )
    _bounded(len(PackagedList.load(PACKAGE, "partnerAreas").records))
    rows = [row for row in await _flows(request) if row.partner_code != 0]
    rows.sort(key=lambda row: (-row.primary_value, row.partner_code))
    return Result(data=rows[:n], meta=_meta({**request, "n": n}))


async def list_reporters_async(search: str | None = None) -> Result[list[Reporter]]:
    """List the reporters UN Comtrade has trade data from, with the codes reporter_code takes.

    Answered from upstream's ``Reporters.json`` as packaged with this version
    (``reference/Reporters.json``), without an upstream call; ``meta.retrieved_at`` is
    when the package fetched it, ``meta.vintage`` is ``None``. 255 rows when packaged,
    one per reporter code, current and historical (``entry_expired_date`` is set on codes
    no longer used, such as ``280`` Fed. Rep. of Germany until 1990 or ``810`` USSR).
    Codes are UN Comtrade's, not always ISO numeric: ``757`` Switzerland (not 756),
    ``842`` USA, ``276`` Germany, ``156`` China; ``97`` European Union and ``975`` ASEAN
    are groups (``is_group``). ``search`` finds a code without reading the whole list.

    Args:
        search: Keep the rows where this text occurs, ignoring case, in the code
            (``reporter_code``), the ISO alpha-3 code or the names (``text``,
            ``reporter_desc``, ``reporter_note``), e.g. ``"switz"``, ``"757"``, ``"CHE"``
            (757 Switzerland, and 690 Seychelles by its name), ``"germany"`` (276 Germany,
            278 and 280 until 1990). Omit for every row.
    """
    packaged = PackagedList.load(PACKAGE, "Reporters")
    rows = [
        row
        for row in packaged.parse(Reporter, source=SOURCE)
        if matches(
            search,
            row.reporter_code,
            row.reporter_code_iso_alpha3,
            row.text,
            row.reporter_desc,
            row.reporter_note,
        )
    ]
    return Result(data=rows, meta=packaged.meta(SOURCE, request={"search": search}))


async def list_partners_async(search: str | None = None) -> Result[list[PartnerArea]]:
    """List the partner areas UN Comtrade records trade with, for partner_code and partner2_code.

    Answered from upstream's ``partnerAreas.json`` as packaged with this version
    (``reference/partnerAreas.json``), without an upstream call; ``meta.retrieved_at`` is
    when the package fetched it, ``meta.vintage`` is ``None``. 310 rows when packaged:
    ``0`` World (the total over all partners), countries in the reporters' code space
    (``757`` Switzerland, ``842`` USA, ``276`` Germany, ``156`` China) and areas that only
    occur as partners, such as ``899`` "Areas, nes" or ``756`` Switzerland under its ISO
    code. ``search`` finds a code without reading the whole list.

    Args:
        search: Keep the rows where this text occurs, ignoring case, in the code
            (``partner_code``), the ISO alpha-3 code or the names (``text``,
            ``partner_desc``, ``partner_note``), e.g. ``"world"``, ``"W00"``, ``"USA"``
            (840 United States of America, 841, 842 USA), ``"nes"``. Omit for every row.
    """
    packaged = PackagedList.load(PACKAGE, "partnerAreas")
    rows = [
        row
        for row in packaged.parse(PartnerArea, source=SOURCE)
        if matches(
            search,
            row.partner_code,
            row.partner_code_iso_alpha3,
            row.text,
            row.partner_desc,
            row.partner_note,
        )
    ]
    return Result(data=rows, meta=packaged.meta(SOURCE, request={"search": search}))


async def list_commodities_async(
    cl_code: str, search: str | None = None
) -> Result[list[Commodity]]:
    """List the product codes of one UN Comtrade classification, the values cmd_code takes.

    Fetched live from upstream's public classification file ``<cl_code>.json`` (no key, no
    quota) and kept for the life of the process: ``meta.retrieved_at`` is when the file
    was fetched, the first call's time on a later one. The lists are large: ``"HS"`` has
    8,262 codes (about 2 MB), each HS edition 6,000 to 7,000, SITC ``"SS"`` 7,863, BEC
    ``"B5"`` 178, EBOPS ``"EB"`` 423, so ``search`` narrows them. Every row has ``id`` (the
    code), ``text`` and ``parent``; the goods files add ``is_leaf`` and ``aggr_level`` (0
    for ``TOTAL``, then 2, 4 and 6 digits for HS). ``meta.vintage`` stays ``None``: the
    files carry no release identifier.

    Args:
        cl_code: The classification, with a file upstream: ``"HS"`` (all HS editions
            combined), an edition ``"H0"`` (1992) to ``"H6"`` (2022), SITC ``"SS"``
            (combined) or ``"S1"`` to ``"S4"``, BEC ``"B4"`` or ``"B5"``, EBOPS ``"EB"``
            (combined), ``"EB02"``, ``"EB10"`` or ``"EB10S"``. ``"BE"`` and ``"TM"``,
            which ``get_data`` takes, have no file.
        search: Keep the rows where this text occurs, ignoring case, in the code (``id``,
            and ``cmd_code`` in ``SS``) or the description (``text``, and
            ``description_original`` in ``SS``), e.g. ``"coffee"``, ``"crude"``,
            ``"0901"``. HS texts start with the code (``"0901 - Coffee, ..."``). Omit for
            every row.
    """
    request = validate_classification_file(cl_code)
    fetched = await api.reference(f"{cl_code}.json", Commodity)
    rows = [
        row
        for row in fetched.rows
        if matches(search, row.id, row.cmd_code, row.text, row.description_original)
    ]
    meta = ResultMeta(
        source=SOURCE,
        endpoint=f"{REFERENCE}/{cl_code}.json",
        retrieved_at=fetched.retrieved_at,
        request={**request, "search": search},
    )
    return Result(data=rows, meta=meta)


get_bilateral_data = sync(get_bilateral_data_async)
get_bilateral_flows = sync(get_bilateral_flows_async)
get_commodity_series = sync(get_commodity_series_async)
get_counts = sync(get_counts_async)
get_data = sync(get_data_async)
get_data_availability = sync(get_data_availability_async)
get_live_update = sync(get_live_update_async)
get_metadata = sync(get_metadata_async)
get_top_partners = sync(get_top_partners_async)
get_trade_balance = sync(get_trade_balance_async)
get_world_trade = sync(get_world_trade_async)
list_commodities = sync(list_commodities_async)
list_partners = sync(list_partners_async)
list_reporters = sync(list_reporters_async)
