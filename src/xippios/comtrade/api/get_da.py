"""``GET data/v1/getDa/{typeCode}/{freqCode}/{clCode}``: availability of final-data datasets.

Reference: ``docs/upstream/apidocs/comtrade.json``, operation ``getDa`` (operationId
``get-getda``); parameters in the order and spelling the spec lists them, and
``docs/upstream/help/data-availability.md``. One row per dataset: a reporter's data for a
period in the classification it reported. What upstream answers stands in
``docs/upstream/OBSERVED.md`` under "Availability, metadata and the release pipeline": one
dataset for each reporter and period, more than 12 periods answered, ``publishedDateFrom``
and ``publishedDateTo`` keeping a dataset revised in the range, and ``clCode`` ``EBSDMX``, in
the spec's enum for this operation, refused with HTTP 400.
"""

from xippios.core import Answer

from xippios.comtrade._client import client
from xippios.comtrade.api._query import upstream_query
from xippios.comtrade.models import DataAvailabilityResponse

__all__ = ["ENDPOINT", "UPSTREAM_NAMES", "get_da"]

ENDPOINT = "data/v1/getDa"
"""The operation as upstream names it in ``help/un-comtrade-api.md``."""

UPSTREAM_NAMES: dict[str, str] = {
    "reporter_code": "reporterCode",
    "period": "period",
    "published_date_from": "publishedDateFrom",
    "published_date_to": "publishedDateTo",
}
"""Query parameters: the wrapper's argument to upstream's spelling, in the spec's order."""


async def get_da(
    type_code: str,
    freq_code: str,
    cl_code: str,
    *,
    reporter_code: str | None = None,
    period: str | None = None,
    published_date_from: str | None = None,
    published_date_to: str | None = None,
) -> Answer[DataAvailabilityResponse]:
    """Call ``data/v1/getDa`` with the parameters as upstream names them.

    Args:
        type_code: ``typeCode``, ``"C"`` goods or ``"S"`` services.
        freq_code: ``freqCode``, ``"A"`` annual or ``"M"`` monthly.
        cl_code: ``clCode``, the classification, e.g. ``"HS"``.
        reporter_code: ``reporterCode``, comma-separated reporter codes, e.g. ``"757"``.
        period: ``period``, comma-separated ``YYYY`` or ``YYYYMM`` values.
        published_date_from: ``publishedDateFrom``, ``YYYY-MM-DD``.
        published_date_to: ``publishedDateTo``, ``YYYY-MM-DD``.
    """
    return await client.get_answer(
        f"/{ENDPOINT}/{type_code}/{freq_code}/{cl_code}",
        params=upstream_query(
            UPSTREAM_NAMES,
            reporter_code=reporter_code,
            period=period,
            published_date_from=published_date_from,
            published_date_to=published_date_to,
        ),
        parse=DataAvailabilityResponse,
        endpoint=ENDPOINT,
    )
