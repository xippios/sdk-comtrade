"""``GET files/v1/app/reference/{name}``: UN Comtrade's public reference files.

Reference: ``docs/upstream/reference/ListofReferences.json`` (the index of the files, one
``fileuri`` per list) and ``docs/upstream/help/list-of-references-parameter-codes.md``.
Every file is ``{"results": [...]}``, some with a ``"more": false`` beside it; the rows
differ per file, so the caller names the row model. The files need no key and are
fetched through ``reference_client``, which never sends one.
"""

from typing import Any

from xippios.core import UpstreamModel, parse

from xippios.comtrade._client import SOURCE, reference_client

__all__ = ["reference"]


class _ReferenceFile(UpstreamModel):
    results: list[dict[str, Any]]


async def reference[M: UpstreamModel](name: str, row: type[M]) -> list[M]:
    """Fetch one reference file and return its ``results`` rows.

    Args:
        name: The file name as ``ListofReferences.json`` lists it, e.g.
            ``"tradeRegimes.json"``, ``"ModeOfTransportCodes.json"``,
            ``"ListofReferences.json"``.
        row: The model of one row, e.g. ``ReferenceCode`` for ``{"id", "text"}`` lists or
            ``Reference`` for ``ListofReferences.json``.
    """
    endpoint = f"files/v1/app/reference/{name}"
    raw = await reference_client.get_json(f"/{endpoint}")
    rows = parse(_ReferenceFile, raw, source=SOURCE, endpoint=endpoint).results
    return [parse(row, item, source=SOURCE, endpoint=endpoint) for item in rows]
