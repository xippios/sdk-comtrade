"""``GET tools/v1/getBilateralData/{typeCode}/{freqCode}/{clCode}``: reported data and its mirror.

Reference: ``docs/upstream/apidocs/comtradeTools.json``, operation ``getBilateralData``
(operationId ``67c5e17e637a37bcdec9bb39``, opaque, so the module is named from the path,
conventions §2); parameters in the order and spelling the spec lists them. The spec marks
it "(EXPERIMENTAL - USE SPARINGLY) Extract basic trade data joined with mirror partner
data. Useful to analyze bilateral trade asymmetries." The Help Center describes the
matching UI tool, Bilateral Data Comparison (``un-comtrade-tools.md``), and the
asymmetries (``bilateral-asymmetries.md``). Recorded answers (2026-10-28, under
``tests/fixtures/get_bilateral_data/``), Switzerland's (757) exports (``X``), ``TOTAL``:

- to the USA (842), 2023: one row with its mirror and a ``note`` that no partner has a
  data gap (``ch_us_exports_2023.json``); ``includeDesc=true`` changes nothing, the
  descriptions stay ``None`` (``ch_us_exports_2023_include_desc.json``).
- to the USA, DPRK (408) and Afghanistan (4), 2023: two rows, Afghanistan's mirror 0, and
  a ``note`` naming a data gap for two partners (``ch_us_kp_af_exports_2023.json``); to
  DPRK alone ``count`` 0 (``ch_kp_exports_2023_include_desc.json``), as ``data/v1/get``
  answers (``tests/fixtures/get/ch_kp_exports_2023_totals.json``).
- 13 periods to the USA: 13 rows (``ch_us_exports_13_periods.json``); the 12-period limit
  of ``data/v1/get`` and ``getTradeBalance`` does not apply here.
- ``flowCode=M,X``: HTTP 400 "Invalid parameter value", "The field flowCode is invalid"
  (``ch_us_2023_flow_code_m_x.json``): one flow per call, the spec's enum, although its
  description reads "Multi value input should be in the form of csv".
- ``countOnly=true``, which the spec does not list: ignored, the same row
  (``count_only_ch_us_exports_2023.json``), so no wrapper sends it.

Error shapes are mapped once in ``xippios.comtrade._client.classify``.
"""

from xippios.core import parse

from xippios.comtrade._client import SOURCE, client
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
) -> BilateralDataResponse:
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
    raw = await client.get_json(
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
    )
    return parse(BilateralDataResponse, raw, source=SOURCE, endpoint=ENDPOINT)
