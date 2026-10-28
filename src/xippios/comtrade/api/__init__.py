"""Endpoint wrappers for UN Comtrade.

Layer 1 of ADR-0001: one module per upstream operation, named after it. A wrapper
takes the parameters as upstream names them (snake_cased), calls
``xippios.comtrade._client.client`` (with ``auth=None`` for the public reference files,
so they never send the key) and returns models from ``models.py`` that mirror the
payload. No composition and no defaults beyond upstream's own. The reference is the
snapshot in ``docs/upstream/``.
"""

from xippios.comtrade.api.get import get, get_count_only
from xippios.comtrade.api.get_bilateral_data import get_bilateral_data
from xippios.comtrade.api.get_da import get_da
from xippios.comtrade.api.get_live_update import get_live_update
from xippios.comtrade.api.get_metadata import get_metadata
from xippios.comtrade.api.get_trade_balance import get_trade_balance
from xippios.comtrade.api.reference import ReferenceFile, reference, reference_rows

__all__ = [
    "ReferenceFile",
    "get",
    "get_bilateral_data",
    "get_count_only",
    "get_da",
    "get_live_update",
    "get_metadata",
    "get_trade_balance",
    "reference",
    "reference_rows",
]
