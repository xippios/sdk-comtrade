"""Pydantic models mirroring UN Comtrade payloads.

One model per upstream object, subclassing ``xippios.core.UpstreamModel``, with fields
named as upstream names them in snake_case. The upstream spelling is the
``validation_alias``: it is read from upstream, while Python, the MCP tools and the HTTP
routes all show the snake_case name, the same spelling the task parameters use.
Within-source hygiene only: numbers become numbers, and a code stays the text or number
upstream sends. No cross-source normalisation (sdk-core ADR-0028): an upstream concept stays an
upstream concept.

Shapes come from ``components.schemas`` in ``docs/upstream/apidocs/comtrade.json`` and,
for the Tools operations, ``comtradeTools.json`` and, for the public operations,
``public.json``, from the recorded fixtures under ``tests/fixtures/`` and, for the
reference tables, from the public files under ``files/v1/app/reference/``. Trade values and
quantities are ``Decimal`` (sdk-core ADR-0031) and travel as JSON numbers through the
adapters.

A record's reporter, partner, flow, customs, transport, supply, quantity unit and frequency
codes declare the packaged list that names them, ``NamedBy`` of a declaration in
``codes.py`` (sdk-core ADR-0067, decision 6), so every answer that holds the record names
each code of its rows in ``meta.names``, and a code the list lacks is said in
``meta.notes`` rather than refused. A list's own code, whose name stands on its record
beside it, takes no mark. ``classification_code``, ``type_code`` and ``cmd_code`` take
none: their lists hold no words, and ``cmdCode`` has no packaged list.
"""

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    AliasChoices,
    BeforeValidator,
    Field,
)
from xippios.core import NamedBy, UpstreamModel

from xippios.comtrade.codes import (
    CUSTOMS_CODES,
    FLOW_CODES,
    FREQ_CODES,
    MOS_CODES,
    MOT_CODES,
    PARTNERS,
    QTY_UNIT_CODES,
    REPORTERS,
)

__all__ = [
    "AggregateByValue",
    "BilateralData",
    "BilateralDataRecord",
    "BilateralDataResponse",
    "BreakdownModeValue",
    "ClCodeValue",
    "CodeValue",
    "Commodity",
    "ComtradeRelease",
    "ComtradeReleasesResponse",
    "CountryAreaCodeIso",
    "CustomsCodeValue",
    "DataAvailability",
    "DataAvailabilityResponse",
    "FlowCodeValue",
    "FreqCodeValue",
    "LiveUpdateRecord",
    "LiveUpdateResponse",
    "MetadataDataset",
    "MetadataNote",
    "MetadataResponse",
    "MosCodeValue",
    "MotCodeValue",
    "PartnerArea",
    "QtyUnitCodeValue",
    "QuantityUnit",
    "Reference",
    "ReferenceCode",
    "Reporter",
    "TradeBalanceRecord",
    "TradeBalanceResponse",
    "TradeDataCountResponse",
    "TradeDataItem",
    "TradeDataRecord",
    "TradeDataResponse",
    "TypeCodeValue",
    "WorldShare",
    "WorldShareResponse",
]


class TradeDataRecord(UpstreamModel):
    """One row of final trade data, ``components.schemas.TradeDataRecord``.

    Every field the schema lists, under its upstream name in snake_case. Codes stay
    codes: ``reporter_code`` and ``partner_code`` are Comtrade's numeric area codes
    (``757`` Switzerland, ``0`` World), ``flow_code`` the trade flow (``"X"``, ``"M"``),
    ``customs_code`` and ``mot_code`` the customs procedure and mode of transport, where
    ``"C00"`` and ``0`` are the totals. The ``*_desc`` and ``*_iso`` fields, and
    ``aggr_level`` and ``is_leaf``, are ``None`` unless the query sets ``includeDesc``
    (``tests/fixtures/get/ch_exports_2023_include_desc.json``). Parameters named in
    ``aggregateBy`` come back as ``-2`` with ``classification_code`` ``"GG"``. ``ref_period_id`` is
    upstream's integer period key (``20230101``) and ``ref_month`` is ``52`` on annual
    rows, both as sent. Upstream's data items (``docs/upstream/reference/TradeDataItems.json``)
    describe ``primary_value`` as "Primary trade values (taken from CIF or FOB values)",
    ``cifvalue`` and ``fobvalue`` as the trade values in CIF and FOB, and ``net_wgt`` and
    ``gross_wgt`` as net and gross weight; ``qty``/``alt_qty`` are counted in the units
    ``qty_unit_code``/``alt_qty_unit_code`` name. The snapshot states no currency or
    weight unit, so none is assumed here.

    Every field is required. The schema has no ``required`` list; all 47 fields are present
    in every recorded response, so a missing one is a ``ValidationError`` rather than a
    silent ``None``.
    """

    type_code: str | None = Field(validation_alias="typeCode")
    freq_code: Annotated[str, NamedBy(FREQ_CODES)] | None = Field(validation_alias="freqCode")
    ref_period_id: int = Field(validation_alias="refPeriodId")
    ref_year: int = Field(validation_alias="refYear")
    ref_month: int = Field(validation_alias="refMonth")
    period: str | None
    reporter_code: Annotated[int, NamedBy(REPORTERS)] = Field(validation_alias="reporterCode")
    reporter_iso: str | None = Field(validation_alias="reporterISO")
    reporter_desc: str | None = Field(validation_alias="reporterDesc")
    flow_code: Annotated[str, NamedBy(FLOW_CODES)] | None = Field(validation_alias="flowCode")
    flow_desc: str | None = Field(validation_alias="flowDesc")
    partner_code: Annotated[int, NamedBy(PARTNERS)] = Field(validation_alias="partnerCode")
    partner_iso: str | None = Field(validation_alias="partnerISO")
    partner_desc: str | None = Field(validation_alias="partnerDesc")
    partner2_code: Annotated[int, NamedBy(PARTNERS)] = Field(validation_alias="partner2Code")
    partner2_iso: str | None = Field(validation_alias="partner2ISO")
    partner2_desc: str | None = Field(validation_alias="partner2Desc")
    classification_code: str | None = Field(validation_alias="classificationCode")
    classification_search_code: str | None = Field(validation_alias="classificationSearchCode")
    is_original_classification: bool = Field(validation_alias="isOriginalClassification")
    cmd_code: str | None = Field(validation_alias="cmdCode")
    cmd_desc: str | None = Field(validation_alias="cmdDesc")
    aggr_level: int | None = Field(validation_alias="aggrLevel")
    is_leaf: bool | None = Field(validation_alias="isLeaf")
    customs_code: Annotated[str, NamedBy(CUSTOMS_CODES)] | None = Field(
        validation_alias="customsCode"
    )
    customs_desc: str | None = Field(validation_alias="customsDesc")
    mos_code: Annotated[str, NamedBy(MOS_CODES)] | None = Field(validation_alias="mosCode")
    mot_code: Annotated[int, NamedBy(MOT_CODES)] = Field(validation_alias="motCode")
    mot_desc: str | None = Field(validation_alias="motDesc")
    qty_unit_code: Annotated[int, NamedBy(QTY_UNIT_CODES)] | None = Field(
        validation_alias="qtyUnitCode"
    )
    qty_unit_abbr: str | None = Field(validation_alias="qtyUnitAbbr")
    qty: Decimal | None
    is_qty_estimated: bool = Field(validation_alias="isQtyEstimated")
    alt_qty_unit_code: Annotated[int, NamedBy(QTY_UNIT_CODES)] | None = Field(
        validation_alias="altQtyUnitCode"
    )
    alt_qty_unit_abbr: str | None = Field(validation_alias="altQtyUnitAbbr")
    alt_qty: Decimal | None = Field(validation_alias="altQty")
    is_alt_qty_estimated: bool = Field(validation_alias="isAltQtyEstimated")
    net_wgt: Decimal | None = Field(validation_alias="netWgt")
    is_net_wgt_estimated: bool = Field(validation_alias="isNetWgtEstimated")
    gross_wgt: Decimal | None = Field(validation_alias="grossWgt")
    is_gross_wgt_estimated: bool = Field(validation_alias="isGrossWgtEstimated")
    cifvalue: Decimal | None
    fobvalue: Decimal | None
    primary_value: Decimal = Field(validation_alias="primaryValue")
    legacy_estimation_flag: int | None = Field(validation_alias="legacyEstimationFlag")
    is_reported: bool | None = Field(validation_alias="isReported")
    is_aggregate: bool | None = Field(validation_alias="isAggregate")


