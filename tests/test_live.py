"""Live smoke tests: skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

Every task function gets one live smoke test here, next to the reachability check. The
whole module costs four keyed calls: the reachability check, one count, and the count
plus the data call of ``get_data``. A Basic Individual key allows 500 calls per day.
"""

from decimal import Decimal
from typing import Any

import pytest

from xippios.comtrade import tasks
from xippios.comtrade._client import client

pytestmark = [pytest.mark.live, pytest.mark.anyio]

# Switzerland's exports to the World in 2023, all products: 32 rows (every customs
# procedure and mode of transport) when recorded on 2026-10-23.
CH_EXPORTS_2023: dict[str, Any] = {
    "type_code": "C",
    "freq_code": "A",
    "cl_code": "HS",
    "reporter_code": "757",
    "partner_code": "0",
    "period": "2023",
    "cmd_code": "TOTAL",
    "flow_code": "X",
}


async def test_upstream_answers() -> None:
    response = await client.request("GET", "/", raise_on_error=False)
    assert response.status_code < 500


async def test_get_counts_live() -> None:
    result = await tasks.get_counts_async(**CH_EXPORTS_2023)
    assert result.data > 0
    assert result.meta.endpoint == "data/v1/get"


async def test_get_data_live() -> None:
    result = await tasks.get_data_async(**CH_EXPORTS_2023)
    assert result.data
    total = [
        row
        for row in result.data
        if (row.customs_code, row.mot_code, row.partner2_code) == ("C00", 0, 0)
    ]
    assert len(total) == 1
    assert total[0].reporter_code == 757
    assert isinstance(total[0].primary_value, Decimal)
    assert total[0].primary_value > 0
