"""The configured ``xippios.core`` client for UN Comtrade.

One ``AsyncClient`` serves every call. It carries the subscription key for the data API;
the public reference files go through it with ``auth=None`` per request, so they never
send the key, and its cache keeps those files, and nothing else, for the life of the
process (``cache_filter``). Task functions share its rate limiter, and the same instance
serves the sync facades and the MCP server.

Limits of a Basic Individual (free) key, ``docs/upstream/help/subscriptions.md``: 1 call
per second, 500 calls per day, 100,000 records per call. Upstream's own headers agree
(``x-ratelimit-limit: 1`` and ``x-ratelimit-operation-limit: 60`` on the recorded backend
answers). The bucket below spaces calls 1.5 s apart (``RATE_LIMIT``). The client counts no
calls against the daily quota; ``policy`` reacts to upstream's answers: once upstream
answers 403 "Quota will be replenished in HH:MM:SS", no call is sent until then.
``countOnly`` calls count against the quota too.
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
    parse_retry_after,
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
_TRY_AGAIN = re.compile(r"try again in (\d+) seconds?", re.IGNORECASE)


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
    # Only the message is read: errorMessage as data/v1/get and the spec's ValidationError
    # spell it, ErrorMessage as getBilateralData's 400 did (ch_us_2023_flow_code_m_x.json);
    # getTradeBalance's recorded 400 had details null.
    notes = [
        str(item.get("errorMessage") or item.get("ErrorMessage"))
        for item in (details if isinstance(details, list) else [])
        if isinstance(item, dict) and (item.get("errorMessage") or item.get("ErrorMessage"))
    ]
    if notes:
        message += " (" + "; ".join(notes) + ")"
    return message


def classify(response: httpx.Response) -> XippiosError | None:
    """UN Comtrade's documented and observed error shapes, mapped once (ADR-0008).

    - HTTP 400 with the backend's ``ErrorResponse`` body ``{"error": ..., "details": ...}``
      (``components.schemas.ErrorResponse``; "Invalid or missing parameters." in the spec)
      is a caller mistake upstream caught: ``InvalidRequestError`` with upstream's text.
      Observed: ``Maximum number of periods is 12`` (``count_13_periods.json``, and on
      ``tools/v1/getTradeBalance`` ``ch_world_13_periods.json``) and ``Invalid parameter
      value`` naming ``clCode`` (``count_cl_code_be5.json``). The message of each
      detail is added to the text: ``errorMessage`` as ``data/v1/get`` and the spec's
      ``ValidationError`` spell it, or ``ErrorMessage`` as ``tools/v1/getBilateralData``'s
      400 did (``ch_us_2023_flow_code_m_x.json``); ``memberNames``/``MemberNames`` is not
      read. ``getTradeBalance``'s recorded 400 had ``details`` null.
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
    """Seconds the quota is spent for, from the two answers that say so; else ``None``.

    The ``spent`` hook of ``policy``. A 403 that names the daily quota gives its
    "replenished in HH:MM:SS". A 429, upstream's pace refusal, gives ``None`` when its
    ``Retry-After`` can be read, so the header rules, else the seconds of "Try again in N
    seconds" in its body, else 1.0, upstream's documented one-second window, so a pace
    refusal never falls back to the day-long ``window``. No other answer is read, so a
    reference file of 2 MB is never decoded for it.
    """
    status = response.status_code
    if status == 429:
        if parse_retry_after(response.headers.get("Retry-After")) is not None:
            return None
        match = _TRY_AGAIN.search(response.text)
        return float(match.group(1)) if match else 1.0
    if status != 403:
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
"""No call into a quota upstream has said is spent (ADR-0010, ADR-0015).

The policy counts no calls against the daily 500; it reacts to the two answers that say
the quota is spent. Upstream's ``x-ratelimit-*`` headers describe the per-second pace, not
the daily quota, so neither is read. ``_quota_spent`` reads the 403 "Out of call volume
quota. Quota will be replenished in HH:MM:SS." for that long, which ``window`` caps at a
day, and a 429 for its ``Retry-After``, upstream's ``1``, or, without one, for the
"Try again in N seconds" of its body, else for 1 s, never for the day-long ``window``. A
wait within ``pause_cap`` (30 s) is waited out, a longer one is refused with
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
