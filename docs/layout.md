# Layout

The files that every source of the family holds are laid out once, in the tree of
sdk-template's README,
[What gets generated](https://github.com/xippios/sdk-template/blob/main/README.md#what-gets-generated).
This file holds what `xippios-comtrade` adds to that tree, a module, a task file, a
script or a test of its own, each with what it holds, and the change that adds one updates it.

The import path is `xippios.comtrade` (sdk-core ADR-0006); `src/xippios/` is a
namespace package.
Where the API's operation ids repeat across its services, `api/` keeps one module per service
instead, named after the service, and this file says so (conventions §2).

```
src/xippios/comtrade/
  _client.py       also the daily quota's policy, CACHE_LIFETIMES, the cache's lifetime of
                   each path prefix, and READ_TIMEOUT, the one read timeout of 180 s
  errors.py        RECORD_LIMIT, MAX_PERIODS, NARROW, what closes core's QueryTooLarge after
                   get_data's count, and over_mcp, which names a task's MCP tool in a refusal;
                   no error class of its own
  codes.py         the packaged lists that name a code, each declared once, PackagedList.codes:
                   REPORTERS, PARTNERS and the lists of the rows' customs, transport, supply,
                   quantity unit and frequency codes, which models.py marks with NamedBy and
                   params.py checks with core's check; FLOW_CODES, named by upstream's words
                   and MIF and XIF by their own code; and for the check alone TYPE_CODES,
                   CL_CODES, AGGREGATE_BY, BREAKDOWN_MODES and CATEGORIES, each code named by
                   its own text
  api/             one module per operation, named after it, or after its path where the
                   operationId is opaque: get (get and get_count_only, data/v1/get),
                   get_da, get_metadata, get_live_update, get_trade_balance,
                   get_bilateral_data, get_comtrade_releases, get_world_share; reference, the
                   public reference files; _query, the query strings in upstream's spelling
  params.py        also PACKAGED_TABLES, CL_CODES_FROM_SPEC, TOOLS_FLOW_CODES, RECENT and
                   classification_files(); Codes and TextCodes, one code or a list of them,
                   and joined(), which sends a list as UN Comtrade's comma-separated text;
                   and the checks run before a call, each refusing the first problem:
                   validate_get(), validate_datasets(), validate_trade_balance(),
                   validate_bilateral_data(), validate_world_share(),
                   validate_classification_file(), validate_code_list() and
                   validate_reference_category()
  reference/       ten lists named after the parameter, <param>.json, and five tables named
                   after upstream's file: Reporters, partnerAreas, country_area_code_iso,
                   TradeDataItems and ListofReferences; the package holds no enums.py
tests/
  fixtures/        recorded exchanges, <wrapper>/<case>.json, one directory per wrapper and
                   reference/ for the reference files, never hand-written
  test_scripts.py  the reference script's declaration, offline: its lists, its provenance
                   rows against the committed ones, the spec's lists and that it sends no key
  test_refresh_upstream.py  the snapshot script's declaration and hooks, offline: its
                   pages, the five OpenAPI files against the committed ones, the statements
                   of the attribution against the kept articles and the documentation
                   page's footer, the agreement that it does not fetch, the record of
                   both in FETCHED.md, each row's note and an article's Markdown
  test_observed.py docs/upstream/OBSERVED.md as committed: each note's probe, operation
                   and sample, the dates of its samples, and that the package's own text
                   dates no answer outside it
docs/
  upstream/        also apidocs/, the five OpenAPI files of the API products; help/, the
                   Help Center articles in Markdown; reference/, ListofReferences.json and
                   TradeDataItems.json; OBSERVED.md, written by hand, what UN Comtrade was
                   seen to answer beyond them, each note with its probe
```
