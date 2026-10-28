"""Replay tests on recorded fixtures, at least one per task (conventions §10).

``/add-endpoint`` and ``/record-fixture`` add them; the checks of this package's own, on
the task docstrings, the adapters' source and the packaged lists, come first.
"""

import dataclasses
import inspect
import json
import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from xippios.core import (
    AsyncClient,
    AuthError,
    InvalidRequestError,
    NotFoundError,
    PackagedList,
    RateLimitError,
    ResultCap,
    RetryPolicy,
    UpstreamError,
    UpstreamModel,
)
from xippios.core.client.cache import CachedResponse, cache_key
from xippios.core.http import status_for
from xippios.core.testing import (
    ReplayFixture,
    assert_projection,
    assert_time_between,
    load_fixture,
    mcp_call,
    recorded_query,
    sent_query,
)

from xippios.comtrade import api, enums, tasks
from xippios.comtrade._client import (
    API_KEY_ENV,
    BASE_URL,
    RATE_LIMIT,
    TIMEOUTS,
    _quota_reset,
    auth,
    classify,
    config,
    policy,
)
from xippios.comtrade.errors import RECORD_LIMIT, QueryTooLarge
from xippios.comtrade.mcp import server
from xippios.comtrade.models import (
    Commodity,
    CountryAreaCodeIso,
    LiveUpdateRecord,
    MetadataDataset,
    PartnerArea,
    ReferenceCode,
    Reporter,
    TradeDataItem,
    TradeDataRecord,
    TradeFlowRecord,
)
from xippios.comtrade.params import (
    CL_CODES_FROM_SPEC,
    MAX_SERIES_PERIODS,
    PACKAGE,
    PACKAGED_LISTS,
    PACKAGED_TABLES,
    classification_files,
    validate_get,
    validate_slice,
)

TASKS = [getattr(tasks, name) for name in tasks.__all__]

UPSTREAM = Path(__file__).resolve().parents[1] / "docs" / "upstream"

GET = Path(__file__).resolve().parent / "fixtures" / "get"
"""The recorded ``data/v1/get`` answers."""

COUNT_ONLY = ["countOnly"]
"""``match_params`` of a count fixture: a count and a data call share one path.

A route cannot require ``countOnly`` to be absent, so a test mounts the count fixture
first; a data request, which the count route does not match, reaches the data fixture
mounted after it (``xippios.core.testing.replay.mount_fixture``).
"""

BY_AREAS = ["reporterCode", "partnerCode", "period", "cmdCode", "flowCode"]
"""``match_params`` of a bilateral slice fixture: the resolved areas, periods, product, flow."""

BY_PERIODS = ["reporterCode", "period"]
"""``match_params`` of a commodity series fixture: one per chunk of 12 periods."""

BY_PARTNER = ["partnerCode", "period", "cmdCode", "flowCode"]
"""``match_params`` of the world trade fixture, which names no reporter."""

BY_REPORTER = ["reporterCode", "period", "cmdCode", "flowCode"]
"""``match_params`` of the every-partner fixture, which names no partner."""


@pytest.mark.parametrize("task", TASKS, ids=tasks.__all__)
def test_every_parameter_is_explained(task: object) -> None:
    doc = inspect.getdoc(task) or ""
    for name in inspect.signature(task).parameters:  # type: ignore[arg-type]
        assert f"    {name}: " in doc, name


def test_the_adapters_name_no_task() -> None:
    """mcp.py and http.py name no task (ADR-0001); the family check covers registration."""
    package_dir = Path(tasks.__file__).parent
    sources = {
        adapter: (package_dir / adapter).read_text(encoding="utf-8")
        for adapter in ("mcp.py", "http.py")
    }
    for name in tasks.__all__:
        for adapter, source in sources.items():
            assert name not in source, f"{adapter} names {name}"


# Switzerland (reporter 757 in Reporters.json) exports to the World in 2023, all products.
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


