# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "beautifulsoup4==4.15.0",
#     "markdownify==1.2.3",
# ]
#
# [tool.uv]
# exclude-newer = "2026-10-23T00:00:00Z"
# ///
"""Refresh the upstream documentation snapshot in ``docs/upstream/`` (``/refresh-upstream``).

ApiDocs (https://comtradeplus.un.org/ApiDocs) is a React app that embeds Swagger UI. Its
bundle ``/static/js/main.<hash>.js`` holds the table of API products (key, label, OpenAPI
file, subscription tiers) and the base URL the files are loaded from. The page shows only
the products of the viewer's tier; this script reads the table from the bundle and saves
every product file as served, so the snapshot covers all of them. It writes:

- ``apidocs/<file>``: each product's OpenAPI document, byte for byte;
- ``help/<slug>.md``: each Help Center article in ``HELP_SLUGS``, the article body from
  the WordPress REST API converted to Markdown under a two-line provenance header;
- ``reference/<name>``: each file in ``REFERENCE_FILES``, byte for byte;
- ``FETCHED.md``: regenerated entirely (conventions §3): the attribution, the products
  found and one row per file and per page read without one (the ApiDocs page and its
  bundle, a slug the REST API does not know, the page ``ATTRIBUTION`` is read from), each
  with the UTC time of the run, the HTTP status, the size and sha256 of the body as
  fetched, and the ETag and Last-Modified where sent.

Everything is fetched before anything is written, one request at a time, each URL retried
at most once; files a previous snapshot had and this one does not are removed. Every run
stops, before writing, when a page states a copyright line, a licence or terms of use that
``ATTRIBUTION`` does not record, or when the page a recorded statement is read from no
longer prints it. The same upstream gives the same files; ``FETCHED.md`` then differs in
``Fetched`` alone. No key is needed or read. Run from the repository root::

    uv run scripts/refresh_upstream.py            # fetch, then write the snapshot
    uv run scripts/refresh_upstream.py --check    # fetch and compare; write nothing

``--check`` exits 1 when the snapshot differs from what upstream serves now, ``Fetched``
aside, and names the files that differ.
"""

import argparse
import gzip
import hashlib
import html
import http.client
import json
import re
import textwrap
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag
from markdownify import ATX, BACKSLASH, MarkdownConverter

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "docs/upstream"
COMMAND = "uv run scripts/refresh_upstream.py"

APIDOCS_URL = "https://comtradeplus.un.org/ApiDocs"
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
)
"""Help Center articles to capture, by WordPress slug (``uncomtrade.org/docs/<slug>/``)."""
REFERENCE_BASE = "https://comtradeapi.un.org/files/v1/app/reference/"
REFERENCE_FILES = ("ListofReferences.json", "TradeDataItems.json")

USER_AGENT = "xippios-comtrade refresh_upstream (+https://github.com/xippios/sdk-comtrade)"
TIMEOUT = 60.0
PAUSE = 2.0
"""Seconds before every request; requests never run in parallel."""
RETRY_PAUSE = 10.0
"""Seconds before the one retry; uncomtrade.org now and then refuses a connection."""
SUBDIRS = ("apidocs", "help", "reference")
REQUESTS: list[str] = []
"""Every request the run sent, retries included, by URL: the count the run reports."""


@dataclass(frozen=True)
class Statement:
    """A copyright line, licence or terms of use upstream prints, and where it is read."""

    text: str
    where: str
    url: str


ATTRIBUTION: tuple[Statement, ...] = (
    Statement(
        "\N{COPYRIGHT SIGN} 2026 UN Comtrade Help Center",
        "in the footer of the UN Comtrade Help Center's pages",
        HELP_HOME,
    ),
)
"""Every copyright line, licence or terms of use the documentation states, as printed.

The REST API serves an article's body without the Help Center's footer, so the footer's
line is read from the Help Center's home page (its article pages print the same footer).
Every run stops when a page states one that is not here, and when the page a statement is
read from no longer prints it (a new year, say).
"""

