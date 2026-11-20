"""``GET files/v1/app/reference/{name}``: UN Comtrade's public reference files.

Reference: ``docs/upstream/reference/ListofReferences.json`` (the index of the files, one
``fileuri`` per list) and ``docs/upstream/help/list-of-references-parameter-codes.md``.
Every file is ``{"results": [...]}``, some with ``"more"`` and, for the classification
files, ``classCode``, ``className`` and ``minimumInputLength`` beside it; the rows differ
per file, so the caller names the row model. The files need no key: they go through the
package's one client with ``auth=None``, which sends none, and the client's cache keeps
every file it fetched for the life of the process (the classification files run to 2 MB).
Both wrappers return core's ``Answer``: the rows as ``payload`` and ``retrieved_at``, on a
cache hit the time the file was stored, else the time it arrived (sdk-core ADR-0037,
decision 5). ``get_answer`` reads the file's ``{"results": [...]}`` before the cache stores
it, so an answer that is no JSON or holds no ``results`` is asked for again on the next
call; the rows are parsed after, so a row the row model refuses fails from the cache for
the life of the process. A file that does not exist answers HTTP 404 (``BlobNotFound``),
raised as ``NotFoundError``.
"""

from typing import Any

from xippios.core import Answer, UpstreamModel, parse

from xippios.comtrade._client import SOURCE, client

__all__ = ["reference", "reference_rows"]


class _ReferenceFile(UpstreamModel):
    results: list[dict[str, Any]]


def _endpoint(name: str) -> str:
    return f"files/v1/app/reference/{name}"


async def reference_rows(name: str) -> Answer[list[dict[str, Any]]]:
    """Fetch one reference file and return its ``results`` rows as upstream sent them.

    Args:
        name: The file name as ``ListofReferences.json`` lists it, e.g.
            ``"Reporters.json"``, ``"partnerAreas.json"``, ``"HS.json"``.
    """
    endpoint = _endpoint(name)
    answer = await client.get_answer(
        f"/{endpoint}", auth=None, parse=_ReferenceFile, endpoint=endpoint
    )
    return Answer(answer.payload.results, answer.retrieved_at)


async def reference[M: UpstreamModel](name: str, row: type[M]) -> Answer[list[M]]:
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
    answer = await reference_rows(name)
    return Answer(
        [parse(row, item, source=SOURCE, endpoint=endpoint) for item in answer.payload],
        answer.retrieved_at,
    )
