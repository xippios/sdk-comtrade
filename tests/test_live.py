"""Live smoke tests: skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

Every task function gets one live smoke test here, next to the reachability check.
"""

import pytest

from xippios.comtrade._client import client

pytestmark = [pytest.mark.live, pytest.mark.anyio]


async def test_upstream_answers() -> None:
    response = await client.request("GET", "/", raise_on_error=False)
    assert response.status_code < 500
