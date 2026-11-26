"""``GET public/v1/getWorldShare/{typeCode}/{freqCode}``: reporters' shares of world trade.

Reference: ``docs/upstream/apidocs/public.json``, operation ``getWorldShare``
(operationId ``66abc37fcbedb74c48662189``, opaque, so the module is named from the path,
conventions §2), under the server ``https://comtradeapi.un.org/public/v1``: "Get the
World Share (including estimates)". Path parameters ``typeCode`` (``C``, ``S``) and
``freqCode`` (``A``, ``M``); query parameters ``period`` ("Period(s): YYYY (annual) or
YYYYMM (monthly), comma-separated, or 'recent'") and ``reporterCode`` ("Reporter code(s):
codes separated by comma (,)"), in the spec's order. No Help Center article names the
operation.

Public, keyless: ``public.json``'s ``security`` is ``[{}, apiKeyHeader, apiKeyQuery]``, a
key optional, and its ``info`` says "No subscription key required", so the call goes
through the package's one client with ``auth=None`` and sends none. It spends no daily
quota and takes the client's pace alone, so a spent key quota does not hold it back: the
client's ``policy`` skips a request sent with ``auth=None``. The client's cache keeps no
answer under ``public/v1``.

What upstream answers stands in ``docs/upstream/OBSERVED.md`` under "The public operations":
one row for each reporter and period, the shares and the placeholder of an unavailable
dataset, ``period=recent`` answered with HTTP 500 and a malformed period refused with HTTP
400 without a ``Content-Type``.
"""

from xippios.core import Answer

from xippios.comtrade._client import client
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
) -> Answer[WorldShareResponse]:
    """Call ``public/v1/getWorldShare`` with the parameters as upstream names them.

    Args:
        type_code: ``typeCode``, ``"C"`` goods or ``"S"`` services.
        freq_code: ``freqCode``, ``"A"`` annual or ``"M"`` monthly.
        period: ``period``, comma-separated ``YYYY`` or ``YYYYMM`` values, or ``"recent"``.
        reporter_code: ``reporterCode``, comma-separated reporter codes, e.g. ``"757"``.
    """
    return await client.get_answer(
        f"/{ENDPOINT}/{type_code}/{freq_code}",
        params=upstream_query(UPSTREAM_NAMES, period=period, reporter_code=reporter_code),
        auth=None,
        parse=WorldShareResponse,
        endpoint=ENDPOINT,
    )