class TradeDataResponse(UpstreamModel):
    """The envelope of ``data/v1/get``, ``components.schemas.TradeDataResponse``.

    Attributes:
        elapsed_time: Server processing time as upstream words it, e.g. ``"0.93 secs"``.
        count: Number of rows in ``data``. Above the per-call record limit upstream cuts
            ``data`` at the limit and reports the cut length here, with an empty
            ``error`` (``docs/upstream/OBSERVED.md``, "Over 100,000 records the answer is
            cut without a word").
        data: The rows.
        error: Empty string on success.
    """

    elapsed_time: str = Field(validation_alias="elapsedTime")
    count: int
    data: list[TradeDataRecord]
    error: str


class TradeDataCountResponse(UpstreamModel):
    """The envelope of ``data/v1/get`` with ``countOnly=true``.

    Upstream answers with the same keys as ``TradeDataResponse``, but ``data`` is a
    single placeholder record (an object of nulls and zeros, not a list), so it is not
    carried; ``tests/fixtures/get/count_ch_exports_2023.json`` shows the shape.

    Attributes:
        elapsed_time: Server processing time as upstream words it, e.g. ``"1.74 secs"``.
        count: Number of records the same query returns without ``countOnly``.
        error: Empty string on success.
    """

    elapsed_time: str = Field(validation_alias="elapsedTime")
    count: int
    error: str


class TradeBalanceRecord(UpstreamModel):
    """One row of ``tools/v1/getTradeBalance``, ``components.schemas.TradeBalanceRecord``.

    From ``docs/upstream/apidocs/comtradeTools.json``. Exports and imports of one
    reporter, partner, second partner, product code, customs procedure, mode of transport
    and period side by side: each measure of ``TradeDataRecord`` comes twice, ``*_x`` for
    exports and ``*_m`` for imports (``qty_x``/``qty_m``, ``alt_qty_x``/``alt_qty_m``,
    ``net_wgt_x``/``net_wgt_m``, ``gross_wgt_x``/``gross_wgt_m``,
    ``cifvalue_x``/``cifvalue_m``, ``fobvalue_x``/``fobvalue_m``,
    ``primary_value_x``/``primary_value_m``), and the row has no ``flow_code``. The
    schema's description reads "One row of trade balance: X = exports, M = imports,
    primaryValueBal = X - M." ``primary_value_bal`` is passed through as upstream sends
    it, never computed here, and upstream's floating-point arithmetic shows in it:
    ``54550055814.504944`` where ``primary_value_x - primary_value_m`` is
    ``54550055814.505`` (Switzerland and the World, 2023,
    ``tests/fixtures/get_trade_balance/ch_world_2023_include_desc.json``). There
    ``primary_value_x`` equals the export ``primary_value`` ``data/v1/get`` answers for
    the same query (``tests/fixtures/get/ch_exports_2023.json``).

    The other fields read as on ``TradeDataRecord``: the ``*_iso`` and ``*_desc`` fields,
    ``aggr_level`` and ``is_leaf`` are filled with ``includeDesc`` (no answer with rows
    was recorded without it), ``ref_month`` is 52 on
    annual rows, ``customs_code`` ``"C00"`` and ``mot_code`` 0 are the totals. Every field
    the schema lists, under its upstream name in snake_case; all 53 are present in every
    recorded row, so every field is required.
    """

    type_code: str | None = Field(validation_alias="typeCode")
    freq_code: Annotated[str, NamedBy(FREQ_CODES)] | None = Field(validation_alias="freqCode")
    ref_period_id: int = Field(validation_alias="refPeriodId")
    ref_year: int = Field(validation_alias="refYear")
    ref_month: int = Field(validation_alias="refMonth")
    period: str | None
    reporter_code: Annotated[int, NamedBy(REPORTERS)] = Field(validation_alias="reporterCode")
    reporter_iso: str | None = Field(validation_alias="reporterISO")
    reporter_desc: str | None = Field(validation_alias="reporterDesc")
    partner_code: Annotated[int, NamedBy(PARTNERS)] = Field(validation_alias="partnerCode")
    partner_iso: str | None = Field(validation_alias="partnerISO")
    partner_desc: str | None = Field(validation_alias="partnerDesc")
    partner2_code: Annotated[int, NamedBy(PARTNERS)] = Field(validation_alias="partner2Code")
    partner2_iso: str | None = Field(validation_alias="partner2ISO")
    partner2_desc: str | None = Field(validation_alias="partner2Desc")
    classification_code: str | None = Field(validation_alias="classificationCode")
    classification_search_code: str | None = Field(validation_alias="classificationSearchCode")
    is_original_classification: bool = Field(validation_alias="isOriginalClassification")
    cmd_code: str | None = Field(validation_alias="cmdCode")
    cmd_desc: str | None = Field(validation_alias="cmdDesc")
    aggr_level: int | None = Field(validation_alias="aggrLevel")
    is_leaf: bool | None = Field(validation_alias="isLeaf")
    customs_code: Annotated[str, NamedBy(CUSTOMS_CODES)] | None = Field(
        validation_alias="customsCode"
    )
    customs_desc: str | None = Field(validation_alias="customsDesc")
    mos_code: Annotated[str, NamedBy(MOS_CODES)] | None = Field(validation_alias="mosCode")
    mot_code: Annotated[int, NamedBy(MOT_CODES)] = Field(validation_alias="motCode")
    mot_desc: str | None = Field(validation_alias="motDesc")
    qty_unit_code: Annotated[int, NamedBy(QTY_UNIT_CODES)] | None = Field(
        validation_alias="qtyUnitCode"
    )
    qty_unit_abbr: str | None = Field(validation_alias="qtyUnitAbbr")
    qty_x: Decimal | None = Field(validation_alias="qtyX")
    qty_m: Decimal | None = Field(validation_alias="qtyM")
    is_qty_estimated: bool = Field(validation_alias="isQtyEstimated")
    alt_qty_unit_code: Annotated[int, NamedBy(QTY_UNIT_CODES)] | None = Field(
        validation_alias="altQtyUnitCode"
    )
    alt_qty_unit_abbr: str | None = Field(validation_alias="altQtyUnitAbbr")
    alt_qty_x: Decimal | None = Field(validation_alias="altQtyX")
    alt_qty_m: Decimal | None = Field(validation_alias="altQtyM")
    is_alt_qty_estimated: bool = Field(validation_alias="isAltQtyEstimated")
    net_wgt_x: Decimal | None = Field(validation_alias="netWgtX")
    net_wgt_m: Decimal | None = Field(validation_alias="netWgtM")
    is_net_wgt_estimated: bool = Field(validation_alias="isNetWgtEstimated")
    gross_wgt_x: Decimal | None = Field(validation_alias="grossWgtX")
    gross_wgt_m: Decimal | None = Field(validation_alias="grossWgtM")
    is_gross_wgt_estimated: bool = Field(validation_alias="isGrossWgtEstimated")
    cifvalue_x: Decimal | None = Field(validation_alias="cifvalueX")
    cifvalue_m: Decimal | None = Field(validation_alias="cifvalueM")
    fobvalue_x: Decimal | None = Field(validation_alias="fobvalueX")
    fobvalue_m: Decimal | None = Field(validation_alias="fobvalueM")
    primary_value_x: Decimal = Field(validation_alias="primaryValueX")
    primary_value_m: Decimal = Field(validation_alias="primaryValueM")
    primary_value_bal: Decimal = Field(validation_alias="primaryValueBal")
    legacy_estimation_flag: int | None = Field(validation_alias="legacyEstimationFlag")
    is_reported: bool | None = Field(validation_alias="isReported")
    is_aggregate: bool | None = Field(validation_alias="isAggregate")


