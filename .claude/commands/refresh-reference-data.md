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
4. Update the provenance table in `reference/README.md`: file, origin (endpoint or
   URL), fetch date.
5. If a `list_<thing>` task does not exist yet for this list, add one with
   `/add-endpoint` so agents can look the codes up; it should return the packaged data,
   not call upstream.
6. Run the checks and open the PR with the diff summarised: how many rows changed, any
   codes that disappeared (those may break existing fixtures or callers). Do not merge.
