"""Task-shaped functions for UN Comtrade.

The public API (ADR-0001, layer 2). A task composes endpoint wrappers from ``api/``,
resolves pagination and reference lookups, and returns ``Result[T]`` with full
``ResultMeta``. Write the async version, derive the sync one with ``xippios.core.sync``,
and list the sync name in ``__all__``: the MCP server and the HTTP router register
exactly what is named there.

Docstrings are read by agents: one sentence first, then ``Args:`` with examples of
valid values for every parameter. ``/add-endpoint`` walks through the whole recipe.

``meta.endpoint`` is the operation as the Help Center names it (``data/v1/get``), or the
reference file a list comes from (``files/v1/app/reference/Reporters.json``), and
``meta.request`` the task's own arguments that were set, so ``get_data(**meta.request)``
repeats the call.

``meta.published_at`` stays ``None`` on every task. Data rows carry no publication date,
and where upstream does publish release dates it publishes one per reporter and period
(``getDa``, ``getMetadata``, ``getLiveUpdate``); a single value for a whole result would
be a guess. The lists packaged with this version (``list_reporters``, ``list_partners``)
carry the day they were fetched as ``meta.vintage``.
"""

from typing import Any

from xippios.core import Result, ResultMeta, sync

from xippios.comtrade import api
from xippios.comtrade._client import SOURCE
from xippios.comtrade.api.get import ENDPOINT
from xippios.comtrade.api.get_da import ENDPOINT as GET_DA
from xippios.comtrade.api.get_live_update import ENDPOINT as GET_LIVE_UPDATE
from xippios.comtrade.api.get_metadata import ENDPOINT as GET_METADATA
from xippios.comtrade.errors import RECORD_LIMIT, QueryTooLarge
from xippios.comtrade.models import (
    Commodity,
    DataAvailability,
    LiveUpdateRecord,
    MetadataDataset,
    PartnerArea,
    Reporter,
    TradeDataRecord,
)
from xippios.comtrade.params import (
    packaged_table,
    packaged_table_info,
    validate_classification_file,
    validate_datasets,
    validate_get,
)

__all__ = [
    "get_counts",
    "get_data",
    "get_data_availability",
    "get_live_update",
    "get_metadata",
    "list_commodities",
    "list_partners",
    "list_reporters",
]

REFERENCE = "files/v1/app/reference"
"""Where upstream serves the reference files; ``meta.endpoint`` of the list tasks."""


def _meta(request: dict[str, Any]) -> ResultMeta:
    return ResultMeta(source=SOURCE, endpoint=ENDPOINT, request=request)


def _packaged_meta(name: str) -> ResultMeta:
    info = packaged_table_info(name)
    if info is None:  # pragma: no cover - the tables ship with the package
        raise KeyError(name)
    file = info.origin.rsplit("/", 1)[-1]
    return ResultMeta(
        source=SOURCE, endpoint=f"{REFERENCE}/{file}", vintage=info.fetched.isoformat()
    )


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
    on a free key). Arguments are checked before the call, reporter and partner codes
    against the packaged tables; an unknown code raises ``InvalidRequestError`` naming the
    closest valid one (756 names 757, Switzerland).

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
    before any call; an unknown code raises ``InvalidRequestError`` naming the closest
    valid one.

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
    before the call; an unknown code raises ``InvalidRequestError`` naming the closest
    valid one.

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


async def list_reporters_async() -> Result[list[Reporter]]:
    """List the reporters UN Comtrade has trade data from, with the codes reporter_code takes.

    Answered from upstream's ``Reporters.json`` as packaged with this version
    (``reference/Reporters.csv``), without an upstream call; ``meta.vintage`` is the day
    it was fetched. 255 rows when packaged, one per reporter code, current and historical
    (``entry_expired_date`` is set on codes no longer used, such as ``280`` Fed. Rep. of
    Germany until 1990 or ``810`` USSR). Codes are UN Comtrade's, not always ISO
    numeric: ``757`` Switzerland (not 756), ``842`` USA, ``276`` Germany, ``156`` China;
    ``97`` European Union and ``975`` ASEAN are groups (``is_group``). Over MCP the list
    is cut at the result cap (200 rows or 64 KB); the Python and HTTP results are whole.
    """
    return Result(data=packaged_table("Reporters", Reporter), meta=_packaged_meta("Reporters"))


async def list_partners_async() -> Result[list[PartnerArea]]:
    """List the partner areas UN Comtrade records trade with, for partner_code and partner2_code.

    Answered from upstream's ``partnerAreas.json`` as packaged with this version
    (``reference/partnerAreas.csv``), without an upstream call; ``meta.vintage`` is the
    day it was fetched. 310 rows when packaged: ``0`` World (the total over all
    partners), countries in the reporters' code space (``757`` Switzerland, ``842`` USA,
    ``276`` Germany, ``156`` China) and areas that only occur as partners, such as ``899``
    "Areas, nes" or ``756`` Switzerland under its ISO code. Over MCP the list is cut at the
    result cap (200 rows or 64 KB); the Python and HTTP results are whole.
    """
    return Result(
        data=packaged_table("partnerAreas", PartnerArea), meta=_packaged_meta("partnerAreas")
    )


async def list_commodities_async(cl_code: str) -> Result[list[Commodity]]:
    """List the product codes of one UN Comtrade classification, the values cmd_code takes.

    Fetched live from upstream's public classification file ``<cl_code>.json`` (no key, no
    quota) and kept for the life of the process. The lists are large: ``"HS"`` has 8,262
    codes (about 2 MB), each HS edition 6,000 to 7,000, SITC ``"SS"`` 7,863, BEC ``"B5"``
    178, EBOPS ``"EB"`` 423. Every row has ``id`` (the code), ``text`` and ``parent``; the
    goods files add ``is_leaf`` and ``aggr_level`` (0 for ``TOTAL``, then 2, 4 and 6 digits
    for HS). Over MCP the list is cut at the result cap (200 rows or 64 KB), which shows
    the top of the tree only. ``meta.vintage`` stays ``None``: the files carry no release
    identifier.

    Args:
        cl_code: The classification, with a file upstream: ``"HS"`` (all HS editions
            combined), an edition ``"H0"`` (1992) to ``"H6"`` (2022), SITC ``"SS"``
            (combined) or ``"S1"`` to ``"S4"``, BEC ``"B4"`` or ``"B5"``, EBOPS ``"EB"``
            (combined), ``"EB02"``, ``"EB10"`` or ``"EB10S"``. ``"BE"`` and ``"TM"``,
            which ``get_data`` takes, have no file.
    """
    request = validate_classification_file(cl_code)
    rows = await api.reference(f"{cl_code}.json", Commodity)
    meta = ResultMeta(source=SOURCE, endpoint=f"{REFERENCE}/{cl_code}.json", request=request)
    return Result(data=rows, meta=meta)


get_counts = sync(get_counts_async)
get_data = sync(get_data_async)
get_data_availability = sync(get_data_availability_async)
get_live_update = sync(get_live_update_async)
get_metadata = sync(get_metadata_async)
list_commodities = sync(list_commodities_async)
list_partners = sync(list_partners_async)
list_reporters = sync(list_reporters_async)