class TradeBalanceResponse(UpstreamModel):
    """The envelope of ``tools/v1/getTradeBalance``, ``components.schemas.TradeBalanceResponse``.

    Attributes:
        elapsed_time: Server processing time as upstream words it, e.g. ``"3.94 secs"``.
        count: Number of rows in ``data``, "Number of items in data." in the spec; 48
            for 48 rows when recorded.
        data: The rows.
        error: Empty string on success.
    """

    elapsed_time: str = Field(validation_alias="elapsedTime")
    count: int
    data: list[TradeBalanceRecord]
    error: str


class BilateralDataRecord(UpstreamModel):
    """One row of ``tools/v1/getBilateralData``, ``components.schemas.BilateralDataRecord``.

    From ``docs/upstream/apidocs/comtradeTools.json``, whose description reads "One row of
    bilateral data: reported values alongside the partner's mirror values." The values of
    one reporter, partner, product code, flow and period come in three sets: reported
    (``qty``, ``alt_qty``, ``net_wgt``, ``gross_wgt``, ``cifvalue``, ``fobvalue``,
    ``primary_value``), ``mirror_*`` and ``mirror2_*`` (the same measures, with their unit
    codes). The Help Center (``un-comtrade-tools.md``, "Bilateral Data Comparison") calls
    the mirror of a reporter's exports "the import data reported by" its partners and
    warns that "the outcome of the mirror data depends on the availability of other
    reporters rather than no-trade": a mirror of 0 is no evidence of no trade. For
    Switzerland's 2023 exports Afghanistan's ``mirror_primary_value`` is 0 and its mirror
    quantities ``None``, beside a ``note`` that counts 2 partners with a data gap without
    naming them (``tests/fixtures/get_bilateral_data/ch_us_kp_af_exports_2023.json``);
    that Afghanistan is one of them is inferred from the counts (DPRK alone: 1,
    ``ch_kp_exports_2023_include_desc.json``; the USA alone: none,
    ``ch_us_exports_2023.json``), not stated.
    The article also says the tool "only compares the data in classic breakdown mode":
    every recorded row has ``customs_code`` ``"C00"`` and ``mot_code`` 0, and the schema
    has no second-partner code.

    Upstream states the meaning of neither ``primary_value_disc`` nor the ``mirror2_*``
    set. Observed, not stated: in every recorded row ``primary_value_disc`` equals
    ``(mirror_primary_value - primary_value) / primary_value``, a relative difference
    (``-0.1597`` for Switzerland's 2023 exports to the USA, ``-1.0`` where the mirror is
    0), while the arithmetic of the spec's example fits ``primary_value -
    mirror_primary_value``; the ``mirror2_*`` quantities and unit codes are ``None`` and
    ``mirror2_primary_value`` is 0 in every recorded row. Both are passed through as
    upstream sends them, never computed here, and so are the flags
    ``is_extended_partner_code`` and ``is_extended_partner2_code``, whose meaning the
    spec does not state for this operation (``DataAvailability`` has flags of the same
    names for a dataset broken down by that parameter).

    ``includeDesc`` filled no description in the recorded answers: the ``*_iso`` and
    ``*_desc`` fields, ``aggr_level`` and ``is_leaf`` are ``None`` with and without it
    (``ch_us_exports_2023_include_desc.json``, ``ch_us_exports_2023.json``). Every field
    the schema lists, under its upstream name in snake_case; all 65 are present in every
    recorded row, so every field is required.
    """

    type_code: str | None = Field(validation_alias="typeCode")
    freq_code: Annotated[str, NamedBy(FREQ_CODES)] | None = Field(validation_alias="freqCode")
    ref_period_id: int = Field(validation_alias="refPeriodId")
    ref_year: int = Field(validation_alias="refYear")
    ref_month: int = Field(validation_alias="refMonth")
    period: str | None
    reporter_code: Annotated[int, NamedBy(REPORTERS)] = Field(validation_alias="reporterCode")
    reporter_iso: str | None = Field(validation_alias="reporterISO")
    reporter_desc: str | None = Field(validation_alias="reporterDesc")
    flow_code: Annotated[str, NamedBy(FLOW_CODES)] | None = Field(validation_alias="flowCode")
    flow_desc: str | None = Field(validation_alias="flowDesc")
    partner_code: Annotated[int, NamedBy(PARTNERS)] = Field(validation_alias="partnerCode")
    partner_iso: str | None = Field(validation_alias="partnerISO")
    partner_desc: str | None = Field(validation_alias="partnerDesc")
    classification_code: str | None = Field(validation_alias="classificationCode")
    classification_search_code: str | None = Field(validation_alias="classificationSearchCode")
    is_original_classification: bool = Field(validation_alias="isOriginalClassification")
    cmd_code: str | None = Field(validation_alias="cmdCode")
    cmd_desc: str | None = Field(validation_alias="cmdDesc")
    aggr_level: int | None = Field(validation_alias="aggrLevel")
    is_leaf: bool | None = Field(validation_alias="isLeaf")
    customs_code: Annotated[str, NamedBy(CUSTOMS_CODES)] | None = Field(
        validation_alias="customsCode"
    )
    customs_desc: str | None = Field(validation_alias="customsDesc")
    mos_code: Annotated[str, NamedBy(MOS_CODES)] | None = Field(validation_alias="mosCode")
    mot_code: Annotated[int, NamedBy(MOT_CODES)] = Field(validation_alias="motCode")
    mot_desc: str | None = Field(validation_alias="motDesc")
    qty_unit_code: Annotated[int, NamedBy(QTY_UNIT_CODES)] | None = Field(
        validation_alias="qtyUnitCode"
    )
    qty_unit_abbr: str | None = Field(validation_alias="qtyUnitAbbr")
    mirror_qty_unit_code: Annotated[int, NamedBy(QTY_UNIT_CODES)] | None = Field(
        validation_alias="mirrorQtyUnitCode"
    )
    mirror_qty_unit_abbr: str | None = Field(validation_alias="mirrorQtyUnitAbbr")
    mirror2_qty_unit_code: Annotated[int, NamedBy(QTY_UNIT_CODES)] | None = Field(
        validation_alias="mirror2QtyUnitCode"
    )
    mirror2_qty_unit_abbr: str | None = Field(validation_alias="mirror2QtyUnitAbbr")
    qty: Decimal | None
    mirror_qty: Decimal | None = Field(validation_alias="mirrorQty")
    mirror2_qty: Decimal | None = Field(validation_alias="mirror2Qty")
    is_qty_estimated: bool = Field(validation_alias="isQtyEstimated")
    alt_qty_unit_code: Annotated[int, NamedBy(QTY_UNIT_CODES)] | None = Field(
        validation_alias="altQtyUnitCode"
    )
    alt_qty_unit_abbr: str | None = Field(validation_alias="altQtyUnitAbbr")
    alt_qty: Decimal | None = Field(validation_alias="altQty")
    mirror_alt_qty_unit_code: Annotated[int, NamedBy(QTY_UNIT_CODES)] | None = Field(
        validation_alias="mirrorAltQtyUnitCode"
    )
    mirror_alt_qty_unit_abbr: str | None = Field(validation_alias="mirrorAltQtyUnitAbbr")
    mirror2_alt_qty_unit_code: Annotated[int, NamedBy(QTY_UNIT_CODES)] | None = Field(
        validation_alias="mirror2AltQtyUnitCode"
    )
    mirror2_alt_qty_unit_abbr: str | None = Field(validation_alias="mirror2AltQtyUnitAbbr")
    mirror_alt_qty: Decimal | None = Field(validation_alias="mirrorAltQty")
    mirror2_alt_qty: Decimal | None = Field(validation_alias="mirror2AltQty")
    is_alt_qty_estimated: bool = Field(validation_alias="isAltQtyEstimated")
    net_wgt: Decimal | None = Field(validation_alias="netWgt")
    mirror_net_wgt: Decimal | None = Field(validation_alias="mirrorNetWgt")
    mirror2_net_wgt: Decimal | None = Field(validation_alias="mirror2NetWgt")
    is_net_wgt_estimated: bool = Field(validation_alias="isNetWgtEstimated")
    gross_wgt: Decimal | None = Field(validation_alias="grossWgt")
    mirror_gross_wgt: Decimal | None = Field(validation_alias="mirrorGrossWgt")
    mirror2_gross_wgt: Decimal | None = Field(validation_alias="mirror2GrossWgt")
    is_gross_wgt_estimated: bool = Field(validation_alias="isGrossWgtEstimated")
    cifvalue: Decimal | None
    fobvalue: Decimal | None
    primary_value: Decimal = Field(validation_alias="primaryValue")
    is_extended_partner_code: bool | None = Field(validation_alias="isExtendedPartnerCode")
    mirror_primary_value: Decimal = Field(validation_alias="mirrorPrimaryValue")
    primary_value_disc: Decimal = Field(validation_alias="primaryValueDisc")
    mirror2_primary_value: Decimal = Field(validation_alias="mirror2PrimaryValue")
    is_extended_partner2_code: bool | None = Field(validation_alias="isExtendedPartner2Code")
    legacy_estimation_flag: int | None = Field(validation_alias="legacyEstimationFlag")
    is_reported: bool | None = Field(validation_alias="isReported")
    is_aggregate: bool | None = Field(validation_alias="isAggregate")


