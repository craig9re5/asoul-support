"""Bind compatibility functions to their API dependency without copying logic."""

from functools import wraps
from inspect import signature


def bind(function, gateway):

    @wraps(function)
    def call(*args, **kwargs):
        return function(*args, _gateway=gateway, **kwargs)

    original = signature(function)
    call.__signature__ = original.replace(
        parameters=[p for p in original.parameters.values() if p.name != "_gateway"]
    )
    return call
