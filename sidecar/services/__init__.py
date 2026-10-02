"""
PhantomX Sidecar — Services
"""

from .bus import get_event_bus, EventBus, ProgressEvent, LogEvent, CompleteEvent

__all__ = ["get_event_bus", "EventBus", "ProgressEvent", "LogEvent", "CompleteEvent"]


def __getattr__(name: str):
    """
    Lazy submodule access for `from sidecar.services import supporter`.

    Every other submodule is imported directly by its callers, but `supporter`
    pulls in `cryptography`, so it stays out of package import time. Without
    this hook `instances._launch()` raised
    ``cannot import name 'supporter' from 'sidecar.services'``.
    """
    if name == "supporter":
        from importlib import import_module

        module = import_module(f"{__name__}.supporter")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
