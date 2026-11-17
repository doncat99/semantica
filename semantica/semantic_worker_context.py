"""Request-local authorization for serial workers and their native task contexts."""
from contextvars import ContextVar
from threading import Event
from contextlib import contextmanager
from functools import wraps
from time import perf_counter
import os

worker_authorization: ContextVar[dict[str, str] | None] = ContextVar("worker_authorization", default=None)
document_processing_authorization: ContextVar[str | None] = ContextVar("document_processing_authorization", default=None)
query_cancellation: ContextVar[Event | None] = ContextVar("query_cancellation", default=None)


def check_query_cancellation() -> None:
    event = query_cancellation.get()
    if event is not None and event.is_set():
        from .utils.exceptions import ProcessingError
        raise ProcessingError('query canceled')


def relay_token(name: str) -> str | None:
    return worker_token(name)


def worker_token(name: str) -> str | None:
    context = worker_authorization.get()
    # An explicit request context must never inherit a previous/process credential.
    return context.get(name) if context is not None else os.environ.get(name)


def document_processing_token() -> str | None:
    return document_processing_authorization.get()


query_diagnostics: ContextVar[dict | None] = ContextVar('query_diagnostics', default=None)


@contextmanager
def query_phase(name):
    started = perf_counter()
    try:
        yield
    finally:
        metrics = query_diagnostics.get()
        if metrics is not None:
            key = name + 'Ms'
            metrics[key] = round(metrics.get(key, 0) + (perf_counter() - started) * 1000, 3)


def measured_query_phase(name):
    def decorate(method):
        @wraps(method)
        def call(*args, **kwargs):
            with query_phase(name):
                return method(*args, **kwargs)
        return call
    return decorate


def count_query_work(name, count=1):
    metrics = query_diagnostics.get()
    if metrics is not None:
        metrics[name] = metrics.get(name, 0) + count
