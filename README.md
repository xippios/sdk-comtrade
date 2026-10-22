# xippios-comtrade

Typed Python client, MCP server and FastAPI routes for
[UN Comtrade](https://comtradeplus.un.org), part of the
[xippios SDK family](https://github.com/xippios). Names and semantics follow the
upstream documentation; every response carries release metadata (source, endpoint,
retrieved_at, published_at, vintage).

## Install

```bash
uv add xippios-comtrade            # client only
uv add "xippios-comtrade[mcp]"     # + MCP server
uv add "xippios-comtrade[http]"    # + FastAPI router
```

Set `COMTRADE_API_KEY` in the environment. Nothing is read from files.

## 30-second example

```python
from xippios.comtrade import tasks

# result = tasks.<task>(...)
# result.data, result.meta.retrieved_at, result.meta.request
```

Task functions are listed in the status table below as they are added.

## MCP

```json
{
  "mcpServers": {
    "comtrade": {
      "command": "uvx",
      "args": ["--from", "xippios-comtrade[mcp]", "xippios-comtrade-mcp"],
      "env": { "COMTRADE_API_KEY": "..." }
    }
  }
}
```

Tools are read-only and named `comtrade_<verb>_<noun>`. Results are capped at
200 rows or 64 KB with a note on how to narrow the query. `--http` serves streamable
HTTP instead of stdio.

## Status

| Upstream operation | Task function | MCP tool | Status |
| --- | --- | --- | --- |
| (none yet) | | | |

## Upstream terms and attribution

Data comes from UN Comtrade (https://comtradeplus.un.org) under its own terms of use;
this package adds no rights to it. Documentation snapshot: `docs/upstream/`.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
