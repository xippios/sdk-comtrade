"""``GET data/v1/getLiveUpdate``: the most recent releases of UN Comtrade's release pipeline.

Reference: ``docs/upstream/apidocs/comtrade.json``, operation ``getLiveUpdate``
(operationId ``get-getliveupdate``), no parameters; ``help/un-comtrade-api.md`` ("extracts
most recent publication updates"). The answer holds the spec's "50 most recently updated
releases", but its ``count`` is not the number of rows, and the rows carry the fields of
``LiveUpdateRecord`` and no ``publishedDate`` (``docs/upstream/OBSERVED.md``,
"``getLiveUpdate``: 50 rows and a ``count`` of 174").
"""

from xippios.core import Answer

from xippios.comtrade._client import client
from xippios.comtrade.models import LiveUpdateResponse

__all__ = ["ENDPOINT", "get_live_update"]

ENDPOINT = "data/v1/getLiveUpdate"
"""The operation as upstream names it in ``help/un-comtrade-api.md``."""


async def get_live_update() -> Answer[LiveUpdateResponse]:
    """Call ``data/v1/getLiveUpdate``."""
    return await client.get_answer(f"/{ENDPOINT}", parse=LiveUpdateResponse, endpoint=ENDPOINT)
