"""Reuse nested verified reads only within one synchronous runtime observation."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from functools import wraps
from typing import Any, TypeVar, cast

F = TypeVar("F", bound=Callable[..., Any])


def authority_read(function: F) -> F:
    @wraps(function)
    def read(self: Any, *args: Any, **kwargs: Any) -> Any:
        outer = getattr(self, "_authority_reads", None) is None
        if outer:
            self._authority_reads = {}
        try:
            return function(self, *args, **kwargs)
        finally:
            if outer:
                # Never retain an authority snapshot across tool calls or model awaits.
                self._authority_reads = None

    return cast(F, read)


def verified_read(function: F) -> F:
    @wraps(function)
    def read(self: Any, *args: Any, **kwargs: Any) -> Any:
        cache = getattr(self, "_authority_reads", None)
        if cache is None:
            return function(self, *args, **kwargs)
        revision = self.store.db.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0]
        if cache.get("revision") != revision:
            cache.clear()
            cache["revision"] = revision
        key = (function.__name__, repr(args), repr(kwargs))
        if key not in cache:
            result = function(self, *args, **kwargs)
            current = self.store.db.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0]
            if current != revision:
                cache.clear()
                cache["revision"] = current
            cache[key] = deepcopy(result)
        return deepcopy(cache[key])

    return cast(F, read)
