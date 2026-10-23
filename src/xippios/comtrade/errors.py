"""UN Comtrade failure modes with a distinct, documented meaning (conventions §5)."""

from xippios.core import InvalidRequestError

from xippios.comtrade._client import SOURCE

__all__ = ["MAX_PERIODS", "RECORD_LIMIT", "QueryTooLarge"]

RECORD_LIMIT = 100_000
"""Most records ``data/v1/get`` returns per call on a Basic Individual (free) key.

``docs/upstream/help/subscriptions.md``: "Data API ... max 100K records per call" (250K on
premium). Above it upstream does not refuse: it answers HTTP 200 with the first 100,000
rows and an empty ``error`` (observed 2026-10-23 for a query counted at 5,006,385, see
``tests/fixtures/get/count_over_limit.json``), so ``get_data`` counts first.
"""

MAX_PERIODS = 12
"""Most comma-separated values ``period`` takes in one call.

Not in the snapshot; upstream answers HTTP 400 ``Maximum number of periods is 12`` to a
13th (``tests/fixtures/get/count_13_periods.json``).
"""


class QueryTooLarge(InvalidRequestError):
    """The query would return more than UN Comtrade's per-call record limit (HTTP 422).

    Raised by ``get_data`` from the ``countOnly`` count, before any data is fetched,
    because upstream would otherwise cut the answer at the limit without saying so.

    Attributes:
        count: Records the query would return.
        limit: The per-call limit.
    """

    def __init__(self, count: int, *, limit: int = RECORD_LIMIT) -> None:
        super().__init__(
            f"query would return {count:,} records; UN Comtrade serves at most {limit:,} per "
            f"call and silently cuts the rest. Split by period (max {MAX_PERIODS} per call), "
            "then by reporter, then raise the aggregation level (for example cmd_code 'AG2' "
            "instead of 'AG6'), and check each part with get_counts.",
            source=SOURCE,
        )
        self.count = count
        self.limit = limit
