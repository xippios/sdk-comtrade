"""Pydantic models mirroring UN Comtrade payloads.

One model per upstream object, subclassing ``xippios.core.UpstreamModel``, with fields
named as upstream names them in snake_case. Within-source hygiene only: dates become
``datetime.date``, numbers become numbers, upstream enumerations become ``StrEnum``.
No cross-source normalisation (ADR-0003): an upstream concept stays an upstream concept.

Example::

    from decimal import Decimal

    from pydantic import Field

    from xippios.core import UpstreamModel


    class Record(UpstreamModel):
        commodity_desc: str
        year: int
        value: Decimal = Field(alias="Value")
"""

__all__: list[str] = []
