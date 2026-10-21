"""Request-local authorization for serial workers and their native task contexts."""
from contextvars import ContextVar
import os

worker_authorization: ContextVar[dict[str, str] | None] = ContextVar("worker_authorization", default=None)
document_processing_authorization: ContextVar[str | None] = ContextVar("document_processing_authorization", default=None)


def relay_token(name: str) -> str | None:
    return worker_token(name)


def worker_token(name: str) -> str | None:
    context = worker_authorization.get()
    # An explicit request context must never inherit a previous/process credential.
    return context.get(name) if context is not None else os.environ.get(name)


def document_processing_token() -> str | None:
    return document_processing_authorization.get()
