Record a fixture for UN Comtrade: $ARGUMENTS

Expected arguments: `<endpoint> <case> [key=value ...]`, for example
`api_GET corn_2024 commodity_desc=CORN year=2024`.

Fixtures are recorded through the real client, never typed in by hand. The file lands at
`tests/fixtures/<endpoint>/<case>.json` with credentials scrubbed.

1. Confirm `COMTRADE_API_KEY` is set in the environment (`[ -n "${COMTRADE_API_KEY}" ] && echo ok`); never print its value.
2. Find the request path and parameters for the endpoint in `docs/upstream/` and in the
   wrapper under `src/xippios/comtrade/api/`. Use the wrapper's parameter names.

3. Record it with a one-off script run through `uv run python`:

   ```python
   from pathlib import Path

   from xippios.core.testing import fixture_path, record_sync
   from xippios.comtrade._client import client

   fixture = record_sync(
       client,
       "<request path>",  # e.g. "/api/api_GET"
       fixture_path(Path("tests/fixtures"), "<endpoint>", "<case>"),
       params={...},  # the parameters from the arguments
   )
   print(fixture.response.status, fixture.request.url)
   ```

   Error cases (a 404 for an unknown code, for instance) are worth recording too; the
   recorder keeps them instead of raising.

4. Check the file: `grep -niE 'api[_-]?key|token|secret|authorization' tests/fixtures/<endpoint>/<case>.json`
   must print nothing but `REDACTED` values. If a credential slipped through, delete the
   file and stop: report which field leaked so the scrubber in `xippios-core` can learn it.

5. Keep the fixture small enough to review (narrow the query if the body is huge), then
   reference it from a test with the `replay_fixture("<endpoint>", "<case>")` fixture.
