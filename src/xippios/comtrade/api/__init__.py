"""Endpoint wrappers for UN Comtrade.

Layer 1 of ADR-0001: one module per upstream operation, named after it. A wrapper
takes the parameters as upstream names them (snake_cased), calls
``xippios.comtrade._client.client`` (or ``reference_client`` for the public reference
files, which never sends the key) and returns models from ``models.py`` that mirror the
payload. No composition and no defaults beyond upstream's own. The reference is the
snapshot in ``docs/upstream/``.
"""

from xippios.comtrade.api.get import get, get_count_only
from xippios.comtrade.api.reference import reference

__all__ = ["get", "get_count_only", "reference"]
