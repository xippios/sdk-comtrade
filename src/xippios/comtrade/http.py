"""FastAPI router for UN Comtrade.

One route per task in ``tasks.__all__``, at ``/comtrade/<task>``, but those
``tasks.BULK_TASKS`` names, which core skips: the router is passed ``tasks.__all__`` whole
(ADR-0019). A task whose parameters are all scalars is a ``GET`` with query parameters; a
task with any non-scalar parameter is a ``POST`` whose JSON body is keyed by parameter
name (ADR-0007). No logic lives here (ADR-0001). The consumer mounts it; it is never
served standalone.
"""

from xippios.core.http import router_from_tasks

from xippios.comtrade import tasks
from xippios.comtrade._client import SOURCE

router = router_from_tasks(SOURCE, [getattr(tasks, name) for name in tasks.__all__])

__all__ = ["router"]