_IDENT = r"[A-Za-z_$][\w$]*"
_BUNDLE = re.compile(r"""src=["'](/static/js/main\.[0-9a-f]+\.js)["']""")
_TIERS = re.compile(rf'({_IDENT})="anonymous",({_IDENT})="free",({_IDENT})="premium"')
_ENTRY = rf'\{{key:"[^"\\]+",label:"[^"\\]+",file:"[^"\\]+",access:\[(?:{_IDENT},?)*\]\}}'
_PRODUCT_TABLE = re.compile(rf"{_IDENT}=\[((?:{_ENTRY},?)+)\]")
_PRODUCT_FIELDS = re.compile(
    r'\{key:"([^"\\]+)",label:"([^"\\]+)",file:"([^"\\]+)",access:\[([^\]]*)\]\}'
)
_APIM_BASE = re.compile(r'"(https://[^"\s]+/apim/)"\s*\+')
_SAFE_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.json")
_STATEMENT = re.compile(
    r"\N{COPYRIGHT SIGN}|copyright|licen[cs]e|terms of (?:use|service)|public domain",
    re.IGNORECASE,
)
_FETCHED = re.compile(r"^\| [^|]+ \| \S+ \| (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z) \|", re.M)


@dataclass(frozen=True)
class Response:
    """One GET as served: the status, the body and the validators sent with it."""

    url: str
    status: int
    body: bytes
    etag: str | None
    last_modified: str | None


@dataclass(frozen=True)
class Product:
    """One row of the ApiDocs product table."""

    key: str
    label: str
    file: str
    tiers: tuple[str, ...]


@dataclass(frozen=True)
class Entry:
    """One row of ``FETCHED.md``: a response, the file it is kept as, if any, and a note."""

    path: str | None
    response: Response
    note: str
    content: bytes | None = None


class _RetryableError(Exception):
    """A network error or a 5xx: worth one more attempt."""


def _log(message: str) -> None:
    print(message, flush=True)  # noqa: T201


def _get(url: str, accept: frozenset[int]) -> Response:
    REQUESTS.append(url)
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body: bytes = response.read()
            status: int = response.status
            headers = response.headers
    except urllib.error.HTTPError as error:
        if error.code >= 500:
            raise _RetryableError(f"HTTP {error.code} {error.reason}") from None
        if error.code not in accept:
            raise SystemExit(f"GET {url}: HTTP {error.code} {error.reason}") from None
        body, status, headers = error.read(), error.code, error.headers
    except (http.client.HTTPException, OSError) as error:  # URLError is an OSError
        raise _RetryableError(str(error)) from None
    if status not in accept:
        raise SystemExit(f"GET {url}: expected HTTP {sorted(accept)}, got {status}")
    encoding = headers.get("Content-Encoding", "identity").strip().lower()
    if encoding == "gzip":
        body = gzip.decompress(body)
    elif encoding != "identity":
        raise SystemExit(f"GET {url}: unexpected Content-Encoding {encoding!r}")
    return Response(url, status, body, headers.get("ETag"), headers.get("Last-Modified"))


def fetch(url: str, accept: frozenset[int] = frozenset({200})) -> Response:
    """GET ``url`` after a polite pause; retry once on a network error or a 5xx."""
    time.sleep(PAUSE)
    try:
        return _get(url, accept)
    except _RetryableError as error:
        _log(f"  {url}: {error}; retrying once in {RETRY_PAUSE:.0f} s")
    time.sleep(RETRY_PAUSE)
    try:
        return _get(url, accept)
    except _RetryableError as error:
        raise SystemExit(f"GET {url}: {error} (after one retry)") from None


def _html_text(body: bytes) -> str:
    """The text a browser shows of an HTML page: no script, style or markup."""
    soup = BeautifulSoup(body.decode("utf-8", "replace"), "html.parser")
    for tag in _tags(soup, "script", "style", "noscript", "template"):
        tag.decompose()
    return " ".join(soup.get_text(" ").split())


