"""``GET files/v1/app/reference/{name}``: UN Comtrade's public reference files.

Reference: ``docs/upstream/reference/ListofReferences.json`` (the index of the files, one
``fileuri`` per list) and ``docs/upstream/help/list-of-references-parameter-codes.md``.
Every file is ``{"results": [...]}``, some with ``"more"`` and, for the classification
files, ``classCode``, ``className`` and ``minimumInputLength`` beside it; the rows differ
per file, so the caller names the row model. The files need no key and are fetched
through ``reference_client``, which never sends one and keeps every file it fetched for
the life of the process (the classification files run to 2 MB). A file that does not
exist answers HTTP 404 (``BlobNotFound``), raised as ``NotFoundError``.
"""

from typing import Any

from xippios.core import UpstreamModel, parse

from xippios.comtrade._client import SOURCE, reference_client

__all__ = ["reference", "reference_rows"]


class _ReferenceFile(UpstreamModel):
    results: list[dict[str, Any]]


def _endpoint(name: str) -> str:
    return f"files/v1/app/reference/{name}"


async def reference_rows(name: str) -> list[dict[str, Any]]:
    """Fetch one reference file and return its ``results`` rows as upstream sent them.

    Args:
        name: The file name as ``ListofReferences.json`` lists it, e.g.
            ``"Reporters.json"``, ``"partnerAreas.json"``, ``"HS.json"``.
    """
    endpoint = _endpoint(name)
    raw = await reference_client.get_json(f"/{endpoint}")
    return parse(_ReferenceFile, raw, source=SOURCE, endpoint=endpoint).results


async def reference[M: UpstreamModel](name: str, row: type[M]) -> list[M]:
    """Fetch one reference file and return its ``results`` rows as models.

    Args:
        name: The file name as ``ListofReferences.json`` lists it, e.g.
            ``"tradeRegimes.json"``, ``"ModeOfTransportCodes.json"``,
            ``"ListofReferences.json"``, ``"HS.json"``.
        row: The model of one row, e.g. ``ReferenceCode`` for ``{"id", "text"}`` lists,
            ``Reference`` for ``ListofReferences.json``, ``Commodity`` for a
            classification file.
    """
    endpoint = _endpoint(name)
    rows = await reference_rows(name)
    return [parse(row, item, source=SOURCE, endpoint=endpoint) for item in rows]
