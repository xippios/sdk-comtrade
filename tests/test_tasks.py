"""Structural checks every task must satisfy. Per-task tests with recorded fixtures go below."""

import inspect
import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from xippios.core import AuthError, InvalidRequestError, RateLimitError, UpstreamError
from xippios.core.http import status_for
from xippios.core.testing import load_fixture, mcp_call

from xippios.comtrade import __version__, api, enums, tasks
from xippios.comtrade._client import API_KEY_ENV, TIMEOUTS, _quota_reset, classify, config
from xippios.comtrade.errors import RECORD_LIMIT, QueryTooLarge
from xippios.comtrade.mcp import server
from xippios.comtrade.models import (
    Commodity,
    CountryAreaCodeIso,
    PartnerArea,
    ReferenceCode,
    Reporter,
    TradeDataItem,
)
from xippios.comtrade.params import (
    PACKAGED_LISTS,
    PACKAGED_TABLES,
    classification_files,
    packaged_table,
    packaged_table_info,
    packaged_values,
    validate_get,
)

TASKS = [getattr(tasks, name) for name in tasks.__all__]

Replay = Callable[[str], respx.Route]
Recorded = Callable[[str], dict[str, str]]

UPSTREAM = Path(__file__).resolve().parents[1] / "docs" / "upstream"


def test_package_has_a_version() -> None:
    assert __version__


@pytest.mark.parametrize("task", TASKS, ids=tasks.__all__)
def test_task_is_a_sync_facade_with_an_agent_docstring(task: object) -> None:
    assert callable(task)
    assert hasattr(task, "async_fn"), "write the async function and derive the sync one with sync()"
    doc = inspect.getdoc(task) or ""
    assert doc, "task functions need a docstring: agents read it"
    assert doc.splitlines()[0].endswith("."), "the first line is one sentence"
    if inspect.signature(task).parameters:
        assert "Args:" in doc, "explain every parameter under Args: with valid-value examples"


@pytest.mark.parametrize("task", TASKS, ids=tasks.__all__)
def test_every_parameter_is_explained(task: object) -> None:
    doc = inspect.getdoc(task) or ""
    for name in inspect.signature(task).parameters:  # type: ignore[arg-type]
        assert f"    {name}: " in doc, name


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


def test_get_counts_sends_the_recorded_count_request(
    replay_get: Replay, recorded_params: Recorded
) -> None:
    route = replay_get("count_ch_exports_2023")
    result = tasks.get_counts(**CH_EXPORTS_2023)
    assert result.data == 32
    assert result.meta.source == "comtrade"
    assert result.meta.endpoint == "data/v1/get"
    assert result.meta.request == CH_EXPORTS_2023
    assert result.meta.published_at is None
    sent = route.calls.last.request
    assert sent.url.path == "/data/v1/get/C/A/HS"
    assert dict(sent.url.params) == recorded_params("count_ch_exports_2023")
    assert sent.headers["Ocp-Apim-Subscription-Key"] == "placeholder-for-fixture-replay"


def test_get_data_counts_first_then_fetches(
    replay_get: Replay, recorded_params: Recorded, respx_mock: respx.MockRouter
) -> None:
    counted = replay_get("count_ch_exports_2023")
    fetched = replay_get("ch_exports_2023")
    result = tasks.get_data(**CH_EXPORTS_2023)
    assert counted.call_count == 1
    assert fetched.call_count == 1
    order = [call.request.url.params.get("countOnly") for call in respx_mock.calls]
    assert order == ["true", None]
    assert dict(fetched.calls.last.request.url.params) == recorded_params("ch_exports_2023")
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
    replay_get: Replay, respx_mock: respx.MockRouter
) -> None:
    replay_get("count_zero_ch_1900")
    result = tasks.get_data(**{**CH_EXPORTS_2023, "period": "1900"})
    assert result.data == []
    assert result.meta.request["period"] == "1900"
    assert len(respx_mock.calls) == 1
    assert respx_mock.calls.last.request.url.params["countOnly"] == "true"


