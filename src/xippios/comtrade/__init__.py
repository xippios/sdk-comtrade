"""Typed client, MCP tools and HTTP routes for UN Comtrade.

Distribution ``xippios-comtrade``. Public API: ``__version__`` and the task
functions re-exported here. Endpoint wrappers under ``api/`` and the configured client
in ``_client`` are internal.
"""

from xippios.comtrade._version import __version__
from xippios.comtrade.tasks import (
    get_counts,
    get_data,
    list_commodities,
    list_partners,
    list_reporters,
)

__all__ = [
    "__version__",
    "get_counts",
    "get_data",
    "list_commodities",
    "list_partners",
    "list_reporters",
]
