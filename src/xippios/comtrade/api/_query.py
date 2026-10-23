"""Query strings in upstream's spelling, shared by the endpoint wrappers."""

from collections.abc import Mapping

__all__ = ["upstream_query"]


def upstream_query(names: Mapping[str, str], **params: str | bool | int | None) -> dict[str, str]:
    """Upstream spellings for the snake_case arguments that are set, in ``names`` order.

    Args:
        names: The wrapper's argument to upstream's spelling, e.g.
            ``{"reporter_code": "reporterCode"}``.
        **params: The arguments; ``None`` leaves a parameter out, booleans go as
            ``true``/``false``.
    """
    return {
        upstream: str(value).lower() if isinstance(value, bool) else str(value)
        for name, upstream in names.items()
        if (value := params.get(name)) is not None
    }
