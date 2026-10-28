"""Live smoke tests: skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

Every task function gets one live smoke test here, next to the reachability check. The
whole module costs eleven keyed calls: the reachability check, one count, the count plus
the data call of ``get_data``, one call each for ``get_data_availability``,
``get_metadata`` and ``get_live_update``, and one for each of the four slices (the
commodity series asks for two periods, one call). A Basic Individual key allows 500
calls per day. The list tasks spend none: ``list_commodities`` and the checks of the
packaged tables fetch the public reference files without the key (three keyless
fetches).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest

from xippios.comtrade import api, tasks
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


async def test_list_reporters_live() -> None:
    """The packaged table still matches upstream's file; a mismatch means a refresh is due."""
    packaged = (await tasks.list_reporters_async()).data
    upstream = (await api.reference_rows("Reporters.json")).rows
    assert {row.reporter_code for row in packaged} == {row["reporterCode"] for row in upstream}
    assert any(row.reporter_code == 757 for row in packaged)


async def test_list_partners_live() -> None:
    """The packaged table still matches upstream's file; a mismatch means a refresh is due."""
    packaged = (await tasks.list_partners_async()).data
    upstream = (await api.reference_rows("partnerAreas.json")).rows
    assert {row.partner_code for row in packaged} == {row["PartnerCode"] for row in upstream}


async def test_list_commodities_live() -> None:
    result = await tasks.list_commodities_async("HS")
    assert len(result.data) > 8000
    total = result.data[0]
    assert (total.id, total.aggr_level, total.parent) == ("TOTAL", 0, "#")
    coffee = next(row for row in result.data if row.id == "090111")
    assert (coffee.parent, coffee.aggr_level, coffee.is_leaf) == ("0901", 6, True)


async def test_get_data_availability_live() -> None:
    result = await tasks.get_data_availability_async(
        "C", "A", "HS", reporter_code="757", period="2023"
    )
    [dataset] = result.data
    assert (dataset.reporter_code, dataset.period) == (757, 2023)
    assert isinstance(dataset.last_released, datetime)
    assert dataset.total_records > 0


async def test_get_metadata_live() -> None:
    result = await tasks.get_metadata_async("C", "A", "HS", reporter_code="757", period="2023")
    [dataset] = result.data
    assert dataset.notes
    assert all(isinstance(note.publication_date, datetime) for note in dataset.notes)


async def test_get_live_update_live() -> None:
    result = await tasks.get_live_update_async()
    assert result.data
    assert all(row.started_at is None or row.started_at.tzinfo for row in result.data)


async def test_get_bilateral_flows_live() -> None:
    result = await tasks.get_bilateral_flows_async("CHE", "USA", "TOTAL", "2023", "X")
    [row] = result.data
    assert (row.reporter_code, row.partner_code, row.cmd_code) == (757, 842, "TOTAL")
    assert (row.reporter_iso, row.partner_iso) == ("CHE", "USA")
    assert isinstance(row.primary_value, Decimal)
    assert row.primary_value > 0


async def test_get_commodity_series_live() -> None:
    result = await tasks.get_commodity_series_async("757", "27", "X", "2022,2023")
    assert [row.period for row in result.data] == ["2022", "2023"]
    assert {row.partner_code for row in result.data} == {0}


async def test_get_world_trade_live() -> None:
    result = await tasks.get_world_trade_async("27", "2023", "M")
    assert len(result.data) > 100
    assert len({row.reporter_code for row in result.data}) == len(result.data)
    values = [row.primary_value for row in result.data]
    assert values == sorted(values, reverse=True)


async def test_get_top_partners_live() -> None:
    result = await tasks.get_top_partners_async("757", "TOTAL", "2023", "X", 5)
    assert len(result.data) == 5
    assert 0 not in {row.partner_code for row in result.data}
    values = [row.primary_value for row in result.data]
    assert values == sorted(values, reverse=True)
