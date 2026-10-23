"""``GET data/v1/getMetadata/{typeCode}/{freqCode}/{clCode}``: publication notes of datasets.

Reference: ``docs/upstream/apidocs/comtrade.json``, operation ``getMetadata``
(operationId ``getmetadata``), and ``docs/upstream/help/metadata.md``. The spec lists
only the three path parameters. The official ``comtradeapicall`` package (1.3.2,
``getMetadata``) also sends ``reporterCode`` and ``period``, and upstream honours both
(recorded 2026-10-23 under ``tests/fixtures/get_metadata/``): ``reporterCode=757`` alone
answers Switzerland's 38 datasets and nobody else's (``ch_all_periods.json``), adding
``period=2023`` narrows it to one (``ch_2023.json``). A call without ``reporterCode``
answers every reporter's notes and was not recorded. ``clCode`` ``H6``, missing from the
spec's enum for this operation, is answered like ``HS`` (``ch_2023_h6.json``).
"""

from xippios.core import parse

from xippios.comtrade._client import SOURCE, client
from xippios.comtrade.api._query import upstream_query
from xippios.comtrade.models import MetadataResponse

__all__ = ["ENDPOINT", "UPSTREAM_NAMES", "get_metadata"]

ENDPOINT = "data/v1/getMetadata"
"""The operation as upstream names it in ``help/un-comtrade-api.md``."""

UPSTREAM_NAMES: dict[str, str] = {"reporter_code": "reporterCode", "period": "period"}
"""Query parameters as ``comtradeapicall`` 1.3.2 sends them; not in the spec."""


async def get_metadata(
    type_code: str,
    freq_code: str,
    cl_code: str,
    *,
    reporter_code: str | None = None,
    period: str | None = None,
) -> MetadataResponse:
    """Call ``data/v1/getMetadata`` with the parameters as upstream names them.

    Args:
        type_code: ``typeCode``, ``"C"`` goods or ``"S"`` services.
        freq_code: ``freqCode``, ``"A"`` annual or ``"M"`` monthly.
        cl_code: ``clCode``, the classification, e.g. ``"HS"``.
        reporter_code: ``reporterCode``, comma-separated reporter codes, e.g. ``"757"``.
        period: ``period``, comma-separated ``YYYY`` or ``YYYYMM`` values.
    """
    raw = await client.get_json(
        f"/{ENDPOINT}/{type_code}/{freq_code}/{cl_code}",
        params=upstream_query(UPSTREAM_NAMES, reporter_code=reporter_code, period=period),
    )
    return parse(MetadataResponse, raw, source=SOURCE, endpoint=ENDPOINT)
