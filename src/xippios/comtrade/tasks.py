"""Task functions, the public API: the adapters serve ``__all__`` (conventions §2).

``/add-endpoint`` adds them. Core builds the server from this module, which declares what
the server holds beside its tools (conventions §8, sdk-core ADR-0063, decision 7):
``MCP_INSTRUCTIONS``, ``MCP_CAPS`` and ``BULK_TASKS``.

``meta.endpoint`` is the operation as the Help Center names it (``data/v1/get``), or as
the Tools spec's server path and summary do (``tools/v1/getTradeBalance``), its path under
the spec's server where no article names it (``public/v1/getWorldShare``), or the
reference file a list comes from (``files/v1/app/reference/Reporters.json``), and
``meta.request`` the task's own arguments that were set, so ``get_data(**meta.request)``
repeats the call. ``meta.retrieved_at`` is the client's time of the answer, a wrapper's
``Answer.retrieved_at``, and the older of its two reads for ``get_data`` (conventions §4).

``meta.published_at`` stays ``None`` on every task. Data rows carry no publication date,
and where upstream does publish release dates it publishes one per reporter and period
(``getDa``, ``getMetadata``, ``getWorldShare``) or per release (``getComtradeReleases``),
each printed without a zone; ``getLiveUpdate`` carries pipeline times, not a publication
date. A single value for a whole result would be a guess.
The lists packaged with this version (``list_reporters``, ``list_partners``,
``list_codes``, ``list_classifications``) carry the time the package fetched them as
``meta.retrieved_at``, and ``meta.vintage`` stays ``None``: upstream gives the files no
release identifier (sdk-core ADR-0041, decision 1).
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from xippios.core import (
    PackagedCodes,
    PackagedList,
    Result,
    ResultCap,
    ResultMeta,
    fetch_counted,
    matches,
    names_codes,
    sync,
)

from xippios.comtrade import api
from xippios.comtrade._client import SOURCE
from xippios.comtrade.api.get import ENDPOINT
from xippios.comtrade.api.get_bilateral_data import ENDPOINT as GET_BILATERAL_DATA
from xippios.comtrade.api.get_comtrade_releases import ENDPOINT as GET_COMTRADE_RELEASES
from xippios.comtrade.api.get_da import ENDPOINT as GET_DA
from xippios.comtrade.api.get_live_update import ENDPOINT as GET_LIVE_UPDATE
from xippios.comtrade.api.get_metadata import ENDPOINT as GET_METADATA
from xippios.comtrade.api.get_trade_balance import ENDPOINT as GET_TRADE_BALANCE
from xippios.comtrade.api.get_world_share import ENDPOINT as GET_WORLD_SHARE
from xippios.comtrade.codes import (
    CUSTOMS_CODES,
    FLOW_CODES,
    FREQ_CODES,
    MOT_CODES,
    PARTNERS,
    REPORTERS,
)
from xippios.comtrade.errors import NARROW, RECORD_LIMIT
from xippios.comtrade.models import (
    BilateralData,
    CodeValue,
    Commodity,
    ComtradeRelease,
    DataAvailability,
    LiveUpdateRecord,
    MetadataDataset,
    PartnerArea,
    Reference,
    Reporter,
    TradeBalanceRecord,
    TradeDataRecord,
    WorldShare,
)
from xippios.comtrade.params import (
    PACKAGE,
    PACKAGED_LISTS,
    Codes,
    TextCodes,
    joined,
    validate_bilateral_data,
    validate_classification_file,
    validate_code_list,
    validate_datasets,
    validate_get,
    validate_reference_category,
    validate_trade_balance,
    validate_world_share,
)

__all__ = [
    "count_data",
    "get_bilateral_data",
    "get_comtrade_releases",
    "get_data",
    "get_data_availability",
    "get_live_update",
    "get_metadata",
    "get_trade_balance",
    "get_world_share",
    "list_classifications",
    "list_codes",
    "list_commodities",
    "list_partners",
    "list_reporters",
]

MCP_INSTRUCTIONS = (
    "UN Comtrade via xippios. Tools are read-only. Where list tools (comtrade_list_*) "
    "exist, call them first to find valid values, then query."
)
"""The server's instructions, which core hands every client (sdk-core ADR-0063, decision 7)."""

