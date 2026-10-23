"""The configured ``xippios.core`` client for UN Comtrade.

One ``AsyncClient`` carries the subscription key for the data API: task functions share
its rate limiter and cache, and the same instance serves the sync facades and the MCP
server. The public reference files go through ``reference_client``, which never sends
the key.

Limits of a Basic Individual (free) key, ``docs/upstream/help/subscriptions.md``: 1 call
per second, 500 calls per day, 100,000 records per call. Upstream's own headers agree
(``x-ratelimit-limit: 1`` and ``x-ratelimit-operation-limit: 60`` on the recorded backend
answers). The bucket below allows 60 calls a minute with no burst, so calls are spaced a
second apart. The daily quota is not enforced here; ``countOnly`` calls count against it.
"""

import re

import httpx
from xippios.core import (
    AsyncClient,
    ClientConfig,
    HeaderKeyAuth,
    InvalidRequestError,
    RateLimit,
    RateLimitError,
    Timeouts,
    XippiosError,
)

from xippios.comtrade._version import __version__

SOURCE = "comtrade"
BASE_URL = "https://comtradeapi.un.org"
API_KEY_ENV = "COMTRADE_API_KEY"  # pragma: allowlist secret (a variable name, not a key)
RATE_LIMIT = RateLimit(per_minute=60, burst=1)
TIMEOUTS = Timeouts(read=180.0)
"""Read timeout 180 s, the rest at the family defaults (conventions §6).

A ``countOnly`` count over all reporters outlasted the default 60 s once and answered in
27 s on the repeat (2026-10-23, ``count_over_limit.json``). Core's retry policy stays: a
timed-out attempt it retries is another call against the daily quota.
"""

_REPLENISHED = re.compile(r"replenished in (\d+):(\d{2}):(\d{2})", re.IGNORECASE)


def _payload(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        return None


def _quota_reset(text: str) -> float | None:
    match = _REPLENISHED.search(text)
    if match is None:
        return None
    hours, minutes, seconds = (int(part) for part in match.groups())
    return float(hours * 3600 + minutes * 60 + seconds)


def _refusal(payload: dict[str, object]) -> str:
    message = f"UN Comtrade refused the request (HTTP 400): {payload['error']}"
    details = payload.get("details")
    notes = [
        str(item.get("errorMessage", ""))
        for item in (details if isinstance(details, list) else [])
        if isinstance(item, dict) and item.get("errorMessage")
    ]
    if notes:
        message += " (" + "; ".join(notes) + ")"
    return message


def classify(response: httpx.Response) -> XippiosError | None:
    """UN Comtrade's documented and observed error shapes, mapped once (ADR-0008).

    - HTTP 400 with the backend's ``ErrorResponse`` body ``{"error": ..., "details": ...}``
      (``components.schemas.ErrorResponse``; "Invalid or missing parameters." in the spec)
      is a caller mistake upstream caught: ``InvalidRequestError`` with upstream's text.
      Observed: ``Maximum number of periods is 12`` (``count_13_periods.json``) and
      ``Invalid parameter value`` naming ``clCode`` (``count_cl_code_be5.json``).
    - HTTP 403 whose body mentions a quota is the daily call quota of the key:
      ``RateLimitError``, with ``retry_after`` read from API Management's standard text
      "Out of call volume quota. Quota will be replenished in HH:MM:SS." The spec's 403
      reads "APIM quota / access denial"; this answer was not observed (never provoked).
    - Everything else falls through to the core mapping: 401 (``invalid_key.json``,
      ``GatewayError`` body) and a 403 "User not allowed" become ``AuthError``, 429
      ``RateLimitError`` with ``Retry-After``. No HTTP 200 with a non-empty ``error``
      was observed, so none is mapped.
    """
    status = response.status_code
    if status == 400:
        payload = _payload(response)
        if isinstance(payload, dict) and isinstance(payload.get("error"), str) and payload["error"]:
            return InvalidRequestError(_refusal(payload), source=SOURCE)
    if status == 403:
        text = response.text
        if "quota" in text.lower():
            return RateLimitError(
                f"UN Comtrade call quota exhausted (HTTP 403): {' '.join(text.split())[:200]} "
                "A Basic Individual key allows 500 calls per day; countOnly calls count too.",
                retry_after=_quota_reset(text),
                source=SOURCE,
            )
    return None


config = ClientConfig(
    source=SOURCE,
    version=__version__,
    base_url=BASE_URL,
    timeouts=TIMEOUTS,
    rate_limit=RATE_LIMIT,
    classify=classify,
)
# The key is read from the environment on the first request, never at import.
auth = HeaderKeyAuth("Ocp-Apim-Subscription-Key", API_KEY_ENV, source=SOURCE)
client = AsyncClient(config, auth=auth)

# The reference files under files/v1/app/reference/ are public: the Help Center links
# them without a key and scripts/refresh_upstream.py fetches them without one. They are
# fetched keyless so a reference refresh never sends the key or spends quota.
reference_client = AsyncClient(config)

__all__ = [
    "API_KEY_ENV",
    "BASE_URL",
    "RATE_LIMIT",
    "SOURCE",
    "TIMEOUTS",
    "classify",
    "client",
    "config",
    "reference_client",
]
