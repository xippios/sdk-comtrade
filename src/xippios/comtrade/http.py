"""FastAPI router for UN Comtrade.

``GET /comtrade/<task>`` for every task. No logic lives here (ADR-0001). The
consumer mounts it; it is never served standalone.
"""

from xippios.core.http import router_from_tasks

from xippios.comtrade import tasks
from xippios.comtrade._client import SOURCE

router = router_from_tasks(SOURCE, [getattr(tasks, name) for name in tasks.__all__])

__all__ = ["router"]
