"""``scripts/refresh_upstream.py``'s declaration and its hooks, offline.

Core's frame (``xippios.core.refresh``, sdk-core ADR-0062) fetches, checks the attribution,
writes ``FETCHED.md`` and the files and compares them in ``--check``, and its own tests hold
each; what stays here is UN Comtrade's: what ``SNAPSHOT`` declares, the statements its
attribution records from a page as the frame's check reads them, and what its hooks make of
an answer. Nothing here sends a request or writes under ``docs/upstream/``.
"""

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from urllib.parse import urlsplit

import pytest
from xippios.core.refresh import Page, Response, Row
from xippios.core.refresh.upstream import check_attribution

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


def test_the_snapshot_declares_every_page_file_and_statement_page() -> None:
    """Every page is public: the frame's own client, no credential, no variable.

    The documentation page comes first, kept without a file, then the five OpenAPI files, the
    articles and the reference files, and the Help Center's home page last.
    """
    snapshot = script.SNAPSHOT
    pages = {page.url: page for page in snapshot.pages}
    files = [page.file for page in snapshot.pages if page.file]
    assert files == [
        *(f"apidocs/{name}" for name in script.APIDOCS_FILES),
        *(f"help/{slug}.md" for slug in script.HELP_SLUGS),
        *(f"reference/{name}" for name in script.REFERENCE_FILES),
    ]
    assert snapshot.pages[0].url == script.DOCS_URL == "https://comtrade.un.org/en/api-docs"
    assert snapshot.pages[0].file is None
    assert snapshot.pages[-1].url == script.HELP_HOME
    assert {statement.source for statement in snapshot.attribution} == {
        script.DOCS_URL,
        script.HELP_HOME,
        *(script.article_url(slug) for slug in script.TERMS),
    }
    assert {statement.source for statement in snapshot.attribution} <= set(pages)
    terms = {page.file for page in snapshot.pages if page.terms}
    assert terms == {f"help/{slug}.md" for slug in script.TERMS}
    unstable = {page.file for page in snapshot.pages if not page.stable}
    assert unstable == {None, *(f"help/{slug}.md" for slug in script.UNSTABLE)}
    assert not pages[script.DOCS_URL].stable
    assert snapshot.client is None
    assert snapshot.variables == ()
    assert not any(page.keyed for page in snapshot.pages)


def test_the_openapi_files_are_fixed_pages_of_the_apim_base() -> None:
    """The five OpenAPI files of the API products, each at the base that serves them.

    No page of the site names the files any longer, so the snapshot declares them, the
    files that ``docs/upstream/apidocs/`` holds (the maintainer's decision of 2026-11-27).
    """
    assert script.APIM_BASE == "https://comtradeapi.un.org/files/v1/app/apim/"
    declared = [page for page in script.SNAPSHOT.pages if (page.file or "").startswith("apidocs/")]
    assert [(page.url, page.file) for page in declared] == [
        (script.APIM_BASE + name, f"apidocs/{name}") for name in script.APIDOCS_FILES
    ]
    committed = {path.name for path in (ROOT / "docs/upstream/apidocs").glob("*.json")}
    assert sorted(script.APIDOCS_FILES) == sorted(committed)
    assert all(page.stable and not page.terms for page in declared)


def test_a_capture_requests_the_declared_pages_and_no_other() -> None:
    """Each page is named at the address that answers it, on three hosts, and none is linked.

    The frame follows no redirect to another host, and ``linked`` names no page, so a capture
    sends one request for each of the 27 pages, before a retry; no section is the script's.
    The four pages that ``not_fetched`` names, the licence agreement, the console's document,
    the data availability API and My API Portal, are no pages of the snapshot: the frame
    writes their rows under ``Not fetched`` and requests them never.
    The answers below are inputs of the test, not answers from UN Comtrade.
    """
    snapshot = script.SNAPSHOT
    assert len(snapshot.pages) == len({page.url for page in snapshot.pages}) == 27
    hosts = {urlsplit(page.url).netloc for page in snapshot.pages}
    assert hosts == {"comtrade.un.org", "comtradeapi.un.org", "uncomtrade.org"}
    assert all(page.url.startswith("https://") for page in snapshot.pages)
    for page in snapshot.pages:
        row = Row(page, answer(page.url, b"{}", "application/json"), None)
        assert snapshot.linked(row) == ()
    assert snapshot.sections([]) == ()
    assert [entry.url for entry in snapshot.not_fetched] == [
        script.LICENCE_URL,
        script.CONSOLE_SPEC_URL,
        script.DATA_AVAILABILITY_API_URL,
        script.API_PORTAL_URL,
    ]
    assert not {entry.url for entry in snapshot.not_fetched} & {page.url for page in snapshot.pages}


