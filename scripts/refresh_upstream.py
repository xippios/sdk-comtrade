"""Refresh the upstream documentation snapshot in ``docs/upstream/`` (``/refresh-upstream``).

The script declares the snapshot, ``SNAPSHOT``, and core's frame runs it
(``xippios.core.refresh``, sdk-core ADR-0062): the fetch, the attribution check,
``FETCHED.md``, the write and ``--check`` are the frame's. Every page is public, on three
hosts, so the snapshot hands the frame no client: the frame's own, built from the slug,
holds no credentials, and the script reads no environment variable. Each page is named at
the address that answers it, since the frame follows no redirect to another host, and no
page is read from another, so a capture sends one request a page. What is UN Comtrade's own
are its pages, its attribution and its hooks:

- the API documentation, ``DOCS_URL``, a server-rendered page that names none of the
  OpenAPI files: it is read for its footer's link to the licence agreement and kept
  without a file, and its scripts' nonce, new on every response, leaves its row without a
  size or a sha256;
- the five OpenAPI files of the API products, ``APIDOCS_FILES``, fixed pages under
  ``APIM_BASE`` that no page names, each saved byte for byte as served,
  ``apidocs/<file>``, and ``note`` gives its row the file's OpenAPI version (the
  maintainer's decision of 2026-11-27);
- ``reduce``: each Help Center article in ``HELP_SLUGS`` is the article body from the
  WordPress REST API converted to Markdown under a two-line provenance header,
  ``help/<slug>.md``, and ``note`` words its row from the answer.

Each file in ``REFERENCE_FILES`` is kept byte for byte as ``reference/<name>``, and the
Help Center's home page is read for its footer alone. Run from the repository root::

    uv run scripts/refresh_upstream.py            # fetch, then write the snapshot
    uv run scripts/refresh_upstream.py --check    # fetch and compare; write nothing
"""

import html
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag
from markdownify import ATX, BACKSLASH, MarkdownConverter
from xippios.core.refresh import (
    Page,
    Response,
    Row,
    Snapshot,
    Statement,
    changed,
    decode,
    parse_json,
    run,
)

ROOT = Path(__file__).resolve().parents[1]
DOCS_URL = "https://comtrade.un.org/en/api-docs"
"""UN Comtrade's API documentation at the address that answers it, on a host of its own
since the site was rebuilt (https://github.com/xippios/sdk-comtrade/issues/71)."""
LICENCE_URL = "https://comtrade.un.org/en/license-agreement"
APIM_BASE = "https://comtradeapi.un.org/files/v1/app/apim/"
APIDOCS_FILES = (
    "public.json",
    "comtrade.json",
    "comtradeTools.json",
    "comtradebulk.json",
    "comtradeAsync.json",
)
"""The OpenAPI files of the five API products, by the names ``APIM_BASE`` serves them at."""
HELP_HOME = "https://uncomtrade.org/"
HELP_API = "https://uncomtrade.org/wp-json/wp/v2/docs"
HELP_FIELDS = "id,slug,link,modified,title,content"
HELP_SLUGS = (
    "un-comtrade-api",
    "subscriptions",
    "list-of-references-parameter-codes",
    "what-is-data-preview",
    "trade-flows-in-un-comtrade",
    "second-partner-country",
    "how-do-i-use-wildcards-to-query-data",
    "data",
    "data-availability",
    "metadata",
    "un-comtrade-tools",
    "developer-tools",
    "un-comtrade-data-pipeline",
    "bilateral-asymmetries",
    "how-to-retrieve-data-for-world-exports-to-a-country-in-un-comtrade",
    "how-should-i-interpret-and-use-quantity-data-in-un-comtrade",
    "policy-on-comtrade-data-use",
    "read-me-first-disclaimer",
)
"""Help Center articles to capture, by WordPress slug (``uncomtrade.org/docs/<slug>/``)."""
REFERENCE_BASE = "https://comtradeapi.un.org/files/v1/app/reference/"
REFERENCE_FILES = ("ListofReferences.json", "TradeDataItems.json")
UNSTABLE = frozenset(
    {"what-is-data-preview", "data", "data-availability", "un-comtrade-data-pipeline"}
)
"""The articles whose body carries a WordPress image id (``data-wp-key``) that is new on
every request, so their rows record no size or sha256: the frame declares a page's
stability, and ``note`` stops the run where an article's answer no longer agrees."""
TERMS = frozenset({"policy-on-comtrade-data-use", "read-me-first-disclaimer"})
"""The articles that are upstream's statement of its terms, kept whole and not searched."""


