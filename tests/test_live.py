"""Live smoke tests: skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

Every task function gets one live smoke test here, next to the reachability probe, which
spends no keyed call. The whole module costs thirteen keyed calls: one count, the count
plus the data call of ``get_data``, one call each for ``get_data_availability``,
``get_metadata`` and ``get_live_update``, one for each of the four slices (the
commodity series asks for two periods, one call), one each for the two Tools
operations, ``get_trade_balance`` and ``get_bilateral_data``, and one for
``get_mirror_flows``, the mirror slice over getBilateralData. A Basic Individual key
allows 500 calls per day. The probe, the list tasks and the public operations spend none:
the probe sends no key, ``list_commodities`` and the checks of the packaged lists and
tables fetch the public reference files without it, and ``get_comtrade_releases`` and
``get_world_share`` call ``public/v1`` without it (eight keyless requests).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest

from xippios.comtrade import api, tasks
from xippios.comtrade._client import BASE_URL, config

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
    """The base URL answers without a server error.

    A plain request, not the package's client, so no key goes out and it spends no keyed
    call; a keyed gateway's answer to it (a 403 or a 404, say) still shows the host is up.
    """
    async with httpx.AsyncClient(
        headers={"User-Agent": config.user_agent},
        timeout=config.timeouts.to_httpx(),
        follow_redirects=True,
    ) as http:
        response = await http.get(BASE_URL)
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


async def test_list_codes_live() -> None:
    """The packaged motCode list still holds upstream's codes and texts; else a refresh is due."""
    packaged = (await tasks.list_codes_async("motCode")).data
    upstream = (await api.reference_rows("ModeOfTransportCodes.json")).rows
    assert [row.model_dump() for row in packaged] == [
        {"mot_code": row["id"], "text": row["text"]} for row in upstream
    ]


async def test_list_classifications_live() -> None:
    """The packaged index still lists upstream's categories; a mismatch means a refresh is due."""
    packaged = (await tasks.list_classifications_async()).data
    upstream = (await api.reference_rows("ListofReferences.json")).rows
    assert [row.category for row in packaged] == [row["category"] for row in upstream]


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


async def test_get_trade_balance_live() -> None:
    result = await tasks.get_trade_balance_async(
        "C", "A", "HS", reporter_code="757", period="2023", partner_code="0",
        cmd_code="TOTAL", breakdown_mode="classic",
    )  # fmt: skip
    [row] = result.data
    assert (row.reporter_code, row.partner_code, row.cmd_code) == (757, 0, "TOTAL")
    assert isinstance(row.primary_value_bal, Decimal)
    assert row.primary_value_x > 0
    assert row.primary_value_m > 0
    assert result.meta.total == 1


async def test_get_bilateral_data_live() -> None:
    result = await tasks.get_bilateral_data_async(
        "C", "A", "HS", reporter_code="757", period="2023", partner_code="842",
        cmd_code="TOTAL", flow_code="X",
    )  # fmt: skip
    assert result.data.note, "upstream's data-gap note"
    assert result.data.timestamp_requested is not None
    assert result.data.timestamp_requested.tzinfo is not None
    [row] = result.data.data
    assert (row.reporter_code, row.partner_code, row.flow_code) == (757, 842, "X")
    assert isinstance(row.mirror_primary_value, Decimal)
    assert row.primary_value > 0
    assert row.mirror_primary_value > 0


async def test_get_mirror_flows_live() -> None:
    result = await tasks.get_mirror_flows_async("CHE", "USA", "27", "2023", "X")
    assert result.data.note, "upstream's data-gap note"
    assert result.data.timestamp_requested is not None
    assert result.data.timestamp_requested.tzinfo is not None
    [row] = result.data.data
    assert (row.reporter_code, row.partner_code, row.cmd_code, row.flow_code) == (
        757,
        842,
        "27",
        "X",
    )
    assert isinstance(row.mirror_primary_value, Decimal)
    assert row.primary_value > 0
    assert row.mirror_primary_value > 0
    assert result.meta.total == 1


async def test_get_comtrade_releases_live() -> None:
    """Keyless: sends no key and spends no keyed call. The calendar may be empty some week."""
    result = await tasks.get_comtrade_releases_async()
    assert result.meta.total == len(result.data)
    assert all(row.date_release.tzinfo is None for row in result.data)


async def test_get_world_share_live() -> None:
    """Keyless: sends no key and spends no keyed call."""
    result = await tasks.get_world_share_async("C", "A", period="2023", reporter_code="757")
    [row] = result.data
    assert (row.reporter_code, row.period, row.freq_code) == (757, 2023, "A")
    assert isinstance(row.world_share, Decimal)
    assert 0 < row.world_share < 1
    assert row.first_released.tzinfo is None
