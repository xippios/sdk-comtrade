"""``scripts/refresh_upstream.py``'s ``FETCHED.md`` and its writing, offline.

Nothing here sends a request: ``render_fetched``, ``write_snapshot`` and ``compare`` take
what a capture run fetched, here a product and a row made up for the test alone, written
under ``tmp_path``, never to ``docs/upstream/``. ``OBSERVED.md`` is the one file under
``docs/upstream/`` written by hand, the notes on what upstream does but never documents
(conventions §3, sdk-core ADR-0028).
"""

import importlib.util
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "refresh_upstream.py"
FETCHED = "2026-11-20T09:00:00Z"
HAND = "written by hand: what upstream does but never documents; not fetched or checked"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("refresh_upstream", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_script()


def an_entry() -> object:
    """A reference file's row, as a capture run makes one."""
    response = script.Response(
        url="https://comtradeapi.un.org/files/v1/app/reference/TradeDataItems.json",
        status=200,
        body=b'{"results": []}',
        etag=None,
        last_modified=None,
    )
    return script.Entry("reference/TradeDataItems.json", response, "a note", response.body)


def render(*, observed: bool, at: str = FETCHED) -> str:
    product = script.Product("comtrade", "UN Comtrade", "comtrade.json", ("free",))
    text: str = script.render_fetched(
        "main.0.js",
        "https://comtradeapi.un.org/files/v1/app/apim/",
        [product],
        ["3.0.1"],
        [an_entry()],
        at,
        observed,
    )
    return text


def test_fetched_md_lists_observed_md_in_a_row_of_its_own() -> None:
    """Once ``OBSERVED.md`` exists, the table lists it as written by hand."""
    text = render(observed=True)
    row = f"| {script.OBSERVED} | - | - | - | - | - | - | - | {HAND} |"
    assert row in text.splitlines()
    assert f"edited by hand but `{script.OBSERVED}`" in " ".join(text.split())


def test_fetched_md_names_no_observed_md_while_there_is_none() -> None:
    text = render(observed=False)
    assert script.OBSERVED not in text
    assert "never edited by hand" in " ".join(text.split())


def test_a_snapshot_leaves_observed_md_as_written(tmp_path: Path) -> None:
    """The run writes its files and ``FETCHED.md``, never touches the notes, and its
    ``--check`` reads them as part of the snapshot."""
    notes = tmp_path / script.OBSERVED
    notes.write_text("# What UN Comtrade does but never documents\n", encoding="utf-8")
    (tmp_path / "FETCHED.md").write_text("old\n", encoding="utf-8")
    script.write_snapshot(tmp_path, [an_entry()], render(observed=True))
    assert notes.read_text(encoding="utf-8") == "# What UN Comtrade does but never documents\n"
    assert (tmp_path / "reference" / "TradeDataItems.json").read_bytes() == b'{"results": []}'
    assert script.compare(tmp_path, [an_entry()], lambda at: render(observed=True, at=at)) == []