def test_each_link_the_attribution_records_is_fetched_or_not_fetched() -> None:
    """The documentation page's footer and the Policy on Comtrade Data Use link the licence
    agreement, which the snapshot does not request, so ``not_fetched`` names it with its reason
    and ``FETCHED.md``'s ``Not fetched`` holds its row (conventions §3)."""
    fetched = {page.url for page in script.SNAPSHOT.pages}
    left_out = {entry.url: entry.reason for entry in script.SNAPSHOT.not_fetched}
    linked = {statement.link for statement in script.ATTRIBUTION if statement.link}
    assert linked == {script.LICENCE_URL}
    assert linked <= fetched | left_out.keys()
    reason = left_out[script.LICENCE_URL]
    assert "License Agreement" in reason
    assert "Policy on Comtrade Data Use" in reason


LINK = re.compile(r"https://[^\s<>()\[\]\"',;]+")
"""An address as an article's Markdown prints it, in a link, an autolink or an ``href``."""
KEPT = re.compile(r"`((?:apidocs|help)/[^`\s]+)`")
"""A file of the snapshot that a reason names, from ``docs/upstream/``."""


def test_the_pages_the_documentation_links_and_no_capture_requests_are_not_fetched() -> None:
    """The console's document, the data availability API and My API Portal have their rows
    under ``Not fetched``, each with its reason (conventions §3,
    https://github.com/xippios/sdk-comtrade/issues/80).

    The documentation page's console loads one document for a viewer without an account, at
    the page's own address, and the snapshot keeps the Public product's OpenAPI file in its
    place. The kept articles link the other two, and each reason names the kept files that
    hold what the snapshot reads in place of the page.
    """
    left_out = {entry.url: entry.reason for entry in script.SNAPSHOT.not_fetched}
    console = script.CONSOLE_SPEC_URL
    assert console == "https://comtrade.un.org/en/api-docs?handler=Spec&product=public"
    assert urlsplit(console)._replace(query="").geturl() == script.DOCS_URL
    assert f"{script.APIM_BASE}public.json" in left_out[console]
    assert script.DATA_AVAILABILITY_API_URL == "https://comtradedeveloper.un.org/"
    assert script.API_PORTAL_URL == "https://comtrade.un.org/en/api-portal"
    kept = {
        slug: set(LINK.findall((ROOT / "docs/upstream/help" / f"{slug}.md").read_text("utf-8")))
        for slug in script.HELP_SLUGS
    }
    linking = {
        url: sorted(slug for slug, links in kept.items() if url in links)
        for url in (script.DATA_AVAILABILITY_API_URL, script.API_PORTAL_URL)
    }
    assert linking == {
        script.DATA_AVAILABILITY_API_URL: ["data-availability"],
        script.API_PORTAL_URL: ["data-availability", "subscriptions", "un-comtrade-api"],
    }
    named = {url: KEPT.findall(left_out[url]) for url in (console, *linking)}
    assert named == {
        console: ["apidocs/public.json"],
        script.DATA_AVAILABILITY_API_URL: ["apidocs/comtrade.json", "apidocs/public.json"],
        script.API_PORTAL_URL: ["help/subscriptions.md"],
    }
    for files in named.values():
        assert all((ROOT / "docs/upstream" / file).is_file() for file in files)


AGREEMENT = re.compile(r"https://comtrade\.un\.org/[^\s<>()\[\],;]+")
"""An address of UN Comtrade's site, as a sentence or a link prints it."""


