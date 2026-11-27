"""The packaged lists that name a code, each declared once (sdk-core ADR-0045).

``PackagedList.codes`` of each packaged list or table whose codes a record carries or a
check reads: the code under upstream's field and the name a refusal and ``meta.names``
show for it. ``models.py`` marks each code field of a record with its list, ``NamedBy``,
so every answer names the codes of its rows in ``meta.names`` and says in ``meta.notes``
which of them the list lacks (sdk-core ADR-0067). ``params.py`` checks an argument
against the same declaration with ``check``, before any request (conventions §5). The
module sits below both, since ``params.py`` imports the models.

The lists read from the spec, ``typeCode``, ``aggregateBy`` and ``breakdownMode``, and
``clCode``, whose ``BE`` and ``TM`` the package adds from the spec without upstream's words,
name each code by its own text: they are declared for ``check`` alone. ``flowCode``'s
``MIF`` and ``XIF``, which the package adds from the spec too, hold no ``text``, so each is
named by its own code, as core names a code whose record holds no name, and the other
flows by upstream's words. ``cmdCode`` has no packaged list: its codes come with the
classification files that ``list_commodities`` fetches.
"""

from xippios.core import PackagedCodes, PackagedList

from xippios.comtrade._client import SOURCE

__all__ = [
    "AGGREGATE_BY",
    "BREAKDOWN_MODES",
    "CATEGORIES",
    "CL_CODES",
    "CUSTOMS_CODES",
    "FLOW_CODES",
    "FREQ_CODES",
    "MOS_CODES",
    "MOT_CODES",
    "PACKAGE",
    "PARTNERS",
    "QTY_UNIT_CODES",
    "REPORTERS",
    "TYPE_CODES",
]

PACKAGE = "xippios.comtrade"
"""The package whose ``reference/`` holds the lists."""


def _codes(
    name: str, code: str, label: str | None = None, *, fold_case: bool = False
) -> PackagedCodes:
    return PackagedList.load(PACKAGE, name).codes(code, label, fold_case=fold_case, source=SOURCE)


def _partly_worded(name: str, code: str, label: str, *, fold_case: bool = False) -> PackagedCodes:
    """A list whose records the package added from the spec hold no ``label``.

    Core declares a list's names from a field that every record holds and names a code
    whose record holds no name by its own text, so each record without ``label`` is read
    with an empty one; the packaged file stays as the refresh script wrote it.
    """
    packaged = PackagedList.load(PACKAGE, name)
    records = [{label: None, **record} for record in packaged.records]
    worded = packaged.model_copy(update={"records": records})
    return worded.codes(code, label, fold_case=fold_case, source=SOURCE)


REPORTERS = _codes("Reporters", "reporterCode", "reporterDesc")
"""The reporter codes of ``Reporters.json``, integers, each named by its ``reporterDesc``."""

PARTNERS = _codes("partnerAreas", "PartnerCode", "PartnerDesc")
"""The partner codes of ``partnerAreas.json``, integers, each named by its ``PartnerDesc``."""

CUSTOMS_CODES = _codes("customsCode", "customsCode", "text", fold_case=True)
"""The customs procedures of ``CustomsCodes.json``; the spec's pattern takes ``c`` and ``C``."""

MOT_CODES = _codes("motCode", "motCode", "text")
"""The modes of transport of ``ModeOfTransportCodes.json``, text codes such as ``"2100"``."""

MOS_CODES = _codes("mosCode", "mosCode", "text")
"""The modes of supply of ``ModeOfSupply.json``, which a services row carries."""

QTY_UNIT_CODES = _codes("qtyUnitCode", "qtyUnitCode", "qtyDescription")
"""The quantity units of ``QuantityUnits.json``, each named by its ``qtyDescription``."""

FREQ_CODES = _codes("freqCode", "freqCode", "text")
"""The frequencies of the spec's enum, ``A`` and ``M``, named by their ``Frequency.json`` text."""

TYPE_CODES = _codes("typeCode", "typeCode")
"""The types of trade of the spec, ``C`` and ``S``, each named by its own code."""

CL_CODES = _codes("clCode", "clCode")
"""The classifications of ``ListofReferences.json`` and the spec, each named by its code."""

FLOW_CODES = _partly_worded("flowCode", "flowCode", "text", fold_case=True)
"""The flows of ``tradeRegimes.json`` and the spec; the spec allows them case-insensitive."""

AGGREGATE_BY = _codes("aggregateBy", "aggregateBy")
"""The parameters of the spec that ``aggregateBy`` aggregates over, ``cmdCode`` among them."""

BREAKDOWN_MODES = _codes("breakdownMode", "breakdownMode")
"""The two breakdown modes of the spec, ``classic`` and ``plus``."""

CATEGORIES = _codes("ListofReferences", "category")
"""The categories of ``ListofReferences.json``, each named by its own text, as written."""