def _utc(value: datetime | None) -> datetime | None:
    """A time the spec documents as UTC but upstream sends without an offset, made aware."""
    return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value


_UtcTime = Annotated[datetime | None, AfterValidator(_utc)]
"""``timestampRequested``: "UTC, yyyy-MM-dd HH:mm:ss.fff" per the spec, read as UTC."""


class BilateralDataResponse(UpstreamModel):
    """The envelope of ``tools/v1/getBilateralData``, ``components.schemas.BilateralDataResponse``.

    Attributes:
        elapsed_time: Server processing time as upstream words it, e.g. ``"0.81 secs"``.
        timestamp_requested: When upstream took the request. The spec documents it as
            "UTC, yyyy-MM-dd HH:mm:ss.fff" and every recorded answer has that form,
            ``"2026-10-28 16:14:25.593"``, within two seconds of the answer's ``Date``
            header; read as UTC. ``None`` when absent: the spec does not require it.
        note: Upstream's note, "Data-gap note for the requested reporters/partners, if
            any." in the spec; ``None`` when absent. Its wording varies with the answer
            and carries HTML markup as sent: "EXPERIMENTAL: We have good news! There is
            no data gap among the selected partners for bilateral trade comparison. ..."
            where every partner reported, "EXPERIMENTAL: In reviewing the selection
            criteria, we've identified a data gap for 2 partner(s) during specific
            periods, ... <b>As a reminder, ...</b>" where some did not.
        count: Number of rows in ``data``, "Number of items in data." in the spec.
        data: The rows.
        error: Empty string on success.
    """

    elapsed_time: str = Field(validation_alias="elapsedTime")
    timestamp_requested: _UtcTime = Field(default=None, validation_alias="timestampRequested")
    note: str | None = None
    count: int
    data: list[BilateralDataRecord]
    error: str


class BilateralData(UpstreamModel):
    """The rows of ``tools/v1/getBilateralData`` with the note that qualifies them.

    What ``get_bilateral_data`` returns: a projection of ``BilateralDataResponse``
    (``UpstreamModel.project``), the envelope's ``timestampRequested``, ``note`` and
    ``data`` under upstream's names in snake_case. ``count`` goes to ``meta.total``;
    ``elapsedTime`` and ``error`` are left out, as for the other envelopes. The rows keep
    upstream's name, ``data`` (sdk-core ADR-0028), so a result reads ``result.data.data``.

    Attributes:
        timestamp_requested: When upstream took the request, "UTC, yyyy-MM-dd
            HH:mm:ss.fff" per the spec, read as UTC, e.g. ``"2026-10-28 16:15:58.965"``;
            ``None`` when upstream sends none.
        note: Upstream's "Data-gap note for the requested reporters/partners, if any." (the
            spec), as sent, HTML markup included; ``None`` when upstream sends none, which
            no recorded answer did. It qualifies the mirror columns: it counts the partners
            with a data gap and gives their share of world trade, without naming them. For
            Switzerland's 2023 exports Afghanistan's mirror of 0 showed which partner the
            gap was, inferred from the counts (DPRK alone: 1, the USA alone: none), not
            stated; that is no general rule, since the note speaks of a gap "during specific
            periods" and says "the calculation of mirror data may be incomplete", and a
            mirror of 0 can also be a partner that reported no such imports. Its wording
            varies with the answer: "EXPERIMENTAL: We have good news! There is no data gap
            among the selected partners for bilateral trade comparison. This means all
            partners in this selection have reported their data to us." where every partner
            reported (``tests/fixtures/get_bilateral_data/ch_us_exports_2023.json``), and
            "EXPERIMENTAL: In reviewing the selection criteria, we've identified a data gap
            for 2 partner(s) during specific periods, which accounts for approximately
            0.015% of the accumulated world's share. ... <b>As a reminder, users should be
            aware of the data availability when using the data.</b>" where some partners
            have a gap (``ch_us_kp_af_exports_2023.json``).
        data: The rows, one ``BilateralDataRecord`` per reporter, partner, product code,
            flow and period.
    """

    timestamp_requested: _UtcTime = Field(default=None, validation_alias="timestampRequested")
    note: str | None = None
    data: list[BilateralDataRecord]


class ReferenceCode(UpstreamModel):
    """One entry of a code list such as ``tradeRegimes.json``: ``{"id": "X", "text": "Export"}``.

    Attributes:
        id: The code as a query parameter takes it.
        text: Upstream's label for it.
    """

    id: str
    text: str


