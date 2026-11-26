"""The packaged lists that name a code, each declared once (sdk-core ADR-0045).

``PackagedList.codes`` of each packaged list or table whose codes a record carries or a
check reads: the code under upstream's field and the name a refusal and ``meta.names``
show for it. ``models.py`` marks each code field of a record with its list, ``NamedBy``,
so every answer names the codes of its rows in ``meta.names`` and says in ``meta.notes``
which of them the list lacks (sdk-core ADR-0067). ``params.py`` checks an argument
against the same declaration with ``check``, before any request (conventions §5). The
module sits below both, since ``params.py`` imports the models.

``typeCode`` has no list here: its words stand in the spec alone. ``cmdCode`` has no
packaged list: its codes come with the classification files that ``list_commodities``
fetches. ``flowCode`` and ``clCode`` have none yet: their lists hold values that the
package adds from the spec without upstream's words (``MIF`` and ``XIF``, ``BE`` and
``TM``), and core declares a list's names only where every record holds one.
"""

from xippios.core import PackagedCodes, PackagedList

from xippios.comtrade._client import SOURCE

__all__ = [
    "CUSTOMS_CODES",
    "FREQ_CODES",
    "MOS_CODES",
    "MOT_CODES",
    "PACKAGE",
    "PARTNERS",
    "QTY_UNIT_CODES",
    "REPORTERS",
]

PACKAGE = "xippios.comtrade"
"""The package whose ``reference/`` holds the lists."""


def _codes(name: str, code: str, label: str, *, fold_case: bool = False) -> PackagedCodes:
    return PackagedList.load(PACKAGE, name).codes(code, label, fold_case=fold_case, source=SOURCE)


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
"""The frequencies of the spec, ``A`` and ``M``, with the spec's words for them."""
