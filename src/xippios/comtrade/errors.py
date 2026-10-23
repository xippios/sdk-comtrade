"""UN Comtrade failure modes with a distinct, documented meaning (conventions §5)."""

from xippios.core import InvalidRequestError

from xippios.comtrade._client import SOURCE

__all__ = ["MAX_PERIODS", "RECORD_LIMIT", "QueryTooLarge"]

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


class QueryTooLarge(InvalidRequestError):
    """The query would return more than UN Comtrade's per-call record limit (HTTP 422).

    Raised by ``get_data`` from the ``countOnly`` count, before any data is fetched,
    because upstream would otherwise cut the answer at the limit without saying so. The
    task-shaped slices skip the count, since their arguments bound the rows (one per
    product code and period, reporter or partner); they raise it with that bound
    (``bound=True``) before the call when it exceeds the limit.

    Attributes:
        count: Records the query would return, or with ``bound`` at most return.
        limit: The per-call limit.
        bound: ``True`` when ``count`` is an upper bound from the arguments, ``False``
            when it is upstream's count.
    """

    def __init__(self, count: int, *, limit: int = RECORD_LIMIT, bound: bool = False) -> None:
        if bound:
            what = f"query could return up to {count:,} records"
            advice = "Name fewer product codes or periods per call."
        else:
            what = f"query would return {count:,} records"
            advice = (
                f"Split by period (max {MAX_PERIODS} per call), then by reporter, then raise "
                "the aggregation level (for example cmd_code 'AG2' instead of 'AG6'), and "
                "check each part with get_counts."
            )
        super().__init__(
            f"{what}; UN Comtrade serves at most {limit:,} per call and silently cuts the "
            f"rest. {advice}",
            source=SOURCE,
        )
        self.count = count
        self.limit = limit
        self.bound = bound
