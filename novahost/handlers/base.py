"""Handler interface and small HTML escaping helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from novahost.core.models import RenderContext


class Handler(ABC):
    """A viewer for one or more file categories."""

    key = "base"
    label = "File"
    native = False

    @abstractmethod
    def render(self, context: RenderContext) -> str:
        """Return a complete HTML document for the given target."""
