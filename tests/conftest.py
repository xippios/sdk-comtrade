from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import respx
from respx.patterns import M

# Importing xippios.core.testing loads its pytest plugin before pytest_plugins below is
# processed; registering the package first lets pytest rewrite its asserts and keeps the
# "already imported" warning away.
pytest.register_assert_rewrite("xippios.core.testing")

from xippios.core.testing import fixture_path, load_fixture  # noqa: E402

from xippios.comtrade._client import API_KEY_ENV, REFERENCE_CACHE, auth  # noqa: E402

pytest_plugins = ["xippios.core.testing.plugin"]

COUNT_ONLY = M(params__contains={"countOnly": "true"})


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


PLACEHOLDER_KEY = "placeholder-for-fixture-replay"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def placeholder_api_key(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> str | None:
    """Every test but a live one sends the placeholder key, whatever the shell holds.

    Setting the variable is not enough: the client's auth resolves the key once per auth
    object and caches it, so a live test earlier in the same run would leave the real
    key in place. ``auth.key``, through which every ``xippios.core`` auth class reads the
    key, is pinned to the placeholder as well; both come back after the test. Returns
    the placeholder, or ``None`` in a live test, which uses the key in the environment.
    """
    if "live" in request.keywords:
        return None
    monkeypatch.setenv(API_KEY_ENV, PLACEHOLDER_KEY)
    monkeypatch.setattr(auth, "key", lambda: PLACEHOLDER_KEY)
    return PLACEHOLDER_KEY


@pytest.fixture(autouse=True)
def empty_reference_cache() -> None:
    """``reference_client`` keeps every file for the process; each test starts without any.

    Otherwise a file one test fetched would answer the next test from the cache and never
    reach the route that test mounted.
    """
    REFERENCE_CACHE.clear()


@pytest.fixture
def replay_get(respx_mock: respx.MockRouter, fixtures_dir: Path) -> Callable[[str], respx.Route]:
    """Mount ``tests/fixtures/get/<case>.json`` for count or data requests only.

    The count and the data call of ``data/v1/get`` share one path and differ in
    ``countOnly=true``, so the route matches that parameter too: a count fixture answers
    only ``countOnly`` requests, a data fixture only the others. Every other query
    parameter is left to the test, which compares the sent query with the recorded one.
    """

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

    def _params(case: str) -> dict[str, str]:
        fixture = load_fixture(fixture_path(fixtures_dir, "get", case))
        return dict(httpx.URL(fixture.request.url).params)

    return _params
