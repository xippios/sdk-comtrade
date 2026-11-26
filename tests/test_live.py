"""Live smoke tests, one per task, skipped unless XIPPIOS_LIVE_TESTS=1 (conventions §10).

Every task has its live smoke test here. The keyed tasks spend calls of the key's daily 500;
the public operations, ``get_comtrade_releases`` and ``get_world_share``, send no key, and
``list_commodities`` fetches a public reference file without it, while ``list_reporters``,
``list_partners``, ``list_codes`` and ``list_classifications`` answer from the packaged lists
and send nothing. After a run, xippios-core's testing plugin prints the requests it sent in
one line, ``requests sent by the live run: <n>``: in the log of ``live.yml``, that line is
the count a release cites (``/release-prep``), so this header states none.

The star import collects core's nightly comparison of each packaged list with the list
upstream serves now, ``test_packaged_list_is_current``, once per entry of ``LIVE_LISTS``
(sdk-core ADR-0055): the nine lists and tables that UN Comtrade serves as public reference
files, each fetched without the key by the fetch that ``scripts/refresh_reference.py``
declares, so the comparison holds the records a refresh would write. The six lists read from
the spec snapshot or reconciled with it stand in ``NO_LIVE_LIST``, each with its reason.
Core's family check imports this module offline and holds every packaged list in one of the
two.
"""

import importlib.util
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from xippios.core import PackagedCodes, PackagedList
from xippios.core.testing.live import *  # noqa: F403

from xippios.comtrade import tasks
from xippios.comtrade._client import SOURCE
from xippios.comtrade.params import PACKAGE

pytestmark = [pytest.mark.live, pytest.mark.anyio]


def _refresh_script() -> ModuleType:
    """``scripts/refresh_reference.py``, loaded by its path: it declares each list's fetch."""
    path = Path(__file__).resolve().parents[1] / "scripts" / "refresh_reference.py"
    spec = importlib.util.spec_from_file_location("refresh_reference", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_LISTED = {listed.name: listed for listed in _refresh_script().LISTS.lists}


def _current(name: str) -> Callable[[], object]:
    """The records of ``name`` as the refresh script fetches and writes them now."""
    fetch = _LISTED[name].fetch
    return lambda: fetch().records


_CODES = {
    "customsCode": "customsCode",
    "motCode": "motCode",
    "mosCode": "mosCode",
    "qtyUnitCode": "qtyUnitCode",
    "Reporters": "reporterCode",
    "partnerAreas": "PartnerCode",
    "country_area_code_iso": "country_area_code",
    "TradeDataItems": "dataItem",
    "ListofReferences": "category",
}
"""Each list compared, by the field its records are compared by."""

LIVE_LISTS: dict[str, tuple[PackagedCodes, Callable[[], object]]] = {
    name: (PackagedList.load(PACKAGE, name).codes(code, source=SOURCE), _current(name))
    for name, code in _CODES.items()
}
"""Each packaged list compared in the nightly run with the file upstream serves now, keyless."""

_SPEC = (
    "Read from the spec snapshot, docs/upstream/apidocs/comtrade.json, and served by no "
    "reference file; the snapshot's --check compares the spec with upstream's."
)

NO_LIVE_LIST: dict[str, str] = {
    "typeCode": _SPEC,
    "freqCode": _SPEC,
    "breakdownMode": _SPEC,
    "aggregateBy": _SPEC,
    "clCode": (
        "The cmd: categories of ListofReferences.json reconciled with the spec snapshot's "
        "clCode enum by the recorded counts under tests/fixtures/get/ (BE and TM added, BE5 "
        "left out), so no file of upstream's holds it; the ListofReferences table compares "
        "the file."
    ),
    "flowCode": (
        "The ids of tradeRegimes.json reconciled with the spec snapshot's flowCode "
        "description (MIF and XIF added), so no file of upstream's holds it; "
        "scripts/refresh_reference.py rebuilds it from both."
    ),
}
"""Each packaged list left out of the nightly comparison, with the reason."""

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
    """Answered from the packaged table, no request; ``LIVE_LISTS`` compares it with upstream's."""
    result = await tasks.list_reporters_async()
    assert any(row.reporter_code == 757 for row in result.data)


async def test_list_partners_live() -> None:
    """Answered from the packaged table, no request; ``LIVE_LISTS`` compares it with upstream's."""
    result = await tasks.list_partners_async()
    assert any(row.partner_code == 0 for row in result.data)


async def test_list_commodities_live() -> None:
    result = await tasks.list_commodities_async("HS")
    assert len(result.data) > 8000
    total = result.data[0]
    assert (total.id, total.aggr_level, total.parent) == ("TOTAL", 0, "#")
    coffee = next(row for row in result.data if row.id == "090111")
    assert (coffee.parent, coffee.aggr_level, coffee.is_leaf) == ("0901", 6, True)


async def test_list_codes_live() -> None:
    """Answered from the packaged list, no request; ``LIVE_LISTS`` compares it with upstream's."""
    result = await tasks.list_codes_async("motCode")
    assert result.data


async def test_list_classifications_live() -> None:
    """Answered from the packaged index, no request; ``LIVE_LISTS`` compares it with upstream's."""
    result = await tasks.list_classifications_async()
    assert any(row.category == "cmd:HS" for row in result.data)


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
