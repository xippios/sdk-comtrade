"""``GET public/v1/getComtradeReleases``: UN Comtrade's list of recent data releases.

Reference: ``docs/upstream/apidocs/public.json``, operation ``getComtradeReleases``
(operationId ``65ee390ccf5b6fd0ea10bfed``, opaque, so the module is named from the path,
conventions §2), under the server ``https://comtradeapi.un.org/public/v1``; no
parameters; "Get list of recent data releases". ``help/data-availability.md``, "Data
Availability via API": it returns "the list of the recent releases, the same with the UI
live update page" (https://comtrade.un.org/en/data-availability/recent-releases).

Public, keyless: ``public.json``'s ``security`` is ``[{}, apiKeyHeader, apiKeyQuery]``, a
key optional, and its ``info`` says "No subscription key required", so the call goes
through the package's one client with ``auth=None`` and sends none. It spends no daily
quota and takes the client's pace alone, so a spent key quota does not hold it back: the
client's ``policy`` skips a request sent with ``auth=None``. The client's cache keeps no
answer under ``public/v1``, so a release calendar always comes from upstream.

What upstream answers stands in ``docs/upstream/OBSERVED.md``, "``getComtradeReleases``: the
recent releases, newest first".
"""

from xippios.core import Answer

from xippios.comtrade._client import client
from xippios.comtrade.models import ComtradeReleasesResponse

__all__ = ["ENDPOINT", "get_comtrade_releases"]

ENDPOINT = "public/v1/getComtradeReleases"
"""The operation's path under the server, as ``help/data-availability.md`` names it."""


async def get_comtrade_releases() -> Answer[ComtradeReleasesResponse]:
    """Call ``public/v1/getComtradeReleases``, which takes no parameters."""
    return await client.get_answer(
        f"/{ENDPOINT}", auth=None, parse=ComtradeReleasesResponse, endpoint=ENDPOINT
    )
