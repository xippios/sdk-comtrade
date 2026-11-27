"""``docs/upstream/OBSERVED.md`` as committed: what UN Comtrade does but never documents.

sdk-core's conventions §3 keep these notes in one file written by hand, which the snapshot
script neither writes nor checks and ``FETCHED.md`` lists in a row of its own, and give each
note its evidence: the probe's date, its operation and its sample, a recording under
``tests/fixtures/`` or a packaged list. Core's family check holds the file's row in
``FETCHED.md``, the label and the date that open each note's last paragraph and the files its
code spans cite (sdk-core ADR-0044, decision 1). The tests here hold the rest, the package's
own (ADR-0044, decision 3): each probe's operation and sample, the dates of its samples, and
that no dated note of what UN Comtrade answered stands outside the file
(https://github.com/xippios/sdk-comtrade/issues/33).
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "xippios" / "comtrade"
OBSERVED = ROOT / "docs" / "upstream" / "OBSERVED.md"
OPERATION = re.compile(
    r"`(?:data/v1/get(?:Da|Metadata|LiveUpdate)?|tools/v1/get(?:TradeBalance|BilateralData)"
    r"|public/v1/get(?:ComtradeReleases|WorldShare)|files/v1/app/reference/[A-Za-z0-9]+\.json)`"
)
"""An operation the package sends to, by its path as ``meta.endpoint`` names it, or a
reference file by its own."""
DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")
SAMPLE = re.compile(r"`((?:tests/fixtures|src/xippios/comtrade/reference)/[^`\s]+\.json)`")
"""A recording under ``tests/fixtures/`` or a packaged list, cited from the repository's root."""
DOCUMENTATION = "`https://comtrade.un.org/en/api-docs`"
"""The documentation page, which a probe of the documentation's own address names, with its row
in ``FETCHED.md`` in place of a sample, since no fixture records a page of the documentation."""
FETCHED = "`docs/upstream/FETCHED.md`"
OLD_ADDRESS = "https://comtradeplus.un.org/ApiDocs"
"""The documentation's address that the snapshot read before UN Comtrade rebuilt its site."""
REFERENCE = re.compile(r"^\[[^\]\n]+\]: \S+\n?", re.MULTILINE)
"""A link reference definition, which renders as nothing and is no note's paragraph."""
ANSWER_DATE = re.compile(r"(?<![`\"'])\b20\d\d-\d\d-\d\d\b")
"""A date that may date an answer: one that opens a value in quotes or a code span, a time as
upstream prints it or an example of an argument, dates none."""
CITED_DATE = re.compile(r"\b(?:decisions? of|amendment) 20\d\d-\d\d-\d\d\b")
"""A date that cites a record, the maintainer's decision or an ADR's amendment, and dates
no answer of UN Comtrade."""
PACKAGE_TEXT = sorted(
    [
        ROOT / "README.md",
        ROOT / "CLAUDE.md",
        ROOT / "docs" / "layout.md",
        ROOT / "scripts" / "refresh_reference.py",
        ROOT / "scripts" / "refresh_upstream.py",
        *PACKAGE.rglob("*.py"),
    ]
)
"""The package's own text: its README, ``CLAUDE.md``, its layout, its scripts and modules."""


def notes() -> dict[str, list[str]]:
    """Each note's heading and its paragraphs, each paragraph's lines joined by a space.

    A ``##`` heading groups notes and is none itself.
    """
    text = REFERENCE.sub("", OBSERVED.read_text(encoding="utf-8"))
    parts = re.split(r"^(##|###) (.+)$", text, flags=re.MULTILINE)
    return {
        heading: [" ".join(block.split()) for block in body.split("\n\n") if block.strip()]
        for level, heading, body in zip(parts[1::3], parts[2::3], parts[3::3], strict=True)
        if level == "###"
    }


def sample_date(path: str) -> str:
    """The day a sample was taken: a recording's ``recorded_at``, a packaged list's ``fetched``."""
    sample = json.loads((ROOT / path).read_text(encoding="utf-8"))
    return str(sample.get("recorded_at") or sample["fetched"])[:10]


def test_every_note_ends_with_its_probe() -> None:
    """The probe names an operation that the package sends to, in a code span, and a sample
    of it: a recording or a packaged list. A probe of the documentation's own address names
    the documentation page and its row in ``FETCHED.md`` in their place."""
    found = notes()
    assert found
    for heading, paragraphs in found.items():
        probe = paragraphs[-1]
        assert re.match(r"(?:Probe|Observed): 20\d\d-\d\d-\d\d\b", probe), heading
        if DOCUMENTATION in probe:
            assert FETCHED in probe, heading
            continue
        assert OPERATION.search(probe), heading
        assert SAMPLE.search(probe), heading


def test_the_documentations_old_address_is_a_note() -> None:
    """What the address that the snapshot read before the site was rebuilt answers stands in a
    note, two redirects, the first to another host, and the snapshot requests no page of it
    (https://github.com/xippios/sdk-comtrade/issues/71, the maintainer's decision of
    2026-11-27 on what a snapshot requests)."""
    [probe] = [
        paragraphs[-1] for paragraphs in notes().values() if f"`{OLD_ADDRESS}`" in paragraphs[-1]
    ]
    assert probe.startswith("Probe: 2026-11-26, ")
    assert "`https://comtrade.un.org/ApiDocs`" in probe
    assert DOCUMENTATION in probe
    assert FETCHED in probe
    script = (ROOT / "scripts" / "refresh_upstream.py").read_text(encoding="utf-8")
    assert "comtradeplus.un.org" not in script


def test_every_sample_a_probe_names_was_taken_on_a_date_it_gives() -> None:
    """A recording's day, from its ``recorded_at``, and a packaged list's, from its
    ``fetched``, is a date of the probe that names it."""
    for heading, paragraphs in notes().items():
        probe = paragraphs[-1]
        dates = DATE.findall(probe)
        for path in SAMPLE.findall(probe):
            assert sample_date(path) in dates, f"{heading}: {path}"


def test_the_package_points_to_the_notes() -> None:
    """``CLAUDE.md`` says what the package does with what UN Comtrade does, and the README
    lists the file among its documents (https://github.com/xippios/sdk-comtrade/issues/33)."""
    for path in (ROOT / "CLAUDE.md", ROOT / "README.md"):
        assert "docs/upstream/OBSERVED.md" in path.read_text(encoding="utf-8"), path.name
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    documents = readme.split("\n## Documents\n", 1)[1].split("\n## ", 1)[0]
    observed = "https://github.com/xippios/sdk-comtrade/blob/main/docs/upstream/OBSERVED.md"
    assert f"({observed})" in documents


def test_no_dated_note_stands_outside_the_notes() -> None:
    """What UN Comtrade was seen to answer stands once, in ``OBSERVED.md``, each note with its
    probe: the package's own text points to a note and dates no answer. A date there cites a
    record, the maintainer's decision or an ADR's amendment, or opens a value as printed. The
    tests are not read: each gives the day its recordings were taken, the provenance of what
    it replays."""
    found = [
        f"{path.relative_to(ROOT)}: {date}"
        for path in PACKAGE_TEXT
        for date in ANSWER_DATE.findall(
            CITED_DATE.sub("", " ".join(path.read_text("utf-8").split()))
        )
    ]
    assert found == []
