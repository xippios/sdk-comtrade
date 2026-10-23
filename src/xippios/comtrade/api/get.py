"""``GET data/v1/get/{typeCode}/{freqCode}/{clCode}``: final trade data in the basic layout.

Reference: ``docs/upstream/apidocs/comtrade.json``, operation ``get`` (operationId
``get-get``); parameters in the order and spelling the spec lists them. Two query
parameters the spec does not list are used as the Help Center and the official
``comtradeapicall`` package (1.3.2) use them, and the fixtures confirm both:

- ``maxRecords`` caps the rows (``help/un-comtrade-api.md`` shows ``maxrecords=500``;
  ``tests/fixtures/get/over_limit_max_records.json`` returns 5 rows for ``maxRecords=5``);
- ``countOnly=true`` returns the number of records instead of the rows
  (``tests/fixtures/get/count_ch_exports_2023.json``).

The ``countOnly`` answer has a different shape, ``data`` being a placeholder object rather
than a list, so it has its own function here, ``get_count_only``. Error shapes are mapped
once in ``xippios.comtrade._client.classify``. A query nothing matches answers HTTP 200
with ``count`` 0 (``unknown_reporter.json``, ``count_zero_ch_1900.json``).
"""

from xippios.core import parse

from xippios.comtrade._client import SOURCE, client
from xippios.comtrade.models import TradeDataCountResponse, TradeDataResponse

__all__ = ["ENDPOINT", "UPSTREAM_NAMES", "get", "get_count_only"]

ENDPOINT = "data/v1/get"
"""The operation as upstream names it in ``help/un-comtrade-api.md``."""


def _path(type_code: str, freq_code: str, cl_code: str) -> str:
    return f"/{ENDPOINT}/{type_code}/{freq_code}/{cl_code}"


UPSTREAM_NAMES: dict[str, str] = {
    "reporter_code": "reporterCode",
    "period": "period",
    "partner_code": "partnerCode",
    "partner2_code": "partner2Code",
    "cmd_code": "cmdCode",
    "flow_code": "flowCode",
    "customs_code": "customsCode",
    "mot_code": "motCode",
    "aggregate_by": "aggregateBy",
    "breakdown_mode": "breakdownMode",
    "include_desc": "includeDesc",
    "max_records": "maxRecords",
}
"""Query parameters: the wrapper's argument to upstream's spelling, in the spec's order."""


def _query(**params: str | bool | int | None) -> dict[str, str]:
    """Upstream spellings for the snake_case arguments; unset ones are left out."""
    return {
        UPSTREAM_NAMES[name]: str(value).lower() if isinstance(value, bool) else str(value)
        for name, value in params.items()
        if value is not None
    }


async def get(
    type_code: str,
    freq_code: str,
    cl_code: str,
    *,
    reporter_code: str | None = None,
    period: str | None = None,
    partner_code: str | None = None,
    partner2_code: str | None = None,
    cmd_code: str | None = None,
    flow_code: str | None = None,
    customs_code: str | None = None,
    mot_code: str | None = None,
    aggregate_by: str | None = None,
    breakdown_mode: str | None = None,
    include_desc: bool | None = None,
    max_records: int | None = None,
) -> TradeDataResponse:
    """Call ``data/v1/get`` with the parameters as upstream names them.

    Args:
        type_code: ``typeCode``, ``"C"`` goods or ``"S"`` services.
        freq_code: ``freqCode``, ``"A"`` annual or ``"M"`` monthly.
        cl_code: ``clCode``, the product classification, e.g. ``"HS"``.
        reporter_code: ``reporterCode``, comma-separated area codes, e.g. ``"757"``.
        period: ``period``, comma-separated ``YYYY`` or ``YYYYMM`` values.
        partner_code: ``partnerCode``, comma-separated area codes, ``"0"`` is World.
        partner2_code: ``partner2Code``, comma-separated area codes.
        cmd_code: ``cmdCode``, comma-separated product codes, e.g. ``"TOTAL"``.
        flow_code: ``flowCode``, comma-separated flow codes, e.g. ``"X"``.
        customs_code: ``customsCode``, comma-separated customs procedure codes.
        mot_code: ``motCode``, comma-separated mode-of-transport codes.
        aggregate_by: ``aggregateBy``, comma-separated parameter names.
        breakdown_mode: ``breakdownMode``, ``"classic"`` or ``"plus"``.
        include_desc: ``includeDesc``, fill the ``*_desc`` fields.
        max_records: ``maxRecords``, at most this many rows.
    """
    raw = await client.get_json(
        _path(type_code, freq_code, cl_code),
        params=_query(
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
            max_records=max_records,
        ),
    )
    return parse(TradeDataResponse, raw, source=SOURCE, endpoint=ENDPOINT)


async def get_count_only(
    type_code: str,
    freq_code: str,
    cl_code: str,
    *,
    reporter_code: str | None = None,
    period: str | None = None,
    partner_code: str | None = None,
    partner2_code: str | None = None,
    cmd_code: str | None = None,
    flow_code: str | None = None,
    customs_code: str | None = None,
    mot_code: str | None = None,
    aggregate_by: str | None = None,
    breakdown_mode: str | None = None,
    include_desc: bool | None = None,
) -> TradeDataCountResponse:
    """Call ``data/v1/get`` with ``countOnly=true``: how many records the query returns.

    Same parameters as ``get`` without ``maxRecords``. Each call counts against the
    key's daily quota like a data call. A count over many reporters can take longer than
    a minute upstream (one such count timed out at the 60 s read timeout before a repeat
    answered in 27 s, 2026-10-23).
    """
    params = _query(
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
    raw = await client.get_json(
        _path(type_code, freq_code, cl_code), params={**params, "countOnly": "true"}
    )
    return parse(TradeDataCountResponse, raw, source=SOURCE, endpoint=ENDPOINT)
