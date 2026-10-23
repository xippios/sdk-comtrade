"""Pydantic models mirroring UN Comtrade payloads.

One model per upstream object, subclassing ``xippios.core.UpstreamModel``, with fields
named as upstream names them in snake_case. The upstream spelling is the
``validation_alias``: it is read from upstream, while Python, the MCP tools and the HTTP
routes all show the snake_case name, the same spelling the task parameters use.
Within-source hygiene only: numbers become numbers, upstream enumerations become
``StrEnum``. No cross-source normalisation (ADR-0003): an upstream concept stays an
upstream concept.

Shapes come from ``components.schemas`` in ``docs/upstream/apidocs/comtrade.json`` and from
the recorded fixtures under ``tests/fixtures/get/``. Trade values and quantities are
``Decimal`` (ADR-0008) and travel as JSON numbers through the adapters.
"""

from decimal import Decimal

from pydantic import Field
from xippios.core import UpstreamModel

__all__ = [
    "Reference",
    "ReferenceCode",
    "TradeDataCountResponse",
    "TradeDataRecord",
    "TradeDataResponse",
]


class TradeDataRecord(UpstreamModel):
    """One row of final trade data, ``components.schemas.TradeDataRecord``.

    Every field the schema lists, under its upstream name in snake_case. Codes stay
    codes: ``reporter_code`` and ``partner_code`` are Comtrade's numeric area codes
    (``757`` Switzerland, ``0`` World), ``flow_code`` the trade flow (``"X"``, ``"M"``),
    ``customs_code`` and ``mot_code`` the customs procedure and mode of transport, where
    ``"C00"`` and ``0`` are the totals. The ``*_desc`` and ``*_iso`` fields are ``None``
    in every recorded answer; none of them set ``includeDesc``. ``ref_period_id`` is
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
    freq_code: str | None = Field(validation_alias="freqCode")
    ref_period_id: int = Field(validation_alias="refPeriodId")
    ref_year: int = Field(validation_alias="refYear")
    ref_month: int = Field(validation_alias="refMonth")
    period: str | None
    reporter_code: int = Field(validation_alias="reporterCode")
    reporter_iso: str | None = Field(validation_alias="reporterISO")
    reporter_desc: str | None = Field(validation_alias="reporterDesc")
    flow_code: str | None = Field(validation_alias="flowCode")
    flow_desc: str | None = Field(validation_alias="flowDesc")
    partner_code: int = Field(validation_alias="partnerCode")
    partner_iso: str | None = Field(validation_alias="partnerISO")
    partner_desc: str | None = Field(validation_alias="partnerDesc")
    partner2_code: int = Field(validation_alias="partner2Code")
    partner2_iso: str | None = Field(validation_alias="partner2ISO")
    partner2_desc: str | None = Field(validation_alias="partner2Desc")
    classification_code: str | None = Field(validation_alias="classificationCode")
    classification_search_code: str | None = Field(validation_alias="classificationSearchCode")
    is_original_classification: bool = Field(validation_alias="isOriginalClassification")
    cmd_code: str | None = Field(validation_alias="cmdCode")
    cmd_desc: str | None = Field(validation_alias="cmdDesc")
    aggr_level: int | None = Field(validation_alias="aggrLevel")
    is_leaf: bool | None = Field(validation_alias="isLeaf")
    customs_code: str | None = Field(validation_alias="customsCode")
    customs_desc: str | None = Field(validation_alias="customsDesc")
    mos_code: str | None = Field(validation_alias="mosCode")
    mot_code: int = Field(validation_alias="motCode")
    mot_desc: str | None = Field(validation_alias="motDesc")
    qty_unit_code: int | None = Field(validation_alias="qtyUnitCode")
    qty_unit_abbr: str | None = Field(validation_alias="qtyUnitAbbr")
    qty: Decimal | None
    is_qty_estimated: bool = Field(validation_alias="isQtyEstimated")
    alt_qty_unit_code: int | None = Field(validation_alias="altQtyUnitCode")
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
            ``error`` (observed 2026-10-23: 100,000 rows of a 5,006,385-record query).
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
