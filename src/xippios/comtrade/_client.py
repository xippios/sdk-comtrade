"""The configured ``xippios.core`` client for UN Comtrade.

One ``AsyncClient`` serves every call. It carries the subscription key for the data API;
the public reference files go through it with ``auth=None`` per request, so they never
send the key, and its cache keeps those files, and nothing else, for the life of the
process (``cache_filter``). Task functions share its rate limiter, and the same instance
serves the sync facades and the MCP server.

Limits of a Basic Individual (free) key, ``docs/upstream/help/subscriptions.md``: 1 call
per second, 500 calls per day, 100,000 records per call. Upstream's own headers agree
(``x-ratelimit-limit: 1`` and ``x-ratelimit-operation-limit: 60`` on the recorded backend
answers). The bucket below spaces calls 1.5 s apart (``RATE_LIMIT``). The daily quota is
kept by ``policy``: once upstream answers 403 "Quota will be replenished in HH:MM:SS",
no call is sent until then; ``countOnly`` calls count against it.
"""

import re

import httpx
from xippios.core import (
    AsyncClient,
    ClientConfig,
    HeaderKeyAuth,
    InvalidRequestError,
    MemoryCache,
    QuotaPolicy,
    RateLimit,
    RateLimitError,
    Timeouts,
    XippiosError,
)

from xippios.comtrade._version import __version__

SOURCE = "comtrade"
BASE_URL = "https://comtradeapi.un.org"
API_KEY_ENV = "COMTRADE_API_KEY"  # pragma: allowlist secret (a variable name, not a key)
# Paced within the limit upstream documents (ADR-0010 decision 1): 1 call per second, 60
# per minute, documented; 40 per minute chosen after the recorded 429s at 1.0 s (D41).
RATE_LIMIT = RateLimit(per_minute=40, burst=1)
"""One call every 1.5 s, no burst: upstream's 1 call per second with a margin.

Spaced exactly 1.0 s apart, 9 of 18 calls drew HTTP 429 "Rate limit is exceeded. Try
again in 1 seconds." with ``Retry-After: 1`` (2026-10-23, ``count_rate_limited.json``):
the gateway's one-second window is not exact. At 1.5 s 2 of 39 calls drew one, at 2.0 s
none of 10. Core retries a 429 after ``Retry-After``; every retry is another call.
"""
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


def _quota_spent(response: httpx.Response) -> float | None:
    """Seconds until the daily quota is back, from a 403 that names it; else ``None``.

    The ``spent`` hook of ``policy``. Only a 403 is read, so a reference file of 2 MB is
    never decoded for it; the time comes from the text ``classify`` reads as well.
    """
    if response.status_code != 403:
        return None
    text = response.text
    if "quota" not in text.lower():
        return None
    return _quota_reset(text)


policy = QuotaPolicy(
    limit_header=None,
    remaining_header=None,
    window=86_400.0,
    spent=_quota_spent,
    source=SOURCE,
)
"""The daily quota of 500 calls (ADR-0010, ADR-0015): no call into a quota known to be spent.

Upstream's ``x-ratelimit-*`` headers describe the per-second pace, not the daily quota, so
neither is read. API Management's 403 "Out of call volume quota. Quota will be replenished
in HH:MM:SS." marks the quota spent for that long (``_quota_spent``), cut to the window of
a day; a 429 marks it spent until its ``Retry-After``, upstream's ``1`` for the pace
refusal. A wait within ``pause_cap`` (30 s) is waited out, a longer one is refused with
``RateLimitError`` before anything is sent. ``classify`` still maps the 403 itself.
"""

_REFERENCE_FILES = "/files/v1/app/reference/"


def _reference_file(request: httpx.Request) -> bool:
    """The cache's filter: a request for a public reference file, and no other."""
    return request.url.path.startswith(_REFERENCE_FILES)


config = policy.install(
    ClientConfig(
        source=SOURCE,
        version=__version__,
        base_url=BASE_URL,
        timeouts=TIMEOUTS,
        rate_limit=RATE_LIMIT,
        # The files change rarely (ListofReferences.json was last modified 2025-11-12 when
        # the snapshot was taken) and the classification files are large (HS.json is about
        # 2 MB, 8,262 codes), so a file is fetched once per process: no TTL, 64 entries for
        # every file ListofReferences.json lists. Only HTTP 200 answers are kept.
        cache=MemoryCache(ttl=None, maxsize=64),
        cache_filter=_reference_file,
        classify=classify,
    )
)
# The key is read from the environment on the first request, never at import. The
# reference files under files/v1/app/reference/ are public: the Help Center links them
# without a key and scripts/refresh_upstream.py fetches them without one. api.reference
# passes auth=None, so a reference refresh never sends the key or spends quota; it shares
# RATE_LIMIT's pace, and once the quota is spent policy holds it back too.
auth = HeaderKeyAuth("Ocp-Apim-Subscription-Key", API_KEY_ENV, source=SOURCE)
client = AsyncClient(config, auth=auth)

__all__ = [
    "API_KEY_ENV",
    "BASE_URL",
    "RATE_LIMIT",
    "SOURCE",
    "TIMEOUTS",
    "auth",
    "classify",
    "client",
    "config",
    "policy",
]
