"""Public API: ``__version__`` and the task functions re-exported here (conventions §2).

Upstream: UN Comtrade.
"""

from xippios.comtrade._version import __version__
from xippios.comtrade.tasks import (
    get_bilateral_flows,
    get_commodity_series,
    get_counts,
    get_data,
    get_data_availability,
    get_live_update,
    get_metadata,
    get_top_partners,
    get_world_trade,
    list_classifications,
    list_codes,
    list_commodities,
    list_partners,
    list_reporters,
)

__all__ = [
    "__version__",
    "get_bilateral_flows",
    "get_commodity_series",
    "get_counts",
    "get_data",
    "get_data_availability",
    "get_live_update",
    "get_metadata",
    "get_top_partners",
    "get_world_trade",
    "list_classifications",
    "list_codes",
    "list_commodities",
    "list_partners",
    "list_reporters",
]
