"""Structural checks every task must satisfy. Per-task tests with recorded fixtures go below."""

import inspect
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx
from xippios.core import AuthError, InvalidRequestError, RateLimitError
from xippios.core.http import status_for
from xippios.core.testing import mcp_call

from xippios.comtrade import __version__, api, enums, tasks
from xippios.comtrade._client import classify
from xippios.comtrade.errors import RECORD_LIMIT, QueryTooLarge
from xippios.comtrade.mcp import server
from xippios.comtrade.params import PACKAGED_LISTS, packaged_values, validate_get

TASKS = [getattr(tasks, name) for name in tasks.__all__]

Replay = Callable[[str], respx.Route]
Recorded = Callable[[str], dict[str, str]]


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


def test_get_data_counts_first_then_fetches(replay_get: Replay, recorded_params: Recorded) -> None:
    counted = replay_get("count_ch_exports_2023")
    fetched = replay_get("ch_exports_2023")
    result = tasks.get_data(**CH_EXPORTS_2023)
    assert counted.call_count == 1
    assert fetched.call_count == 1
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


def test_a_code_that_is_not_a_reporter_counts_zero(replay_get: Replay) -> None:
    """756 is Switzerland's ISO numeric code; Comtrade's reporter code is 757."""
    replay_get("count_not_a_reporter_756")
    result = tasks.get_data(**{**CH_EXPORTS_2023, "reporter_code": "756"})
    assert result.data == []


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
    """Characterisation: the spec lists MIF, tradeRegimes.json does not, upstream answers 200."""
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
    assert "Valid values: M, X, DX, FM, MIP, MOP, RM, RX, XIP, XOP" in message


def test_flow_codes_not_in_trade_regimes_are_refused(respx_mock: respx.MockRouter) -> None:
    assert "'MIF' is not a UN Comtrade flowCode value" in _refused(respx_mock, flow_code="MIF")


def test_unknown_cl_code_names_the_closest_value(respx_mock: respx.MockRouter) -> None:
    message = _refused(respx_mock, cl_code="BE5")
    assert "cl_code 'BE5' is not a UN Comtrade clCode value; closest: 'B5'" in message


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