# A task named here is Python-only: no tool, no route; the adapters skip it
# (sdk-core ADR-0040 decision 4).
BULK_TASKS: frozenset[str] = frozenset()

# Result caps of their own, keyed by the task function's name (conventions §8,
# sdk-core ADR-0038): the reporter (256) and partner (310) tables reach an agent whole; a
# classification file (8,262 HS codes) cannot, and its note tells the agent to search. One
# period's world share for every reporter (214 rows, 88.5 KB for 2023) reaches an agent
# whole too, where the default cap cut it at 157 rows, dropping the USA (842): upstream
# sends the available rows first, by reporter code, then the unavailable ones in an order
# the recording does not explain. No cap is paged: an answer of get_data can pass the
# cache's bound of 8 MiB, core's cache_max_bytes, which the client keeps, and a
# continuation past it would send its count and its data again (conventions §8, sdk-core
# ADR-0061, decision 9).
MCP_CAPS: Mapping[str, ResultCap] = {
    "list_reporters": ResultCap(max_rows=400, max_bytes=100_000),
    "list_partners": ResultCap(max_rows=400, max_bytes=100_000),
    "list_commodities": ResultCap(
        max_rows=400,
        max_bytes=100_000,
        note='search by code or text, e.g. search="0901" or search="coffee", to see the rest',
    ),
    "get_world_share": ResultCap(
        max_rows=400,
        max_bytes=100_000,
        note='narrow by reporter_code (e.g. "842") or period (e.g. "2023") to see the rest',
    ),
}

REFERENCE = "files/v1/app/reference"
"""Where upstream serves the reference files; ``meta.endpoint`` of the list tasks."""


DATA_CODES: Mapping[str, PackagedCodes] = {
    "freq_code": FREQ_CODES,
    "reporter_code": REPORTERS,
    "partner_code": PARTNERS,
    "partner2_code": PARTNERS,
    "flow_code": FLOW_CODES,
    "customs_code": CUSTOMS_CODES,
    "mot_code": MOT_CODES,
}
"""The code arguments of ``data/v1/get`` that a packaged list names, for ``names_codes``.

Every answer names the codes it was called with in ``meta.names``, so an answer without
rows names what the call asked for (sdk-core ADR-0067, decision 3).
"""

COUNTED_NONE = "UN Comtrade counted no record for the query, so no data request was sent."
"""``get_data``'s note after a count of 0: a code UN Comtrade does not have counts 0 too.

https://github.com/xippios/sdk-comtrade/issues/32; the empty list and its note answer no
data (https://github.com/xippios/sdk-usda-esr/issues/88).
"""


def _meta(
    request: dict[str, Any],
    retrieved_at: datetime,
    *,
    total: int | None = None,
    notes: list[str] | None = None,
) -> ResultMeta:
    return ResultMeta(
        source=SOURCE,
        endpoint=ENDPOINT,
        request=request,
        retrieved_at=retrieved_at,
        total=total,
        notes=notes or [],
    )


