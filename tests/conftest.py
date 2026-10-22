import os

import pytest

from xippios.comtrade._client import API_KEY_ENV

pytest_plugins = ["xippios.core.testing.plugin"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def placeholder_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixture-backed tests never need a real key; live tests use the one in the environment."""
    if not os.environ.get(API_KEY_ENV):
        monkeypatch.setenv(API_KEY_ENV, "placeholder-for-fixture-replay")
