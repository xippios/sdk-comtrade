"""The maintenance scripts under ``scripts/``, checked without a request or a key.

``scripts/refresh_reference.py`` is a declaration of core's frame (sdk-core ADR-0062), whose
command line, fetch, write and count are core's and tested there; what stays here is what
the script declares.
"""

import importlib.util
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
import respx
from xippios.core import Answer, PackagedList, RetryPolicy, TransportError, ValidationError

from xippios.comtrade import api
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
        "clCode", "flowCode", "customsCode", "motCode", "mosCode", "qtyUnitCode", "freqCode",
        "typeCode", "breakdownMode", "aggregateBy",
        "Reporters", "partnerAreas", "country_area_code_iso", "TradeDataItems",
        "ListofReferences",
    ]  # fmt: skip
    assert reference.LISTS_FROM_FILES["freqCode"][0] == "Frequency.json"
    assert list(reference.SPEC_LISTS) == ["typeCode", "breakdownMode", "aggregateBy"]
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
    """The three lists of the spec snapshot hold the records their files hold, read offline."""
    for name in reference.SPEC_LISTS:
        packaged = PackagedList.load(PACKAGE, name)
        read = reference.from_spec(name)
        assert (read.param, read.endpoint, read.records) == (
            packaged.param,
            packaged.endpoint,
            packaged.records,
        ), name


def test_refresh_reference_reads_type_code_without_words() -> None:
    """``typeCode``'s values alone: UN Comtrade lists no reference file of them.

    A label names a code in upstream's own words, from upstream's own list (sdk-core
    docs/conventions.md, §14, sentence 3), and the wording of a parameter's description is
    none, so ``C`` and ``S`` stand alone, as ``breakdownMode``'s values do.
    """
    read = reference.from_spec("typeCode")
    assert read.records == [{"typeCode": "C"}, {"typeCode": "S"}]
    assert read.endpoint == "files/v1/app/apim/comtrade.json"


FREQUENCY_FETCHED = datetime(2026, 11, 27, 9, 0, 0, tzinfo=UTC)
"""The ``retrieved_at`` of the replaced wrapper's answer below."""


def _hand_frequency(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]) -> list[str]:
    """Replace ``api.reference_rows`` so that it hands ``rows`` on as ``Frequency.json``'s.

    No route serves the rows and no ``classify`` reads them: they reach the script through
    the replaced wrapper, so nothing is sent. The rows are an input of the test, not an
    answer from UN Comtrade. The list returned names each file the script asked for.
    """
    asked: list[str] = []

    async def reference_rows(name: str) -> Answer[list[dict[str, Any]]]:
        asked.append(name)
        return Answer(rows, FREQUENCY_FETCHED)

    monkeypatch.setattr(api, "reference_rows", reference_rows)
    return asked


def test_refresh_reference_reads_the_words_of_freq_code_from_frequency_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``freqCode`` is the ``id`` of each row of ``Frequency.json`` with its ``text``.

    The rows are read by their model, ``ReferenceCode``, as the other code lists of UN
    Comtrade's reference files are, in place of the words cut from the spec's description
    ("Trade frequency: A for annual and M for monthly"), by the maintainer's decision of
    2026-11-26 (https://github.com/xippios/sdk-comtrade/issues/68).
    """
    asked = _hand_frequency(
        monkeypatch, [{"id": "A", "text": "Annual"}, {"id": "M", "text": "Monthly"}]
    )
    read = reference.from_file("freqCode")
    assert asked == ["Frequency.json"]
    assert read.param == "freqCode"
    assert read.endpoint == "files/v1/app/reference/Frequency.json"
    assert read.fetched == FREQUENCY_FETCHED
    assert read.records == [
        {"freqCode": "A", "text": "Annual"},
        {"freqCode": "M", "text": "Monthly"},
    ]
    assert read.note is not None
    assert read.note.startswith("The ids of Frequency.json with their text")


def _packaged_files() -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(REFERENCE.iterdir())}


@pytest.mark.parametrize(
    ("rows", "error", "message"),
    [
        ([{"id": "M", "text": "Monthly"}], SystemExit, "no row of A,"),
        ([{"id": "A", "text": "Annual"}], SystemExit, "no row of M,"),
        (
            [{"id": "A", "text": "Annual", "order": 1}, {"id": "M", "text": "Monthly", "order": 2}],
            SystemExit,
            r"keys \['order'\] are not in ReferenceCode",
        ),
        (
            [{"freqCode": "A", "freqDesc": "Annual"}, {"freqCode": "M", "freqDesc": "Monthly"}],
            ValidationError,
            r"reference/Frequency\.json: .+ first at id \(missing\)",
        ),
    ],
    ids=["without-A", "without-M", "a-key-the-model-lacks", "rows-of-another-model"],
)
def test_refresh_reference_stops_before_it_writes_where_frequency_json_differs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    rows: list[dict[str, Any]],
    error: type[BaseException],
    message: str,
) -> None:
    """A run stops before it writes where the rows of ``Frequency.json`` lack ``A`` or ``M``.

    ``A`` and ``M`` are the values of the spec's ``freqCode`` enum, which every task takes;
    rows that the model does not read stop it too. The frame fetches every list before it
    writes one, so every packaged file and the provenance table keep their bytes, and the
    reading follows the fetched rows before the script runs again.
    """
    _hand_frequency(monkeypatch, rows)
    before = _packaged_files()
    with pytest.raises(error, match=message):
        reference.main(["--only", "freqCode"])
    assert _packaged_files() == before
    assert "requests sent: 0" in capsys.readouterr().out, "the replaced wrapper sent none"


def test_refresh_reference_sends_no_key(
    respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every request of the declaration goes to one of eleven public reference files, keyless.

    The route refuses each connection, so no answer is built: the test reads what was sent.
    The client keeps one attempt per request, as the frame sets it for a run. The eleven are
    the ten files the packaged lists and tables are read from and ``Frequency.json``.
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
    assert len(files) == 11
    assert "Frequency.json" in files
    assert {url for url, _ in sent} == {
        f"https://comtradeapi.un.org/files/v1/app/reference/{file}" for file in files
    }
    assert not any(keyed for _, keyed in sent)
