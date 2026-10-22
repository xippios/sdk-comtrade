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
- ``FETCHED.md``: regenerated entirely, with the products found and one row per file.

Everything is fetched before anything is written, one request at a time, each URL retried
at most once; files a previous snapshot had and this one does not are removed. The same
upstream on the same day gives the same bytes on disk. No key is needed or read. Run from
the repository root::

    uv run scripts/refresh_upstream.py
"""

import argparse
import gzip
import hashlib
import html
import http.client
import json
import re
import time
import urllib.error
import urllib.request
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


@dataclass(frozen=True)
class Response:
    """One successful GET: the body as served and the validators sent with it."""

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
    """One snapshot file: its path under the snapshot, its source and its content."""

    path: str
    url: str
    upstream_modified: str
    body: bytes


class _RetryableError(Exception):
    """A network error or a 5xx: worth one more attempt."""


def _log(message: str) -> None:
    print(message, flush=True)  # noqa: T201


def _get(url: str) -> Response:
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
        raise SystemExit(f"GET {url}: HTTP {error.code} {error.reason}") from None
    except (http.client.HTTPException, OSError) as error:  # URLError is an OSError
        raise _RetryableError(str(error)) from None
    if status != 200:
        raise SystemExit(f"GET {url}: expected HTTP 200, got {status}")
    encoding = headers.get("Content-Encoding", "identity").strip().lower()
    if encoding == "gzip":
        body = gzip.decompress(body)
    elif encoding != "identity":
        raise SystemExit(f"GET {url}: unexpected Content-Encoding {encoding!r}")
    return Response(url, status, body, headers.get("ETag"), headers.get("Last-Modified"))


def fetch(url: str) -> Response:
    """GET ``url`` after a polite pause; retry once on a network error or a 5xx."""
    time.sleep(PAUSE)
    try:
        return _get(url)
    except _RetryableError as error:
        _log(f"  {url}: {error}; retrying once in {RETRY_PAUSE:.0f} s")
    time.sleep(RETRY_PAUSE)
    try:
        return _get(url)
    except _RetryableError as error:
        raise SystemExit(f"GET {url}: {error} (after one retry)") from None


def _bundle_changed(what: str, where: str) -> SystemExit:
    return SystemExit(
        f"The ApiDocs bundle changed: {what}.\n"
        f"Inspect {where} (the page is {APIDOCS_URL}; the bundle is the main.<hash>.js it "
        'loads) for the product table [{key:"...",label:"...",file:"....json",access:[...]}], '
        'the tier constants X="anonymous",Y="free",Z="premium" and the '
        '"https://.../apim/"+file base URL, then update the patterns in '
        "scripts/refresh_upstream.py. Nothing was written."
    )


def discover() -> tuple[str, str, list[Product]]:
    """Read the bundle file name, the apim base URL and the product table from ApiDocs."""
    shell = fetch(APIDOCS_URL).body.decode("utf-8")
    bundles = sorted(set(_BUNDLE.findall(shell)))
    if len(bundles) != 1:
        raise _bundle_changed(f"expected one main.<hash>.js, found {bundles}", APIDOCS_URL)
    bundle_url = urljoin(APIDOCS_URL, bundles[0])
    source = fetch(bundle_url).body.decode("utf-8")

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
    return bundles[0].rsplit("/", 1)[-1], bases[0], products


def _iso_http_date(value: str | None) -> str:
    if value is None:
        return "not given"
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


def _entry(path: str, response: Response, *, with_etag: bool) -> Entry:
    _report(path, response)
    modified = _iso_http_date(response.last_modified)
    if with_etag and response.etag:
        modified += f", ETag {response.etag}"
    return Entry(path, response.url, modified, response.body)


def fetch_spec(base: str, product: Product) -> tuple[Entry, str]:
    """Fetch one product's OpenAPI document as served, with its ``openapi`` version."""
    response = fetch(base + product.file)
    document = _json(response)
    version = document.get("openapi") if isinstance(document, dict) else None
    if not (isinstance(version, str) and version.startswith("3.")):
        raise SystemExit(f"GET {response.url}: expected OpenAPI 3.x, found openapi={version!r}")
    return _entry(f"apidocs/{product.file}", response, with_etag=True), version


def fetch_reference(name: str) -> Entry:
    """Fetch one reference file as served; it must parse as JSON."""
    response = fetch(REFERENCE_BASE + name)
    _json(response)
    return _entry(f"reference/{name}", response, with_etag=False)


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


