"""``GET tools/v1/getTradeBalance/{typeCode}/{freqCode}/{clCode}``: exports beside imports.

Reference: ``docs/upstream/apidocs/comtradeTools.json``, operation ``getTradeBalance``
(operationId ``67c5e15c82a9a2df9de48685``, opaque, so the module is named from the path,
conventions §2); parameters in the order and spelling the spec lists them. The spec marks
it "(EXPERIMENTAL - USE SPARINGLY) Extract trade data in a pivoted flow (exports and
imports) layout." The Help Center describes the matching UI tool, Trade Balance View
(``un-comtrade-tools.md``). Recorded answers (2026-10-28, under
``tests/fixtures/get_trade_balance/``), Switzerland (757) and the World (0), ``TOTAL``:

- 2023 without ``breakdownMode``: 48 rows, every customs procedure and mode of transport
  (``ch_world_2023_include_desc.json``); with ``classic``: the total row alone, the same
  row (``ch_world_2023_include_desc_breakdown_mode_classic.json``). Upstream's default
  gives every breakdown, not ``classic``'s total row; ``plus``, the spec's other value,
  was not sent. ``includeDesc`` fills the ``*_iso``/``*_desc`` fields.
- 1900: HTTP 200, ``count`` 0, no rows (``ch_world_1900_empty.json``).
- 13 periods: HTTP 400 "Maximum number of periods is 12" (``ch_world_13_periods.json``),
  which ``_client.classify`` maps to ``InvalidRequestError``.
- ``countOnly=true``, which the spec does not list: HTTP 200 with ``count`` 0 and a
  placeholder object in ``data`` for the query that answers 48 rows
  (``count_only_ch_world_2023.json``), so it counts nothing and no wrapper sends it.

The key was answered, not refused: the spec's 403 "Free-tier user not on the allow-list
("User not allowed")" was not met. Error shapes are mapped once in
``xippios.comtrade._client.classify``.
"""

from xippios.core import parse

from xippios.comtrade._client import SOURCE, client
from xippios.comtrade.api._query import upstream_query
from xippios.comtrade.models import TradeBalanceResponse

__all__ = ["ENDPOINT", "UPSTREAM_NAMES", "get_trade_balance"]

ENDPOINT = "tools/v1/getTradeBalance"
"""The operation as upstream names it: the spec's server path and its ``summary``."""

UPSTREAM_NAMES: dict[str, str] = {
    "reporter_code": "reporterCode",
    "period": "period",
    "partner_code": "partnerCode",
    "partner2_code": "partner2Code",
    "cmd_code": "cmdCode",
    "customs_code": "customsCode",
    "mot_code": "motCode",
    "aggregate_by": "aggregateBy",
    "breakdown_mode": "breakdownMode",
    "include_desc": "includeDesc",
}
"""Query parameters: the wrapper's argument to upstream's spelling, in the spec's order."""


async def get_trade_balance(
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
) -> TradeBalanceResponse:
    """Call ``tools/v1/getTradeBalance`` with the parameters as upstream names them.

    Args:
        type_code: ``typeCode``, ``"C"`` goods or ``"S"`` services.
        freq_code: ``freqCode``, ``"A"`` annual or ``"M"`` monthly.
        cl_code: ``clCode``, the product classification, e.g. ``"HS"``.
        reporter_code: ``reporterCode``, comma-separated area codes, e.g. ``"757"``.
        period: ``period``, comma-separated ``YYYY`` or ``YYYYMM`` values, at most 12.
        partner_code: ``partnerCode``, comma-separated area codes, ``"0"`` is World.
        partner2_code: ``partner2Code``, comma-separated area codes.
        cmd_code: ``cmdCode``, comma-separated product codes, e.g. ``"TOTAL"``.
        customs_code: ``customsCode``, comma-separated customs procedure codes.
        mot_code: ``motCode``, comma-separated mode-of-transport codes.
        aggregate_by: ``aggregateBy``, comma-separated parameter names.
        breakdown_mode: ``breakdownMode``, ``"classic"`` or ``"plus"``.
        include_desc: ``includeDesc``, fill the ``*_desc`` fields.
    """
    raw = await client.get_json(
        f"/{ENDPOINT}/{type_code}/{freq_code}/{cl_code}",
        params=upstream_query(
            UPSTREAM_NAMES,
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
        ),
    )
    return parse(TradeBalanceResponse, raw, source=SOURCE, endpoint=ENDPOINT)