def test_get_data_refuses_over_the_limit_before_fetching(
    replay_get: Replay, respx_mock: respx.MockRouter
) -> None:
    replay_get("count_over_limit")
    fetched = replay_get("over_limit_max_records")
    with pytest.raises(QueryTooLarge) as info:
        tasks.get_data(
            "C", "A", "HS", partner_code="0", period="2022", cmd_code="AG4", flow_code="M"
        )
    assert info.value.count == 5_006_385
    assert info.value.limit == RECORD_LIMIT == 100_000
    message = str(info.value)
    assert "5,006,385" in message
    assert "Split by period (max 12 per call), then by reporter" in message
    assert not fetched.called
    assert len(respx_mock.calls) == 1
    assert "reporterCode" not in respx_mock.calls.last.request.url.params


def test_query_too_large_is_an_invalid_request_for_http_too() -> None:
    assert issubclass(QueryTooLarge, InvalidRequestError)
    assert status_for(QueryTooLarge(200_000)) == 422


@pytest.mark.anyio
async def test_a_code_that_is_not_a_reporter_counts_zero_upstream(replay_get: Replay) -> None:
    """Layer 1: 756 is Switzerland's ISO numeric code, not a reporter; upstream counts 0."""
    replay_get("count_not_a_reporter_756")
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
async def test_unknown_reporter_is_an_empty_answer_upstream(
    replay_get: Replay, recorded_params: Recorded
) -> None:
    """Layer 1: reporterCode 999 answers HTTP 200 with count 0 and no rows, not an error."""
    route = replay_get("unknown_reporter")
    response = await api.get(
        "C", "A", "HS", reporter_code="999", period="2023", partner_code="0", cmd_code="TOTAL",
        flow_code="X",
    )  # fmt: skip
    assert (response.count, response.data, response.error) == (0, [], "")
    assert dict(route.calls.last.request.url.params) == recorded_params("unknown_reporter")


def test_invalid_key_is_an_auth_error(replay_get: Replay) -> None:
    replay_get("invalid_key")
    with pytest.raises(AuthError) as info:
        tasks.get_counts(**CH_EXPORTS_2023)
    assert info.value.status == 401
    assert "invalid subscription key" in str(info.value)


@pytest.mark.anyio
async def test_max_records_caps_the_rows(replay_get: Replay, recorded_params: Recorded) -> None:
    route = replay_get("over_limit_max_records")
    response = await api.get(
        "C", "A", "HS", period="2022", partner_code="0", cmd_code="AG4", flow_code="M",
        max_records=5,
    )  # fmt: skip
    assert response.count == 5
    assert len(response.data) == 5
    assert route.calls.last.request.url.params["maxRecords"] == "5"
    assert dict(route.calls.last.request.url.params) == recorded_params("over_limit_max_records")


@pytest.mark.anyio
async def test_wildcard_product_codes_are_counted_upstream(replay_get: Replay) -> None:
    replay_get("count_cmd_code_wildcard")
    response = await api.get_count_only(
        "C", "A", "HS", reporter_code="757", period="2023", partner_code="0", cmd_code="27??",
        flow_code="X",
    )  # fmt: skip
    assert response.count == 113


def test_wildcards_pass_validation(replay_get: Replay) -> None:
    replay_get("count_cmd_code_wildcard")
    assert tasks.get_counts(**{**CH_EXPORTS_2023, "cmd_code": "27??"}).data == 113


@pytest.mark.anyio
async def test_upstream_period_limit_is_an_invalid_request(replay_get: Replay) -> None:
    """Layer 1, past the task's own check: upstream refuses a 13th period with HTTP 400."""
    replay_get("count_13_periods")
    with pytest.raises(InvalidRequestError, match="Maximum number of periods is 12"):
        await api.get_count_only(
            "C", "A", "HS", reporter_code="757", period=",".join(map(str, range(2010, 2023))),
            partner_code="0", cmd_code="TOTAL", flow_code="X",
        )  # fmt: skip