@names_codes(**DATA_CODES)
async def count_data_async(
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
) -> Result[int]:
    """Count the UN Comtrade trade records a query would return, without fetching them.

    The same request as ``get_data`` with upstream's ``countOnly``. One call returns at
    most 100,000 records, so count first and split a larger query. A count of 0 means no
    data matches: an unreported period, a code that is not a reporter, a flow the
    reporter does not record. Every count costs one call of the key's daily quota (500
    on a free key). Arguments are checked before the call, and the first problem is
    refused: an unknown reporter, partner, customs or transport code raises
    ``UnknownCode``, an ``InvalidRequestError`` naming the packaged list, its fetch date
    and the closest code (756 names 757, Switzerland).

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
        reporter_code: Reporting areas as UN Comtrade's numeric codes, one or a list, e.g.
            ``"757"`` Switzerland, ``842`` USA, ``"276"`` Germany, ``"156"`` China,
            ``[757, 842]``, as ``list_reporters`` lists them. Some differ from ISO numeric
            codes: Switzerland is 757, not 756. Omit for every reporter.
        period: Years ``"2023"`` (annual) or months ``"202305"`` (monthly), one or a list
            of at most 12, e.g. ``["2021", "2022", "2023"]``.
        partner_code: Partner areas, one or a list, as ``list_partners`` lists them:
            ``"0"`` World (the total over all partners), ``"276"`` Germany. Omit for every
            partner, one row each.
        partner2_code: Second partner (consignment) areas, one or a list, codes of
            ``list_partners``; ``"0"`` is the total.
        cmd_code: Product codes of ``cl_code``, one or a list, as
            ``list_commodities(cl_code)`` lists them: ``"TOTAL"`` for all goods,
            ``"AG2"``, ``"AG4"``, ``"AG6"`` for every code at that level, codes such as
            ``"0901"`` or ``"090111"``, wildcards such as ``"27??"`` (every four-digit code
            under 27) or ``"27*"``. For services the classification files name ``"200"``
            (EB, EB02, EB10) or ``"S"`` (EB10S) as the total; recorded counts confirm
            ``"200"`` on EB10 and EB02, where ``"TOTAL"`` counted 0 (EB10). A code
            upstream does not have counts 0 too, so a 0 does not prove that a code exists.
        flow_code: Trade flows, one or a list: ``"X"`` exports, ``"M"`` imports,
            ``"RX"`` re-exports, ``"RM"`` re-imports, also ``"DX"``, ``"FM"``, ``"MIP"``,
            ``"MOP"``, ``"XIP"``, ``"XOP"``, ``"MIF"``, ``"XIF"``; e.g. ``["M", "X"]``.
        customs_code: Customs procedures, one or a list: ``"C00"`` the total, ``"C01"``
            clearance for home use, ``"C03"`` outright exportation. Omit for every
            procedure, one row each.
        mot_code: Modes of transport, one or a list: ``"0"`` the total, ``"1000"`` air,
            ``"2100"`` sea, ``"3100"`` railway, ``"3200"`` road, ``"9100"`` pipelines and
            cables. Omit for every mode, one row each.
        aggregate_by: Upstream parameters to aggregate the results over, one or a list
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
    sent = joined(request)
    answer = await api.get_count_only(**sent)
    return Result(data=answer.payload.count, meta=_meta(request, answer.retrieved_at))


@names_codes(**DATA_CODES)
async def get_data_async(
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
) -> Result[list[TradeDataRecord]]:
    """Fetch UN Comtrade final trade data for one query, up to 100,000 records.

    One call sends two requests, the count, as ``count_data``, then the data, each tried at
    most 4 times, so at most 8: a count of 0 returns an empty list and a note without the
    data request, and a count above 100,000 raises ``QueryTooLarge`` with the count before
    any data is fetched, since upstream would cut the answer at 100,000 rows without saying
    so. ``meta.total`` is the count. Each row carries every field of upstream's
    ``TradeDataRecord`` under its snake_case name. Leaving out ``partner2_code``,
    ``customs_code`` and ``mot_code`` returns every breakdown; the row with
    ``partner2_code`` 0, ``customs_code`` ``"C00"`` and ``mot_code`` 0 is the total.
    Arguments are checked before any call, and the first problem is refused: an unknown
    reporter, partner, customs or transport code raises ``UnknownCode``, naming the
    packaged list and the closest code.

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
        reporter_code: Reporting areas as UN Comtrade's numeric codes, one or a list, e.g.
            ``"757"`` Switzerland, ``842`` USA, ``"276"`` Germany, ``"156"`` China,
            ``[757, 842]``, as ``list_reporters`` lists them. Some differ from ISO numeric
            codes: Switzerland is 757, not 756. Omit for every reporter.
        period: Years ``"2023"`` (annual) or months ``"202305"`` (monthly), one or a list
            of at most 12, e.g. ``["2021", "2022", "2023"]``.
        partner_code: Partner areas, one or a list, as ``list_partners`` lists them:
            ``"0"`` World (the total over all partners), ``"276"`` Germany. Omit for every
            partner, one row each.
        partner2_code: Second partner (consignment) areas, one or a list, codes of
            ``list_partners``; ``"0"`` is the total.
        cmd_code: Product codes of ``cl_code``, one or a list, as
            ``list_commodities(cl_code)`` lists them: ``"TOTAL"`` for all goods,
            ``"AG2"``, ``"AG4"``, ``"AG6"`` for every code at that level, codes such as
            ``"0901"`` or ``"090111"``, wildcards such as ``"27??"`` (every four-digit code
            under 27) or ``"27*"``. For services the classification files name ``"200"``
            (EB, EB02, EB10) or ``"S"`` (EB10S) as the total; recorded counts confirm
            ``"200"`` on EB10 and EB02, where ``"TOTAL"`` counted 0 (EB10). A code
            upstream does not have counts 0 too, so a 0 does not prove that a code exists.
        flow_code: Trade flows, one or a list: ``"X"`` exports, ``"M"`` imports,
            ``"RX"`` re-exports, ``"RM"`` re-imports, also ``"DX"``, ``"FM"``, ``"MIP"``,
            ``"MOP"``, ``"XIP"``, ``"XOP"``, ``"MIF"``, ``"XIF"``; e.g. ``["M", "X"]``.
        customs_code: Customs procedures, one or a list: ``"C00"`` the total, ``"C01"``
            clearance for home use, ``"C03"`` outright exportation. Omit for every
            procedure, one row each.
        mot_code: Modes of transport, one or a list: ``"0"`` the total, ``"1000"`` air,
            ``"2100"`` sea, ``"3100"`` railway, ``"3200"`` road, ``"9100"`` pipelines and
            cables. Omit for every mode, one row each.
        aggregate_by: Upstream parameters to aggregate the results over, one or a list
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
    sent = joined(request)
    reads: list[datetime] = []

    async def count() -> int:
        answer = await api.get_count_only(**sent)
        reads.append(answer.retrieved_at)
        return answer.payload.count

    async def fetch() -> list[TradeDataRecord]:
        answer = await api.get(**sent)
        reads.append(answer.retrieved_at)
        return answer.payload.data

    rows, total = await fetch_counted(
        count, fetch, limit=RECORD_LIMIT, empty=[], narrow=NARROW, source=SOURCE
    )
    notes = [COUNTED_NONE] if total == 0 else []
    return Result(data=rows, meta=_meta(request, min(reads), total=total, notes=notes))


