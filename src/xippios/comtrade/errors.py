"""UN Comtrade's limits and the words of the refusals they cause (conventions §5).

A query over upstream's per-call record limit is refused with core's
``xippios.core.QueryTooLarge`` (sdk-core ADR-0053), which ``get_data``'s count first,
core's ``fetch_counted``, raises with the count, the limit and ``NARROW``.
"""

from xippios.comtrade._client import SOURCE

__all__ = ["MAX_PERIODS", "NARROW", "RECORD_LIMIT", "over_mcp"]


def over_mcp(task: str) -> str:
    """How a refusal names the MCP tool of a task it points to, after the task's name.

    Conventions §8: an error a tool can return that names another task, the one to call
    instead or the list task that lists the codes, names that task's tool too, e.g.
    ``list_reporters (over MCP, the tool comtrade_list_reporters)``.

    Args:
        task: The task's name in ``tasks.__all__``, e.g. ``"count_data"``.
    """
    return f"(over MCP, the tool {SOURCE}_{task})"


RECORD_LIMIT = 100_000
"""Most records ``data/v1/get`` returns per call on a Basic Individual (free) key.

``docs/upstream/help/subscriptions.md``: "Data API ... max 100K records per call" (250K on
premium). Above it upstream does not refuse: it answers HTTP 200 with the first 100,000
rows and an empty ``error``, so ``get_data`` counts first. The truncation was observed on
2026-10-23 (HTTP 200, 100,000 rows, ``count`` 100000, empty ``error``, 89 MB) and not
recorded; ``tests/fixtures/get/count_over_limit.json`` holds the count of the same query,
5,006,385.
"""

MAX_PERIODS = 12
"""Most comma-separated values ``period`` takes in one call.

Not in the snapshot; upstream answers HTTP 400 ``Maximum number of periods is 12`` to a
13th (``tests/fixtures/get/count_13_periods.json``).
"""


NARROW = (
    "The count was sent and no data fetched. "
    f"Split by period (max {MAX_PERIODS} per call), then by reporter, then raise the "
    "aggregation level (for example cmd_code 'AG2' instead of 'AG6'), and check each part "
    f"with count_data {over_mcp('count_data')}."
)
"""What closes ``QueryTooLarge`` after ``get_data``'s count: core's ``narrow``.

Its first sentence says what was sent, as a refusal after a request of the call does
(conventions §5; sdk-core ADR-0054, amendment 2026-11-22), the rest what narrows the query.
"""
