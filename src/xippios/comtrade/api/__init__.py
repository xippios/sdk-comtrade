"""Endpoint wrappers for UN Comtrade.

Layer 1 of ADR-0001: one module per upstream operation, named after it. A wrapper
takes the parameters as upstream names them (snake_cased), calls
``xippios.comtrade._client.client`` (with ``auth=None`` for the public reference files
and the public operations under ``public/v1``, so they never send the key) and returns
models from ``models.py`` that mirror the payload. No composition and no defaults beyond
upstream's own. The reference is the snapshot in ``docs/upstream/``.
"""

from xippios.comtrade.api.get import get, get_count_only
from xippios.comtrade.api.get_comtrade_releases import get_comtrade_releases
from xippios.comtrade.api.get_da import get_da
from xippios.comtrade.api.get_live_update import get_live_update
from xippios.comtrade.api.get_metadata import get_metadata
from xippios.comtrade.api.get_world_share import get_world_share
from xippios.comtrade.api.reference import ReferenceFile, reference, reference_rows

__all__ = [
    "ReferenceFile",
    "get",
    "get_comtrade_releases",
    "get_count_only",
    "get_da",
    "get_live_update",
    "get_metadata",
    "get_world_share",
    "reference",
    "reference_rows",
]
