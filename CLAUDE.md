# sdk-comtrade — instructions for Claude Code

`xippios-comtrade` wraps UN Comtrade as a typed Python client, an MCP server
and FastAPI routes, built on `xippios-core`. This file is the contract for every session
that works here; the family rules it points to apply as well.

## What this package wraps

| | |
| --- | --- |
| Upstream | UN Comtrade, https://comtradeplus.un.org |
| API base URL | `https://comtradeapi.un.org` |
| Documentation | https://comtradeplus.un.org/ApiDocs, snapshotted in `docs/upstream/` |
| Credentials | `COMTRADE_API_KEY` from the environment, sent as the `Ocp-Apim-Subscription-Key` header |
| Rate limit | 1 per second, no burst (60 per minute), enforced client-side in `_client.py` |
| Write tools | no, this package is read-only |

The snapshot in `docs/upstream/` is the reference for names, parameters and semantics.
If it is empty or stale, run `/refresh-upstream` first and review the diff. Never write a
wrapper from memory of the API.

## The client, the key and the quota

The limits of a Basic Individual (free) key, from `docs/upstream/help/subscriptions.md`,
and how `_client.py` treats them:

- **1 call per second.** `RATE_LIMIT = RateLimit(per_minute=60, burst=1)`: the bucket
  never bursts, so calls are spaced a second apart. Upstream's headers agree
  (`x-ratelimit-limit: 1`, `x-ratelimit-operation-limit: 60`). Replay tests pay that
  second too.
- **500 calls per day.** Not enforced client-side. `countOnly` calls count against it,
  so `get_data` costs two calls (count, then data) and `get_counts` one. Over the quota
  API Management answers 403 "Out of call volume quota. Quota will be replenished in
  HH:MM:SS"; `classify` maps a 403 that mentions a quota to `RateLimitError` with
  `retry_after`. That answer has not been observed; never provoke it.
- **100,000 records per call.** Above it upstream answers HTTP 200 with the first
  100,000 rows, `count` 100000 and an empty `error`: it truncates silently (observed
  2026-10-23 for a query counted at 5,006,385). `get_data` counts first and raises
  `QueryTooLarge` before any data call.
- **12 periods per call.** A 13th gets HTTP 400 "Maximum number of periods is 12";
  `params.validate_get` refuses it before the call.
- **Slow counts.** A broad count can take over a minute, so the read timeout is 180 s
  (`TIMEOUTS`), and a timed-out attempt that core retries counts against the quota each
  time; so does each retry of a 5xx.