@names_codes(freq_code=FREQ_CODES, reporter_code=REPORTERS)
async def get_data_availability_async(
    type_code: str,
    freq_code: str,
    cl_code: str,
    *,
    reporter_code: Codes | None = None,
    period: Codes | None = None,
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
        reporter_code: Reporters, one or a list, as ``list_reporters`` lists them:
            ``"757"`` Switzerland, ``"842"`` USA, ``"276"`` Germany, ``"156"`` China,
            ``[757, 842]``. Omit for every reporter (169 datasets for 2023, annual HS).
        period: Years ``"2023"`` or months ``"202305"``, one or a list, e.g.
            ``["2021", "2022", "2023"]``; unlike ``get_data``, more than 12 are accepted.
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
    answer = await api.get_da(**joined(request))
    meta = ResultMeta(
        source=SOURCE, endpoint=GET_DA, request=request, retrieved_at=answer.retrieved_at
    )
    return Result(data=answer.payload.data, meta=meta)


@names_codes(freq_code=FREQ_CODES, reporter_code=REPORTERS)
async def get_metadata_async(
    type_code: str,
    freq_code: str,
    cl_code: str,
    *,
    reporter_code: Codes | None = None,
    period: Codes | None = None,
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
        reporter_code: Reporters, one or a list, as ``list_reporters`` lists them:
            ``"757"`` Switzerland (38 annual datasets, 1988 onwards), ``"842"`` USA,
            ``"276"`` Germany, ``"156"`` China.
        period: Years ``"2023"`` or months ``"202305"``, one or a list. Omit for every
            period.
    """
    request = validate_datasets(
        type_code, freq_code, cl_code, reporter_code=reporter_code, period=period
    )
    answer = await api.get_metadata(**joined(request))
    meta = ResultMeta(
        source=SOURCE, endpoint=GET_METADATA, request=request, retrieved_at=answer.retrieved_at
    )
    return Result(data=answer.payload.data, meta=meta)


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
    answer = await api.get_live_update()
    meta = ResultMeta(source=SOURCE, endpoint=GET_LIVE_UPDATE, retrieved_at=answer.retrieved_at)
    return Result(data=answer.payload.data, meta=meta)


@names_codes(
    freq_code=FREQ_CODES,
    reporter_code=REPORTERS,
    partner_code=PARTNERS,
    partner2_code=PARTNERS,
    customs_code=CUSTOMS_CODES,
    mot_code=MOT_CODES,
)
async def get_trade_balance_async(
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
) -> Result[list[TradeBalanceRecord]]:
    """Fetch UN Comtrade trade data with a reporter's exports and imports side by side.

    Upstream's ``getTradeBalance``, which its spec marks "EXPERIMENTAL - USE SPARINGLY": one
    keyed call, no count first. Each row, a ``TradeBalanceRecord``, holds a reporter's
    exports (``*_x``) and imports (``*_m``) with one partner, second partner, product code,
    customs procedure, mode of transport and period, and ``primary_value_bal``, which the
    spec defines as "X - M". A query nothing matches returns an empty list. ``meta.total``
    is upstream's ``count``. The query must name ``reporter_code`` or ``partner_code``, and
    ``cmd_code``: upstream offers no count to check a query's size before the call, so a
    broader query is refused before it is sent. Arguments are checked before the call: an
    unknown reporter, partner, customs or transport code raises ``UnknownCode``, naming the
    packaged list and the closest code, another mistake ``InvalidRequestError``.

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
        reporter_code: Reporting areas as UN Comtrade's numeric codes, one or a list,
            e.g. ``"757"`` Switzerland, ``842`` USA, ``"276"`` Germany, ``"156"`` China,
            ``[757, 842]``, as ``list_reporters`` lists them. Some differ from ISO numeric
            codes: Switzerland is 757, not 756. Required unless ``partner_code`` is given.
        period: Years ``"2023"`` (annual) or months ``"202305"`` (monthly), one or a list
            of at most 12, e.g. ``["2021", "2022", "2023"]``.
        partner_code: Partner areas, one or a list, as ``list_partners`` lists them:
            ``"0"`` World (the total over all partners), ``"276"`` Germany. Required
            unless ``reporter_code`` is given; omitted, upstream's default applies, which
            on ``get_data`` is every partner, one row each.
        partner2_code: Second partner (consignment) areas, one or a list, codes of
            ``list_partners``; ``"0"`` is the total.
        cmd_code: Product codes of ``cl_code``, one or a list, as
            ``list_commodities(cl_code)`` lists them: ``"TOTAL"`` for all goods,
            ``"AG2"`` for every chapter, codes such as ``"27"``, ``"0901"`` or
            ``"090111"``, wildcards such as ``"27??"``.
        customs_code: Customs procedures, one or a list: ``"C00"`` the total, ``"C01"``
            clearance for home use, ``"C03"`` outright exportation. Omit for every
            procedure, one row each.
        mot_code: Modes of transport, one or a list: ``"0"`` the total, ``"1000"`` air,
            ``"2100"`` sea, ``"3100"`` railway, ``"3200"`` road, ``"9100"`` pipelines and
            cables. Omit for every mode, one row each.
        aggregate_by: Upstream parameters to aggregate the results over, one or a list
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
    answer = await api.get_trade_balance(**joined(request))
    meta = ResultMeta(
        source=SOURCE,
        endpoint=GET_TRADE_BALANCE,
        request=request,
        retrieved_at=answer.retrieved_at,
        total=answer.payload.count,
    )
    return Result(data=answer.payload.data, meta=meta)


@names_codes(
    freq_code=FREQ_CODES,
    reporter_code=REPORTERS,
    partner_code=PARTNERS,
    flow_code=FLOW_CODES,
)
async def get_bilateral_data_async(
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
) -> Result[BilateralData]:
    """Compare a reporter's trade figures with its partners' mirror figures, row by row.

    Upstream's ``getBilateralData``, which its spec marks "EXPERIMENTAL - USE SPARINGLY":
    one keyed call, "basic trade data joined with mirror partner data". ``data`` is a
    ``BilateralData``, not a list: upstream's ``note``, its ``timestamp_requested`` and the
    rows, ``data.data``, since the note qualifies the mirror values. Each row, a
    ``BilateralDataRecord``, is one reporter, partner, product code, flow and period: the
    reporter's figures beside the mirror, for a reporter's exports the imports its partners
    reported. UN Comtrade's Help Center warns that the mirror depends on the availability of
    other reporters, so a mirror of 0 is no evidence of no trade. ``meta.total`` is
    upstream's ``count``. The query must name ``reporter_code`` or ``partner_code``, and
    ``cmd_code``, since upstream offers no count to check a query's size first.

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
        reporter_code: Reporting areas as UN Comtrade's numeric codes, one or a list,
            e.g. ``"757"`` Switzerland, ``842`` USA, ``"276"`` Germany, ``"156"`` China,
            ``[757, 842]``, as ``list_reporters`` lists them. Some differ from ISO numeric
            codes: Switzerland is 757, not 756. Required unless ``partner_code`` is given.
        period: Years ``"2023"`` (annual) or months ``"202305"`` (monthly), one or a
            list, e.g. ``["2021", "2022", "2023"]``; unlike ``get_data``, more than 12
            are accepted (13 answered 13 rows).
        partner_code: Partner areas, one or a list, as ``list_partners`` lists them:
            ``"842"`` USA, ``"276"`` Germany, ``[842, 276]``, one row each. Required
            unless ``reporter_code`` is given.
        cmd_code: Product codes of ``cl_code``, one or a list, as
            ``list_commodities(cl_code)`` lists them: ``"TOTAL"`` for all goods,
            ``"AG2"`` for every chapter, codes such as ``"27"``, ``"0901"`` or
            ``"090111"``, wildcards such as ``"27??"``.
        flow_code: One trade flow, never a list: ``"X"`` exports or ``"M"`` imports;
            upstream refuses both in one call (``"M,X"``), so call once per flow.
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
    answer = await api.get_bilateral_data(**joined(request))
    meta = ResultMeta(
        source=SOURCE,
        endpoint=GET_BILATERAL_DATA,
        request=request,
        retrieved_at=answer.retrieved_at,
        total=answer.payload.count,
    )
    return Result(data=BilateralData.project(answer.payload), meta=meta)


async def get_comtrade_releases_async() -> Result[list[ComtradeRelease]]:
    """List UN Comtrade's recent data releases: which reporter's dataset came out when.

    Upstream's public ``getComtradeReleases``, "the list of the recent releases, the same
    with the UI live update page" (https://comtradeplus.un.org/RecentReleases). Keyless:
    no key is sent and no daily quota is spent, so the call goes out once the key's daily
    quota is spent too, at the client's pace. One row per release: ``reporter_code`` (UN
    Comtrade's code, e.g. 757 Switzerland), ``dataset_desc`` (e.g. ``"Switzerland CM
    202601"``), ``flag_code`` and ``nr``, whose meanings upstream does not state, and
    ``date_release``, a naive datetime: upstream prints it without a UTC offset and states
    no zone. UN Comtrade keeps one version of each dataset, so a revised release replaces
    the earlier data. ``meta.total`` is upstream's count. No arguments, one call;
    ``get_data_availability`` gives a dataset's first and latest release.
    """
    answer = await api.get_comtrade_releases()
    meta = ResultMeta(
        source=SOURCE,
        endpoint=GET_COMTRADE_RELEASES,
        retrieved_at=answer.retrieved_at,
        total=answer.payload.count,
    )
    return Result(data=answer.payload.data, meta=meta)


@names_codes(freq_code=FREQ_CODES, reporter_code=REPORTERS)
async def get_world_share_async(
    type_code: str,
    freq_code: str,
    *,
    reporter_code: Codes | None = None,
    period: Codes | None = None,
) -> Result[list[WorldShare]]:
    """List each reporter's share of world trade per period, with its release dates.

    Upstream's public ``getWorldShare``, "Get the World Share (including estimates)". The
    spec states neither whether ``world_share`` is a fraction or a percentage nor of which
    trade. A row with ``is_available`` false still carries a ``world_share``, but
    ``first_released`` and ``last_released`` read ``0001-01-01T00:00:00``, upstream's
    placeholder on unavailable datasets, kept as sent; upstream states no meaning for
    ``is_available`` or ``data_count``. The four times are naive, as upstream prints them.
    Keyless: no key is sent and no daily quota is spent. One call, rows in upstream's order;
    a period nobody reported returns an empty list. The MCP tool returns up to 400 rows or
    100 KB, so one period for every reporter reaches an agent whole. Arguments are checked
    before the call: an unknown reporter code raises ``UnknownCode``, another mistake
    ``InvalidRequestError``.

    Args:
        type_code: ``"C"`` goods or ``"S"`` services.
        freq_code: ``"A"`` annual or ``"M"`` monthly.
        reporter_code: Reporters, one or a list, as ``list_reporters`` lists them:
            ``"757"`` Switzerland, ``"842"`` USA, ``"156"`` China, ``[757, 842]``. Omit for
            every reporter (214 rows for 2023, annual goods).
        period: Years ``"2023"`` (annual) or months ``"202301"`` (monthly), one or a
            list, e.g. ``["2022", "2023"]``. The spec also lists ``"recent"``, which is
            accepted alone, but upstream answered it with HTTP 500 on all three tries on
            2026-10-28, with and without a reporter (``ch_recent.json``,
            ``all_reporters_recent.json``): the client makes 4 attempts (3 retries) on a
            5xx and then raises ``UpstreamError``, and what ``"recent"`` selects is
            unknown, so name the periods. Omit for every period (64 annual rows for
            Switzerland, 1962 to 2025).
    """
    request = validate_world_share(type_code, freq_code, reporter_code=reporter_code, period=period)
    answer = await api.get_world_share(**joined(request))
    meta = ResultMeta(
        source=SOURCE,
        endpoint=GET_WORLD_SHARE,
        request=request,
        retrieved_at=answer.retrieved_at,
        total=answer.payload.count,
    )
    return Result(data=answer.payload.data, meta=meta)


async def list_reporters_async(*, search: str | None = None) -> Result[list[Reporter]]:
    """List the reporters UN Comtrade has trade data from, with the codes reporter_code takes.

    Answered from upstream's ``Reporters.json`` as packaged with this version
    (``reference/Reporters.json``), without an upstream call; ``meta.retrieved_at`` is
    when the package fetched it, ``meta.vintage`` is ``None``. 256 rows when packaged,
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


async def list_partners_async(*, search: str | None = None) -> Result[list[PartnerArea]]:
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
    cl_code: str, *, search: str | None = None
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
        for row in fetched.payload
        if matches(search, row.id, row.cmd_code, row.text, row.description_original)
    ]
    meta = ResultMeta(
        source=SOURCE,
        endpoint=f"{REFERENCE}/{cl_code}.json",
        retrieved_at=fetched.retrieved_at,
        request={**request, "search": search},
    )
    return Result(data=rows, meta=meta)


async def list_codes_async(param: str) -> Result[list[CodeValue]]:
    """List the values one UN Comtrade parameter takes, each with upstream's words for it.

    Answered from the list packaged with this version (``reference/<param>.json``),
    without an upstream call; ``meta.endpoint`` is the reference file or the spec the list
    came from, ``meta.retrieved_at`` when the package fetched it, ``meta.vintage`` is
    ``None``. Each row holds the value under the parameter's name in snake_case
    (``flow_code``, ``qty_unit_code``) and upstream's words for it under upstream's names,
    as ``param`` says for each list; a value the package takes from the spec carries none.
    At most 41 rows (``qtyUnitCode``).

    Args:
        param: The parameter, as upstream names it: ``"flowCode"``, ``"customsCode"``,
            ``"motCode"``, ``"clCode"``, ``"typeCode"``, ``"freqCode"``,
            ``"breakdownMode"``, ``"aggregateBy"``, ``"qtyUnitCode"`` or ``"mosCode"``.
            The words are ``text`` from the reference files for ``flowCode``
            (``tradeRegimes.json``), ``customsCode``, ``motCode`` and ``mosCode``;
            ``qty_abbr`` and ``qty_description`` for ``qtyUnitCode``; ``variable`` and
            ``description`` from ``ListofReferences.json`` for ``clCode``; for
            ``typeCode`` and ``freqCode`` ``text`` is the spec's wording (``"C"``
            commodities, ``"A"`` annual). ``"MIF"`` and ``"XIF"`` (``flowCode``), ``"BE"``
            and ``"TM"`` (``clCode``), ``breakdownMode`` and ``aggregateBy`` carry no
            words. ``mosCode`` lists ``ModeOfSupply.json``'s ids, not proven parameter
            values (``data/v1/get`` refused ``"Mode 1"`` and accepted ``"0"`` and ``"1"``).
    """
    request = validate_code_list(param)
    packaged = PackagedList.load(PACKAGE, param)
    rows: list[CodeValue] = list(packaged.parse(PACKAGED_LISTS[param], source=SOURCE))
    return Result(data=rows, meta=packaged.meta(SOURCE, request=request))


async def list_classifications_async(*, category: str | None = None) -> Result[list[Reference]]:
    """List UN Comtrade's reference files, the product classifications among them, by category.

    Answered from upstream's index of the files, ``ListofReferences.json``, as packaged
    with this version (``reference/ListofReferences.json``), without an upstream call;
    ``meta.retrieved_at`` is when the package fetched it, ``meta.vintage`` is ``None``.
    28 rows when packaged, one per file: its ``category`` (``"flow"``, ``"reporter"``,
    ``"cmd:HS"``), the ``variable`` it lists (``"Product [HS 2022]"``), upstream's
    ``description`` and where the file is served, ``fileuri``. A category
    ``cmd:<clCode>`` is a product classification, 19 of them: the ``cl_code`` that
    ``get_data`` and ``list_commodities`` take (``"cmd:H6"`` is ``"H6"``, HS 2022).

    Args:
        category: Keep the row of this category, as upstream writes it, e.g.
            ``"cmd:HS"``, ``"cmd:H6"``, ``"cmd:EB10"``, ``"flow"``, ``"reporter"``,
            ``"qtyunit"``. Omit for every row.
    """
    request = validate_reference_category(category)
    packaged = PackagedList.load(PACKAGE, "ListofReferences")
    rows = [
        row
        for row in packaged.parse(Reference, source=SOURCE)
        if category is None or row.category == category
    ]
    return Result(data=rows, meta=packaged.meta(SOURCE, request=request))


get_bilateral_data = sync(get_bilateral_data_async)
get_comtrade_releases = sync(get_comtrade_releases_async)
count_data = sync(count_data_async)
get_data = sync(get_data_async)
get_data_availability = sync(get_data_availability_async)
get_live_update = sync(get_live_update_async)
get_metadata = sync(get_metadata_async)
get_trade_balance = sync(get_trade_balance_async)
get_world_share = sync(get_world_share_async)
list_classifications = sync(list_classifications_async)
list_codes = sync(list_codes_async)
list_commodities = sync(list_commodities_async)
list_partners = sync(list_partners_async)
list_reporters = sync(list_reporters_async)
