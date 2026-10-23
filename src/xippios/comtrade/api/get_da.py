"""``GET data/v1/getDa/{typeCode}/{freqCode}/{clCode}``: availability of final-data datasets.

Reference: ``docs/upstream/apidocs/comtrade.json``, operation ``getDa`` (operationId
``get-getda``); parameters in the order and spelling the spec lists them, and
``docs/upstream/help/data-availability.md``. One row per dataset: a reporter's data for a
period in the classification it reported. Recorded answers (2026-10-23, under
``tests/fixtures/get_da/``):

- ``reporterCode=757&period=2023``: one dataset (``ch_2023.json``); ``period=2023``
  alone: 169, one per reporter (``all_reporters_2023.json``); ``period=1900``: HTTP 200,
  ``count`` 0, no rows (``nobody_1900.json``).
- 13 comma-separated periods are answered, 13 rows (``ch_13_periods.json``): the 12-period
  limit of ``data/v1/get`` does not apply here.
- ``publishedDateFrom``/``publishedDateTo`` (``YYYY-MM-DD``) keep the datasets released in
  the range: for 2024, Switzerland's 2022 dataset (first released 2023-02-01, last
  2024-04-29) and 2023 dataset (``ch_published_2024.json``).
- ``clCode`` ``EBSDMX``, in the spec's enum for this operation, is refused with HTTP 400
  "The field clCode is invalid" (``services_ebsdmx.json``).
"""

from xippios.core import parse

from xippios.comtrade._client import SOURCE, client
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
) -> DataAvailabilityResponse:
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
    raw = await client.get_json(
        f"/{ENDPOINT}/{type_code}/{freq_code}/{cl_code}",
        params=upstream_query(
            UPSTREAM_NAMES,
            reporter_code=reporter_code,
            period=period,
            published_date_from=published_date_from,
            published_date_to=published_date_to,
        ),
    )
    return parse(DataAvailabilityResponse, raw, source=SOURCE, endpoint=ENDPOINT)