- **Keys may be periodically regenerated** on Basic accounts. A sudden 401 ("Access
  denied due to invalid subscription key", `AuthError`) means re-copying the key from
  https://comtradeplus.un.org/MyComtrade/APIPortal into the environment.

The reference files under `files/v1/app/reference/` are public: `reference_client`
fetches them without the key and keeps each for the life of the process (core's GET
cache, `REFERENCE_CACHE`; tests empty it before each test), so
`scripts/refresh_reference.py` and `list_commodities` need no key and cost no quota.
Reporter and partner codes are UN Comtrade's, not ISO numeric: Switzerland is 757 in
`Reporters.json`. Upstream answers 756, which is no reporter, with count 0; the tasks
refuse it before the call, naming 757, because they check `reporter_code` against the
packaged `Reporters.json` and partner codes against `partnerAreas.json`. Both tables
share one code space (a code in both is the same area) but differ: 0 World and 56 other
areas are partners only, 97 European Union and 975 ASEAN reporters only.

The MCP result cap (200 rows or 64 KB) cuts `list_reporters` (255 rows) and
`list_partners` (310) in upstream's alphabetical order, past Switzerland and the USA;
the tasks take no filter yet.

When recording fixtures, budget the calls. The package client retries 5xx and transport
errors up to four attempts, each a keyed call (a count on `clCode=H6` answered HTTP 500
once), and a count over all reporters outlasted the former 60 s read timeout (the repeat
answered in 27 s). Record with a one-attempt copy of the client, and never keep a body of
many megabytes: narrow the query or use `maxRecords`. Replay tests always send a
placeholder key, whatever the shell holds (`tests/conftest.py`).

## Read first, in this order

1. `docs/upstream/FETCHED.md` and the files it lists: what the upstream actually offers
2. The family conventions: `../sdk-core/docs/conventions.md` and `../sdk-core/docs/adr/`
   (also at https://github.com/xippios/sdk-core/tree/main/docs)
3. `../sdk-core/docs/definition-of-done.md`: what a PR must satisfy
4. The family file `../CLAUDE.md`

## The one rule: three layers (ADR-0001)

```
api/<operation>.py   one async function per upstream operation, upstream names, returns models
tasks.py             the public API: composes wrappers, returns Result[T], sync facade via sync()
mcp.py  http.py      adapters: register tasks.__all__, nothing else. Never edited to add an endpoint.
```

Adapters call only task functions. Tasks call only endpoint wrappers and reference
data. If logic appears in `mcp.py` or `http.py`, it belongs in `tasks.py`.

## Layout

```
src/xippios/comtrade/
  __init__.py      public surface: __version__ and re-exported task functions
  py.typed         PEP 561 marker; consumers' mypy --strict needs it
  _version.py      __version__ from distribution metadata
  _client.py       the configured AsyncClient (base URL, key, rate limit, classify) and
                   a keyless one for the public reference files
  errors.py        RECORD_LIMIT, MAX_PERIODS and QueryTooLarge
  models.py        pydantic models mirroring upstream payloads (UpstreamModel)
  api/             endpoint wrappers, one module per upstream operation
  tasks.py         task functions; __all__ is what the adapters register
  mcp.py           xippios-comtrade-mcp entry point
  http.py          FastAPI router
  params.py        packaged value lists: PACKAGED_LISTS, packaged_values(), validate_get()
  enums.py         StrEnums generated from the packaged lists; never edited by hand
  reference/       packaged value lists (JSON), tables (CSV, provenance in tables.json)
                   plus README with provenance
scripts/
  refresh_reference.py   fetches the packaged lists through api/ and regenerates enums.py
  refresh_upstream.py    regenerates docs/upstream/ and its FETCHED.md from upstream
tests/
  conftest.py      enables xippios.core.testing.plugin; placeholder key for replay
  fixtures/        recorded responses, <endpoint>/<case>.json, never hand-written
  test_tasks.py    structural checks on every task plus per-task replay tests
  test_adapters.py the adapters expose exactly tasks.__all__
  test_layout.py   namespace levels stay empty; py.typed ships
  test_live.py     @pytest.mark.live smoke tests, one per task
docs/upstream/     documentation snapshot and FETCHED.md
.claude/commands/  add-endpoint, record-fixture, refresh-upstream, refresh-reference-data, release-prep
```

`src/xippios/` has **no** `__init__.py`: it is a PEP 420 namespace package shared with
`xippios-core` and every other source package.
Never add one; `tests/test_layout.py` fails if it appears. The import path is
`xippios.comtrade` (ADR-0006).

## How to add an endpoint

Run `/add-endpoint <upstream operation>`. In short:

1. Read the operation in `docs/upstream/`. Names, parameters and semantics come from
   there, snake_cased, nothing renamed, nothing normalised across sources.
2. `models.py`: an `UpstreamModel` per payload object; dates, numbers and enums typed.
3. `api/<operation>.py`: one async wrapper that calls `_client.client` and returns
   models through `xippios.core.parse`.
4. `tasks.py`: an async task that composes wrappers and returns `Result[T]` with full
   `ResultMeta` (source, endpoint, request parameters, `published_at`/`vintage` when the
   upstream gives them). Derive the sync one with `sync()`, add its name to `__all__`,
   re-export it from `__init__.py`.
5. Docstring for agents: one sentence, then `Args:` with examples of valid values for
   every parameter. The MCP tool description and the OpenAPI summary come from it.
6. `/record-fixture` for at least one case, a replay test in `test_tasks.py` that also
   calls the tool end to end with `xippios.core.testing.mcp_call`, a live smoke test in
   `test_live.py`.
7. `CHANGELOG.md` under Unreleased, README status table, then the full check suite.

Reference lookups (commodities, countries, attributes) are tasks too, named
`list_<thing>`, so agents can form valid calls. A task-shaped function that returns a
subset of an upstream record builds its model with `UpstreamModel.project`; nothing is
renamed or computed, parsing a value (`parse_decimal`) is the only override. Upstream's
documented error shapes go into `ClientConfig.classify` in `_client.py`, once; wrappers
use `client.get_json` and never inspect status codes.

## How to record a fixture

Run `/record-fixture <endpoint> <case> <parameters>`. It performs one live request
through the real client with `xippios.core.testing.record_sync` and writes
`tests/fixtures/<endpoint>/<case>.json` with credentials scrubbed. Grep the file for
key patterns before committing. Fixtures are never typed in by hand.

## Commands

```bash
uv sync --all-extras
uv run pytest                      # offline, replays fixtures
uv run pytest -m live              # needs XIPPIOS_LIVE_TESTS=1 and COMTRADE_API_KEY; 4 keyed calls, 3 keyless
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
uv run xippios-comtrade-mcp   # stdio; add --http for streamable HTTP
```

## Workflow rules

- Branch from `main` as `feature/<topic>`, `fix/<topic>`, `chore/<topic>` or `docs/<topic>`.
  Never commit to `main`.
- Commit small, with Conventional Commits messages (`feat(tasks): add get_balance_sheet`).
- Open the PR with `gh pr create`; the body is the definition-of-done checklist from
  `.github/PULL_REQUEST_TEMPLATE.md`, ticked honestly, with assumptions listed.
- `ruff` leaves `docs/` alone; never reformat the upstream snapshot.
- Template updates: `uvx copier update` pulls the latest sdk-template tag into the
  infrastructure files (answers are in `.copier-answers.yml`; content files such as
  `tasks.py`, `api/`, `tests/` and `README.md` are never overwritten). Review the diff
  and open a `chore/template-update` PR.
- If a convention seems wrong, say so in the PR and follow it anyway; changing it is a
  PR against `sdk-core/docs/conventions.md` plus an ADR.

## Never

- Never hand-write a fixture, and never commit one without grepping for key patterns.
- Never read or print `.envrc`, `.env`, or any variable ending in `_API_KEY`.
- Never write a key into a file or a commit.
- Never put logic in `mcp.py` or `http.py`; never add a route or tool by hand.
- Never rename or re-map an upstream concept to another source's (ADR-0003).
- Never edit `docs/upstream/` by hand; `/refresh-upstream` fetches, a PR reviews.
- Never add `src/xippios/__init__.py`.
- Never tag, merge, release, force-push, or touch `gh secret`. Those are human actions.

## When something is unclear

Prefer the smallest change that satisfies the documents above, state the assumption in
the PR description, and stop rather than guess at upstream semantics or public API shape.
