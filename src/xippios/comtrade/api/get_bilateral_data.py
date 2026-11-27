"""``GET tools/v1/getBilateralData/{typeCode}/{freqCode}/{clCode}``: reported data and its mirror.

Reference: ``docs/upstream/apidocs/comtradeTools.json``, operation ``getBilateralData``
(operationId ``67c5e17e637a37bcdec9bb39``, opaque, so the module is named from the path,
conventions §2); parameters in the order and spelling the spec lists them. The spec marks
it "(EXPERIMENTAL - USE SPARINGLY) Extract basic trade data joined with mirror partner
data. Useful to analyze bilateral trade asymmetries." The Help Center describes the
matching UI tool, Bilateral Data Comparison (``un-comtrade-tools.md``), and the
asymmetries (``bilateral-asymmetries.md``). What upstream answers stands in
``docs/upstream/OBSERVED.md`` under "The Tools": more than 12 periods answered, one
``flowCode`` a call, refused with HTTP 400 for ``M,X`` although the spec's description reads
"Multi value input should be in the form of csv", ``includeDesc`` filling no description,
the note on a data gap that counts the partners without naming them, and ``countOnly=true``,
which the spec does not list, ignored, so no wrapper sends it. Error shapes are mapped once
in ``xippios.comtrade._client.classify``.
"""

from xippios.core import Answer

from xippios.comtrade._client import client
from xippios.comtrade.api._query import upstream_query
from xippios.comtrade.models import BilateralDataResponse

__all__ = ["ENDPOINT", "UPSTREAM_NAMES", "get_bilateral_data"]

ENDPOINT = "tools/v1/getBilateralData"
"""The operation as upstream names it: the spec's server path and its ``summary``."""

UPSTREAM_NAMES: dict[str, str] = {
    "reporter_code": "reporterCode",
    "period": "period",
    "partner_code": "partnerCode",
    "cmd_code": "cmdCode",
    "flow_code": "flowCode",
    "include_desc": "includeDesc",
}
"""Query parameters: the wrapper's argument to upstream's spelling, in the spec's order."""


async def get_bilateral_data(
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
) -> Answer[BilateralDataResponse]:
    """Call ``tools/v1/getBilateralData`` with the parameters as upstream names them.

    Args:
        type_code: ``typeCode``, ``"C"`` goods or ``"S"`` services.
        freq_code: ``freqCode``, ``"A"`` annual or ``"M"`` monthly.
        cl_code: ``clCode``, the product classification, e.g. ``"HS"``.
        reporter_code: ``reporterCode``, comma-separated area codes, e.g. ``"757"``.
        period: ``period``, comma-separated ``YYYY`` or ``YYYYMM`` values.
        partner_code: ``partnerCode``, comma-separated area codes, e.g. ``"842"``.
        cmd_code: ``cmdCode``, comma-separated product codes, e.g. ``"TOTAL"``.
        flow_code: ``flowCode``, one flow, ``"X"`` or ``"M"``.
        include_desc: ``includeDesc``, as upstream takes it.
    """
    return await client.get_answer(
        f"/{ENDPOINT}/{type_code}/{freq_code}/{cl_code}",
        params=upstream_query(
            UPSTREAM_NAMES,
            reporter_code=reporter_code,
            period=period,
            partner_code=partner_code,
            cmd_code=cmd_code,
            flow_code=flow_code,
            include_desc=include_desc,
        ),
        parse=BilateralDataResponse,
        endpoint=ENDPOINT,
    )
