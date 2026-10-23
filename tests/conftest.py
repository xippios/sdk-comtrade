import os
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import respx
from respx.patterns import M

from xippios.comtrade._client import API_KEY_ENV

pytest_plugins = ["xippios.core.testing.plugin"]

COUNT_ONLY = M(params__contains={"countOnly": "true"})


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def placeholder_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixture-backed tests never need a real key; live tests use the one in the environment."""
    if not os.environ.get(API_KEY_ENV):
        monkeypatch.setenv(API_KEY_ENV, "placeholder-for-fixture-replay")


@pytest.fixture
def replay_get(respx_mock: respx.MockRouter, fixtures_dir: Path) -> Callable[[str], respx.Route]:
    """Mount ``tests/fixtures/get/<case>.json`` for count or data requests only.

    The count and the data call of ``data/v1/get`` share one path and differ in
    ``countOnly=true``, so the route matches that parameter too: a count fixture answers
    only ``countOnly`` requests, a data fixture only the others. Every other query
    parameter is left to the test, which compares the sent query with the recorded one.
    """

    from xippios.core.testing import fixture_path, load_fixture

    def _replay(case: str) -> respx.Route:
        fixture = load_fixture(fixture_path(fixtures_dir, "get", case))
        url = httpx.URL(fixture.request.url)
        where = M(method=fixture.request.method, host=url.host, path=url.path)
        is_count = url.params.get("countOnly") == "true"
        route = respx_mock.route(where & COUNT_ONLY if is_count else where & ~COUNT_ONLY)
        route.mock(
            return_value=httpx.Response(
                fixture.response.status,
                headers=fixture.response.headers,
                content=fixture.response.content,
            )
        )
        return route

    return _replay


@pytest.fixture
def recorded_params(fixtures_dir: Path) -> Callable[[str], dict[str, str]]:
    """The query parameters a fixture was recorded with, for comparison with what is sent."""

    from xippios.core.testing import fixture_path, load_fixture

    def _params(case: str) -> dict[str, str]:
        fixture = load_fixture(fixture_path(fixtures_dir, "get", case))
        return dict(httpx.URL(fixture.request.url).params)

    return _params