def check_attribution(url: str, text: str) -> None:
    """Stop when ``text`` states a copyright, licence or terms that ``ATTRIBUTION`` lacks.

    ``text`` is what the snapshot keeps of the page, or what a browser shows of an HTML
    page; the page a statement is read from must still print it.
    """
    for statement in ATTRIBUTION:
        if statement.url == url and statement.text not in text:
            raise SystemExit(
                f"GET {url}: the page no longer prints {statement.text!r}, which ATTRIBUTION "
                "records.\nRead it by hand and update ATTRIBUTION in "
                "scripts/refresh_upstream.py. Nothing was written."
            )
        text = text.replace(statement.text, "")
    match = _STATEMENT.search(text)
    if match:
        around = " ".join(text[max(match.start() - 60, 0) : match.end() + 60].split())
        raise SystemExit(
            f"GET {url}: the page states {match.group(0)!r} ({around!r}), a copyright, "
            "licence or terms of use that ATTRIBUTION does not record.\nRead it by hand, "
            "record it in ATTRIBUTION in scripts/refresh_upstream.py. Nothing was written."
        )


def _bundle_changed(what: str, where: str) -> SystemExit:
    return SystemExit(
        f"The ApiDocs bundle changed: {what}.\n"
        f"Inspect {where} (the page is {APIDOCS_URL}; the bundle is the main.<hash>.js it "
        'loads) for the product table [{key:"...",label:"...",file:"....json",access:[...]}], '
        'the tier constants X="anonymous",Y="free",Z="premium" and the '
        '"https://.../apim/"+file base URL, then update the patterns in '
        "scripts/refresh_upstream.py. Nothing was written."
    )


def discover() -> tuple[Response, Response, str, list[Product]]:
    """Fetch ApiDocs and its bundle; read the apim base URL and the product table.

    The page is checked for attribution, the bundle is not: it is code, which carries its
    libraries' licence headers.
    """
    shell = fetch(APIDOCS_URL)
    _report("(no file)", shell)
    page = shell.body.decode("utf-8")
    check_attribution(APIDOCS_URL, _html_text(shell.body))
    bundles = sorted(set(_BUNDLE.findall(page)))
    if len(bundles) != 1:
        raise _bundle_changed(f"expected one main.<hash>.js, found {bundles}", APIDOCS_URL)
    bundle_url = urljoin(APIDOCS_URL, bundles[0])
    bundle = fetch(bundle_url)
    _report("(no file)", bundle)
    source = bundle.body.decode("utf-8")

    constants = _TIERS.findall(source)
    if len(constants) != 1:
        raise _bundle_changed(f"found {len(constants)} sets of tier constants", bundle_url)
    tier_names = dict(zip(constants[0], ("anonymous", "free", "premium"), strict=True))

    tables = _PRODUCT_TABLE.findall(source)
    if len(tables) != 1:
        raise _bundle_changed(f"found {len(tables)} product tables", bundle_url)
    products: list[Product] = []
    for key, label, file, access in _PRODUCT_FIELDS.findall(tables[0]):
        idents = [ident for ident in access.split(",") if ident]
        if not idents or any(ident not in tier_names for ident in idents):
            raise _bundle_changed(f"product {key!r} has access [{access}]", bundle_url)
        if not _SAFE_FILE.fullmatch(file):
            raise _bundle_changed(f"product {key!r} names the file {file!r}", bundle_url)
        products.append(Product(key, label, file, tuple(tier_names[i] for i in idents)))
    files = [product.file for product in products]
    if not products or len(set(files)) != len(files):
        raise _bundle_changed(f"product files are {files}", bundle_url)

    bases = sorted(set(_APIM_BASE.findall(source)))
    if len(bases) != 1:
        raise _bundle_changed(f"expected one apim base URL, found {bases}", bundle_url)
    return shell, bundle, bases[0], products


def _iso_http_date(value: str | None) -> str:
    if value is None:
        return "-"
    return parsedate_to_datetime(value).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json(response: Response) -> Any:
    try:
        return json.loads(response.body)
    except ValueError as error:
        raise SystemExit(f"GET {response.url}: not JSON ({error})") from None


def _report(path: str, response: Response) -> None:
    digest = hashlib.sha256(response.body).hexdigest()
    _log(
        f"  {path}: HTTP {response.status}, {len(response.body)} bytes, sha256 {digest}, "
        f"Last-Modified {response.last_modified or '-'}, ETag {response.etag or '-'}"
    )


