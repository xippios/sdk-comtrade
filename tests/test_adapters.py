"""The adapters expose exactly the tasks, in the shapes the conventions prescribe.

Per-task end-to-end calls belong next to the task's replay test, with
``xippios.core.testing.mcp_call`` and FastAPI's ``TestClient``.
"""

import inspect
import typing
from collections.abc import Callable

import pytest
from fastapi.routing import APIRoute
from xippios.core.http import is_scalar
from xippios.core.mcp import tool_name

from xippios.comtrade import tasks
from xippios.comtrade._client import SOURCE
from xippios.comtrade.http import router
from xippios.comtrade.mcp import server

pytestmark = pytest.mark.anyio

TASKS: dict[str, Callable[..., object]] = {name: getattr(tasks, name) for name in tasks.__all__}


def _parameters(fn: Callable[..., object]) -> dict[str, object]:
    hints = typing.get_type_hints(fn)
    parameters = inspect.signature(fn).parameters.values()
    return {p.name: hints.get(p.name, p.annotation) for p in parameters}


async def test_mcp_tools_are_the_tasks_with_their_parameters() -> None:
    tools = {tool.name: tool for tool in await server.list_tools()}
    assert set(tools) == {tool_name(SOURCE, fn) for fn in TASKS.values()}
    for name, fn in TASKS.items():
        tool = tools[tool_name(SOURCE, fn)]
        assert set(tool.input_schema.get("properties", {})) == set(_parameters(fn)), name
        assert tool.description, f"{name} has no docstring; agents read it"


async def test_http_routes_are_the_tasks_with_the_right_methods() -> None:
    routes = {route.path: route for route in router.routes if isinstance(route, APIRoute)}
    assert set(routes) == {f"/{SOURCE}/{name}" for name in TASKS}
    for name, fn in TASKS.items():
        scalar_only = all(is_scalar(annotation) for annotation in _parameters(fn).values())
        assert routes[f"/{SOURCE}/{name}"].methods == ({"GET"} if scalar_only else {"POST"}), name


async def test_get_data_and_get_counts_are_exposed_without_touching_the_adapters() -> None:
    """Both tasks reach MCP and HTTP through tasks.__all__ alone; mcp.py and http.py are generic."""
    from pathlib import Path

    import xippios.comtrade as package

    tools = {tool.name for tool in await server.list_tools()}
    assert {"comtrade_get_counts", "comtrade_get_data"} <= tools
    routes = {route.path: route.methods for route in router.routes if isinstance(route, APIRoute)}
    assert routes["/comtrade/get_counts"] == {"GET"}
    assert routes["/comtrade/get_data"] == {"GET"}
    package_dir = Path(package.__file__ or "").parent
    for adapter in ("mcp.py", "http.py"):
        source = (package_dir / adapter).read_text(encoding="utf-8")
        assert "get_data" not in source
        assert "get_counts" not in source
