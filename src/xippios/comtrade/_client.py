"""The configured ``xippios.core`` client for UN Comtrade.

One ``AsyncClient`` for the whole package: task functions share its rate limiter and
cache, and the same instance serves the sync facades and the MCP server.
"""

from xippios.core import AsyncClient, ClientConfig, HeaderKeyAuth, RateLimit

from xippios.comtrade._version import __version__

SOURCE = "comtrade"
BASE_URL = "https://comtradeapi.un.org"
API_KEY_ENV = "COMTRADE_API_KEY"  # pragma: allowlist secret (a variable name, not a key)
RATE_LIMIT = RateLimit(per_minute=60)

config = ClientConfig(
    source=SOURCE,
    version=__version__,
    base_url=BASE_URL,
    rate_limit=RATE_LIMIT,
)
# The key is read from the environment on the first request, never at import.
auth = HeaderKeyAuth("Ocp-Apim-Subscription-Key", API_KEY_ENV, source=SOURCE)
client = AsyncClient(config, auth=auth)

__all__ = ["API_KEY_ENV", "BASE_URL", "RATE_LIMIT", "SOURCE", "client", "config"]
