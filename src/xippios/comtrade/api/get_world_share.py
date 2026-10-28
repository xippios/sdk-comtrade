"""``GET public/v1/getWorldShare/{typeCode}/{freqCode}``: reporters' shares of world trade.

Reference: ``docs/upstream/apidocs/public.json``, path ``/getWorldShare/{typeCode}/{freqCode}``
under the server ``https://comtradeapi.un.org/public/v1``, operationId
``66abc37fcbedb74c48662189``, an opaque id, so the wrapper is named after the path
(conventions §2): "Get the World Share (including estimates)". Path parameters
``typeCode`` (``C``, ``S``) and ``freqCode`` (``A``, ``M``); query parameters ``period``
("Period(s): YYYY (annual) or YYYYMM (monthly), comma-separated, or 'recent'") and
``reporterCode`` ("Reporter code(s): codes separated by comma (,)"), in the spec's order.
No Help Center article names the operation.

Public, keyless: ``public.json``'s ``security`` allows no key, so the call goes through
the package's one client with ``auth=None`` and sends none; it still takes the client's
pace. The client's cache keeps the reference files only, never this answer.

Recorded answers (2026-10-28, under ``tests/fixtures/get_world_share/``):

- ``period=2023&reporterCode=757``: one row (``ch_2023.json``); its ``firstReleased``
  and ``lastReleased`` equal those of ``data/v1/getDa`` for the same reporter and period
  (``tests/fixtures/get_da/ch_2023.json``). Monthly, ``C/M`` with ``period=202301``: one
  row, ``month`` 1 (``ch_202301.json``).
- ``period=2023`` alone: 214 rows, one per reporter, 47 of them with ``isAvailable``
  false and ``0001-01-01T00:00:00`` as both release times; the 214 ``worldShare`` values
  sum to 1.0 (``all_reporters_2023.json``). ``reporterCode=757`` alone: 64 rows, every
  year from 1962 to 2025 (``ch_every_period.json``). ``period=1900``: HTTP 200, ``count``
  0, no rows (``ch_1900_empty.json``).
- ``period=recent``, which the spec lists: HTTP 500, ``count`` -1, ``error`` an object
  ``{"error": "Something went wrong. Please try again or contact comtrade@un.org."}``, on
  all three tries, with ``reporterCode=757`` and without (``ch_recent.json``,
  ``all_reporters_recent.json``).
- ``period=2023-01``: HTTP 400 "Invalid parameter value", its ``details`` spelt
  ``MemberNames``/``ErrorMessage`` ("The field period is invalid"), no ``Content-Type``
  (``period_malformed.json``).
"""

from xippios.core import parse

from xippios.comtrade._client import SOURCE, client
from xippios.comtrade.api._query import upstream_query
from xippios.comtrade.models import WorldShareResponse

__all__ = ["ENDPOINT", "UPSTREAM_NAMES", "get_world_share"]

ENDPOINT = "public/v1/getWorldShare"
"""The operation's path under the server, without its path parameters."""

UPSTREAM_NAMES: dict[str, str] = {
    "period": "period",
    "reporter_code": "reporterCode",
}
"""Query parameters: the wrapper's argument to upstream's spelling, in the spec's order."""


async def get_world_share(
    type_code: str,
    freq_code: str,
    *,
    period: str | None = None,
    reporter_code: str | None = None,
) -> WorldShareResponse:
    """Call ``public/v1/getWorldShare`` (operationId ``66abc37fcbedb74c48662189``).

    Args:
        type_code: ``typeCode``, ``"C"`` goods or ``"S"`` services.
        freq_code: ``freqCode``, ``"A"`` annual or ``"M"`` monthly.
        period: ``period``, comma-separated ``YYYY`` or ``YYYYMM`` values, or ``"recent"``.
        reporter_code: ``reporterCode``, comma-separated reporter codes, e.g. ``"757"``.
    """
    raw = await client.get_json(
        f"/{ENDPOINT}/{type_code}/{freq_code}",
        params=upstream_query(UPSTREAM_NAMES, period=period, reporter_code=reporter_code),
        auth=None,
    )
    return parse(WorldShareResponse, raw, source=SOURCE, endpoint=ENDPOINT)