class Reference(UpstreamModel):
    """One entry of ``ListofReferences.json``: a reference file and what it lists.

    Attributes:
        category: Upstream's category key, e.g. ``"flow"``, ``"reporter"``, ``"cmd:HS"``;
            for product classifications the part after ``cmd:`` is the ``clCode``.
        variable: The variable the file lists, e.g. ``"Trade Flow"``.
        description: Upstream's description.
        fileuri: Where the file is served, under ``files/v1/app/reference/``.
    """

    category: str
    variable: str
    description: str
    fileuri: str


class QuantityUnit(UpstreamModel):
    """One entry of ``QuantityUnits.json``, the units of ``qty`` and ``altQty``.

    Attributes:
        qty_code: The unit's code, as ``qtyUnitCode``/``altQtyUnitCode`` carry it on trade
            rows; ``-1`` is "Not available or not specified or no quantity."
        qty_abbr: Upstream's abbreviation, e.g. ``"kg"``.
        qty_description: Upstream's description, e.g. ``"Weight in kilograms"``.
    """

    qty_code: int = Field(validation_alias="qtyCode")
    qty_abbr: str = Field(validation_alias="qtyAbbr")
    qty_description: str = Field(validation_alias="qtyDescription")


class TypeCodeValue(UpstreamModel):
    """One value of ``typeCode``, a member of the spec's enum for the parameter, without words.

    UN Comtrade lists no reference file of ``typeCode``, so no value carries upstream's
    words, as no value of ``breakdownMode`` or ``aggregateBy`` does.

    Attributes:
        type_code: The value as ``type_code`` takes it, ``"C"`` or ``"S"``.
    """

    type_code: str = Field(validation_alias="typeCode")


class FreqCodeValue(UpstreamModel):
    """One value of ``freqCode``, a row of ``Frequency.json`` under the parameter's name.

    Attributes:
        freq_code: The frequency as ``freq_code`` takes it, e.g. ``"A"``; the file holds
            ``A`` and ``M``, the values of the spec's enum.
        text: Upstream's label for it in ``Frequency.json``.
    """

    freq_code: str = Field(validation_alias="freqCode")
    text: str


class ClCodeValue(UpstreamModel):
    """One value of ``clCode``, with its entry in ``ListofReferences.json`` where it has one.

    Attributes:
        cl_code: The classification as ``cl_code`` takes it, e.g. ``"H6"``.
        variable: The index's ``variable`` for ``cmd:<clCode>``, e.g. ``"Product [HS
            2022]"``; ``None`` for a value the package takes from the spec (``BE``,
            ``TM``), which the index does not list.
        description: The index's ``description``, e.g. "The classification of HS 2022",
            followed by an en dash and "goods"; ``None`` where ``variable`` is.
    """

    cl_code: str = Field(validation_alias="clCode")
    variable: str | None = None
    description: str | None = None


class FlowCodeValue(UpstreamModel):
    """One value of ``flowCode``, with its ``text`` in ``tradeRegimes.json`` where it has one.

    Attributes:
        flow_code: The trade flow as ``flow_code`` takes it, e.g. ``"X"``.
        text: Upstream's label, e.g. ``"Export"``; ``None`` for ``MIF`` and ``XIF``, which
            the package takes from the spec's ``flowCode`` description, a list of values
            without wording.
    """

    flow_code: str = Field(validation_alias="flowCode")
    text: str | None = None


class CustomsCodeValue(UpstreamModel):
    """One value of ``customsCode``, a row of ``CustomsCodes.json`` under the parameter's name.

    Attributes:
        customs_code: The customs procedure as ``customs_code`` takes it, e.g. ``"C00"``.
        text: Upstream's label, e.g. ``"TOTAL customs procedure codes"``.
    """

    customs_code: str = Field(validation_alias="customsCode")
    text: str


class MotCodeValue(UpstreamModel):
    """One value of ``motCode``, a row of ``ModeOfTransportCodes.json`` under the parameter's name.

    Attributes:
        mot_code: The mode of transport as ``mot_code`` takes it, e.g. ``"2100"``.
        text: Upstream's label, e.g. ``"Sea"``.
    """

    mot_code: str = Field(validation_alias="motCode")
    text: str


class AggregateByValue(UpstreamModel):
    """One value of ``aggregateBy``, a name the spec's description of the parameter lists.

    Attributes:
        aggregate_by: The name as ``aggregate_by`` takes it, e.g. ``"cmdCode"``.
    """

    aggregate_by: str = Field(validation_alias="aggregateBy")


class BreakdownModeValue(UpstreamModel):
    """One value of ``breakdownMode``, a member of the spec's enum for the parameter.

    Attributes:
        breakdown_mode: The value as ``breakdown_mode`` takes it, e.g. ``"classic"``.
    """

    breakdown_mode: str = Field(validation_alias="breakdownMode")


class MosCodeValue(UpstreamModel):
    """One id of ``ModeOfSupply.json`` with its ``text``, under the name ``mosCode``.

    Attributes:
        mos_code: The file's id, e.g. ``"0"`` or ``"Mode 1"``; ``data/v1/get`` refused
            ``"Mode 1"`` and accepted ``"0"`` and ``"1"``, so the ids are not proven
            parameter values.
        text: Upstream's label, e.g. ``"Cross-border"``.
    """

    mos_code: str = Field(validation_alias="mosCode")
    text: str


class QtyUnitCodeValue(UpstreamModel):
    """One unit of ``QuantityUnits.json``: its ``qtyCode`` under the name ``qtyUnitCode``.

    Attributes:
        qty_unit_code: The code as ``qty_unit_code`` and ``alt_qty_unit_code`` carry it on
            trade rows, as text, e.g. ``"8"``; ``"-1"`` is no quantity.
        qty_abbr: Upstream's abbreviation, e.g. ``"kg"``.
        qty_description: Upstream's description, e.g. ``"Weight in kilograms"``.
    """

    qty_unit_code: str = Field(validation_alias="qtyUnitCode")
    qty_abbr: str = Field(validation_alias="qtyAbbr")
    qty_description: str = Field(validation_alias="qtyDescription")


CodeValue = (
    TypeCodeValue
    | FreqCodeValue
    | ClCodeValue
    | FlowCodeValue
    | CustomsCodeValue
    | MotCodeValue
    | AggregateByValue
    | BreakdownModeValue
    | MosCodeValue
    | QtyUnitCodeValue
)
"""A record of one packaged list, as ``list_codes`` returns it; ``params.PACKAGED_LISTS``
names the model of each list."""


class Reporter(UpstreamModel):
    """One reporter area of ``Reporters.json``: a country or area that reports trade.

    Codes are UN Comtrade's own, close to but not always ISO 3166 numeric: Switzerland is
    757 here, 756 in ISO. Every column of the file, in its order, under its upstream name
    in snake_case. ``entry_effective_date`` and ``entry_expired_date`` bound the period
    the code is used for (``entry_expired_date`` is ``None`` for codes still in use);
    ``is_group`` marks groups such as 97 European Union. Dates carry no UTC offset
    upstream and are kept naive.
    """

    id: int
    text: str
    reporter_code: int = Field(validation_alias="reporterCode")
    reporter_desc: str = Field(validation_alias="reporterDesc")
    reporter_note: str | None = Field(default=None, validation_alias="reporterNote")
    reporter_code_iso_alpha2: str | None = Field(
        default=None, validation_alias="reporterCodeIsoAlpha2"
    )
    reporter_code_iso_alpha3: str = Field(validation_alias="reporterCodeIsoAlpha3")
    entry_effective_date: datetime = Field(validation_alias="entryEffectiveDate")
    entry_expired_date: datetime | None = Field(default=None, validation_alias="entryExpiredDate")
    is_group: bool = Field(validation_alias="isGroup")