def fetch_spec(base: str, product: Product) -> tuple[Entry, str]:
    """Fetch one product's OpenAPI document as served, with its ``openapi`` version."""
    response = fetch(base + product.file)
    document = _json(response)
    version = document.get("openapi") if isinstance(document, dict) else None
    if not (isinstance(version, str) and version.startswith("3.")):
        raise SystemExit(f"GET {response.url}: expected OpenAPI 3.x, found openapi={version!r}")
    check_attribution(response.url, json.dumps(document, ensure_ascii=False))
    path = f"apidocs/{product.file}"
    _report(path, response)
    return Entry(path, response, f"OpenAPI {version}, as served", response.body), version


def fetch_reference(name: str) -> Entry:
    """Fetch one reference file as served; it must parse as JSON."""
    response = fetch(REFERENCE_BASE + name)
    check_attribution(response.url, json.dumps(_json(response), ensure_ascii=False))
    path = f"reference/{name}"
    _report(path, response)
    return Entry(path, response, "as served", response.body)


def fetch_attribution(url: str) -> Entry:
    """Fetch a page ``ATTRIBUTION`` reads a statement from; it must still print it."""
    response = fetch(url)
    check_attribution(url, _html_text(response.body))
    _report("(no file)", response)
    return Entry(None, response, "read for the Attribution above, kept without a file")


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


def fetch_article(slug: str) -> Entry:
    """Fetch one Help Center article through the WordPress REST API as Markdown.

    A slug the REST API does not know, an empty list or a 404, is recorded without a file.
    """
    url = f"{HELP_API}?{urlencode({'slug': slug, '_fields': HELP_FIELDS}, safe=',')}"
    response = fetch(url, frozenset({200, 404}))
    articles = _json(response) if response.status == 200 else []
    if articles == []:
        what = "an empty list" if response.status == 200 else f"HTTP {response.status}"
        _report("(no file)", response)
        _log(f"  {slug}: no article, the REST API answered {what}; recorded without a file")
        return Entry(None, response, f"no article {slug!r}: the WordPress REST API answered {what}")
    if not (isinstance(articles, list) and len(articles) == 1 and isinstance(articles[0], dict)):
        raise SystemExit(f"GET {url}: expected one article, got {str(articles)[:200]}")
    article: dict[str, Any] = articles[0]
    try:
        link, modified = str(article["link"]), str(article["modified"])
        title = html.unescape(str(article["title"]["rendered"])).strip()
        body = str(article["content"]["rendered"])
    except (KeyError, TypeError) as error:
        raise SystemExit(f"GET {url}: article without {error}") from None
    if article.get("slug") != slug or not body.strip():
        raise SystemExit(f"GET {url}: no article body for {slug!r}")
    escaped = title.replace("[", r"\[").replace("]", r"\]")
    header = f"# [{escaped}]({link})\n\nUpstream modified: {modified}\n\n"
    markdown = header + to_markdown(body, link)
    check_attribution(url, markdown)
    path = f"help/{slug}.md"
    note = f"article {link}, WordPress modified {modified} (site time), converted to Markdown"
    merged = _merged_tables(body)
    if merged:
        note += f"; {merged} table{'s' if merged > 1 else ''} with merged cells kept as HTML"
    _log(f"  {path}: HTTP {response.status}, {len(markdown)} characters, modified {modified}")
    return Entry(path, response, note, markdown.encode("utf-8"))


def _cell(value: str) -> str:
    return value.replace("|", r"\|")


def _paragraph(*sentences: str) -> list[str]:
    text = " ".join(sentences)
    wrapped = textwrap.fill(text, width=88, break_long_words=False, break_on_hyphens=False)
    return [*wrapped.splitlines(), ""]


def _row(entry: Entry, fetched: str) -> str:
    response = entry.response
    cells = [
        entry.path or "(no file)",
        response.url,
        fetched,
        str(response.status),
        str(len(response.body)),
        hashlib.sha256(response.body).hexdigest(),
        response.etag or "-",
        _iso_http_date(response.last_modified),
        entry.note,
    ]
    return "| " + " | ".join(_cell(cell) for cell in cells) + " |"


