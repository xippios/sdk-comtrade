"""``GET tools/v1/getTradeBalance/{typeCode}/{freqCode}/{clCode}``: exports beside imports.

Reference: ``docs/upstream/apidocs/comtradeTools.json``, operation ``getTradeBalance``
(operationId ``67c5e15c82a9a2df9de48685``, opaque, so the module is named from the path,
conventions §2); parameters in the order and spelling the spec lists them. The spec marks
it "(EXPERIMENTAL - USE SPARINGLY) Extract trade data in a pivoted flow (exports and
imports) layout." The Help Center describes the matching UI tool, Trade Balance View
(``un-comtrade-tools.md``). What upstream answers stands in ``docs/upstream/OBSERVED.md``
under "The Tools": every breakdown without ``breakdownMode`` and the total row alone with
``classic``, a 13th period refused with HTTP 400, which ``_client.classify`` maps to
``InvalidRequestError``, and ``countOnly=true``, which the spec does not list, answered with
``count`` 0 and a placeholder, so it counts nothing and no wrapper sends it. The package's
free key was answered, not refused with the spec's HTTP 403 "User not allowed". Error shapes
are mapped once in ``xippios.comtrade._client.classify``.
"""

from xippios.core import Answer

from xippios.comtrade._client import client
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
) -> Answer[TradeBalanceResponse]:
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
    return await client.get_answer(
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
        parse=TradeBalanceResponse,
        endpoint=ENDPOINT,
    )