class PartnerArea(UpstreamModel):
    """One partner area of ``partnerAreas.json``: a country, area or group traded with.

    Every column of the file, in its order, under its upstream name in snake_case;
    upstream spells three of them with a capital first letter (``PartnerCode``,
    ``PartnerDesc``, ``PartnerCodeIsoAlpha2``/``3``). Partner 0 is World, a group. The
    codes are the reporters' code space: a code in both files names the same area with
    the same ISO alpha-3, but the sets differ (World 0, and areas such as 756, are
    partners only; 97 European Union and 975 ASEAN are reporters only).
    """

    id: int
    text: str
    partner_code: int = Field(validation_alias="PartnerCode")
    partner_desc: str = Field(validation_alias="PartnerDesc")
    partner_note: str | None = Field(default=None, validation_alias="partnerNote")
    partner_code_iso_alpha2: str | None = Field(
        default=None, validation_alias="PartnerCodeIsoAlpha2"
    )
    partner_code_iso_alpha3: str = Field(validation_alias="PartnerCodeIsoAlpha3")
    entry_effective_date: datetime = Field(validation_alias="entryEffectiveDate")
    entry_expired_date: datetime | None = Field(default=None, validation_alias="entryExpiredDate")
    is_group: bool = Field(validation_alias="isGroup")


class CountryAreaCodeIso(UpstreamModel):
    """One row of ``country_area_code_iso.json``, UN Comtrade's area code to ISO alpha-3.

    Covers every reporter and partner code (312 rows when packaged). Some ``iso3`` values
    are UN Comtrade's own, e.g. ``"W00"`` for 0 World, ``"_AC"`` for 472.
    """

    country_area_code: int
    iso3: str


class TradeDataItem(UpstreamModel):
    """One data item of ``TradeDataItems.json``: a column of the trade data and where it occurs.

    Attributes:
        data_item: The column as upstream spells it, e.g. ``"primaryValue"``.
        description: Upstream's description.
        is_in_data_api_commodity: Present in the data API for goods.
        is_in_data_api_services: Present in the data API for services.
        is_in_bulk_file_final: Present in the final-data bulk files.
        is_in_bulk_file_tariffline: Present in the tariff-line bulk files.
    """

    data_item: str = Field(validation_alias="dataItem")
    description: str
    is_in_data_api_commodity: bool = Field(validation_alias="isInDataAPICommodity")
    is_in_data_api_services: bool = Field(validation_alias="isInDataAPIServices")
    is_in_bulk_file_final: bool = Field(validation_alias="isInBulkFileFinal")
    is_in_bulk_file_tariffline: bool = Field(validation_alias="isInBulkFileTariffline")


class Commodity(UpstreamModel):
    """One product code of a classification file such as ``HS.json`` (``cmdCode`` values).

    The files differ in their columns, so only ``id``, ``text`` and ``parent`` are in every
    one: ``isLeaf`` and the aggregation level are missing from the EBOPS files,
    ``standardUnitAbbr`` is only in the HS files, ``cmdCode`` and ``descriptionOriginal``
    only in ``SS.json``. The aggregation level is spelt ``aggrLevel`` in ``HS.json`` (as
    ``TradeDataItems.json`` names the data item) and ``aggrlevel`` in the other files;
    both are read into ``aggr_level``.

    Attributes:
        id: The code as ``cmd_code`` takes it, e.g. ``"TOTAL"``, ``"09"``, ``"0901"``,
            ``"090111"``; the EBOPS files label ``"200"`` (EB, EB02, EB10) or ``"S"``
            (EB10S) as the services total (``get_data`` counts confirm ``"200"`` on EB10
            and EB02 only).
        text: Upstream's label, e.g. ``"0901 - Coffee, whether or not roasted or ..."``.
        parent: The ``id`` of the parent code; ``"#"`` for a top-level code.
        is_leaf: ``True`` for the most detailed codes (upstream sends ``"1"``/``"0"``).
        aggr_level: Aggregation level: 0 for ``TOTAL``, then 2, 4, 6 digits for HS.
        standard_unit_abbr: Standard unit of quantity, e.g. ``"kg"``; ``"n/a"`` above
            the 6-digit level and on some 6-digit codes.
        cmd_code: ``SS.json`` only: the code in the original SITC revision.
        description_original: ``SS.json`` only: the label in the original revision.
    """

    id: str
    text: str
    parent: str
    is_leaf: bool | None = Field(default=None, validation_alias="isLeaf")
    aggr_level: int | None = Field(
        default=None, validation_alias=AliasChoices("aggrLevel", "aggrlevel")
    )
    standard_unit_abbr: str | None = Field(default=None, validation_alias="standardUnitAbbr")
    cmd_code: str | None = Field(default=None, validation_alias="cmdCode")
    description_original: str | None = Field(default=None, validation_alias="descriptionOriginal")


class DataAvailability(UpstreamModel):
    """One final-data dataset of ``data/v1/getDa``, ``components.schemas.DataAvailability``.

    A dataset is one reporter's data for one period in the classification it reported.
    Every field of the schema under its upstream name in snake_case, all present in every
    recorded row. ``first_released`` and ``last_released`` are the dataset's first and
    latest publication; upstream sends them without a UTC offset and with seven
    fractional digits (``2024-02-02T04:52:35.2166667``), so they are naive and keep
    microseconds. The ``is_extended_*`` flags say whether the dataset breaks the data down
    by that parameter (Switzerland 2023: partner, product, customs procedure and mode of
    transport, not flow or second partner).

    Attributes:
        dataset_code: Upstream's dataset identifier, e.g. ``20757202301202100``; beyond
            JavaScript's safe-integer range, exact in Python.
        total_records: Records the dataset holds in ``data/v1/get``.
        dataset_checksum: Upstream's checksum of the dataset.
    """

    dataset_code: int = Field(validation_alias="datasetCode")
    type_code: str | None = Field(validation_alias="typeCode")
    freq_code: Annotated[str, NamedBy(FREQ_CODES)] | None = Field(validation_alias="freqCode")
    period: int
    reporter_code: Annotated[int, NamedBy(REPORTERS)] = Field(validation_alias="reporterCode")
    reporter_iso: str | None = Field(validation_alias="reporterISO")
    reporter_desc: str | None = Field(validation_alias="reporterDesc")
    classification_code: str | None = Field(validation_alias="classificationCode")
    classification_search_code: str | None = Field(validation_alias="classificationSearchCode")
    is_original_classification: bool = Field(validation_alias="isOriginalClassification")
    is_extended_flow_code: bool = Field(validation_alias="isExtendedFlowCode")
    is_extended_partner_code: bool = Field(validation_alias="isExtendedPartnerCode")
    is_extended_partner2_code: bool = Field(validation_alias="isExtendedPartner2Code")
    is_extended_cmd_code: bool = Field(validation_alias="isExtendedCmdCode")
    is_extended_customs_code: bool = Field(validation_alias="isExtendedCustomsCode")
    is_extended_mot_code: bool = Field(validation_alias="isExtendedMotCode")
    total_records: int = Field(validation_alias="totalRecords")
    dataset_checksum: int = Field(validation_alias="datasetChecksum")
    first_released: datetime = Field(validation_alias="firstReleased")
    last_released: datetime = Field(validation_alias="lastReleased")