def article_url(slug: str) -> str:
    """The WordPress REST API's URL of the article ``slug``, its fields named."""
    return f"{HELP_API}?{urlencode({'slug': slug, '_fields': HELP_FIELDS}, safe=',')}"


ATTRIBUTION: tuple[Statement, ...] = (
    Statement(
        "License agreement",
        DOCS_URL,
        "in the footer of UN Comtrade's pages",
        link=LICENCE_URL,
    ),
    Statement(
        "\N{COPYRIGHT SIGN} 2026 UN Comtrade Help Center",
        HELP_HOME,
        "in the footer of the UN Comtrade Help Center's pages",
    ),
    Statement(
        "The United Nations copyright UN Comtrade data.",
        article_url("policy-on-comtrade-data-use"),
        'under "Copyright Statement and Citation" in the Policy on Comtrade Data Use, '
        "https://uncomtrade.org/docs/policy-on-comtrade-data-use/",
    ),
    Statement(
        "Use of UN Comtrade data is subject to a license agreement found at",
        article_url("policy-on-comtrade-data-use"),
        'under "License Agreement" in the Policy on Comtrade Data Use, up to its link to the '
        "agreement, https://comtrade.un.org/licenseagreement.html",
    ),
    Statement(
        "The License Agreement specifies that the UN Comtrade data are copyrighted by the "
        "United Nations and are made available for your internal use only. They may not be "
        "re-disseminated in any form without prior written consent of the United Nations "
        "Statistics Division subject to the clarification at",
        article_url("read-me-first-disclaimer"),
        'under "License Agreement" in Read Me First (Disclaimer), '
        "https://uncomtrade.org/docs/read-me-first-disclaimer/, up to its link to the Policy "
        "on use and re-dissemination",
    ),
)
"""Every copyright line, licence or terms of use the documentation states, as printed.

The documentation page states none but its footer's link, whose text the check reads past
only as the text of a link to the agreement. The REST API serves an article's body without
the Help Center's footer, so the footer's line is read from the Help Center's home page.
The data's terms are two articles of their own, captured with the others and marked
``terms``: each must print its lines. The frame
reads a JSON answer as its text, the article's HTML in a string, so a line quoted from an
article stops where the printed text meets markup or a character outside ASCII, a link, a
paragraph's end or a curly apostrophe; the articles are kept whole under ``help/``.
"""

_NONCE = re.compile(r"""<meta\s+name=["']csp-nonce["']\s+content=["'][^"']+["']""")
"""The documentation page's Content Security Policy nonce, which its scripts carry."""
_RENDER_ID = re.compile(r"data-wp-key=")
"""WordPress's lightbox image block, whose ``data-wp-key`` id is new on every render."""

_TABLE_TAGS = {"table", "thead", "tbody", "tfoot", "tr", "th", "td"}
_KEPT_TAGS = _TABLE_TAGS | {"a", "br", "strong", "em", "b", "i", "code"}
"""Tags a table with merged cells keeps; any other tag is dropped and its text kept."""


def _tags(root: Tag, *names: str, recursive: bool = True) -> list[Tag]:
    found = root.find_all(list(names) or True, recursive=recursive)
    return [tag for tag in found if isinstance(tag, Tag)]


def _has_merged_cells(table: Tag) -> bool:
    return any(c.has_attr("rowspan") or c.has_attr("colspan") for c in _tags(table, "th", "td"))