def test_the_agreement_is_named_where_the_kept_policy_links_it() -> None:
    """The Policy on Comtrade Data Use, as kept, links the agreement at the address that the
    documentation page's footer links, and the statement that quotes the Policy's sentence and
    the README's terms name that address and no other."""
    kept = (ROOT / "docs/upstream/help/policy-on-comtrade-data-use.md").read_text(encoding="utf-8")
    section = kept.split("\n## License Agreement\n", 1)[1].split("\n## ", 1)[0]
    assert AGREEMENT.findall(section) == [script.LICENCE_URL]
    [policy] = [s for s in script.ATTRIBUTION if s.text.startswith("Use of UN Comtrade data")]
    assert AGREEMENT.findall(policy.where) == [script.LICENCE_URL]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    terms = readme.split("\n## Upstream terms and attribution\n", 1)[1].split("\n## ", 1)[0]
    assert AGREEMENT.findall(terms) == [script.LICENCE_URL]


FOOTER = (
    '<!DOCTYPE html><html><head><meta name="csp-nonce" content="bm9uY2U="></head><body>'
    '<main><h1>API documentation</h1></main><footer><ul><li><a href="/en/site-index">'
    'A-Z site index</a></li><li><a href="/en/license-agreement">License agreement</a></li>'
    "</ul></footer></body></html>"
)
"""The footer of the documentation page as the attribution reads it, built for the test."""


def test_the_documentation_page_records_its_footers_licence_link() -> None:
    """The footer links "License agreement" to the site's agreement, which the attribution
    records as that link, so the check reads past it there and stops where it moved.

    Each page below is an input of the test, not an answer from UN Comtrade.
    """
    [statement] = [s for s in script.ATTRIBUTION if s.source == script.DOCS_URL]
    assert statement.text == "License agreement"
    assert statement.link == "https://comtrade.un.org/en/license-agreement"
    page = script.SNAPSHOT.pages[0]
    check_attribution(script.SNAPSHOT, page, answer(page.url, FOOTER.encode(), "text/html"))
    moved = FOOTER.replace("/en/license-agreement", "/en/terms")
    with pytest.raises(SystemExit, match="no longer links 'License agreement'"):
        check_attribution(script.SNAPSHOT, page, answer(page.url, moved.encode(), "text/html"))


def test_the_documentation_pages_note_holds_its_nonce() -> None:
    """The page's scripts carry a Content Security Policy nonce, so its row records no size
    or sha256, and the run stops where the nonce is gone.

    Each page below is an input of the test, not an answer from UN Comtrade.
    """
    page = script.SNAPSHOT.pages[0]
    shell = answer(page.url, FOOTER.encode(), "text/html; charset=utf-8")
    assert script.note(Row(page, shell, None)) == page.note
    assert "nonce" in page.note
    plain = FOOTER.replace('<meta name="csp-nonce" content="bm9uY2U=">', "")
    with pytest.raises(SystemExit, match="csp-nonce"):
        script.note(Row(page, answer(page.url, plain.encode(), "text/html"), None))


def test_an_openapi_files_note_is_its_version() -> None:
    """A product file's row names its OpenAPI version, 3.x, read without duplicate keys.

    Each answer below is an input of the test, not an answer from UN Comtrade.
    """
    [page] = [p for p in script.SNAPSHOT.pages if p.file == "apidocs/comtradebulk.json"]
    served = answer(page.url, b'{"openapi": "3.0.1"}', "application/json")
    assert script.note(Row(page, served, served.body)) == "OpenAPI 3.0.1, as served"
    swagger = answer(page.url, b'{"swagger": "2.0"}', "application/json")
    with pytest.raises(SystemExit, match=r"expected OpenAPI 3\.x"):
        script.note(Row(page, swagger, swagger.body))
    twice = answer(page.url, b'{"openapi": "3.0.1", "openapi": "3.1.0"}', "text/plain")
    with pytest.raises(SystemExit, match="duplicate keys"):
        script.note(Row(page, twice, b""))


def test_each_statement_of_an_article_is_printed_in_its_kept_file() -> None:
    """A line quoted from an article is plain text that its Markdown under ``help/`` prints.

    The frame reads the REST API's answer as its JSON text, so a line stops before any markup
    or character outside ASCII.
    """
    for statement in script.ATTRIBUTION:
        if statement.source in (script.HELP_HOME, script.DOCS_URL):
            continue
        slug = next(slug for slug in script.TERMS if script.article_url(slug) == statement.source)
        kept = (ROOT / "docs/upstream/help" / f"{slug}.md").read_text(encoding="utf-8")
        assert " ".join(statement.text.split()) in " ".join(kept.split()), slug
        assert statement.text.isascii(), slug
        assert not set(statement.text) & set("<>&\\/\"'"), slug


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