class DataAvailabilityResponse(UpstreamModel):
    """The envelope of ``data/v1/getDa``, ``components.schemas.DataAvailabilityResponse``.

    Attributes:
        elapsed_time: Server processing time as upstream words it, e.g. ``"0.18 secs"``.
        count: Number of rows in ``data``.
        data: The datasets.
        error: Empty string on success.
    """

    elapsed_time: str = Field(validation_alias="elapsedTime")
    count: int
    data: list[DataAvailability]
    error: str


class MetadataNote(UpstreamModel):
    """One publication note of a dataset, ``components.schemas.MetadataNote``.

    A dataset gets one note per publication: "New Data" when first published, "Revised
    Data" for each revision, each with its ``publication_date``. Every field of the schema
    under its upstream name in snake_case. ``publication_date`` comes without a UTC offset
    (naive; seven fractional digits are cut to microseconds); ``publication_date_short``
    is its day. The conversion factors are sent as strings of digits and read as
    ``Decimal``; ``currency`` is the currency of the reported values (``"CHF"`` or
    ``"USD"`` among Switzerland's notes).

    Attributes:
        import_conv_factor: Upstream's conversion factor for imports, e.g. ``1.11256298``.
        export_conv_factor: Upstream's conversion factor for exports.
        trade_system: ``"General"`` or ``"Special"``.
        import_valuation: Valuation of imports, e.g. ``"CIF"``.
        export_valuation: Valuation of exports, e.g. ``"FOB"``.
        import_partner_country: Partner attribution for imports, e.g. ``"Origin"``.
        export_partner_country: Partner attribution for exports, e.g. ``"Last Known
            Destination"``.
        publication_note: Upstream's note, e.g. "New Data: Data for this period is
            published for the first time; ...".
    """

    dataset_code: int = Field(validation_alias="datasetCode")
    type_code: str | None = Field(validation_alias="typeCode")
    freq_code: Annotated[str, NamedBy(FREQ_CODES)] | None = Field(validation_alias="freqCode")
    period: int
    reporter_code: Annotated[int, NamedBy(REPORTERS)] = Field(validation_alias="reporterCode")
    reporter_description: str | None = Field(validation_alias="reporterDescription")
    currency: str | None
    import_conv_factor: Decimal | None = Field(validation_alias="importConvFactor")
    export_conv_factor: Decimal | None = Field(validation_alias="exportConvFactor")
    trade_system: str | None = Field(validation_alias="tradeSystem")
    classification_code: str | None = Field(validation_alias="classificationCode")
    import_valuation: str | None = Field(validation_alias="importValuation")
    export_valuation: str | None = Field(validation_alias="exportValuation")
    import_partner_country: str | None = Field(validation_alias="importPartnerCountry")
    export_partner_country: str | None = Field(validation_alias="exportPartnerCountry")
    import_partner2_country: str | None = Field(validation_alias="importPartner2Country")
    export_partner2_country: str | None = Field(validation_alias="exportPartner2Country")
    publication_note: str | None = Field(validation_alias="publicationNote")
    publication_date: datetime = Field(validation_alias="publicationDate")
    publication_date_short: date | None = Field(validation_alias="publicationDateShort")


class MetadataDataset(UpstreamModel):
    """A dataset's publication notes, ``components.schemas.MetadataDataset``.

    Attributes:
        reporter_code: The reporter, e.g. ``757``.
        period: The period, e.g. ``2023``.
        dataset_code: The dataset, as ``DataAvailability.dataset_code`` names it.
        notes: One note per publication, first publication first.
    """

    reporter_code: Annotated[int, NamedBy(REPORTERS)] = Field(validation_alias="reporterCode")
    period: int
    type_code: str | None = Field(validation_alias="typeCode")
    freq_code: Annotated[str, NamedBy(FREQ_CODES)] | None = Field(validation_alias="freqCode")
    dataset_code: int = Field(validation_alias="datasetCode")
    notes: list[MetadataNote]


class MetadataResponse(UpstreamModel):
    """The envelope of ``data/v1/getMetadata``, ``components.schemas.MetadataResponse``.

    Attributes:
        elapsed_time: Server processing time as upstream words it, e.g. ``"0.02 secs"``.
        count: Number of datasets in ``data``.
        data: The datasets with their notes.
        error: Empty string on success.
    """

    elapsed_time: str = Field(validation_alias="elapsedTime")
    count: int
    data: list[MetadataDataset]
    error: str


_MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "January", "February", "March", "April", "May", "June", "July", "August",
            "September", "October", "November", "December",
        ),
        start=1,
    )
}  # fmt: skip
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_LONG_DATE = re.compile(r"([A-Za-z]+), ([A-Za-z]+) (\d{1,2}), (\d{4})")
_US_DATETIME = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4}) (\d{1,2}):(\d{2}):(\d{2}) ([AP]M)")


def _long_date(value: Any) -> Any:
    """``"Thursday, October 22, 2026"``, getLiveUpdate's ``lastUpdated``, as a date.

    English names from fixed tables, so the process locale plays no part. A text that is
    no such date, or whose weekday does not fit it, fails the read, so no time that
    upstream sent turns into ``None``.

    Raises:
        ValueError: The text names no day, or a weekday that is not the day's.
    """
    if not isinstance(value, str):
        return value
    match = _LONG_DATE.fullmatch(value.strip())
    if match is None or match[2] not in _MONTHS:
        raise ValueError(f"{value!r} is no date as 'Thursday, October 22, 2026'")
    day = date(int(match[4]), _MONTHS[match[2]], int(match[3]))
    if _WEEKDAYS[day.weekday()] != match[1]:
        raise ValueError(f"{value!r} names {match[1]}, and the day is a {_WEEKDAYS[day.weekday()]}")
    return day


def _us_datetime(value: Any) -> Any:
    """``"10/22/2026 11:18:33 PM"``, getLiveUpdate's ``queuedAt``, as a naive datetime.

    Month first, 12-hour clock with ``AM``/``PM`` read by hand, so the process locale
    plays no part. A text that is no such time fails the read.

    Raises:
        ValueError: The text is no time as ``"10/22/2026 11:18:33 PM"``.
    """
    if not isinstance(value, str):
        return value
    match = _US_DATETIME.fullmatch(value.strip())
    if match is None or not 1 <= int(match[4]) <= 12:
        raise ValueError(f"{value!r} is no time as '10/22/2026 11:18:33 PM'")
    month, day, year, hour, minute, second = (int(part) for part in match.groups()[:6])
    hour = hour % 12 + (12 if match[7] == "PM" else 0)
    return datetime(year, month, day, hour, minute, second)