@pytest.mark.anyio
async def test_upstream_parameter_refusal_names_the_parameter(replay_get: Replay) -> None:
    """``BE5`` is in the spec's clCode enum, but upstream refuses it (HTTP 400)."""
    replay_get("count_cl_code_be5")
    with pytest.raises(InvalidRequestError) as info:
        await api.get_count_only("C", "A", "BE5", reporter_code="757", period="2023")
    assert "Invalid parameter value" in str(info.value)
    assert "The field clCode is invalid" in str(info.value)


@pytest.mark.anyio
async def test_mif_is_accepted_upstream(replay_get: Replay) -> None:
    """The spec lists MIF, tradeRegimes.json does not; upstream answers 200, so it is packaged."""
    replay_get("count_flow_code_mif")
    response = await api.get_count_only(
        "C", "A", "HS", reporter_code="757", period="2023", partner_code="0", cmd_code="TOTAL",
        flow_code="MIF",
    )  # fmt: skip
    assert (response.count, response.error) == (0, "")


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


def test_flow_codes_the_spec_adds_pass_validation(replay_get: Replay) -> None:
    replay_get("count_flow_code_mif")
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


def test_enums_match_the_packaged_lists() -> None:
    for name in PACKAGED_LISTS:
        cls = getattr(enums, name[0].upper() + name[1:])
        packaged = packaged_values(name)
        assert packaged is not None
        assert packaged.param == name
        assert packaged.origin
        assert [member.value for member in cls] == packaged.values, name
    assert packaged_values("Reporters") is None
    assert enums.FlowCode.X.value == "X"
    assert enums.MotCode._0.value == "0"
    assert enums.ClCode.EB10S.value == "EB10S"
    assert enums.FlowCode.XIF.value == "XIF"
    assert [member.value for member in enums.MosCode] == ["0", "Mode 1", "Mode 2", "Mode 3",
                                                          "Mode 4"]  # fmt: skip
    assert enums.QtyUnitCode("-1").name == "_1"
    assert enums.QtyUnitCode("8").name == "_8"
    assert len(enums.QtyUnitCode) == 41


def test_list_exceptions_rest_on_recorded_answers(fixtures_dir: Path) -> None:
    """clCode is ListofReferences plus what upstream accepted, minus what it refused."""
    cl_code = packaged_values("clCode")
    assert cl_code is not None
    decisions = {item.value: item.decision for item in cl_code.exceptions}
    assert decisions == {"BE": "added", "BE5": "left out", "TM": "added", "H6": "kept"}
    assert {"BE", "TM", "H6"} <= set(cl_code.values)
    assert "BE5" not in cl_code.values
    flow_code = packaged_values("flowCode")
    assert flow_code is not None
    assert {item.value: item.decision for item in flow_code.exceptions} == {
        "MIF": "added",
        "XIF": "added",
    }
    statuses = {"added": 200, "left out": 400, "kept": 500}
    for item in [*cl_code.exceptions, *flow_code.exceptions]:
        if "tests/fixtures/get/" not in item.evidence:
            assert item.value == "XIF"
            continue
        name = item.evidence.split("tests/fixtures/get/")[1].split(",")[0]
        fixture = load_fixture(fixtures_dir / "get" / name)
        assert fixture.response.status == statuses[item.decision], item.value


@pytest.mark.anyio
async def test_spec_cl_codes_upstream_accepts(replay_get: Replay) -> None:
    replay_get("count_cl_code_tm")
    assert (await api.get_count_only("C", "A", "TM", reporter_code="757")).count == 1
    assert validate_get("C", "A", "BE", cmd_code="TOTAL")["cl_code"] == "BE"


