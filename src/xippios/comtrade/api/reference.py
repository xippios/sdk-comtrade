"""``GET files/v1/app/reference/{name}``: UN Comtrade's public reference files.

Reference: ``docs/upstream/reference/ListofReferences.json`` (the index of the files, one
``fileuri`` per list) and ``docs/upstream/help/list-of-references-parameter-codes.md``.
Every file is ``{"results": [...]}``, some with ``"more"`` and, for the classification
files, ``classCode``, ``className`` and ``minimumInputLength`` beside it; the rows differ
per file, so the caller names the row model. The files need no key: they go through the
package's one client with ``auth=None``, which sends none, and the client's cache keeps
every file it fetched for the life of the process (the classification files run to 2 MB).
``AsyncClient.get_answer`` says when a file was retrieved: on a cache hit the time it
was stored (ADR-0015, decision 5). A file that does not exist answers HTTP 404
(``BlobNotFound``), raised as ``NotFoundError``.
"""

from datetime import datetime
from typing import Any, NamedTuple

from xippios.core import UpstreamModel, parse

from xippios.comtrade._client import SOURCE, client

__all__ = ["ReferenceFile", "reference", "reference_rows"]


class _ReferenceFile(UpstreamModel):
    results: list[dict[str, Any]]


class ReferenceFile[T](NamedTuple):
    """The ``results`` rows of one reference file and when they were retrieved.

    Attributes:
        rows: The rows, in upstream order: as upstream sent them from
            ``reference_rows``, as models from ``reference``.
        retrieved_at: Timezone-aware UTC: on a cache hit the time the file was stored,
            else the time it arrived; a task's ``ResultMeta.retrieved_at``.
    """

    rows: list[T]
    retrieved_at: datetime


def _endpoint(name: str) -> str:
    return f"files/v1/app/reference/{name}"


async def reference_rows(name: str) -> ReferenceFile[dict[str, Any]]:
    """Fetch one reference file and return its ``results`` rows as upstream sent them.

    Args:
        name: The file name as ``ListofReferences.json`` lists it, e.g.
            ``"Reporters.json"``, ``"partnerAreas.json"``, ``"HS.json"``.
    """
    endpoint = _endpoint(name)
    answer = await client.get_answer(f"/{endpoint}", auth=None)
    rows = parse(_ReferenceFile, answer.payload, source=SOURCE, endpoint=endpoint).results
    return ReferenceFile(rows, answer.retrieved_at)


async def reference[M: UpstreamModel](name: str, row: type[M]) -> ReferenceFile[M]:
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
    rows, retrieved_at = await reference_rows(name)
    return ReferenceFile(
        [parse(row, item, source=SOURCE, endpoint=endpoint) for item in rows], retrieved_at
    )
