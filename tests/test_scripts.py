"""The maintenance scripts under ``scripts/``, checked without a request or a key.

``scripts/refresh_reference.py`` is a declaration of core's frame (sdk-core ADR-0062), whose
command line, fetch, write and count are core's and tested there; what stays here is what
the script declares.
"""

import importlib.util
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import httpx
import pytest
import respx
from xippios.core import PackagedList, RetryPolicy, TransportError

from xippios.comtrade._client import client
from xippios.comtrade.params import PACKAGE, PACKAGED_LISTS, PACKAGED_TABLES

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
REFERENCE = ROOT / "src/xippios/comtrade/reference"
KEY_HEADER = "Ocp-Apim-Subscription-Key"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reference = _load("refresh_reference")


def test_refresh_reference_declares_the_packaged_lists_and_no_quota_header() -> None:
    """One ``Listed`` per file under ``reference/``, no enum, and no quota header.

    UN Comtrade's ``x-ratelimit-*`` headers count the per-second pace, not the daily quota.
    """
    lists = reference.LISTS
    names = [listed.name for listed in lists.lists]
    assert names == [
        "clCode", "flowCode", "customsCode", "motCode", "mosCode", "qtyUnitCode",
        "typeCode", "freqCode", "breakdownMode", "aggregateBy",
        "Reporters", "partnerAreas", "country_area_code_iso", "TradeDataItems",
        "ListofReferences",
    ]  # fmt: skip
    files = {path.stem for path in REFERENCE.glob("*.json")}
    assert set(names) == set(lists.packaged) == {*PACKAGED_LISTS, *PACKAGED_TABLES} == files
    assert names.index("clCode") < names.index("ListofReferences")
    assert lists.package == PACKAGE
    assert lists.client is client
    assert lists.quota_header is None
    assert all(listed.enum is None for listed in lists.lists)


def test_refresh_reference_writes_the_provenance_rows_as_committed() -> None:
    """Each list's row, its origin and its fetch time, is the row ``reference/README.md`` holds.

    The frame writes ``| `<name>.json` | <origin> | <fetched> |`` under the table's one
    header, so a refresh that changes no list leaves the README's rows as they stand.
    """
    rows = set((REFERENCE / "README.md").read_text(encoding="utf-8").splitlines())
    for listed in reference.LISTS.lists:
        packaged = PackagedList.load(PACKAGE, listed.name)
        origin = listed.origin if isinstance(listed.origin, str) else listed.origin(packaged)
        fetched = f"{packaged.fetched:%Y-%m-%dT%H:%M:%SZ}"
        assert f"| `{listed.name}.json` | {origin} | {fetched} |" in rows, listed.name


def test_refresh_reference_reads_the_spec_lists_as_packaged() -> None:
    """The four lists of the spec snapshot hold the records their files hold, read offline."""
    for name in reference.SPEC_LISTS:
        packaged = PackagedList.load(PACKAGE, name)
        read = reference.from_spec(name)
        assert (read.param, read.endpoint, read.records) == (
            packaged.param,
            packaged.endpoint,
            packaged.records,
        ), name


def test_refresh_reference_sends_no_key(
    respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every request of the declaration goes to a public reference file, without the key.

    The route refuses each connection, so no answer is built: the test reads what was sent.
    The client keeps one attempt per request, as the frame sets it for a run.
    """
    monkeypatch.setattr(client, "config", replace(client.config, retry=RetryPolicy(max_attempts=1)))
    sent: list[tuple[str, bool]] = []

    def refuse(request: httpx.Request) -> None:
        sent.append((str(request.url), KEY_HEADER in request.headers))
        raise httpx.ConnectError("refused by the test", request=request)

    respx_mock.get(url__startswith="https://comtradeapi.un.org/").mock(side_effect=refuse)
    for listed in reference.LISTS.lists:
        if listed.name in reference.SPEC_LISTS:
            continue
        with pytest.raises(TransportError):
            listed.fetch()
    files = {file for file, _, _ in reference.LISTS_FROM_FILES.values()}
    files |= set(reference.TABLES.values())
    assert len(files) == 10
    assert {url for url, _ in sent} == {
        f"https://comtradeapi.un.org/files/v1/app/reference/{file}" for file in files
    }
    assert not any(keyed for _, keyed in sent)
