Refresh the packaged reference data for UN Comtrade: $ARGUMENTS

Reference data (commodity codes, country codes, attribute lists, report calendars)
ships inside the package under `src/xippios/comtrade/reference/` and is loaded
with `xippios.core.reference`. It comes from the upstream, never from memory.

1. Work on a branch `chore/reference-<thing>`.
2. Identify the upstream list endpoint for each list named in the arguments, using
   `docs/upstream/`; a wrapper for it belongs in `api/` (`/add-endpoint`).
3. Add the list to `LISTS` in `scripts/refresh_reference.py` (name as upstream calls it,
   fetcher through `api/`) and to `PACKAGED_LISTS` in `params.py`, then run the script:
   it writes `reference/<name>.json` with the fetch date and regenerates `enums.py`.
   Tables that are not plain value lists go under `reference/` as CSV with upstream
   column names, written by the same script.
4. Format the regenerated `enums.py`, in this order:
   `uv run ruff format src/xippios/comtrade/enums.py && uv run ruff check --fix src/xippios/comtrade/enums.py`.
   `render_str_enums` in xippios-core currently writes `__all__` unsorted on one line
   (ruff RUF022 and, past 100 characters, E501); formatting first leaves only the sort
   for `--fix`. The fix in core is tracked as row 12 of the family's `COORDINATION.md`
   queue (`render_str_enums`); drop this step once a core release carries it.
5. Update the provenance table in `reference/README.md`: file, origin (endpoint or
   URL), fetch date.
6. If a `list_<thing>` task does not exist yet for this list, add one with
   `/add-endpoint` so agents can look the codes up; it should return the packaged data,
   not call upstream.
7. Run the checks and open the PR with the diff summarised: how many rows changed, any
   codes that disappeared (those may break existing fixtures or callers). Do not merge.