def _html_table(table: Tag) -> str:
    """A table with merged cells as plain HTML, since a pipe table cannot merge cells.

    Only ``rowspan``/``colspan`` (and a link's ``href``) survive; an image becomes its alt
    text or, without one, its file name; other markup is dropped and its text kept.
    """
    for image in _tags(table, "img"):
        alt = str(image.get("alt") or "").strip()
        image.replace_with(alt or Path(urlsplit(str(image.get("src") or "")).path).name)
    for tag in _tags(table):
        if tag.name not in _KEPT_TAGS:
            tag.unwrap()
            continue
        kept = ("rowspan", "colspan") if tag.name in ("th", "td") else ("href",)
        tag.attrs = {name: value for name, value in tag.attrs.items() if name in kept}
    lines = ["<table>"]
    for row in _tags(table, "tr"):
        cells = []
        for cell in _tags(row, "th", "td", recursive=False):
            spans = "".join(f' {name}="{html.escape(str(v))}"' for name, v in cell.attrs.items())
            content = re.sub(r"\s+", " ", cell.decode_contents()).strip()
            content = re.sub(r"^(?:<br/>\s*)+|(?:\s*<br/>)+$", "", content)
            cells.append(f"<{cell.name}{spans}>{content}</{cell.name}>")
        lines.append("<tr>" + "".join(cells) + "</tr>")
    return "\n".join([*lines, "</table>"])


def to_markdown(fragment: str, base: str) -> str:
    """Convert an article body to Markdown, with absolute links and ATX headings.

    Tables become pipe tables, except a table with merged cells, which stays HTML.
    """
    soup = BeautifulSoup(fragment, "html.parser")
    for tag in _tags(soup, "button", "svg", "script", "style", "noscript"):
        tag.decompose()
    for tag in _tags(soup):
        for attribute in ("href", "src"):
            value = tag.get(attribute)
            if isinstance(value, str):
                tag[attribute] = urljoin(base, value.strip())
    merged: list[str] = []
    for table in _tags(soup, "table"):
        if _has_merged_cells(table):
            placeholder = soup.new_tag("p")
            placeholder.string = f"XIPPIOSTABLE{len(merged)}X"
            merged.append(_html_table(table))
            table.replace_with(placeholder)
    converter = MarkdownConverter(
        heading_style=ATX, bullets="-", escape_underscores=False, newline_style=BACKSLASH
    )
    text = converter.convert_soup(soup)
    for index, table_html in enumerate(merged):
        text = text.replace(f"XIPPIOSTABLE{index}X", table_html)
    lines = [line.rstrip() for line in text.replace("\xa0", " ").strip().splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)) + "\n"


def _merged_tables(fragment: str) -> int:
    tables = _tags(BeautifulSoup(fragment, "html.parser"), "table")
    return sum(1 for table in tables if _has_merged_cells(table))


def openapi_version(response: Response) -> str:
    """The ``openapi`` version of a product file, which must be 3.x."""
    document = parse_json(response)
    version = document.get("openapi") if isinstance(document, dict) else None
    if not (isinstance(version, str) and version.startswith("3.")):
        raise changed(response.url, f"expected OpenAPI 3.x, found openapi={version!r}")
    return version


def _article(page: Page, response: Response) -> dict[str, Any]:
    """The one article the REST API answers for the page's slug."""
    articles = parse_json(response)
    if not (isinstance(articles, list) and len(articles) == 1 and isinstance(articles[0], dict)):
        raise changed(page.url, f"expected one article, got {str(articles)[:200]}")
    article: dict[str, Any] = articles[0]
    slug = Path(page.file or "").stem
    content = article.get("content")
    body = content.get("rendered") if isinstance(content, dict) else None
    if article.get("slug") != slug or not isinstance(body, str) or not body.strip():
        raise changed(page.url, f"no article body for {slug!r}")
    return article


