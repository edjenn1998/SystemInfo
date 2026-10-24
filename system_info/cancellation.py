"""Cooperative cancellation shared by collectors and their command/file helpers."""
from contextlib import contextmanager
from contextvars import ContextVar

CURRENT_CANCEL = ContextVar('system_info_cancel', default=None)


class Cancelled(Exception):
    pass


def checkpoint(cancel=None):
    token = CURRENT_CANCEL.get() if cancel is None else cancel
    if token is not None and token.is_set():
        raise Cancelled('Collection cancelled; the previous report remains available.')


@contextmanager
def collection_scope(cancel):
    token = CURRENT_CANCEL.set(cancel)
    try:
        checkpoint()
        yield
    finally:
        CURRENT_CANCEL.reset(token)