@pytest.mark.anyio
async def test_a_server_error_is_retried_and_each_retry_is_a_call(replay_get: Replay) -> None:
    """Upstream answered a count on H6 with HTTP 500; core retries it, every attempt a call."""
    route = replay_get("count_cl_code_h6")
    with pytest.raises(UpstreamError) as info:
        await api.get_count_only("C", "A", "H6", reporter_code="757", period="2023")
    assert info.value.status == 500
    assert "Something went wrong" in str(info.value)
    assert route.call_count == config.retry.max_attempts == 4


def test_enum_members_are_accepted_as_arguments(replay_get: Replay) -> None:
    route = replay_get("count_ch_exports_2023")
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
    assert route.calls.last.request.url.params["flowCode"] == "X"


def test_replay_never_sends_the_key_from_the_shell(
    replay_get: Replay, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(API_KEY_ENV, "dummy-value-from-the-shell")
    route = replay_get("count_ch_exports_2023")
    tasks.get_counts(**CH_EXPORTS_2023)
    sent = route.calls.last.request.headers["Ocp-Apim-Subscription-Key"]
    assert sent == "placeholder-for-fixture-replay"


@pytest.mark.anyio
async def test_reference_files_are_fetched_without_the_key(respx_mock: respx.MockRouter) -> None:
    """Constructed route, not a fixture: what matters is the request, not upstream's answer."""
    route = respx_mock.get(
        "https://comtradeapi.un.org/files/v1/app/reference/tradeRegimes.json"
    ).mock(return_value=httpx.Response(200, json={"results": [{"id": "X", "text": "Export"}]}))
    rows = await api.reference("tradeRegimes.json", ReferenceCode)
    assert [row.id for row in rows] == ["X"]
    assert "Ocp-Apim-Subscription-Key" not in route.calls.last.request.headers
    assert "subscription-key" not in route.calls.last.request.url.params


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


@pytest.mark.anyio
async def test_mcp_tool_call_end_to_end(replay_get: Replay) -> None:
    replay_get("count_ch_exports_2023")
    replay_get("ch_exports_2023")
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


def test_http_route_end_to_end(replay_get: Replay) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from xippios.comtrade.http import router

    replay_get("count_ch_exports_2023")
    replay_get("ch_exports_2023")
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


# Packaged reference tables.


@pytest.mark.parametrize("name", list(PACKAGED_TABLES))
def test_packaged_tables_match_their_provenance(name: str) -> None:
    info = packaged_table_info(name)
    assert info is not None
    assert info.file == f"{name}.csv"
    assert info.origin == f"https://comtradeapi.un.org/files/v1/app/reference/{name}.json"
    assert len(packaged_table(name, PACKAGED_TABLES[name])) == info.rows
    assert packaged_table_info("Frequency") is None
    with pytest.raises(KeyError):
        packaged_table(name, Commodity)


def test_reporters_and_partners_share_one_code_space() -> None:
    """A code in both tables is the same area; World and others are partners only."""
    reporters = {row.reporter_code: row for row in packaged_table("Reporters", Reporter)}
    partners = {row.partner_code: row for row in packaged_table("partnerAreas", PartnerArea)}
    assert set(reporters) - set(partners) == {97, 975}
    assert len(set(partners) - set(reporters)) == 57
    assert {0, 756, 899} <= set(partners) - set(reporters)
    for code in set(reporters) & set(partners):
        assert reporters[code].reporter_code_iso_alpha3 == partners[code].partner_code_iso_alpha3
    iso = {row.country_area_code: row.iso3 for row in packaged_table(
        "country_area_code_iso", CountryAreaCodeIso)}  # fmt: skip
    assert set(iso) == set(reporters) | set(partners)
    assert (iso[756], iso[757], iso[0]) == ("CHE", "CHE", "W00")


def test_trade_data_items_describe_the_record_columns() -> None:
    items = {row.data_item: row for row in packaged_table("TradeDataItems", TradeDataItem)}
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