def test_get_counts_sends_the_recorded_count_request(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("get", "count_ch_exports_2023", match_params=COUNT_ONLY)
    result = tasks.get_counts(**CH_EXPORTS_2023)
    assert result.data == 32
    assert result.meta.source == "comtrade"
    assert result.meta.endpoint == "data/v1/get"
    assert result.meta.request == CH_EXPORTS_2023
    assert result.meta.published_at is None
    sent = route.calls.last.request
    assert sent.url.path == "/data/v1/get/C/A/HS"
    assert sent_query(route) == recorded_query(load_fixture(GET / "count_ch_exports_2023.json"))
    assert sent.headers["Ocp-Apim-Subscription-Key"] == "placeholder-for-fixture-replay"


def test_get_data_counts_first_then_fetches(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    counted = replay_fixture("get", "count_ch_exports_2023", match_params=COUNT_ONLY)
    fetched = replay_fixture("get", "ch_exports_2023")
    result = tasks.get_data(**CH_EXPORTS_2023)
    assert counted.call_count == 1
    assert fetched.call_count == 1
    order = [call.request.url.params.get("countOnly") for call in respx_mock.calls]
    assert order == ["true", None]
    assert sent_query(fetched) == recorded_query(load_fixture(GET / "ch_exports_2023.json"))
    assert result.meta.endpoint == "data/v1/get"
    assert result.meta.request == CH_EXPORTS_2023
    assert result.meta.published_at is None
    assert len(result.data) == 32
    total = next(
        row
        for row in result.data
        if (row.customs_code, row.mot_code, row.partner2_code) == ("C00", 0, 0)
    )
    assert total.primary_value == Decimal("419922543423.509")
    assert total.fobvalue == Decimal("419922543423.509")
    assert total.cifvalue is None
    assert total.reporter_code == 757
    assert total.partner_code == 0
    assert total.flow_code == "X"
    assert total.cmd_code == "TOTAL"
    assert total.period == "2023"
    assert total.ref_period_id == 20230101
    assert total.classification_code == "H6"
    assert total.is_original_classification is True
    assert total.is_reported is False
    assert total.is_aggregate is True
    assert total.reporter_desc is None
    assert all(isinstance(row.primary_value, Decimal) for row in result.data)
    first = result.data[0]
    assert (first.customs_code, first.mot_code) == ("C03", 9100)
    assert first.qty == Decimal("0.0")
    assert first.qty_unit_code == -1
    assert first.net_wgt is None
    assert first.gross_wgt == Decimal("0.0")
    assert first.is_net_wgt_estimated is False


def test_get_data_returns_empty_after_one_call_when_nothing_matches(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    counted = replay_fixture("get", "count_zero_ch_1900", match_params=COUNT_ONLY)
    result = tasks.get_data(**{**CH_EXPORTS_2023, "period": "1900"})
    assert result.data == []
    assert result.meta.request["period"] == "1900"
    assert len(respx_mock.calls) == counted.call_count == 1
    assert sent_query(counted)["countOnly"] == "true"


def test_get_data_refuses_over_the_limit_before_fetching(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    counted = replay_fixture("get", "count_over_limit", match_params=COUNT_ONLY)
    fetched = replay_fixture("get", "over_limit_max_records")
    with pytest.raises(QueryTooLarge) as info:
        tasks.get_data(
            "C", "A", "HS", partner_code="0", period="2022", cmd_code="AG4", flow_code="M"
        )
    assert info.value.count == 5_006_385
    assert info.value.limit == RECORD_LIMIT == 100_000
    assert info.value.bound is False
    message = str(info.value)
    assert "5,006,385" in message
    assert "Split by period (max 12 per call), then by reporter" in message
    assert not fetched.called
    assert len(respx_mock.calls) == counted.call_count == 1
    assert "reporterCode" not in sent_query(counted)


def test_query_too_large_is_an_invalid_request_for_http_too() -> None:
    assert issubclass(QueryTooLarge, InvalidRequestError)
    assert status_for(QueryTooLarge(200_000)) == 422


@pytest.mark.anyio
async def test_a_code_that_is_not_a_reporter_counts_zero_upstream(
    replay_fixture: ReplayFixture,
) -> None:
    """Layer 1: 756 is Switzerland's ISO numeric code, not a reporter; upstream counts 0."""
    replay_fixture("get", "count_not_a_reporter_756", match_params=COUNT_ONLY)
    response = await api.get_count_only(
        "C", "A", "HS", reporter_code="756", period="2023", partner_code="0", cmd_code="TOTAL",
        flow_code="X",
    )  # fmt: skip
    assert (response.count, response.error) == (0, "")


def test_a_code_that_is_not_a_reporter_is_refused_naming_the_reporter(
    respx_mock: respx.MockRouter,
) -> None:
    """The task refuses 756 before the call: Reporters.json has Switzerland as 757."""
    message = _refused(respx_mock, reporter_code="757,756")
    assert (
        "reporter_code '756' is not a UN Comtrade reporter code (Reporters.json); "
        "closest: '757' (Switzerland); list_reporters lists every code" in message
    )
    assert "'757' is not" not in message


def test_unknown_partner_codes_are_refused(respx_mock: respx.MockRouter) -> None:
    message = _refused(respx_mock, partner_code="0,9999", partner2_code="97")
    assert "partner_code '9999' is not a UN Comtrade partner code (partnerAreas.json)" in message
    assert "list_partners lists every code" in message
    assert "partner_code '0'" not in message
    assert (
        "partner2_code '97' is not a UN Comtrade partner code (partnerAreas.json); "
        "'97' (European Union) is a reporter code only" in message
    )


def test_world_is_a_partner_not_a_reporter(respx_mock: respx.MockRouter) -> None:
    message = _refused(respx_mock, reporter_code="0")
    assert "reporter_code '0' is not a UN Comtrade reporter code" in message
    assert "'0' (World) is a partner code only" in message


def test_every_member_of_an_area_list_is_checked() -> None:
    checked = validate_get(
        "C", "A", "HS", reporter_code="757,842,276,156", partner_code="0,276,756",
        partner2_code="0",
    )  # fmt: skip
    assert checked["reporter_code"] == "757,842,276,156"
    assert checked["partner_code"] == "0,276,756"
    with pytest.raises(InvalidRequestError) as info:
        validate_get("C", "A", "HS", reporter_code="757,999,842,1000")
    message = str(info.value)
    assert "reporter_code '999' is not" in message
    assert "reporter_code '1000' is not" in message


@pytest.mark.anyio
async def test_unknown_reporter_is_an_empty_answer_upstream(replay_fixture: ReplayFixture) -> None:
    """Layer 1: reporterCode 999 answers HTTP 200 with count 0 and no rows, not an error."""
    route = replay_fixture("get", "unknown_reporter")
    response = await api.get(
        "C", "A", "HS", reporter_code="999", period="2023", partner_code="0", cmd_code="TOTAL",
        flow_code="X",
    )  # fmt: skip
    assert (response.count, response.data, response.error) == (0, [], "")
    assert sent_query(route) == recorded_query(load_fixture(GET / "unknown_reporter.json"))


def test_invalid_key_is_an_auth_error(replay_fixture: ReplayFixture) -> None:
    replay_fixture("get", "invalid_key", match_params=COUNT_ONLY)
    with pytest.raises(AuthError) as info:
        tasks.get_counts(**CH_EXPORTS_2023)
    assert info.value.status == 401
    assert "invalid subscription key" in str(info.value)


@pytest.mark.anyio
async def test_max_records_caps_the_rows(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("get", "over_limit_max_records")
    response = await api.get(
        "C", "A", "HS", period="2022", partner_code="0", cmd_code="AG4", flow_code="M",
        max_records=5,
    )  # fmt: skip
    assert response.count == 5
    assert len(response.data) == 5
    assert sent_query(route)["maxRecords"] == "5"
    assert sent_query(route) == recorded_query(load_fixture(GET / "over_limit_max_records.json"))


@pytest.mark.anyio
async def test_wildcard_product_codes_are_counted_upstream(replay_fixture: ReplayFixture) -> None:
    replay_fixture("get", "count_cmd_code_wildcard", match_params=COUNT_ONLY)
    response = await api.get_count_only(
        "C", "A", "HS", reporter_code="757", period="2023", partner_code="0", cmd_code="27??",
        flow_code="X",
    )  # fmt: skip
    assert response.count == 113


def test_wildcards_pass_validation(replay_fixture: ReplayFixture) -> None:
    replay_fixture("get", "count_cmd_code_wildcard", match_params=COUNT_ONLY)
    assert tasks.get_counts(**{**CH_EXPORTS_2023, "cmd_code": "27??"}).data == 113


@pytest.mark.anyio
async def test_upstream_period_limit_is_an_invalid_request(replay_fixture: ReplayFixture) -> None:
    """Layer 1, past the task's own check: upstream refuses a 13th period with HTTP 400."""
    replay_fixture("get", "count_13_periods", match_params=COUNT_ONLY)
    with pytest.raises(InvalidRequestError, match="Maximum number of periods is 12"):
        await api.get_count_only(
            "C", "A", "HS", reporter_code="757", period=",".join(map(str, range(2010, 2023))),
            partner_code="0", cmd_code="TOTAL", flow_code="X",
        )  # fmt: skip


@pytest.mark.anyio
async def test_upstream_parameter_refusal_names_the_parameter(
    replay_fixture: ReplayFixture,
) -> None:
    """``BE5`` is in the spec's clCode enum, but upstream refuses it (HTTP 400)."""
    replay_fixture("get", "count_cl_code_be5", match_params=COUNT_ONLY)
    with pytest.raises(InvalidRequestError) as info:
        await api.get_count_only("C", "A", "BE5", reporter_code="757", period="2023")
    assert "Invalid parameter value" in str(info.value)
    assert "The field clCode is invalid" in str(info.value)


@pytest.mark.anyio
async def test_mif_is_accepted_upstream(replay_fixture: ReplayFixture) -> None:
    """The spec lists MIF, tradeRegimes.json does not; upstream answers 200, so it is packaged."""
    replay_fixture("get", "count_flow_code_mif", match_params=COUNT_ONLY)
    response = await api.get_count_only(
        "C", "A", "HS", reporter_code="757", period="2023", partner_code="0", cmd_code="TOTAL",
        flow_code="MIF",
    )  # fmt: skip
    assert (response.count, response.error) == (0, "")


def _rows(fixtures_dir: Path, case: str) -> list[dict[str, Any]]:
    """The raw ``data`` rows of a recorded ``data/v1/get`` answer."""
    fixture = load_fixture(fixtures_dir / "get" / f"{case}.json")
    rows: list[dict[str, Any]] = json.loads(fixture.response.body)["data"]
    return rows


TOTAL_ROW = ("C00", 0, 0)
"""customs_code, mot_code, partner2_code of the total row."""


def test_flow_code_xif_is_accepted_upstream(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("get", "count_flow_code_xif", match_params=COUNT_ONLY)
    assert tasks.get_counts(**{**CH_EXPORTS_2023, "flow_code": "XIF"}).data == 0
    assert sent_query(route) == recorded_query(load_fixture(GET / "count_flow_code_xif.json"))


def test_breakdown_mode_classic_returns_the_total_row_only(replay_fixture: ReplayFixture) -> None:
    counted = replay_fixture("get", "count_breakdown_mode_classic", match_params=COUNT_ONLY)
    fetched = replay_fixture("get", "ch_exports_2023_breakdown_mode_classic")
    result = tasks.get_data(**CH_EXPORTS_2023, breakdown_mode="classic")
    assert sent_query(counted) == recorded_query(
        load_fixture(GET / "count_breakdown_mode_classic.json")
    )
    assert sent_query(fetched) == recorded_query(
        load_fixture(GET / "ch_exports_2023_breakdown_mode_classic.json")
    )
    [row] = result.data
    assert (row.customs_code, row.mot_code, row.partner2_code) == TOTAL_ROW
    assert row.primary_value == Decimal("419922543423.509")


def test_breakdown_mode_plus_is_upstreams_default(
    replay_fixture: ReplayFixture, fixtures_dir: Path
) -> None:
    """``plus`` counts 32 like the omitted parameter, and returns the same rows."""
    replay_fixture("get", "count_breakdown_mode_plus", match_params=COUNT_ONLY)
    fetched = replay_fixture("get", "ch_exports_2023_breakdown_mode_plus")
    result = tasks.get_data(**CH_EXPORTS_2023, breakdown_mode="plus")
    assert sent_query(fetched) == recorded_query(
        load_fixture(GET / "ch_exports_2023_breakdown_mode_plus.json")
    )
    assert len(result.data) == 32
    plus = _rows(fixtures_dir, "ch_exports_2023_breakdown_mode_plus")
    assert plus == _rows(fixtures_dir, "ch_exports_2023")


def test_pinning_the_totals_returns_one_row(
    replay_fixture: ReplayFixture, fixtures_dir: Path
) -> None:
    """partner2Code 0, customsCode C00 and motCode 0: one row, the same as ``classic``."""
    replay_fixture("get", "count_ch_exports_2023_totals", match_params=COUNT_ONLY)
    fetched = replay_fixture("get", "ch_exports_2023_totals")
    result = tasks.get_data(**CH_EXPORTS_2023, partner2_code="0", customs_code="C00", mot_code="0")
    assert sent_query(fetched) == recorded_query(load_fixture(GET / "ch_exports_2023_totals.json"))
    [row] = result.data
    assert (row.customs_code, row.mot_code, row.partner2_code) == TOTAL_ROW
    assert _rows(fixtures_dir, "ch_exports_2023_totals") == _rows(
        fixtures_dir, "ch_exports_2023_breakdown_mode_classic"
    )


def test_partner2_code_0_counts_what_omitting_it_counts(
    replay_fixture: ReplayFixture, fixtures_dir: Path
) -> None:
    replay_fixture("get", "count_partner2_code_0", match_params=COUNT_ONLY)
    assert tasks.get_counts(**CH_EXPORTS_2023, partner2_code="0").data == 32
    assert {row["partner2Code"] for row in _rows(fixtures_dir, "ch_exports_2023")} == {0}


AG2 = {**CH_EXPORTS_2023, "cmd_code": "AG2"}


def test_ag2_counts_every_chapter_and_breakdown(replay_fixture: ReplayFixture) -> None:
    replay_fixture("get", "count_ch_exports_2023_ag2", match_params=COUNT_ONLY)
    assert tasks.get_counts(**AG2).data == 1338


@pytest.mark.parametrize(
    ("aggregate_by", "case", "partner_code"),
    [
        ("cmdCode", "aggregate_by_cmd_code", 0),
        ("partnerCode,cmdCode", "aggregate_by_partner_code_cmd_code", -2),
    ],
)
def test_aggregate_by_collapses_the_named_parameters_into_minus_2(
    replay_fixture: ReplayFixture, aggregate_by: str, case: str, partner_code: int
) -> None:
    """Over the 1,338 AG2 records: one row per remaining breakdown; the count matches."""
    replay_fixture("get", f"count_{case}", match_params=COUNT_ONLY)
    fetched = replay_fixture("get", f"ch_exports_2023_ag2_{case}")
    assert tasks.get_counts(**AG2, aggregate_by=aggregate_by).data == 32
    result = tasks.get_data(**AG2, aggregate_by=aggregate_by)
    assert sent_query(fetched) == recorded_query(
        load_fixture(GET / f"ch_exports_2023_ag2_{case}.json")
    )
    assert len(result.data) == 32
    assert {row.cmd_code for row in result.data} == {"-2"}
    assert {row.partner_code for row in result.data} == {partner_code}
    assert {row.classification_code for row in result.data} == {"GG"}
    assert {(row.aggr_level, row.is_leaf, row.cmd_desc) for row in result.data} == {
        (None, None, None)
    }
    total = next(
        row for row in result.data
        if (row.customs_code, row.mot_code, row.partner2_code) == TOTAL_ROW
    )  # fmt: skip
    assert total.primary_value == Decimal("419922543423.5139")


@pytest.mark.anyio
async def test_include_desc_fills_the_descriptions(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("get", "ch_exports_2023_include_desc")
    response = await api.get(
        "C", "A", "HS", reporter_code="757", period="2023", partner_code="0", cmd_code="TOTAL",
        flow_code="X", include_desc=True,
    )  # fmt: skip
    assert sent_query(route) == recorded_query(
        load_fixture(GET / "ch_exports_2023_include_desc.json")
    )
    total = next(
        row for row in response.data
        if (row.customs_code, row.mot_code, row.partner2_code) == TOTAL_ROW
    )  # fmt: skip
    assert (total.reporter_iso, total.reporter_desc) == ("CHE", "Switzerland")
    assert (total.partner_iso, total.partner_desc) == ("W00", "World")
    assert (total.partner2_iso, total.partner2_desc) == ("W00", "World")
    assert (total.flow_desc, total.cmd_desc) == ("Export", "All Commodities")
    assert (total.customs_desc, total.mot_desc) == ("TOTAL CPC", "TOTAL MOT")
    assert (total.qty_unit_abbr, total.alt_qty_unit_abbr) == ("N/A", "N/A")
    assert (total.aggr_level, total.is_leaf) == (0, False)
    assert all(row.reporter_desc == "Switzerland" for row in response.data)


@pytest.mark.parametrize(
    ("cmd_code", "case", "count"),
    [("999999", "count_cmd_code_999999", 10), ("999998", "count_cmd_code_absent", 0)],
)
def test_product_codes_upstream_does_not_have_count_zero(
    replay_fixture: ReplayFixture, cmd_code: str, case: str, count: int
) -> None:
    """999999 is HS's "Commodities not specified according to kind"; 999998 is not in HS.json."""
    replay_fixture("get", case, match_params=COUNT_ONLY)
    assert tasks.get_counts(**{**CH_EXPORTS_2023, "cmd_code": cmd_code}).data == count


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("case", "overrides", "field"),
    [
        ("count_period_malformed", {"period": "2023-01"}, "period"),
        ("count_flow_code_unknown", {"flow_code": "Z"}, "flowCode"),
    ],
)
async def test_upstream_refuses_malformed_values_naming_the_field(
    replay_fixture: ReplayFixture, case: str, overrides: dict[str, str], field: str
) -> None:
    """Layer 1, past the task's own checks (which refuse both before any call)."""
    replay_fixture("get", case, match_params=COUNT_ONLY)
    query: dict[str, Any] = {
        "reporter_code": "757", "period": "2023", "partner_code": "0", "cmd_code": "TOTAL",
        "flow_code": "X", **overrides,
    }  # fmt: skip
    with pytest.raises(InvalidRequestError) as info:
        await api.get_count_only("C", "A", "HS", **query)
    assert f"Invalid parameter value (The field {field} is invalid)" in str(info.value)
    with pytest.raises(InvalidRequestError):
        validate_get("C", "A", "HS", **query)


SERVICES_2023 = {**CH_EXPORTS_2023, "type_code": "S", "cl_code": "EB10", "cmd_code": "200"}


@pytest.mark.parametrize(
    ("cl_code", "cmd_code", "case", "count"),
    [
        ("EB10", "200", "count_cl_code_eb10", 1),
        ("EB10", "TOTAL", "count_services_eb10_total", 0),
        ("EB02", "200", "count_cl_code_eb02", 1),
        ("EB10S", "S", "count_cl_code_eb10s", 0),
        ("EB", "200", "count_cl_code_eb", 0),
        ("EB", "TOTAL", "count_services_eb_total", 0),
    ],
)
def test_services_take_their_files_total_code_not_total(
    replay_fixture: ReplayFixture, cl_code: str, cmd_code: str, case: str, count: int
) -> None:
    """EB10 counts its one row under 200 and none under TOTAL; combined EB counts none."""
    route = replay_fixture("get", case, match_params=COUNT_ONLY)
    query = {**SERVICES_2023, "cl_code": cl_code, "cmd_code": cmd_code}
    assert tasks.get_counts(**query).data == count
    assert route.calls.last.request.url.path == f"/data/v1/get/S/A/{cl_code}"


def test_services_rows(replay_fixture: ReplayFixture) -> None:
    replay_fixture("get", "count_cl_code_eb10", match_params=COUNT_ONLY)
    replay_fixture("get", "services_ch_exports_2023_eb10")
    [row] = tasks.get_data(**SERVICES_2023).data
    assert (row.type_code, row.classification_code, row.cmd_code) == ("S", "EB10", "200")
    assert (row.mos_code, row.customs_code, row.mot_code, row.partner2_code) == ("0", "C00", 0, 0)
    assert row.cifvalue == row.primary_value == Decimal("165139886737.593")
    assert row.fobvalue is None
    assert row.is_reported is True


def test_mos_code_is_accepted_upstream_but_not_a_parameter_here(fixtures_dir: Path) -> None:
    """Not in the spec: upstream filters on 0 and 1 and refuses ModeOfSupply.json's "Mode 1"."""
    answers = {}
    for case in ["eb10_mos_code_0", "eb10_mos_code_1", "eb10_mos_code_mode_1", "eb_mos_code_0"]:
        fixture = load_fixture(fixtures_dir / "get" / f"count_services_{case}.json")
        assert "mosCode=" in fixture.request.url
        body = json.loads(fixture.response.body)
        answers[case] = (fixture.response.status, body.get("count"))
    assert answers == {
        "eb10_mos_code_0": (200, 1), "eb10_mos_code_1": (200, 0),
        "eb10_mos_code_mode_1": (400, None), "eb_mos_code_0": (200, 0),
    }  # fmt: skip
    assert "mos_code" not in inspect.signature(tasks.get_data).parameters
    mos_code = PackagedList.load(PACKAGE, "mosCode")
    assert mos_code.note is not None
    assert mos_code.note.startswith("The ids of ModeOfSupply.json, not proven parameter values")
    assert enums.MosCode.__doc__ == "Values of ``mosCode`` (fetched 2026-10-23)."


def _refused(respx_mock: respx.MockRouter, **overrides: str) -> str:
    with pytest.raises(InvalidRequestError) as info:
        tasks.get_data(**{**CH_EXPORTS_2023, **overrides})
    assert not respx_mock.calls, "validation happens before any call"
    return str(info.value)


def test_thirteen_periods_are_refused_before_any_call(respx_mock: respx.MockRouter) -> None:
    message = _refused(respx_mock, period=",".join(str(year) for year in range(2010, 2023)))
    assert "period has 13 values" in message
    assert "at most 12" in message


def test_unknown_flow_code_names_the_closest_value(respx_mock: respx.MockRouter) -> None:
    message = _refused(respx_mock, flow_code="X,XX")
    assert "flow_code 'XX' is not a UN Comtrade flowCode value; closest: 'X'" in message
    assert "Valid values: M, X, DX, FM, MIP, MOP, RM, RX, XIP, XOP, MIF, XIF" in message


def test_flow_codes_the_spec_adds_pass_validation(replay_fixture: ReplayFixture) -> None:
    replay_fixture("get", "count_flow_code_mif", match_params=COUNT_ONLY)
    assert tasks.get_counts(**{**CH_EXPORTS_2023, "flow_code": "MIF"}).data == 0
    assert validate_get("C", "A", "HS", flow_code="XIF,mif")["flow_code"] == "XIF,mif"


def test_unknown_cl_code_names_the_closest_value(respx_mock: respx.MockRouter) -> None:
    message = _refused(respx_mock, cl_code="BE5")
    assert "cl_code 'BE5' is not a UN Comtrade clCode value; closest: 'BE'" in message


def test_malformed_product_codes_are_refused(respx_mock: respx.MockRouter) -> None:
    message = _refused(respx_mock, cmd_code="0901,coffee")
    assert "cmd_code 'coffee' is not a HS product code" in message
    assert "cmd_code '0901'" not in message


def test_area_codes_and_periods_are_checked_by_shape(respx_mock: respx.MockRouter) -> None:
    message = _refused(respx_mock, reporter_code="CH", partner_code="0, 276", period="2023-01")
    assert "reporter_code 'CH' is not a numeric UN Comtrade area code" in message
    assert "partner_code '0, 276' must be values separated by commas, without spaces" in message
    assert "period '2023-01' is neither a year (YYYY" in message


@pytest.mark.parametrize(
    ("cl_code", "cmd_code"),
    [
        ("HS", "TOTAL"),
        ("H6", "AG6"),
        ("HS", "ag2"),
        ("HS", "01,0901,090111"),
        ("HS", "27*"),
        ("SS", "001X,0011X"),
        ("B5", "111"),
        ("EB02", "205X"),
        ("EB10", "10.1.1"),
        ("EB10S", "SC11z"),
    ],
)
def test_product_code_shapes_from_the_classification_files(cl_code: str, cmd_code: str) -> None:
    type_code = "S" if cl_code.startswith("EB") else "C"
    checked = validate_get(type_code, "A", cl_code, cmd_code=cmd_code)
    assert checked == {"type_code": type_code, "freq_code": "A", "cl_code": cl_code,
                       "cmd_code": cmd_code}  # fmt: skip


def test_case_insensitive_codes_pass_unchanged() -> None:
    checked = validate_get("C", "M", "HS", flow_code="x,M", customs_code="c00", period="202305")
    assert checked["flow_code"] == "x,M"
    assert checked["customs_code"] == "c00"


def test_every_list_parameter_is_checked() -> None:
    with pytest.raises(InvalidRequestError) as info:
        validate_get(
            "G", "Y", "HS", mot_code="9", customs_code="C16", aggregate_by="cmdcode",
            breakdown_mode="full",
        )  # fmt: skip
    message = str(info.value)
    for fragment in [
        "type_code 'G' is not a UN Comtrade typeCode value",
        "freq_code 'Y' is not a UN Comtrade freqCode value",
        "mot_code '9' is not a UN Comtrade motCode value",
        "customs_code 'C16' is not a UN Comtrade customsCode value",
        "aggregate_by 'cmdcode' is not a UN Comtrade aggregateBy value; closest: 'cmdCode'",
        "breakdown_mode 'full' is not a UN Comtrade breakdownMode value",
    ]:
        assert fragment in message


@pytest.mark.parametrize("name", [*PACKAGED_LISTS, *PACKAGED_TABLES])
def test_every_packaged_list_is_upstreams_records_with_their_provenance(name: str) -> None:
    """Structure, not counts: each refresh changes the sizes and writes the full fetch time."""
    packaged = PackagedList.load(PACKAGE, name)
    assert packaged.param == name
    assert packaged.endpoint.startswith(("files/v1/app/reference/", "files/v1/app/apim/"))
    assert packaged.fetched.tzinfo is UTC
    assert packaged.fetched.date() == date(2026, 10, 23)
    assert packaged.records
    if name in PACKAGED_LISTS:
        assert all(list(record) == [name] for record in packaged.records), name
        assert all(isinstance(record[name], str) for record in packaged.records), name
    else:
        model = PACKAGED_TABLES[name]
        for row, record in zip(
            packaged.parse(model, source="comtrade"), packaged.records, strict=True
        ):
            dumped = row.dump_upstream()
            assert set(record) <= set(dumped), "every key is a column of the row model"
            assert {key: dumped[key] for key in record} == record, "with the model's types"
        assert packaged.endpoint == f"files/v1/app/reference/{name}.json"


def test_the_spec_lists_name_the_operation_they_were_read_from() -> None:
    for name in ["typeCode", "freqCode", "breakdownMode", "aggregateBy"]:
        packaged = PackagedList.load(PACKAGE, name)
        assert packaged.endpoint == "files/v1/app/apim/comtrade.json", name
        assert packaged.note is not None
        assert packaged.note.startswith(
            "Read from docs/upstream/apidocs/comtrade.json, the snapshot of "
            "files/v1/app/apim/comtrade.json fetched 2026-10-23: operation get, the "
        ), name


def test_enums_match_the_packaged_lists() -> None:
    for name in PACKAGED_LISTS:
        cls = getattr(enums, name[0].upper() + name[1:])
        packaged = PackagedList.load(PACKAGE, name)
        assert [member.value for member in cls] == [r[name] for r in packaged.records], name
        assert cls.__doc__ == f"Values of ``{name}`` (fetched {packaged.fetched:%Y-%m-%d}).", name
    assert enums.FlowCode.X.value == "X"
    assert enums.MotCode._0.value == "0"
    assert enums.ClCode.EB10S.value == "EB10S"
    assert enums.FlowCode.XIF.value == "XIF"
    assert [member.value for member in enums.MosCode] == ["0", "Mode 1", "Mode 2", "Mode 3",
                                                          "Mode 4"]  # fmt: skip
    assert enums.QtyUnitCode("-1").name == "_1"
    assert enums.QtyUnitCode("8").name == "_8"
    assert len(enums.QtyUnitCode) == 41


EXCEPTION = re.compile(r"(?:^|\. )([A-Z0-9]+) (added|left out|removed|kept): (.+?\))(?=\.(?: |$))")
"""One exception sentence of a reconciled list's ``note``: value, decision, evidence."""


def _exceptions(name: str) -> dict[str, tuple[str, str]]:
    note = PackagedList.load(PACKAGE, name).note or ""
    return {value: (decision, evidence) for value, decision, evidence in EXCEPTION.findall(note)}


def test_list_exceptions_rest_on_recorded_answers(fixtures_dir: Path) -> None:
    """Every clCode value rests on a recorded count; flowCode's spec additions too.

    clCode is ListofReferences plus what upstream accepted, minus what it refused, each
    exception a sentence of the list's note. H6 answered HTTP 500 to all five tries (two
    reporters, two cmdCodes) and stays, unsettled.
    """
    cl_code = _exceptions("clCode")
    values = [record["clCode"] for record in PackagedList.load(PACKAGE, "clCode").records]
    decisions = {value: decision for value, (decision, _) in cl_code.items()}
    assert decisions == {
        "BE": "added", "BE5": "left out", "TM": "added",
        **{value: "kept" for value in values if value not in {"BE", "TM"}},
    }  # fmt: skip
    assert set(values) == set(decisions) - {"BE5"}
    assert "BE5" not in values
    flow_code = _exceptions("flowCode")
    assert {value: decision for value, (decision, _) in flow_code.items()} == {
        "MIF": "added",
        "XIF": "added",
    }
    cited = re.compile(r"tests/fixtures/get/(\S+?\.json), HTTP (\d+)")
    for value, (decision, evidence) in [*cl_code.items(), *flow_code.items()]:
        recorded = cited.findall(evidence)
        assert recorded, value
        statuses = set()
        for name, status in recorded:
            fixture = load_fixture(fixtures_dir / "get" / name)
            assert fixture.response.status == int(status), name
            statuses.add(fixture.response.status)
        if "accepted it" in evidence:
            assert 200 in statuses, value
            assert decision in {"added", "kept"}, value
        elif "refused it" in evidence:
            assert statuses == {400}, value
            assert decision in {"left out", "removed"}, value
        else:
            assert (value, statuses) == ("H6", {500})
    assert len(cited.findall(cl_code["H6"][1])) == 5
    added = {value for value, (decision, _) in cl_code.items() if decision == "added"}
    assert set(CL_CODES_FROM_SPEC) == added, "classification_files drops exactly these"


@pytest.mark.anyio
async def test_spec_cl_codes_upstream_accepts(replay_fixture: ReplayFixture) -> None:
    replay_fixture("get", "count_cl_code_tm", match_params=COUNT_ONLY)
    assert (await api.get_count_only("C", "A", "TM", reporter_code="757")).count == 1
    assert validate_get("C", "A", "BE", cmd_code="TOTAL")["cl_code"] == "BE"


@pytest.mark.anyio
async def test_a_server_error_is_retried_and_each_retry_is_a_call(
    replay_fixture: ReplayFixture,
) -> None:
    """Upstream answered a count on H6 with HTTP 500; core retries it, every attempt a call."""
    route = replay_fixture("get", "count_cl_code_h6", match_params=COUNT_ONLY)
    with pytest.raises(UpstreamError) as info:
        await api.get_count_only("C", "A", "H6", reporter_code="757", period="2023")
    assert info.value.status == 500
    assert "Something went wrong" in str(info.value)
    assert route.call_count == config.retry.max_attempts == 4


def test_enum_members_are_accepted_as_arguments(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("get", "count_ch_exports_2023", match_params=COUNT_ONLY)
    result = tasks.get_counts(
        enums.TypeCode.C,
        enums.FreqCode.A,
        enums.ClCode.HS,
        reporter_code="757",
        partner_code="0",
        period="2023",
        cmd_code="TOTAL",
        flow_code=enums.FlowCode.X,
    )
    assert result.data == 32
    assert sent_query(route)["flowCode"] == "X"


def test_replay_never_sends_the_key_from_the_shell(
    replay_fixture: ReplayFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(API_KEY_ENV, "dummy-value-from-the-shell")
    route = replay_fixture("get", "count_ch_exports_2023", match_params=COUNT_ONLY)
    tasks.get_counts(**CH_EXPORTS_2023)
    sent = route.calls.last.request.headers["Ocp-Apim-Subscription-Key"]
    assert sent == "placeholder-for-fixture-replay"


@pytest.mark.anyio
async def test_reference_files_are_fetched_without_the_key(respx_mock: respx.MockRouter) -> None:
    """Constructed route, not a fixture: what matters is the request, not upstream's answer."""
    route = respx_mock.get(
        "https://comtradeapi.un.org/files/v1/app/reference/tradeRegimes.json"
    ).mock(return_value=httpx.Response(200, json={"results": [{"id": "X", "text": "Export"}]}))
    rows = (await api.reference("tradeRegimes.json", ReferenceCode)).rows
    assert [row.id for row in rows] == ["X"]
    assert "Ocp-Apim-Subscription-Key" not in route.calls.last.request.headers
    assert "subscription-key" not in sent_query(route)


def test_calls_are_spaced_one_and_a_half_seconds_apart() -> None:
    assert config.rate_limit is RATE_LIMIT
    assert (RATE_LIMIT.per_minute, RATE_LIMIT.capacity) == (40, 1)
    assert 1 / RATE_LIMIT.per_second == 1.5


@pytest.mark.anyio
async def test_upstreams_rate_limit_answer_is_a_rate_limit_error(
    replay_fixture: ReplayFixture,
) -> None:
    """Recorded when calls were spaced exactly 1.0 s apart; core retries it after 1 s."""
    route = replay_fixture("get", "count_rate_limited", match_params=COUNT_ONLY)
    once = AsyncClient(dataclasses.replace(config, retry=RetryPolicy(max_attempts=1)), auth=auth)
    with pytest.raises(RateLimitError) as info:
        await once.get_json(
            "/data/v1/get/C/A/H1", params={"reporterCode": "757", "countOnly": "true"}
        )
    assert info.value.retry_after == 1.0
    assert "Rate limit is exceeded" in str(info.value)
    assert route.call_count == 1


def test_read_timeout_is_three_minutes_the_rest_family_defaults() -> None:
    assert config.timeouts is TIMEOUTS
    assert (TIMEOUTS.connect, TIMEOUTS.read, TIMEOUTS.write, TIMEOUTS.pool) == (10, 180, 10, 10)
    assert config.retry.max_attempts == 4


def _response(status: int, body: object) -> httpx.Response:
    request = httpx.Request("GET", "https://comtradeapi.un.org/data/v1/get/C/A/HS")
    return httpx.Response(status, json=body, request=request)


def test_classify_maps_the_quota_answer_to_a_rate_limit() -> None:
    """Not observed (never provoked): API Management's standard quota text, per the spec's 403."""
    error = classify(
        _response(
            403,
            {
                "statusCode": 403,
                "message": "Out of call volume quota. Quota will be replenished in 05:12:34.",
            },
        )
    )
    assert isinstance(error, RateLimitError)
    assert error.retry_after == 5 * 3600 + 12 * 60 + 34
    assert "500 calls per day" in str(error)


def test_quota_reset_is_none_without_a_replenish_time() -> None:
    assert _quota_reset("Out of call volume quota.") is None
    assert _quota_reset("Quota will be replenished in 00:00:07.") == 7.0
    error = classify(_response(403, {"statusCode": 403, "message": "Out of call volume quota."}))
    assert isinstance(error, RateLimitError)
    assert error.retry_after is None


def test_classify_leaves_other_answers_to_the_core_mapping() -> None:
    assert classify(_response(403, {"error": "User not allowed", "details": None})) is None
    assert classify(_response(401, {"statusCode": 401, "message": "Access denied"})) is None
    assert classify(_response(200, {"elapsedTime": "0.1 secs", "count": 0, "data": []})) is None
    assert classify(_response(400, "not an ErrorResponse")) is None


QUOTA_SPENT = {
    "statusCode": 403,
    "message": "Out of call volume quota. Quota will be replenished in 05:12:34.",
}
"""API Management's standard quota answer; not observed (never provoked)."""


def test_the_policy_reads_the_quota_answer_and_no_other() -> None:
    """The policy's ``spent`` hook: the 403's replenish time, nothing from other answers."""
    assert policy.spent is not None
    assert (policy.limit_header, policy.remaining_header, policy.window) == (None, None, 86_400.0)
    assert policy.spent(_response(403, QUOTA_SPENT)) == 5 * 3600 + 12 * 60 + 34
    assert policy.spent(_response(403, {"error": "User not allowed"})) is None
    assert policy.spent(_response(200, {"message": "replenished in 01:00:00"})) is None
    assert config.observe == policy.observe
    assert config.before_request == policy.before_request


@pytest.mark.rate_limited
def test_a_spent_daily_quota_refuses_the_next_call_before_sending(
    respx_mock: respx.MockRouter,
) -> None:
    """After the quota answer the next call is refused without a request (ADR-0010).

    Constructed route, not a fixture: the answer was never observed, and never provoked.
    Marked ``rate_limited``, since the plugin turns the policy's pause off otherwise.
    """
    route = respx_mock.get(f"{BASE_URL}/data/v1/get/C/A/HS").mock(
        return_value=httpx.Response(403, json=QUOTA_SPENT)
    )
    with pytest.raises(RateLimitError) as answered:
        tasks.get_counts(**CH_EXPORTS_2023)
    assert answered.value.retry_after == 5 * 3600 + 12 * 60 + 34
    snapshot = policy.snapshot()
    assert snapshot is not None
    assert snapshot.remaining == 0
    with pytest.raises(RateLimitError) as refused:
        tasks.get_counts(**CH_EXPORTS_2023)
    assert "nothing was sent for GET /data/v1/get/C/A/HS" in str(refused.value)
    assert refused.value.retry_after is not None
    assert 5 * 3600 < refused.value.retry_after <= 5 * 3600 + 12 * 60 + 34
    assert route.call_count == 1


def test_the_list_tasks_have_caps_of_their_own() -> None:
    """ADR-0016: the two tables whole, a classification with a note that says to search."""
    tables = ResultCap(max_rows=400, max_bytes=100_000)
    assert tasks.MCP_CAPS["list_reporters"] == tasks.MCP_CAPS["list_partners"] == tables
    commodities = tasks.MCP_CAPS["list_commodities"]
    assert (commodities.max_rows, commodities.max_bytes) == (400, 100_000)
    assert commodities.note is not None
    assert "search" in commodities.note
    assert set(tasks.MCP_CAPS) <= set(tasks.__all__)
    assert not tasks.BULK_TASKS


@pytest.mark.anyio
async def test_mcp_tool_call_end_to_end(replay_fixture: ReplayFixture) -> None:
    replay_fixture("get", "count_ch_exports_2023", match_params=COUNT_ONLY)
    replay_fixture("get", "ch_exports_2023")
    payload = await mcp_call(server, "comtrade_get_data", CH_EXPORTS_2023)
    assert len(payload["data"]) == 32
    total = next(
        row
        for row in payload["data"]
        if (row["customs_code"], row["mot_code"], row["partner2_code"]) == ("C00", 0, 0)
    )
    assert total["primary_value"] == 419922543423.509
    assert total["reporter_code"] == 757
    assert payload["meta"]["endpoint"] == "data/v1/get"
    assert payload["meta"]["request"] == CH_EXPORTS_2023
    assert payload["meta"]["published_at"] is None
    counted = await mcp_call(server, "comtrade_get_counts", CH_EXPORTS_2023)
    assert counted["data"] == 32
    with pytest.raises(AssertionError, match=r"InvalidRequestError.*closest: 'X'"):
        await mcp_call(server, "comtrade_get_counts", {**CH_EXPORTS_2023, "flow_code": "XX"})


def test_http_route_end_to_end(replay_fixture: ReplayFixture) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from xippios.comtrade.http import router

    replay_fixture("get", "count_ch_exports_2023", match_params=COUNT_ONLY)
    replay_fixture("get", "ch_exports_2023")
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as http:
        answer = http.get("/comtrade/get_counts", params=CH_EXPORTS_2023)
        assert answer.status_code == 200
        assert answer.json()["data"] == 32
        rows = http.get("/comtrade/get_data", params=CH_EXPORTS_2023).json()["data"]
        assert len(rows) == 32
        assert rows[0]["primary_value"] == 5205025990.437
        assert rows[0]["customs_code"] == "C03"
        refused = http.get("/comtrade/get_counts", params={**CH_EXPORTS_2023, "flow_code": "XX"})
        assert refused.status_code == 422


# Reference lists: reporters and partners are packaged, commodities fetched keyless.


def test_list_reporters_returns_the_packaged_table(respx_mock: respx.MockRouter) -> None:
    result = tasks.list_reporters()
    assert not respx_mock.calls, "packaged: no upstream call"
    assert len(result.data) == 255
    assert result.meta.endpoint == "files/v1/app/reference/Reporters.json"
    assert result.meta.retrieved_at == PackagedList.load(PACKAGE, "Reporters").fetched
    assert result.meta.retrieved_at == datetime(2026, 10, 23, tzinfo=UTC)
    assert result.meta.vintage is None
    assert result.meta.published_at is None
    assert result.meta.request == {}
    by_code = {row.reporter_code: row for row in result.data}
    switzerland = by_code[757]
    assert (switzerland.text, switzerland.reporter_note) == (
        "Switzerland",
        "Switzerland, Liechtenstein",
    )
    assert (switzerland.reporter_code_iso_alpha2, switzerland.reporter_code_iso_alpha3) == (
        "CH",
        "CHE",
    )
    assert switzerland.entry_effective_date == datetime(1900, 1, 1)
    assert switzerland.entry_expired_date is None
    assert switzerland.is_group is False
    assert 756 not in by_code
    assert {842, 276, 156} <= set(by_code)
    assert sorted(code for code, row in by_code.items() if row.is_group) == [97, 490, 975]
    assert all(isinstance(row.entry_effective_date, datetime) for row in result.data)
    assert sum(row.entry_expired_date is not None for row in result.data) == 33
    assert all(row.id == row.reporter_code for row in result.data)


def test_list_partners_returns_the_packaged_table(respx_mock: respx.MockRouter) -> None:
    result = tasks.list_partners()
    assert not respx_mock.calls, "packaged: no upstream call"
    assert len(result.data) == 310
    assert result.meta.endpoint == "files/v1/app/reference/partnerAreas.json"
    assert result.meta.retrieved_at == PackagedList.load(PACKAGE, "partnerAreas").fetched
    assert result.meta.vintage is None
    assert result.meta.published_at is None
    by_code = {row.partner_code: row for row in result.data}
    world = by_code[0]
    assert (world.text, world.partner_code_iso_alpha3, world.is_group) == ("World", "W00", True)
    assert world.partner_code_iso_alpha2 is None
    assert by_code[757].partner_desc == "Switzerland"
    assert by_code[756].partner_desc == "Switzerland "  # upstream's trailing space, kept
    assert by_code[756].partner_note is None


def _table[M: UpstreamModel](name: str, model: type[M]) -> list[M]:
    return PackagedList.load(PACKAGE, name).parse(model, source="comtrade")


def test_reporters_and_partners_share_one_code_space() -> None:
    """A code in both tables is the same area; World and others are partners only."""
    reporters = {row.reporter_code: row for row in _table("Reporters", Reporter)}
    partners = {row.partner_code: row for row in _table("partnerAreas", PartnerArea)}
    assert set(reporters) - set(partners) == {97, 975}
    assert len(set(partners) - set(reporters)) == 57
    assert {0, 756, 899} <= set(partners) - set(reporters)
    for code in set(reporters) & set(partners):
        assert reporters[code].reporter_code_iso_alpha3 == partners[code].partner_code_iso_alpha3
    iso = {row.country_area_code: row.iso3 for row in _table(
        "country_area_code_iso", CountryAreaCodeIso)}  # fmt: skip
    assert set(iso) == set(reporters) | set(partners)
    assert (iso[756], iso[757], iso[0]) == ("CHE", "CHE", "W00")


def test_trade_data_items_describe_the_record_columns() -> None:
    items = {row.data_item: row for row in _table("TradeDataItems", TradeDataItem)}
    assert len(items) == 50
    primary = items["primaryValue"]
    assert primary.description.startswith("Primary trade values")
    assert primary.is_in_data_api_commodity is True
    assert items["mosCode"].is_in_data_api_services is True


def test_classification_files_are_the_cmd_categories_of_list_of_references() -> None:
    index = json.loads((UPSTREAM / "reference" / "ListofReferences.json").read_text("utf-8-sig"))
    categories = [row["category"] for row in index["results"]]
    expected = [name.removeprefix("cmd:") for name in categories if name.startswith("cmd:")]
    assert list(classification_files()) == expected
    assert "BE" not in classification_files()
    assert "TM" not in classification_files()


def test_list_commodities_fetches_the_file_without_the_key(
    replay_fixture: ReplayFixture,
) -> None:
    route = replay_fixture("reference", "b4")
    before = datetime.now(UTC)
    result = tasks.list_commodities("B4")
    after = datetime.now(UTC)
    assert len(result.data) == 30
    assert result.meta.endpoint == "files/v1/app/reference/B4.json"
    assert result.meta.request == {"cl_code": "B4"}
    assert_time_between(result.meta.retrieved_at, before, after)
    assert result.meta.published_at is None
    assert result.meta.vintage is None
    total = result.data[0]
    assert (total.id, total.parent, total.is_leaf, total.aggr_level) == ("TOTAL", "#", False, 0)
    assert total.text == "Total of all BEC4 categories"
    leaves = [row for row in result.data if row.is_leaf]
    assert leaves
    assert all(row.aggr_level and row.aggr_level > 0 for row in leaves)
    assert all(row.standard_unit_abbr is None and row.cmd_code is None for row in result.data)
    sent = route.calls.last.request
    assert "Ocp-Apim-Subscription-Key" not in sent.headers


def test_list_commodities_keeps_the_file_for_the_process(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("reference", "b4")
    first = tasks.list_commodities("B4")
    second = tasks.list_commodities("B4")
    assert route.call_count == 1
    assert second.data == first.data
    assert second.meta.retrieved_at <= first.meta.retrieved_at, "stored before it was read"


def test_a_cached_reference_file_was_retrieved_when_it_was_stored(
    respx_mock: respx.MockRouter, fixtures_dir: Path
) -> None:
    """On a cache hit ``retrieved_at`` is the time the entry was stored (ADR-0015, decision 5).

    The plugin empties every ``MemoryCache`` around an offline test, so the test fills it:
    the recorded ``B4.json``, stored at a time no call could have taken.
    """
    stored = datetime(2026, 10, 23, 8, 0, tzinfo=UTC)
    recorded = load_fixture(fixtures_dir / "reference" / "b4.json").response
    assert config.cache is not None
    config.cache.set(
        cache_key("GET", httpx.URL(f"{BASE_URL}/files/v1/app/reference/B4.json")),
        CachedResponse(
            status=recorded.status,
            headers=tuple(recorded.headers),
            content=recorded.body.encode(),
            stored_at=stored.timestamp(),
        ),
    )
    result = tasks.list_commodities("B4")
    assert not respx_mock.calls, "answered from the cache"
    assert result.meta.retrieved_at == stored
    assert len(result.data) == 30


def test_the_cache_keeps_the_reference_files_and_nothing_else(
    replay_fixture: ReplayFixture,
) -> None:
    """One client: ``cache_filter`` admits the public reference files only (ADR-0015)."""
    keeps = config.cache_filter
    assert keeps is not None
    assert keeps(httpx.Request("GET", f"{BASE_URL}/files/v1/app/reference/HS.json"))
    assert not keeps(httpx.Request("GET", f"{BASE_URL}/data/v1/get/C/A/HS"))
    route = replay_fixture("get", "count_ch_exports_2023", match_params=COUNT_ONLY)
    tasks.get_counts(**CH_EXPORTS_2023)
    tasks.get_counts(**CH_EXPORTS_2023)
    assert route.call_count == 2, "a data call is never answered from the cache"


def test_services_classifications_have_no_leaf_or_level(replay_fixture: ReplayFixture) -> None:
    replay_fixture("reference", "eb10s")
    rows = tasks.list_commodities("EB10S").data
    assert len(rows) == 152
    assert (rows[0].id, rows[0].text, rows[0].parent) == (
        "S",
        "Total EBOPS 2010 SDMX Services",
        "#",
    )
    assert all(row.is_leaf is None and row.aggr_level is None for row in rows)


def test_hs_spells_the_level_aggr_level_the_other_files_aggrlevel() -> None:
    """Model check: HS.json (2 MB, not recorded) spells it ``aggrLevel``; the live test reads it."""
    hs = Commodity.model_validate(
        {"id": "0901", "text": "0901 - Coffee", "parent": "09", "isLeaf": "0", "aggrLevel": 4,
         "standardUnitAbbr": "n/a"}
    )  # fmt: skip
    b4 = Commodity.model_validate(
        {"id": "1", "text": "1 - Food", "parent": "TOTAL", "isLeaf": "0", "aggrlevel": 1}
    )
    assert (hs.aggr_level, b4.aggr_level) == (4, 1)


def test_a_classification_without_a_file_is_refused(respx_mock: respx.MockRouter) -> None:
    with pytest.raises(InvalidRequestError) as info:
        tasks.list_commodities("BE")
    assert not respx_mock.calls
    message = str(info.value)
    assert "cl_code 'BE' has no classification file at UN Comtrade" in message
    assert "Valid values: B4, B5, EB02, EB10, EB10S, EB, H0," in message
    with pytest.raises(InvalidRequestError, match="closest: 'HS'"):
        tasks.list_commodities("hs")


@pytest.mark.anyio
async def test_a_missing_reference_file_is_not_found(replay_fixture: ReplayFixture) -> None:
    """Layer 1: upstream's blob store answers 404 BlobNotFound for BE.json."""
    replay_fixture("reference", "be_absent")
    with pytest.raises(NotFoundError, match="BlobNotFound"):
        await api.reference("BE.json", Commodity)


@pytest.mark.anyio
async def test_list_tools_end_to_end(replay_fixture: ReplayFixture) -> None:
    replay_fixture("reference", "b4")
    payload = await mcp_call(server, "comtrade_list_commodities", {"cl_code": "B4"})
    assert len(payload["data"]) == 30
    assert payload["data"][0] == {
        "id": "TOTAL", "text": "Total of all BEC4 categories", "parent": "#", "is_leaf": False,
        "aggr_level": 0, "standard_unit_abbr": None, "cmd_code": None,
        "description_original": None,
    }  # fmt: skip
    assert payload["meta"]["endpoint"] == "files/v1/app/reference/B4.json"
    assert payload["meta"]["request"] == {"cl_code": "B4"}
    # MCP_CAPS: both tables reach an agent whole, Switzerland (757) and the USA (842) among
    # them, which the default cap of 200 rows cut off in upstream's alphabetical order.
    reporters = await mcp_call(server, "comtrade_list_reporters", {})
    assert reporters["meta"]["retrieved_at"] == "2026-10-23T00:00:00Z"
    assert reporters["meta"]["vintage"] is None
    assert len(reporters["data"]) == 255
    assert "note" not in reporters
    assert reporters["data"][0]["text"] == "Afghanistan"
    assert reporters["data"][0]["entry_effective_date"] == "1900-01-01T00:00:00"
    assert {757, 842} <= {row["reporter_code"] for row in reporters["data"]}
    partners = await mcp_call(server, "comtrade_list_partners", {})
    assert len(partners["data"]) == 310
    assert "note" not in partners
    assert partners["data"][0]["partner_code"] == 4
    with pytest.raises(AssertionError, match=r"InvalidRequestError.*no classification file"):
        await mcp_call(server, "comtrade_list_commodities", {"cl_code": "TM"})


def test_list_routes_end_to_end(replay_fixture: ReplayFixture) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from xippios.comtrade.http import router

    replay_fixture("reference", "b4")
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as http:
        answer = http.get("/comtrade/list_commodities", params={"cl_code": "B4"})
        assert answer.status_code == 200
        assert len(answer.json()["data"]) == 30
        reporters = http.get("/comtrade/list_reporters").json()
        assert len(reporters["data"]) == 255, "HTTP results are not capped"
        partners = http.get("/comtrade/list_partners").json()["meta"]
        assert (partners["retrieved_at"], partners["vintage"]) == ("2026-10-23T00:00:00Z", None)
        refused = http.get("/comtrade/list_commodities", params={"cl_code": "BE"})
        assert refused.status_code == 422


# Datasets: getDa, getMetadata, getLiveUpdate. One call each, no count first.


def test_get_data_availability_for_one_reporter_and_period(
    replay_fixture: ReplayFixture, fixtures_dir: Path
) -> None:
    route = replay_fixture("get_da", "ch_2023")
    result = tasks.get_data_availability("C", "A", "HS", reporter_code="757", period="2023")
    assert route.calls.last.request.url.path == "/data/v1/getDa/C/A/HS"
    assert sent_query(route) == recorded_query(
        load_fixture(fixtures_dir / "get_da" / "ch_2023.json")
    )
    assert result.meta.endpoint == "data/v1/getDa"
    assert result.meta.request == {
        "type_code": "C", "freq_code": "A", "cl_code": "HS", "reporter_code": "757",
        "period": "2023",
    }  # fmt: skip
    assert result.meta.published_at is None
    [dataset] = result.data
    assert dataset.dataset_code == 20757202301202100
    assert (dataset.reporter_code, dataset.period, dataset.reporter_iso) == (757, 2023, "CHE")
    assert (dataset.classification_code, dataset.classification_search_code) == ("H6", "HS")
    assert dataset.first_released == datetime(2024, 2, 2, 4, 52, 35, 216666)
    assert dataset.last_released == datetime(2024, 6, 7, 17, 13, 50, 536666)
    assert dataset.first_released.tzinfo is None
    assert dataset.total_records == 2_530_737
    assert dataset.is_extended_partner_code is True
    assert dataset.is_extended_flow_code is False


def test_get_data_availability_for_every_reporter(replay_fixture: ReplayFixture) -> None:
    replay_fixture("get_da", "all_reporters_2023")
    result = tasks.get_data_availability("C", "A", "HS", period="2023")
    assert len(result.data) == 169
    assert len({row.reporter_code for row in result.data}) == 169
    assert {row.period for row in result.data} == {2023}
    assert 757 in {row.reporter_code for row in result.data}
    assert all(isinstance(row.last_released, datetime) for row in result.data)


def test_a_period_nobody_reported_has_no_datasets(replay_fixture: ReplayFixture) -> None:
    replay_fixture("get_da", "nobody_1900")
    assert tasks.get_data_availability("C", "A", "HS", period="1900").data == []


def test_get_data_availability_by_publication_date(
    replay_fixture: ReplayFixture, fixtures_dir: Path
) -> None:
    route = replay_fixture("get_da", "ch_published_2024")
    result = tasks.get_data_availability(
        "C", "A", "HS", reporter_code="757", published_date_from="2024-01-01",
        published_date_to="2024-12-31",
    )  # fmt: skip
    assert sent_query(route) == recorded_query(
        load_fixture(fixtures_dir / "get_da" / "ch_published_2024.json")
    )
    released = [
        (row.period, row.first_released.year, row.last_released.year) for row in result.data
    ]
    assert released == [(2022, 2023, 2024), (2023, 2024, 2024)]


def test_get_data_availability_takes_more_than_12_periods(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    replay_fixture("get_da", "ch_13_periods")
    periods = ",".join(str(year) for year in range(2010, 2023))
    result = tasks.get_data_availability("C", "A", "HS", reporter_code="757", period=periods)
    assert sorted(row.period for row in result.data) == list(range(2010, 2023))
    assert len(respx_mock.calls) == 1


def test_dataset_arguments_are_checked_before_the_call(respx_mock: respx.MockRouter) -> None:
    with pytest.raises(InvalidRequestError) as info:
        tasks.get_data_availability(
            "C", "A", "EBSDMX", reporter_code="756", period="2023-01",
            published_date_from="2024/01/01", published_date_to="2024-02-30",
        )  # fmt: skip
    assert not respx_mock.calls
    message = str(info.value)
    for fragment in [
        "cl_code 'EBSDMX' is not a UN Comtrade clCode value",
        "reporter_code '756' is not a UN Comtrade reporter code (Reporters.json); "
        "closest: '757' (Switzerland)",
        "period '2023-01' is neither a year",
        "published_date_from '2024/01/01' is not a day as YYYY-MM-DD",
        "published_date_to '2024-02-30' is not a day as YYYY-MM-DD",
    ]:
        assert fragment in message
    with pytest.raises(InvalidRequestError, match="reporter_code '0' is not"):
        tasks.get_metadata("C", "A", "HS", reporter_code="0")


@pytest.mark.anyio
async def test_get_da_refuses_the_specs_ebsdmx(replay_fixture: ReplayFixture) -> None:
    """Layer 1: EBSDMX is in the spec's clCode enum for getDa; upstream answers HTTP 400."""
    replay_fixture("get_da", "services_ebsdmx")
    with pytest.raises(InvalidRequestError, match="The field clCode is invalid"):
        await api.get_da("S", "A", "EBSDMX", reporter_code="757", period="2023")


def test_get_metadata_for_one_reporter_and_period(
    replay_fixture: ReplayFixture, fixtures_dir: Path
) -> None:
    route = replay_fixture("get_metadata", "ch_2023")
    result = tasks.get_metadata("C", "A", "HS", reporter_code="757", period="2023")
    assert route.calls.last.request.url.path == "/data/v1/getMetadata/C/A/HS"
    assert sent_query(route) == {"reporterCode": "757", "period": "2023"}
    assert sent_query(route) == recorded_query(
        load_fixture(fixtures_dir / "get_metadata" / "ch_2023.json")
    )
    assert result.meta.endpoint == "data/v1/getMetadata"
    assert result.meta.request["reporter_code"] == "757"
    assert result.meta.published_at is None
    [dataset] = result.data
    assert (dataset.reporter_code, dataset.period, dataset.dataset_code) == (
        757,
        2023,
        20757202301202100,
    )
    first, revised = dataset.notes
    assert first.publication_note is not None
    assert first.publication_note.startswith("New Data")
    assert revised.publication_note is not None
    assert revised.publication_note.startswith("Revised Data")
    assert first.publication_date == datetime(2024, 2, 2, 5, 18, 25, 780000)
    assert revised.publication_date == datetime(2024, 6, 7, 18, 14, 53, 432741)
    assert revised.publication_date_short == date(2024, 6, 7)
    assert first.import_conv_factor == first.export_conv_factor == Decimal("1.11256298")
    assert (first.currency, first.trade_system, first.classification_code) == (
        "CHF",
        "Special",
        "H6",
    )
    assert (first.import_valuation, first.export_valuation) == ("CIF", "FOB")


def test_get_metadata_without_a_period_answers_every_period(
    replay_fixture: ReplayFixture,
) -> None:
    """reporterCode is honoured: only Switzerland's datasets come back."""
    route = replay_fixture("get_metadata", "ch_all_periods")
    result = tasks.get_metadata("C", "A", "HS", reporter_code="757")
    assert sent_query(route) == {"reporterCode": "757"}
    assert len(result.data) == 38
    assert {dataset.reporter_code for dataset in result.data} == {757}
    assert min(dataset.period for dataset in result.data) == 1988
    assert sum(len(dataset.notes) for dataset in result.data) == 42
    factors = [note.import_conv_factor for dataset in result.data for note in dataset.notes]
    assert all(isinstance(factor, Decimal) for factor in factors)


def test_get_metadata_answers_h6_as_hs(replay_fixture: ReplayFixture, fixtures_dir: Path) -> None:
    """H6 is not in the spec's clCode enum for getMetadata; upstream answers it like HS."""
    route = replay_fixture("get_metadata", "ch_2023_h6")
    h6 = tasks.get_metadata("C", "A", "H6", reporter_code="757", period="2023").data
    assert route.calls.last.request.url.path == "/data/v1/getMetadata/C/A/H6"
    fixture = load_fixture(fixtures_dir / "get_metadata" / "ch_2023.json")
    hs = json.loads(fixture.response.body)["data"]
    assert [MetadataDataset.model_validate(row) for row in hs] == h6


def test_get_live_update(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("get_live_update", "latest")
    result = tasks.get_live_update()
    assert route.calls.last.request.url.path == "/data/v1/getLiveUpdate"
    assert not sent_query(route)
    assert result.meta.endpoint == "data/v1/getLiveUpdate"
    assert result.meta.request == {}
    assert result.meta.published_at is None
    assert len(result.data) == 50
    newest = result.data[0]
    assert newest.started_at == datetime(2026, 10, 22, 21, 27, 39, tzinfo=UTC)
    assert newest.completed_at == datetime(2026, 10, 22, 21, 24, 18, tzinfo=UTC)
    assert newest.last_updated == date(2026, 10, 22)
    assert newest.queued_at == datetime(2026, 10, 22, 23, 18, 33)
    assert (newest.reporter_code, newest.period, newest.size) == ("234", 202604, 21_285_480)
    assert (newest.status, newest.release_status) == ("Success", "Released")
    started = [row.started_at for row in result.data]
    assert started == sorted(started, reverse=True)  # type: ignore[type-var]
    assert "published_date" not in type(newest).model_fields


def _live_update_row(fixtures_dir: Path) -> dict[str, Any]:
    body = load_fixture(fixtures_dir / "get_live_update" / "latest.json").response.body
    row: dict[str, Any] = json.loads(body)["data"][0]
    return row


def test_a_live_update_time_that_does_not_parse_is_none(fixtures_dir: Path) -> None:
    """Only Released/Success rows were recorded; other shapes must not fail the whole call."""
    row = _live_update_row(fixtures_dir)
    odd = {
        **row, "startedAt": "", "completedAt": "soon",
        "lastUpdated": "Donnerstag, 22. Oktober 2026", "queuedAt": "22.10.2026 23:18:33",
    }  # fmt: skip
    record = LiveUpdateRecord.model_validate(odd)
    assert (record.started_at, record.completed_at) == (None, None)
    assert (record.last_updated, record.queued_at) == (None, None)
    assert (record.reporter_code, record.period, record.size) == ("234", 202604, 21_285_480)
    wrong_weekday = LiveUpdateRecord.model_validate(
        {**row, "lastUpdated": "Friday, October 22, 2026", "queuedAt": "13/22/2026 01:00:00 PM"}
    )
    assert (wrong_weekday.last_updated, wrong_weekday.queued_at) == (None, None)
    midnight = LiveUpdateRecord.model_validate({**row, "queuedAt": "10/22/2026 12:05:00 AM"})
    noon = LiveUpdateRecord.model_validate({**row, "queuedAt": "10/22/2026 12:05:00 PM"})
    assert midnight.queued_at == datetime(2026, 10, 22, 0, 5)
    assert noon.queued_at == datetime(2026, 10, 22, 12, 5)


def test_live_update_times_do_not_depend_on_the_locale(fixtures_dir: Path) -> None:
    """Parsed from fixed English tables; checked under a German LC_TIME where one exists."""
    import locale

    previous = locale.setlocale(locale.LC_TIME)
    for name in ("de_DE.UTF-8", "de_DE.utf8", "de_CH.UTF-8", "fr_FR.UTF-8"):
        try:
            locale.setlocale(locale.LC_TIME, name)
            break
        except locale.Error:
            continue
    else:
        pytest.skip("no non-English LC_TIME locale is installed")
    try:
        record = LiveUpdateRecord.model_validate(_live_update_row(fixtures_dir))
    finally:
        locale.setlocale(locale.LC_TIME, previous)
    assert record.last_updated == date(2026, 10, 22)
    assert record.queued_at == datetime(2026, 10, 22, 23, 18, 33)


@pytest.mark.anyio
async def test_live_updates_count_is_not_the_number_of_rows(replay_fixture: ReplayFixture) -> None:
    replay_fixture("get_live_update", "latest")
    response = await api.get_live_update()
    assert (response.count, len(response.data)) == (174, 50)


@pytest.mark.anyio
async def test_dataset_tools_end_to_end(replay_fixture: ReplayFixture) -> None:
    replay_fixture("get_da", "ch_2023")
    replay_fixture("get_metadata", "ch_2023")
    replay_fixture("get_live_update", "latest")
    query = {"type_code": "C", "freq_code": "A", "cl_code": "HS", "reporter_code": "757",
             "period": "2023"}  # fmt: skip
    availability = await mcp_call(server, "comtrade_get_data_availability", query)
    [dataset] = availability["data"]
    assert dataset["dataset_code"] == 20757202301202100
    assert dataset["first_released"] == "2024-02-02T04:52:35.216666"
    assert availability["meta"]["endpoint"] == "data/v1/getDa"
    metadata = await mcp_call(server, "comtrade_get_metadata", query)
    assert metadata["data"][0]["notes"][0]["import_conv_factor"] == 1.11256298
    assert metadata["data"][0]["notes"][1]["publication_date_short"] == "2024-06-07"
    live = await mcp_call(server, "comtrade_get_live_update", {})
    assert len(live["data"]) == 50
    assert live["data"][0]["started_at"] == "2026-10-22T21:27:39Z"
    assert live["data"][0]["last_updated"] == "2026-10-22"
    with pytest.raises(AssertionError, match=r"InvalidRequestError.*closest: '757'"):
        await mcp_call(server, "comtrade_get_data_availability", {**query, "reporter_code": "756"})


def test_dataset_routes_end_to_end(replay_fixture: ReplayFixture) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from xippios.comtrade.http import router

    replay_fixture("get_da", "ch_2023")
    replay_fixture("get_live_update", "latest")
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as http:
        query = {"type_code": "C", "freq_code": "A", "cl_code": "HS", "reporter_code": "757",
                 "period": "2023"}  # fmt: skip
        answer = http.get("/comtrade/get_data_availability", params=query)
        assert answer.status_code == 200
        assert answer.json()["data"][0]["total_records"] == 2530737
        assert len(http.get("/comtrade/get_live_update").json()["data"]) == 50
        refused = http.get("/comtrade/get_metadata", params={**query, "period": "2023-01"})
        assert refused.status_code == 422


# Task-shaped slices: data/v1/get pinned to the total row, bounded by construction, no count.

BILATERAL_REQUEST: dict[str, Any] = {
    "type_code": "C", "freq_code": "A", "cl_code": "HS", "reporter_code": "757",
    "partner_code": "842", "partner2_code": "0", "period": "2022,2023",
    "cmd_code": "TOTAL,27", "flow_code": "X", "mot_code": "0", "customs_code": "C00",
    "breakdown_mode": "classic", "include_desc": True,
}  # fmt: skip
"""What get_bilateral_flows("CHE", "USA", "TOTAL,27", "2022,2023", "X") sends, resolved."""

SERIES = ",".join(str(year) for year in range(2010, 2024))
"""Fourteen years: more than upstream's 12 periods per call."""

MONTHS = [f"{year}{month:02d}" for year in range(2010, 2021) for month in range(1, 13)]
"""132 months, January 2010 to December 2020."""


def _records(fixtures_dir: Path, case: str) -> list[TradeDataRecord]:
    return [TradeDataRecord.model_validate(row) for row in _rows(fixtures_dir, case)]


def test_bilateral_flows_resolve_iso3_codes_before_the_call(replay_fixture: ReplayFixture) -> None:
    """The fixture answers 757 and 842 only; CHE and USA reach it resolved, without a count."""
    route = replay_fixture("get", "bilateral_ch_us_2022_2023", match_params=BY_AREAS)
    by_iso3 = tasks.get_bilateral_flows("CHE", "USA", "TOTAL,27", "2022,2023", "X")
    by_code = tasks.get_bilateral_flows("757", "842", "TOTAL,27", "2022,2023", "X")
    assert route.call_count == 2
    assert by_iso3.meta.request == by_code.meta.request == BILATERAL_REQUEST
    assert by_iso3.data == by_code.data


def test_bilateral_flows_project_the_total_rows(
    replay_fixture: ReplayFixture, fixtures_dir: Path
) -> None:
    route = replay_fixture("get", "bilateral_ch_us_2022_2023", match_params=BY_AREAS)
    result = tasks.get_bilateral_flows("757", "842", "TOTAL,27", "2022,2023", "X")
    assert route.calls.last.request.url.path == "/data/v1/get/C/A/HS"
    assert result.meta.endpoint == "data/v1/get"
    assert result.meta.published_at is None
    assert [(row.period, row.cmd_code) for row in result.data] == [
        ("2022", "27"), ("2022", "TOTAL"), ("2023", "27"), ("2023", "TOTAL"),
    ]  # fmt: skip
    raw = _records(fixtures_dir, "bilateral_ch_us_2022_2023")
    records = {(row.period, row.cmd_code): row for row in raw}
    for row in result.data:
        assert isinstance(row, TradeFlowRecord)
        assert_projection(row, records[(row.period, row.cmd_code)])
    total = result.data[3]
    assert total.primary_value == total.fobvalue == Decimal("62852531481.607")
    assert isinstance(total.primary_value, Decimal)
    assert total.cifvalue is None
    assert (total.reporter_code, total.reporter_iso, total.reporter_desc) == (
        757,
        "CHE",
        "Switzerland",
    )
    assert (total.partner_code, total.partner_iso, total.partner_desc) == (842, "USA", "USA")
    assert (total.flow_code, total.flow_desc, total.cmd_desc) == ("X", "Export", "All Commodities")
    assert (total.freq_code, total.ref_year, total.ref_month) == ("A", 2023, 52)
    assert total.classification_code == "H6"
    # A UNSD aggregate, not a reported figure: no quantity, the weight flagged as estimated.
    assert (total.is_reported, total.is_aggregate) == (False, True)
    assert (total.qty_unit_code, total.qty_unit_abbr) == (-1, "N/A")
    assert (total.qty, total.is_qty_estimated) == (Decimal("0.0"), False)
    assert (total.net_wgt, total.is_net_wgt_estimated) == (Decimal("0.0"), True)
    pinned = {"type_code", "partner2_code", "customs_code", "mot_code"}
    assert not pinned & set(TradeFlowRecord.model_fields), "pinned totals are not carried"


def test_monthly_periods_ask_for_monthly_data(replay_fixture: ReplayFixture) -> None:
    """YYYYMM periods go to freqCode M; the format, not an argument, sets the frequency."""
    route = replay_fixture("get", "bilateral_ch_us_202301_202302", match_params=BY_AREAS)
    result = tasks.get_bilateral_flows("CHE", "USA", "TOTAL", "202301,202302", "X")
    assert route.calls.last.request.url.path == "/data/v1/get/C/M/HS"
    assert result.meta.request["freq_code"] == "M"
    assert [(row.freq_code, row.period, row.ref_year, row.ref_month) for row in result.data] == [
        ("M", "202301", 2023, 1), ("M", "202302", 2023, 2),
    ]  # fmt: skip


def test_commodity_series_sends_14_periods_in_two_calls_in_order(
    replay_fixture: ReplayFixture, respx_mock: respx.MockRouter
) -> None:
    first = replay_fixture("get", "series_ch_27_2010_2021", match_params=BY_PERIODS)
    second = replay_fixture("get", "series_ch_27_2022_2023", match_params=BY_PERIODS)
    result = tasks.get_commodity_series("CHE", "27", "X", SERIES)
    assert (first.call_count, second.call_count) == (1, 1)
    sent = [call.request.url.params["period"] for call in respx_mock.calls]
    assert sent == [",".join(str(year) for year in range(2010, 2022)), "2022,2023"]
    assert [row.period for row in result.data] == SERIES.split(",")
    assert {(row.reporter_code, row.partner_code, row.cmd_code) for row in result.data} == {
        (757, 0, "27")
    }
    reported = [row.period for row in result.data if row.is_reported]
    assert reported == ["2010", "2011"], "the other years are UNSD aggregates"
    assert {(row.is_aggregate, row.qty, row.net_wgt) for row in result.data[:2]} == {
        (False, None, None)
    }
    editions = {row.period: row.classification_code for row in result.data}
    assert [editions[year] for year in ("2010", "2012", "2017", "2022")] == ["H3", "H4", "H5", "H6"]
    assert result.data[-1].primary_value == Decimal("6140348352.207")
    assert result.meta.request == {
        **BILATERAL_REQUEST, "partner_code": "0", "period": SERIES, "cmd_code": "27",
    }  # fmt: skip


def test_world_trade_has_one_row_per_reporter_largest_first(
    replay_fixture: ReplayFixture, fixtures_dir: Path
) -> None:
    route = replay_fixture("get", "world_27_2023_imports", match_params=BY_PARTNER)
    result = tasks.get_world_trade("27", "2023", "M")
    assert "reporterCode" not in sent_query(route)
    assert "reporter_code" not in result.meta.request
    assert result.meta.request["partner_code"] == "0"
    assert len(result.data) == len({row.reporter_code for row in result.data}) == 167
    assert {(row.partner_code, row.cmd_code, row.flow_code, row.period) for row in result.data} == {
        (0, "27", "M", "2023")
    }
    values = [row.primary_value for row in result.data]
    assert values == sorted(values, reverse=True)
    assert [row.reporter_desc for row in result.data[:3]] == ["China", "USA", "India"]
    upstream = [row["reporterCode"] for row in _rows(fixtures_dir, "world_27_2023_imports")]
    assert upstream[:3] == [8, 20, 24], "upstream sends them by code; the task sorts by value"


def test_top_partners_drop_world_and_keep_n(
    replay_fixture: ReplayFixture, fixtures_dir: Path
) -> None:
    route = replay_fixture("get", "partners_ch_total_2023", match_params=BY_REPORTER)
    result = tasks.get_top_partners("CHE", "TOTAL", "2023", "X", 5)
    assert "partnerCode" not in sent_query(route)
    every_partner = {
        key: value for key, value in BILATERAL_REQUEST.items() if key != "partner_code"
    }
    assert result.meta.request == {**every_partner, "period": "2023", "cmd_code": "TOTAL", "n": 5}
    assert [row.partner_code for row in result.data] == [842, 276, 156, 380, 251]
    raw = {row.partner_code: row for row in _records(fixtures_dir, "partners_ch_total_2023")}
    assert raw[0].primary_value == Decimal("419922543423.509"), "World is the total row"
    for row in result.data:
        assert_projection(row, raw[row.partner_code])
    assert result.data[0].primary_value == Decimal("62852531481.607"), "as get_bilateral_flows"
    everyone = tasks.get_top_partners("757", "TOTAL", "2023", "X", 500)
    assert len(everyone.data) == len(raw) - 1 == 225
    assert 0 not in {row.partner_code for row in everyone.data}
    values = [row.primary_value for row in everyone.data]
    assert values == sorted(values, reverse=True)


def test_iso3_codes_resolve_to_the_codes_upstream_data_uses(fixtures_dir: Path) -> None:
    def codes(reporter: str, partner: str) -> tuple[str, str]:
        request = validate_slice(
            "HS", "X", reporter=reporter, partner=partner, commodity="TOTAL", period="2023"
        )
        return request["reporter_code"], request["partner_code"]

    assert codes(reporter="CHE", partner="USA") == ("757", "842")
    assert codes(reporter="che", partner="W00") == ("757", "0")
    assert codes(reporter="DEU", partner="FRA") == ("276", "251"), "280 expired; 250 no reporter"
    assert codes(reporter="USA", partner="NOR") == ("842", "579"), "841 expired; 578 no reporter"
    assert codes(reporter="757", partner="0") == ("757", "0")
    partners = {row["partnerCode"] for row in _rows(fixtures_dir, "partners_ch_total_2023")}
    assert {842, 251, 579} <= partners
    assert not {840, 250, 578} & partners
    with pytest.raises(InvalidRequestError) as info:
        validate_slice("HS", "X", partner="A79", commodity="TOTAL", period="2023")
    assert "'473' (LAIA, nes), '636' (Rest of America, nes); give the numeric code" in str(
        info.value
    )


def _slice_refused(respx_mock: respx.MockRouter, call: Callable[[], object]) -> str:
    with pytest.raises(InvalidRequestError) as info:
        call()
    assert not respx_mock.calls, "resolution and validation happen before any call"
    return str(info.value)


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (
            lambda: tasks.get_bilateral_flows("CHE", "USA", "TOTAL", "2023,202301", "X"),
            "periods '2023,202301' mixes years (2023) and months (202301)",
        ),
        (
            lambda: tasks.get_bilateral_flows("CHF", "USA", "TOTAL", "2023", "X"),
            "reporter 'CHF' is neither a UN Comtrade reporter code nor the ISO alpha-3 code of "
            "one (Reporters.json); closest: 'CHN' (156, China)",
        ),
        (
            lambda: tasks.get_top_partners("Switzerland", "TOTAL", "2023", "X", 5),
            "closest: 'CHE' (757, Switzerland)",
        ),
        (
            lambda: tasks.get_bilateral_flows("CHE", "US", "TOTAL", "2023", "X"),
            "partner 'US' is neither a UN Comtrade partner code nor the ISO alpha-3 code of one "
            "(partnerAreas.json); closest: 'USA' (842, USA)",
        ),
        (
            lambda: tasks.get_bilateral_flows("756", "USA", "TOTAL", "2023", "X"),
            "reporter '756' is not a UN Comtrade reporter code (Reporters.json); closest: '757'",
        ),
        (
            lambda: tasks.get_bilateral_flows("W00", "USA", "TOTAL", "2023", "X"),
            "reporter 'W00' (0, World) is a partner area only",
        ),
        (
            lambda: tasks.get_bilateral_flows("CHE", "USA", "TOTAL", SERIES[:-5], "X"),
            "periods has 13 values; UN Comtrade takes at most 12 per call",
        ),
        (
            lambda: tasks.get_bilateral_flows("CHE", "USA", "TOTAL,AG2", "2023", "X"),
            "commodities 'AG2' expands to many product codes",
        ),
        (
            lambda: tasks.get_world_trade("27??", "2023", "M"),
            "commodity '27??' expands to many product codes",
        ),
        (
            lambda: tasks.get_world_trade("TOTAL,27", "2023", "M"),
            "commodity 'TOTAL,27' must be one product code",
        ),
        (
            lambda: tasks.get_world_trade("27", "2023-01", "M"),
            "period '2023-01' is neither a year (YYYY, e.g. '2023') nor a month (YYYYMM, e.g. "
            "'202305'); closest: '202301'",
        ),
        (
            lambda: tasks.get_top_partners("CHE", "TOTAL", "2022,2023", "X", 5),
            "period '2022,2023' must be one year or month",
        ),
        (
            lambda: tasks.get_top_partners("CHE", "TOTAL", "2023", "X", 0),
            "n 0 must be at least 1; closest: 1",
        ),
        (
            lambda: tasks.get_commodity_series("CHE", "27", "X,M", "2022,2023"),
            "flow 'X,M' must be one flow code",
        ),
        (
            lambda: tasks.get_commodity_series("CHE", "27", "X", "2022,2023,2022"),
            "periods names '2022' more than once",
        ),
        (
            lambda: tasks.get_bilateral_flows("CHE", "USA", "TOTAL,27,total", "2023", "X"),
            "commodities names 'TOTAL' more than once",
        ),
    ],
)
def test_slice_arguments_are_refused_before_any_call(
    respx_mock: respx.MockRouter, call: Callable[[], object], expected: str
) -> None:
    assert expected in _slice_refused(respx_mock, call)


def test_a_series_takes_at_most_120_periods(respx_mock: respx.MockRouter) -> None:
    """Ten calls of 12 against 500 a day: 121 periods are refused before the first call."""
    message = _slice_refused(
        respx_mock, lambda: tasks.get_commodity_series("CHE", "27", "X", ",".join(MONTHS[:121]))
    )
    assert "periods has 121 values; get_commodity_series takes at most 120, 10 calls of 12" in (
        message
    )
    request = validate_slice(
        "HS", "X", reporter="757", partner="0", commodity="27", periods=",".join(MONTHS[:120]),
        max_periods=MAX_SERIES_PERIODS,
    )  # fmt: skip
    assert (request["freq_code"], len(request["period"].split(","))) == ("M", 120)
    assert MAX_SERIES_PERIODS == 120


def test_a_bound_over_the_limit_is_refused_without_a_call(respx_mock: respx.MockRouter) -> None:
    """8,334 product codes over 12 periods could return 100,008 rows: refused, not counted."""
    codes = ",".join(f"{code:06d}" for code in range(8334))
    periods = ",".join(str(year) for year in range(2012, 2024))
    with pytest.raises(QueryTooLarge) as info:
        tasks.get_bilateral_flows("757", "842", codes, periods, "X")
    assert not respx_mock.calls
    assert info.value.count == 8334 * 12 == 100_008
    assert info.value.bound is True
    assert "query could return up to 100,008 records" in str(info.value)
    assert "Name fewer product codes or periods per call" in str(info.value)


def test_the_list_tasks_search_code_iso3_and_text(respx_mock: respx.MockRouter) -> None:
    assert [row.reporter_code for row in tasks.list_reporters(search="switz").data] == [757]
    assert [row.reporter_code for row in tasks.list_reporters(search="757").data] == [757]
    by_iso3 = tasks.list_reporters(search="che")
    assert [row.reporter_code for row in by_iso3.data] == [690, 757], "Seychelles by its name"
    assert by_iso3.meta.request == {"search": "che"}
    assert (by_iso3.meta.retrieved_at, by_iso3.meta.vintage) == (
        datetime(2026, 10, 23, tzinfo=UTC),
        None,
    )
    germany = tasks.list_reporters(search="GERMANY").data
    assert sorted(row.reporter_code for row in germany) == [276, 278, 280]
    world = tasks.list_partners(search="W00")
    assert [row.partner_code for row in world.data] == [0]
    assert world.meta.request == {"search": "W00"}
    usa = tasks.list_partners(search="usa").data
    assert sorted(row.partner_code for row in usa) == [840, 841, 842]
    assert tasks.list_partners(search="no such area").data == []
    whole = tasks.list_reporters()
    assert (len(whole.data), whole.meta.request) == (255, {})
    assert len(tasks.list_partners().data) == 310
    assert not respx_mock.calls, "packaged: no upstream call"


def test_list_commodities_searches_the_fetched_file(replay_fixture: ReplayFixture) -> None:
    route = replay_fixture("reference", "b4")
    food = tasks.list_commodities("B4", search="FOOD")
    assert [row.id for row in food.data] == ["1", "11", "12", "111", "112", "121", "122"]
    assert food.meta.request == {"cl_code": "B4", "search": "FOOD"}
    by_code = tasks.list_commodities("B4", search="52")
    assert [row.id for row in by_code.data] == ["52", "521", "522"]
    assert len(tasks.list_commodities("B4").data) == 30
    assert route.call_count == 1, "one fetch, kept for the process"


@pytest.mark.anyio
async def test_slice_tools_end_to_end(replay_fixture: ReplayFixture) -> None:
    replay_fixture("get", "bilateral_ch_us_2022_2023", match_params=BY_AREAS)
    arguments = {"reporter": "CHE", "partner": "USA", "commodities": "TOTAL,27",
                 "periods": "2022,2023", "flow": "X"}  # fmt: skip
    bilateral = await mcp_call(server, "comtrade_get_bilateral_flows", arguments)
    assert [row["cmd_code"] for row in bilateral["data"]] == ["27", "TOTAL", "27", "TOTAL"]
    assert bilateral["data"][3]["primary_value"] == 62852531481.607
    assert bilateral["meta"]["request"] == BILATERAL_REQUEST
    replay_fixture("get", "series_ch_27_2010_2021", match_params=BY_PERIODS)
    replay_fixture("get", "series_ch_27_2022_2023", match_params=BY_PERIODS)
    series = await mcp_call(
        server,
        "comtrade_get_commodity_series",
        {"reporter": "757", "commodity": "27", "flow": "X", "periods": SERIES},
    )
    assert [row["period"] for row in series["data"]] == SERIES.split(",")
    replay_fixture("get", "world_27_2023_imports", match_params=BY_PARTNER)
    world = await mcp_call(
        server, "comtrade_get_world_trade", {"commodity": "27", "period": "2023", "flow": "M"}
    )
    assert world["note"].startswith("showing 104 of 167 rows"), "64 KB: the largest come first"
    assert world["data"][0]["reporter_code"] == 156
    replay_fixture("get", "partners_ch_total_2023", match_params=BY_REPORTER)
    top = await mcp_call(
        server,
        "comtrade_get_top_partners",
        {"reporter": "CHE", "commodity": "TOTAL", "period": "2023", "flow": "X", "n": 3},
    )
    assert [row["partner_code"] for row in top["data"]] == [842, 276, 156]
    assert top["meta"]["request"]["n"] == 3
    reporters = await mcp_call(server, "comtrade_list_reporters", {"search": "switz"})
    assert [row["reporter_code"] for row in reporters["data"]] == [757]
    assert reporters["meta"]["request"] == {"search": "switz"}
    assert "note" not in reporters
    with pytest.raises(AssertionError, match=r"InvalidRequestError.*mixes years"):
        await mcp_call(
            server, "comtrade_get_bilateral_flows", {**arguments, "periods": "2023,202301"}
        )


def test_list_search_route_end_to_end() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from xippios.comtrade.http import router

    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as http:
        answer = http.get("/comtrade/list_partners", params={"search": "world"}).json()
        assert [row["partner_code"] for row in answer["data"]] == [0]
        assert answer["meta"]["request"] == {"search": "world"}


def test_slice_route_end_to_end(replay_fixture: ReplayFixture) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from xippios.comtrade.http import router

    route = replay_fixture("get", "bilateral_ch_us_2022_2023", match_params=BY_AREAS)
    app = FastAPI()
    app.include_router(router)
    query = {"reporter": "CHE", "partner": "USA", "commodities": "TOTAL,27",
             "periods": "2022,2023", "flow": "X"}  # fmt: skip
    with TestClient(app) as http:
        answer = http.get("/comtrade/get_bilateral_flows", params=query)
        assert answer.status_code == 200
        body = answer.json()
        assert [row["cmd_code"] for row in body["data"]] == ["27", "TOTAL", "27", "TOTAL"]
        assert body["data"][3]["primary_value"] == 62852531481.607
        assert body["meta"]["request"] == BILATERAL_REQUEST
        assert route.call_count == 1
        refused = http.get("/comtrade/get_bilateral_flows", params={**query, "partner": "US"})
        assert refused.status_code == 422
        assert "closest: 'USA' (842, USA)" in refused.json()["detail"]
        assert route.call_count == 1, "refused before any call"
