"""Pydantic models mirroring UN Comtrade payloads.

One model per upstream object, subclassing ``xippios.core.UpstreamModel``, with fields
named as upstream names them in snake_case. The upstream spelling is the
``validation_alias``: it is read from upstream, while Python, the MCP tools and the HTTP
routes all show the snake_case name, the same spelling the task parameters use.
Within-source hygiene only: numbers become numbers, upstream enumerations become
``StrEnum``. No cross-source normalisation (ADR-0003): an upstream concept stays an
upstream concept.

Shapes come from ``components.schemas`` in ``docs/upstream/apidocs/comtrade.json``, from
the recorded fixtures under ``tests/fixtures/`` and, for the reference tables, from the
public files under ``files/v1/app/reference/``. Trade values and quantities are
``Decimal`` (ADR-0008) and travel as JSON numbers through the adapters.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import AliasChoices, Field, model_validator
from xippios.core import UpstreamModel

__all__ = [
    "Commodity",
    "CountryAreaCodeIso",
    "PartnerArea",
    "QuantityUnit",
    "Reference",
    "ReferenceCode",
    "Reporter",
    "TradeDataCountResponse",
    "TradeDataItem",
    "TradeDataRecord",
    "TradeDataResponse",
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


class _TableRow(UpstreamModel):
    """A row of a reference table packaged as CSV, where an empty cell is an absent key.

    Upstream leaves keys out of some rows (``entryExpiredDate`` on areas still in use);
    the packaged CSV writes those as empty cells. No upstream value is an empty string
    (checked by ``scripts/refresh_reference.py``), so reading an empty cell as absent
    loses nothing.
    """

    @model_validator(mode="before")
    @classmethod
    def _empty_cell_is_absent(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {key: value for key, value in data.items() if value != ""}
        return data


class Reporter(_TableRow):
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


class PartnerArea(_TableRow):
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


class CountryAreaCodeIso(_TableRow):
    """One row of ``country_area_code_iso.json``, UN Comtrade's area code to ISO alpha-3.

    Covers every reporter and partner code (312 rows when packaged). Some ``iso3`` values
    are UN Comtrade's own, e.g. ``"W00"`` for 0 World, ``"_AC"`` for 472.
    """

    country_area_code: int
    iso3: str


class TradeDataItem(_TableRow):
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
            ``"090111"``; for EBOPS ``"200"`` (EB, EB02, EB10) or ``"S"`` (EB10S) is the
            services total.
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