def render_fetched(
    bundle: str,
    apim_base: str,
    products: list[Product],
    versions: list[str],
    entries: list[Entry],
    fetched: str,
) -> str:
    """The whole of ``FETCHED.md``, ``fetched`` being the UTC time the run started."""
    found = ", ".join(sorted(set(versions)))
    stated = [
        f"- `{s.text}`, {s.where}, as printed at {s.url}, fetched {fetched}." for s in ATTRIBUTION
    ]
    lines = [
        "# Upstream documentation snapshot \N{EM DASH} UN Comtrade",
        "",
        "Source of truth for every endpoint wrapper (ADR-0003). Files in this directory are",
        f"fetched from {APIDOCS_URL}, the UN Comtrade Help Center and",
        "the Comtrade reference files by `scripts/refresh_upstream.py` (`/refresh-upstream`),",
        "never edited by hand, and refreshed deliberately by PR so that changes show up as",
        "diffs. This file is generated by the same script.",
        "",
        "## Attribution",
        "",
        *(stated or ["- None stated."]),
        "",
        *_paragraph(
            "Every other page the script reads states none: it stops, before writing, when a",
            "page states a copyright line, a licence or terms of use not listed here, or when",
            "the page a line is read from no longer prints it. ApiDocs is rendered in the",
            "browser, so a plain fetch receives no footer text from it; its bundle is code,",
            "which carries its libraries' licence headers, and is not checked. The",
            "documentation's text is reproduced here as this package's reference (ADR-0003);",
            "the publisher's objection is met by replacing it with a summary that keeps the",
            "names and semantics the wrappers rely on.",
        ),
        "## How ApiDocs is captured",
        "",
        "ApiDocs is a React app that embeds Swagger UI. Its JavaScript bundle holds a table of",
        f"API products, each an OpenAPI file (version {found} as fetched) under",
        f"`{apim_base}` with the subscription tiers that may",
        "see it. The page loads only the products of the viewer's tier (anonymous, free or",
        'premium) and merges them client-side into one document, "UN Comtrade API Products",',
        "with one collapsible Swagger UI tag per product, paths prefixed with the product's",
        "server path and operationIds with its key. The script reads the product table from",
        "the bundle and saves every product file byte for byte as served, so the snapshot",
        "holds every product, including the premium ones a free-tier browser never shows.",
        "",
        "Help Center articles come from the WordPress REST API,",
        f"`{HELP_API}?slug=<slug>`, as the article body only",
        "(no theme, no navigation), converted to Markdown. A table with merged cells",
        "(`rowspan`/`colspan`) stays an HTML table that keeps only the spans and links, with",
        "images as their alt text or file name, and the article's row says so; every other",
        "table becomes a pipe table.",
        "",
        f"Regenerate: `{COMMAND}`",
        "",
        "## Products found",
        "",
        f"In the ApiDocs bundle `{bundle}`:",
        "",
        "| Key | Label | File | Tiers | OpenAPI |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {_cell(p.key)} | {_cell(p.label)} | {p.file} | {', '.join(p.tiers)} | {_cell(v)} |"
        for p, v in zip(products, versions, strict=True)
    ]
    lines += [
        "",
        "## Files and pages",
        "",
        *_paragraph(
            "Fetched is the UTC time the run started, in ISO 8601 with an explicit Z, the",
            "same for every row. HTTP, Bytes and sha256 are those of the body as fetched: for",
            "a Help Center article the REST API's JSON, whose `content` the Markdown file is",
            "converted from, the article's WordPress `modified` field (site time) being in",
            "its note. ETag is as sent, Last-Modified the HTTP header in UTC, `-` where not",
            "sent. A page read without a file is `(no file)`. Requests go one at a time,",
            f"{PAUSE:g} s apart, each retried at most once after a network error or a 5xx,",
            f"identified as `{USER_AGENT}`; no API key is sent or read.",
        ),
        "| File | URL | Fetched | HTTP | Bytes | sha256 | ETag | Last-Modified | Note |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines += [_row(entry, fetched) for entry in entries]
    return "\n".join(lines) + "\n"


def _files(entries: Sequence[Entry]) -> dict[str, bytes]:
    return {e.path: e.content for e in entries if e.path is not None and e.content is not None}


def _stale(out: Path, files: dict[str, bytes]) -> list[str]:
    """The files under ``SUBDIRS`` that this run does not produce."""
    found = [
        f"{subdir}/{path.name}"
        for subdir in SUBDIRS
        if (out / subdir).is_dir()
        for path in sorted((out / subdir).iterdir())
        if path.is_file()
    ]
    return [name for name in found if name not in files]


def write_snapshot(out: Path, entries: Sequence[Entry], fetched_md: str) -> None:
    """Write every file, drop files the new snapshot no longer has, write ``FETCHED.md``."""
    if out.exists() and any(out.iterdir()) and not (out / "FETCHED.md").is_file():
        raise SystemExit(f"{out} is neither empty nor a snapshot (no FETCHED.md); not writing")
    files = _files(entries)
    for name in _stale(out, files):
        (out / name).unlink()
        _log(f"  removed {name}: no longer upstream")
    for name, content in files.items():
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        (out / name).write_bytes(content)
    (out / "FETCHED.md").write_text(fetched_md, encoding="utf-8")


def compare(out: Path, entries: Sequence[Entry], render: Callable[[str], str]) -> list[str]:
    """The snapshot's files that differ from this run's, ``FETCHED.md``'s ``Fetched`` aside."""
    files = _files(entries)
    differ = [
        name
        for name, content in files.items()
        if not (out / name).is_file() or (out / name).read_bytes() != content
    ]
    differ += [f"{name} (no longer upstream)" for name in _stale(out, files)]
    current = out / "FETCHED.md"
    old = current.read_text(encoding="utf-8") if current.is_file() else ""
    match = _FETCHED.search(old)
    if match is None or render(match.group(1)) != old:
        differ.append("FETCHED.md")
    return differ


def main(argv: Sequence[str] | None = None) -> int:
    """Discover the ApiDocs products, fetch everything, then write or compare the snapshot."""
    parser = argparse.ArgumentParser(description="Refresh docs/upstream/ from UN Comtrade.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="snapshot directory")
    parser.add_argument(
        "--check", action="store_true", help="fetch and compare with the snapshot; write nothing"
    )
    args = parser.parse_args(argv)
    out: Path = args.out
    fetched = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    _log(f"ApiDocs: {APIDOCS_URL}")
    shell, bundle, apim_base, products = discover()
    bundle_name = bundle.url.rsplit("/", 1)[-1]
    _log(f"  bundle {bundle_name}, apim base {apim_base}")
    for product in products:
        tiers = ", ".join(product.tiers)
        _log(f"  product {product.key} ({product.label}): {product.file} [{tiers}]")
    entries = [
        Entry(None, shell, "the ApiDocs page, a client-rendered shell that names the bundle"),
        Entry(None, bundle, "the ApiDocs bundle: the product table and apim base are read here"),
    ]
    specs = [fetch_spec(apim_base, product) for product in products]
    entries += [entry for entry, _ in specs]
    versions = [version for _, version in specs]
    _log(f"  OpenAPI versions: {', '.join(sorted(set(versions)))}")
    _log("Help Center articles")
    articles = [fetch_article(slug) for slug in HELP_SLUGS]
    if all(article.path is None for article in articles):
        raise SystemExit(f"{HELP_API} knows none of HELP_SLUGS: look at it by hand. Not writing")
    entries += articles
    _log("Reference files")
    entries += [fetch_reference(name) for name in REFERENCE_FILES]
    _log("Attribution")
    entries += [fetch_attribution(url) for url in dict.fromkeys(s.url for s in ATTRIBUTION)]

    def render(at: str) -> str:
        return render_fetched(bundle_name, apim_base, products, versions, entries, at)

    if args.check:
        differ = compare(out, entries, render)
        for name in differ:
            _log(f"  differs: {name}")
        _log(
            f"{len(differ)} of the snapshot's files differ from upstream; run without --check"
            if differ
            else "The snapshot is current: upstream serves what it records."
        )
        _log(f"{len(REQUESTS)} requests, none with a key")
        return 1 if differ else 0
    write_snapshot(out, entries, render(fetched))
    written = len(_files(entries))
    _log(f"Wrote {written} files and FETCHED.md under {out} (Fetched {fetched})")
    _log(f"{len(REQUESTS)} requests, none with a key")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