def fetch_article(slug: str) -> Entry:
    """Fetch one Help Center article through the WordPress REST API as Markdown."""
    url = f"{HELP_API}?{urlencode({'slug': slug, '_fields': HELP_FIELDS}, safe=',')}"
    response = fetch(url)
    articles = _json(response)
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
    markdown = (header + to_markdown(body, link)).encode("utf-8")
    path = f"help/{slug}.md"
    _log(f"  {path}: HTTP {response.status}, {len(markdown)} bytes, modified {modified}")
    return Entry(path, link, modified, markdown)


def _cell(value: str) -> str:
    return value.replace("|", r"\|")


def render_fetched(
    bundle: str,
    apim_base: str,
    products: list[Product],
    versions: list[str],
    entries: list[Entry],
    day: str,
) -> str:
    """The whole of ``FETCHED.md``; ``versions`` holds each product's ``openapi`` value."""
    found = ", ".join(sorted(set(versions)))
    lines = [
        "# Upstream documentation snapshot \N{EM DASH} UN Comtrade",
        "",
        "Source of truth for every endpoint wrapper (ADR-0003). Files in this directory are",
        f"fetched from {APIDOCS_URL}, the UN Comtrade Help Center and",
        "the Comtrade reference files by `scripts/refresh_upstream.py` (`/refresh-upstream`),",
        "never edited by hand, and refreshed deliberately by PR so that changes show up as",
        "diffs. This file is generated by the same script.",
        "",
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
        "images as their alt text or file name; every other table becomes a pipe table.",
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
        "## Files",
        "",
        "Fetched is the local calendar date of the run. Upstream modified is the HTTP",
        "`Last-Modified` (UTC), with the `ETag` for the ApiDocs files, and the WordPress",
        "`modified` field (site time) for Help Center articles.",
        "",
        "| File | URL | Fetched | Upstream modified |",
        "| --- | --- | --- | --- |",
    ]
    lines += [f"| {e.path} | {e.url} | {day} | {_cell(e.upstream_modified)} |" for e in entries]
    return "\n".join(lines) + "\n"


def write_snapshot(out: Path, entries: list[Entry], fetched_md: str) -> None:
    """Write every file, drop files the new snapshot no longer has, write ``FETCHED.md``."""
    if out.exists() and any(out.iterdir()) and not (out / "FETCHED.md").is_file():
        raise SystemExit(f"{out} is neither empty nor a snapshot (no FETCHED.md); not writing")
    keep = {entry.path for entry in entries}
    for subdir in SUBDIRS:
        directory = out / subdir
        directory.mkdir(parents=True, exist_ok=True)
        for path in sorted(directory.iterdir()):
            if path.is_file() and f"{subdir}/{path.name}" not in keep:
                path.unlink()
                _log(f"  removed {subdir}/{path.name}: no longer upstream")
    for entry in entries:
        (out / entry.path).write_bytes(entry.body)
    (out / "FETCHED.md").write_text(fetched_md, encoding="utf-8")


def main() -> None:
    """Discover the ApiDocs products, fetch everything, then write the snapshot."""
    parser = argparse.ArgumentParser(description="Refresh docs/upstream/ from UN Comtrade.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="snapshot directory")
    out: Path = parser.parse_args().out
    day = datetime.now().astimezone().date().isoformat()  # the run's local calendar date

    _log(f"ApiDocs: {APIDOCS_URL}")
    bundle, apim_base, products = discover()
    _log(f"  bundle {bundle}, apim base {apim_base}")
    for product in products:
        tiers = ", ".join(product.tiers)
        _log(f"  product {product.key} ({product.label}): {product.file} [{tiers}]")
    specs = [fetch_spec(apim_base, product) for product in products]
    entries = [entry for entry, _ in specs]
    versions = [version for _, version in specs]
    _log(f"  OpenAPI versions: {', '.join(sorted(set(versions)))}")
    _log("Help Center articles")
    entries += [fetch_article(slug) for slug in HELP_SLUGS]
    _log("Reference files")
    entries += [fetch_reference(name) for name in REFERENCE_FILES]
    fetched_md = render_fetched(bundle, apim_base, products, versions, entries, day)
    write_snapshot(out, entries, fetched_md)
    _log(f"Wrote {len(entries)} files and FETCHED.md under {out}")


if __name__ == "__main__":
    main()
