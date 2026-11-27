"""``scripts/refresh_upstream.py``'s declaration and its hooks, offline.

Core's frame (``xippios.core.refresh``, sdk-core ADR-0062) fetches, checks the attribution,
writes ``FETCHED.md`` and the files and compares them in ``--check``, and its own tests hold
each; what stays here is UN Comtrade's: what ``SNAPSHOT`` declares and what its hooks make of
an answer. Nothing here sends a request or writes under ``docs/upstream/``.
"""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from xippios.core.refresh import Page, Response, Row

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refresh_upstream.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("refresh_upstream", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_script()


def answer(url: str, body: bytes, content_type: str) -> Response:
    """The answer a hook reads.

    The answer is an input of the test, not an answer from UN Comtrade.
    """
    return Response(url, 200, body, content_type, None, None, ())


def test_the_snapshot_declares_every_article_reference_file_and_statement_page() -> None:
    """Every page is public: the frame's own client, no credential, no variable."""
    snapshot = script.SNAPSHOT
    pages = {page.url: page for page in snapshot.pages}
    files = [page.file for page in snapshot.pages if page.file]
    assert files == [
        *(f"help/{slug}.md" for slug in script.HELP_SLUGS),
        *(f"reference/{name}" for name in script.REFERENCE_FILES),
    ]
    assert snapshot.pages[0].url == script.APIDOCS_URL
    assert snapshot.pages[-1].url == script.HELP_HOME
    assert {statement.source for statement in snapshot.attribution} == {
        script.HELP_HOME,
        *(script.article_url(slug) for slug in script.TERMS),
    }
    assert {statement.source for statement in snapshot.attribution} <= set(pages)
    terms = {page.file for page in snapshot.pages if page.terms}
    assert terms == {f"help/{slug}.md" for slug in script.TERMS}
    unstable = {page.file for page in snapshot.pages if not page.stable}
    assert unstable == {f"help/{slug}.md" for slug in script.UNSTABLE}
    assert snapshot.client is None
    assert snapshot.variables == ()
    assert not any(page.keyed for page in snapshot.pages)


def test_each_statement_of_an_article_is_printed_in_its_kept_file() -> None:
    """A line quoted from an article is plain text that its Markdown under ``help/`` prints.

    The frame reads the REST API's answer as its JSON text, so a line stops before any markup
    or character outside ASCII.
    """
    for statement in script.ATTRIBUTION:
        if statement.source == script.HELP_HOME:
            continue
        slug = next(slug for slug in script.TERMS if script.article_url(slug) == statement.source)
        kept = (ROOT / "docs/upstream/help" / f"{slug}.md").read_text(encoding="utf-8")
        assert " ".join(statement.text.split()) in " ".join(kept.split()), slug
        assert statement.text.isascii(), slug
        assert not set(statement.text) & set("<>&\\/\"'"), slug


def test_linked_reads_the_bundle_and_then_its_products() -> None:
    """The page names one bundle, and the bundle its tiers, its products and its base.

    Each answer below is an input of the test, not an answer from UN Comtrade.
    """
    shell = answer(
        script.APIDOCS_URL, b'<script src="/static/js/main.0a1b.js"></script>', "text/html"
    )
    [bundle] = script.linked(Row(script.SNAPSHOT.pages[0], shell, None))
    assert bundle.url == "https://comtradeplus.un.org/static/js/main.0a1b.js"
    assert bundle.file is None
    source = (
        'a="anonymous",b="free",c="premium";var t=[{key:"comtrade",label:"UN Comtrade",'
        'file:"comtrade.json",access:[a,b,c]},{key:"bulk",label:"Bulk",file:"bulk.json",'
        'access:[c]}];fetch("https://comtradeapi.un.org/files/v1/app/apim/"+f)'
    )
    code = answer(bundle.url, source.encode(), "application/javascript")
    products = script.linked(Row(bundle, code, None))
    assert [(page.url, page.file) for page in products] == [
        ("https://comtradeapi.un.org/files/v1/app/apim/comtrade.json", "apidocs/comtrade.json"),
        ("https://comtradeapi.un.org/files/v1/app/apim/bulk.json", "apidocs/bulk.json"),
    ]
    rows = [
        Row(bundle, code, None),
        *(
            Row(page, answer(page.url, b'{"openapi": "3.0.1"}', "application/json"), b"")
            for page in products
        ),
    ]
    [section] = script.sections(rows)
    assert section.heading == "Products found"
    assert "| bulk | Bulk | bulk.json | premium | 3.0.1 |" in section.text.splitlines()
    assert script.note(rows[1]) == "OpenAPI 3.0.1, as served"
    with pytest.raises(SystemExit, match="the ApiDocs bundle changed"):
        script.linked(Row(bundle, answer(bundle.url, b"var t=[]", "text/javascript"), None))
    twice = answer(products[0].url, b'{"openapi": "3.0.1", "openapi": "3.1.0"}', "text/plain")
    with pytest.raises(SystemExit, match="duplicate keys"):
        script.note(Row(products[0], twice, b""))


def test_an_article_becomes_markdown_under_its_title_and_its_note_says_how() -> None:
    """The REST API's one article: Markdown with absolute links, a merged table kept as HTML.

    The article is an input of the test, not an answer from UN Comtrade.
    """
    page = next(p for p in script.SNAPSHOT.pages if p.file == "help/subscriptions.md")
    body = (
        '<p>See <a href="/docs/data/">Data</a>.</p><table><tr><th colspan="2">Limits</th></tr>'
        "<tr><td>calls</td><td>500</td></tr></table>"
    )
    article = {
        "slug": "subscriptions",
        "link": "https://uncomtrade.org/docs/subscriptions/",
        "modified": "2026-01-02T03:04:05",
        "title": {"rendered": "Subscriptions &amp; limits"},
        "content": {"rendered": body},
    }
    response = answer(page.url, json.dumps([article]).encode(), "application/json")
    markdown = script.reduce(page, response).decode("utf-8")
    assert markdown.startswith(
        "# [Subscriptions & limits](https://uncomtrade.org/docs/subscriptions/)\n\n"
        "Upstream modified: 2026-01-02T03:04:05\n\n"
    )
    assert "[Data](https://uncomtrade.org/docs/data/)" in markdown
    assert '<th colspan="2">Limits</th>' in markdown
    note = script.note(Row(page, response, markdown.encode()))
    assert note == (
        "article https://uncomtrade.org/docs/subscriptions/, WordPress modified "
        "2026-01-02T03:04:05 (site time), converted to Markdown; 1 table with merged cells "
        "kept as HTML"
    )
    empty = answer(page.url, b"[]", "application/json")
    with pytest.raises(SystemExit, match="expected one article"):
        script.reduce(page, empty)
    unstable = Page(page.url, page.file, stable=False)
    with pytest.raises(SystemExit, match="data-wp-key"):
        script.note(Row(unstable, response, markdown.encode()))