def reduce(page: Page, response: Response) -> bytes:
    """An article as Markdown under its title and WordPress ``modified``; any other as served."""
    if not (page.file or "").startswith("help/"):
        return response.body
    article = _article(page, response)
    try:
        link, modified = str(article["link"]), str(article["modified"])
        title = html.unescape(str(article["title"]["rendered"])).strip()
    except (KeyError, TypeError) as error:
        raise changed(page.url, f"article without {error}") from None
    escaped = title.replace("[", r"\[").replace("]", r"\]")
    header = f"# [{escaped}]({link})\n\nUpstream modified: {modified}\n\n"
    return (header + to_markdown(str(article["content"]["rendered"]), link)).encode("utf-8")


def note(row: Row) -> str:
    """An article's note from its answer, a product file's its version; else the page's.

    The documentation page keeps its note while it carries the nonce that leaves its row
    without a size or a sha256, and stops the run where the nonce is gone.
    """
    file = row.page.file or ""
    if row.page.url == DOCS_URL:
        if _NONCE.search(decode(row.response)) is None:
            raise changed(DOCS_URL, "its csp-nonce is gone: declare the page stable")
        return row.page.note
    if file.startswith("apidocs/"):
        return f"OpenAPI {openapi_version(row.response)}, as served"
    if not file.startswith("help/"):
        return row.page.note
    article = _article(row.page, row.response)
    body = str(article["content"]["rendered"])
    text = (
        f"article {article['link']}, WordPress modified {article['modified']} (site time), "
        "converted to Markdown"
    )
    merged = _merged_tables(body)
    if merged:
        text += f"; {merged} table{'s' if merged > 1 else ''} with merged cells kept as HTML"
    if (_RENDER_ID.search(body) is None) != row.page.stable:
        raise changed(row.page.url, "the article's data-wp-key image id came or went: see UNSTABLE")
    if not row.page.stable:
        text += (
            "; the body carries a WordPress image id (data-wp-key) that is new on every "
            "request, so no size or sha256"
        )
    return text


CAPTURE = """The API documentation, https://comtrade.un.org/en/api-docs, is a server-rendered
page that names none of the OpenAPI files and prints no table of the API products: its
console loads one product's document in a browser. The script reads the page for its
footer's link to the licence agreement and keeps no file of it, and its row has no size or
sha256, since its scripts carry a nonce that is new on every response. The five OpenAPI
files of the API products are fixed pages under
https://comtradeapi.un.org/files/v1/app/apim/, each saved byte for byte as served under
`apidocs/`, the premium products' files among them, by the maintainer's decision of
2026-11-27.

Help Center articles come from the WordPress REST API, as the article body only (no theme,
no navigation), converted to Markdown. A table with merged cells (`rowspan`/`colspan`)
stays an HTML table that keeps only the spans and links, with images as their alt text or
file name, and the article's row says so; every other table becomes a pipe table. The two
articles that state the data's terms are kept whole and not searched beyond the lines the
Attribution quotes, each up to the first markup or character outside ASCII in its printed
text, since the check reads the REST API's answer as its JSON text."""

SNAPSHOT = Snapshot(
    name="UN Comtrade",
    slug="comtrade",
    pages=(
        Page(
            DOCS_URL,
            stable=False,
            note=(
                "the API documentation, read for the Attribution above, kept without a file; "
                "its scripts carry a nonce that is new on every response, so no size or sha256"
            ),
        ),
        *(Page(APIM_BASE + name, f"apidocs/{name}") for name in APIDOCS_FILES),
        *(
            Page(
                article_url(slug),
                f"help/{slug}.md",
                stable=slug not in UNSTABLE,
                terms=slug in TERMS,
            )
            for slug in HELP_SLUGS
        ),
        *(
            Page(REFERENCE_BASE + name, f"reference/{name}", note="as served")
            for name in REFERENCE_FILES
        ),
        Page(HELP_HOME, note="read for the Attribution above, kept without a file"),
    ),
    attribution=ATTRIBUTION,
    capture=CAPTURE,
    out=ROOT / "docs/upstream",
    reduce=reduce,
    note=note,
)
"""UN Comtrade's snapshot, which core's frame runs through its own client, without a key."""


if __name__ == "__main__":
    raise SystemExit(run(SNAPSHOT))
