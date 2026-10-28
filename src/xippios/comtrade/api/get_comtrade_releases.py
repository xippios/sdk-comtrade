"""``GET public/v1/getComtradeReleases``: UN Comtrade's list of recent data releases.

Reference: ``docs/upstream/apidocs/public.json``, operation ``getComtradeReleases``
(operationId ``65ee390ccf5b6fd0ea10bfed``, opaque, so the module is named from the path,
conventions §2), under the server ``https://comtradeapi.un.org/public/v1``; no
parameters; "Get list of recent data releases". ``help/data-availability.md``, "Data
Availability via API": it returns "the list of the recent releases, the same with the UI
live update page" (https://comtradeplus.un.org/RecentReleases).

Public, keyless: ``public.json``'s ``security`` is ``[{}, apiKeyHeader, apiKeyQuery]``, a
key optional, and its ``info`` says "No subscription key required", so the call goes
through the package's one client with ``auth=None`` and sends none. It spends no daily
quota but still takes the client's pace and its ``policy``: once upstream has said the
key's quota is spent, this call is held back too. The client's cache keeps the reference
files only, never this answer.

Recorded 2026-10-28 (``tests/fixtures/get_comtrade_releases/calendar.json``): 38 rows,
``count`` 38, released from 2026-10-22 to 2026-10-28, newest first, every
``dateRelease`` a midnight without an offset; no date after the recording day.
"""

from xippios.core import parse

from xippios.comtrade._client import SOURCE, client
from xippios.comtrade.models import ComtradeReleasesResponse

__all__ = ["ENDPOINT", "get_comtrade_releases"]

ENDPOINT = "public/v1/getComtradeReleases"
"""The operation's path under the server, as ``help/data-availability.md`` names it."""


async def get_comtrade_releases() -> ComtradeReleasesResponse:
    """Call ``public/v1/getComtradeReleases``, which takes no parameters."""
    raw = await client.get_json(f"/{ENDPOINT}", auth=None)
    return parse(ComtradeReleasesResponse, raw, source=SOURCE, endpoint=ENDPOINT)