class LiveUpdateRecord(UpstreamModel):
    """One release in upstream's release pipeline, ``components.schemas.LiveUpdateRecord``.

    Every field of the schema under its upstream name in snake_case, typed from the
    recorded answer (``tests/fixtures/get_live_update/latest.json``); there is no
    ``publishedDate``. That answer holds only ``"Released"``/``"Success"`` rows, so the
    shapes of the other release states are unseen. The four times come in three formats,
    read without the process locale and strictly: a time that none of them reads fails the
    call with core's ``ValidationError``, which names the operation, so no time that
    upstream sent turns into ``None``:

    - ``started_at``, ``completed_at``: ``"2026-10-22 21:27:39Z"``, UTC, timezone-aware.
      Upstream's ``completed_at`` is often earlier than ``started_at`` (it equals the next
      row's ``started_at``); both are kept as sent.
    - ``last_updated``: ``"Thursday, October 22, 2026"``, a date.
    - ``queued_at``: ``"10/22/2026 11:18:33 PM"``, no offset, kept naive. It reads about
      two hours after ``started_at``, so it is probably a local time; which zone is not
      documented.

    Attributes:
        size: File size in bytes.
        status: Pipeline status, e.g. ``"Success"``.
        release_status: ``"Released"``, ``"In progress"``, ``"Failed"`` or ``"Coming
            soon"`` per the spec.
        reporter_code: The reporter as upstream sends it here, a string: ``"842"``.
        period: ``YYYY`` or ``YYYYMM``, e.g. ``202604``.
    """

    size: int
    started_at: datetime | None = Field(validation_alias="startedAt")
    completed_at: datetime | None = Field(validation_alias="completedAt")
    status: str | None
    last_updated: Annotated[date | None, BeforeValidator(_long_date)] = Field(
        validation_alias="lastUpdated"
    )
    queued_at: Annotated[datetime | None, BeforeValidator(_us_datetime)] = Field(
        validation_alias="queuedAt"
    )
    release_status: str | None = Field(validation_alias="releaseStatus")
    reporter_code: Annotated[str, NamedBy(REPORTERS)] | None = Field(
        validation_alias="reporterCode"
    )
    freq_code: Annotated[str, NamedBy(FREQ_CODES)] | None = Field(validation_alias="freqCode")
    type_code: str | None = Field(validation_alias="typeCode")
    classification_code: str | None = Field(validation_alias="classificationCode")
    period: int | None


class LiveUpdateResponse(UpstreamModel):
    """The envelope of ``data/v1/getLiveUpdate``, ``components.schemas.LiveUpdateResponse``.

    Attributes:
        elapsed_time: Server processing time as upstream words it, e.g. ``"0.5870672 secs"``.
        count: Not the number of rows here, despite the spec: 174 with 50 rows in ``data``
            (``docs/upstream/OBSERVED.md``, "``getLiveUpdate``: 50 rows and a ``count`` of
            174").
        data: The 50 most recent releases.
        error: Empty string on success.
    """

    elapsed_time: str = Field(validation_alias="elapsedTime")
    count: int
    data: list[LiveUpdateRecord]
    error: str


class ComtradeRelease(UpstreamModel):
    """One release of ``public/v1/getComtradeReleases``, ``components.schemas.ComtradeRelease``.

    "A recent or upcoming dataset release." (``public.json``). Every field of the schema
    under its upstream name in snake_case, typed from the recorded answer
    (``docs/upstream/OBSERVED.md``, "``getComtradeReleases``: the recent releases, newest
    first"). The spec states neither what ``nr`` nor what ``flag_code`` means; the recorded
    values are ``"N"`` and ``"R"`` for ``nr`` and two letters for ``flag_code`` (``"CH"`` on
    reporter 757).

    Attributes:
        reporter_code: UN Comtrade's reporter code, e.g. ``757`` Switzerland.
        flag_code: As upstream sends it, e.g. ``"CH"``.
        dataset_desc: The dataset as upstream labels it, e.g. ``"Switzerland CM 202601"``.
        nr: As upstream sends it, ``"N"`` or ``"R"`` when recorded.
        date_release: The release time. Upstream prints it without a UTC offset ("ISO
            8601 date-time without a UTC offset") and states no zone, so it is naive and
            no zone is attached; every recorded value is a midnight.
    """

    reporter_code: Annotated[int, NamedBy(REPORTERS)] = Field(validation_alias="reporterCode")
    flag_code: str | None = Field(validation_alias="flagCode")
    dataset_desc: str | None = Field(validation_alias="datasetDesc")
    nr: str | None
    date_release: datetime = Field(validation_alias="dateRelease")


class ComtradeReleasesResponse(UpstreamModel):
    """The envelope of ``public/v1/getComtradeReleases``, ``ComtradeReleasesResponse``.

    Attributes:
        elapsed_time: Server processing time as upstream words it, e.g. ``"0.86 secs"``.
        count: "Number of items in data." (the spec); 38 with 38 rows when recorded.
        data: The releases, newest first when recorded.
        error: Empty string on success.
    """

    elapsed_time: str = Field(validation_alias="elapsedTime")
    count: int
    data: list[ComtradeRelease]
    error: str


class WorldShare(UpstreamModel):
    """One row of ``public/v1/getWorldShare``, ``components.schemas.WorldShare``.

    "A reporter's share of world trade for one period." (``public.json``). Every field of
    the schema under its upstream name in snake_case, all present in every recorded row
    (``docs/upstream/OBSERVED.md``, under "The public operations"). ``month`` is 52 on
    annual rows, as on the trade data rows. The four times are printed without a UTC offset
    and upstream states no zone, so they are naive and no zone is attached; seven fractional
    digits are cut to microseconds (``2024-02-02T04:52:35.2166667`` reads ``.216666``). A
    row with
    ``is_available`` false carries ``0001-01-01T00:00:00`` in ``first_released`` and
    ``last_released``, upstream's placeholder on unavailable datasets (47 of the 214 rows
    in ``get_world_share/all_reporters_2023.json``): it is kept as sent, a naive datetime,
    and never turned into ``None``.

    Attributes:
        dataset_desc: The dataset as upstream labels it, e.g. ``"Switzerland CA 2023"``,
            ``"Switzerland CM 2023-01"``.
        reporter_code: UN Comtrade's reporter code, e.g. ``757`` Switzerland.
        world_share: "the World Share (including estimates)" (the spec), a double read as
            ``Decimal`` like the package's other upstream numbers (sdk-core ADR-0031); the
            spec states neither whether it is a fraction or a percentage nor of which trade.
            The 214 values recorded for 2023 (annual goods, every reporter) sum to 1.0.
        is_available: As upstream sends it; the spec states no meaning.
        data_count: As upstream sends it; 1 on every recorded row.
        first_released: Naive, no zone stated; ``0001-01-01T00:00:00``, upstream's
            placeholder, where ``is_available`` is false.
        last_released: Naive, no zone stated; as ``first_released``.
        created: Naive, no zone stated.
        updated: Naive, no zone stated.
    """

    type_code: str | None = Field(validation_alias="typeCode")
    freq_code: Annotated[str, NamedBy(FREQ_CODES)] | None = Field(validation_alias="freqCode")
    period: int
    year: int
    month: int
    dataset_desc: str | None = Field(validation_alias="datasetDesc")
    reporter_code: Annotated[int, NamedBy(REPORTERS)] = Field(validation_alias="reporterCode")
    reporter_iso: str | None = Field(validation_alias="reporterISO")
    reporter_desc: str | None = Field(validation_alias="reporterDesc")
    world_share: Decimal | None = Field(validation_alias="worldShare")
    is_available: bool = Field(validation_alias="isAvailable")
    data_count: int = Field(validation_alias="dataCount")
    first_released: datetime = Field(validation_alias="firstReleased")
    last_released: datetime = Field(validation_alias="lastReleased")
    created: datetime
    updated: datetime


class WorldShareResponse(UpstreamModel):
    """The envelope of ``public/v1/getWorldShare``, ``components.schemas.WorldShareResponse``.

    Attributes:
        elapsed_time: Server processing time as upstream words it, e.g. ``"0.22 secs"``.
        count: "Number of items in data." (the spec); equal to the rows in every recorded
            answer.
        data: The rows.
        error: Empty string on success.
    """

    elapsed_time: str = Field(validation_alias="elapsedTime")
    count: int
    data: list[WorldShare]
    error: str
