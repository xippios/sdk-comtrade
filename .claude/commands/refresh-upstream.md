Refresh the upstream documentation snapshot for UN Comtrade: $ARGUMENTS

The snapshot in `docs/upstream/` is the reference for every endpoint wrapper
(ADR-0003). It is refreshed deliberately, by PR, so changes are visible as diffs.

1. Work on a branch `docs/upstream-<yyyy-mm-dd>`.
2. A source whose documentation needs a reproducible capture keeps
   `scripts/refresh_upstream.py`. Where it exists, run it from the repository root as its
   docstring says, usually `uv run scripts/refresh_upstream.py`, and skip the by-hand
   fetch. Otherwise fetch the documentation pages from
   https://comtradeplus.un.org/ApiDocs (and any pages the arguments name). Save each page under
   `docs/upstream/` as Markdown where the page is HTML (convert, keep headings, tables and
   parameter lists; drop navigation) or as the original file where it is JSON, YAML,
   OpenAPI or PDF. Keep file names stable across refreshes so diffs are meaningful.
3. Update the table in `docs/upstream/FETCHED.md`: file, URL, fetch date (today, ISO).
   Where the script writes the table itself, check it instead.
4. Diff against the previous snapshot: `git diff --stat docs/upstream/` and read the
   changes. Summarise in the PR description what changed upstream: new or removed
   operations, renamed or newly required parameters, changed semantics, and which
   wrappers in `src/xippios/comtrade/api/` are affected.
5. Do not change any code in this PR. If wrappers must follow, list them as follow-up
   issues or `/add-endpoint` runs.
6. Open the PR with the definition-of-done checklist. Do not merge.
