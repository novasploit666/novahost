"""Files intended to open directly in the browser's native viewer."""

from novahost.core.models import RenderContext
from novahost.handlers.base import Handler
from novahost.ui.shell import page


class NativeHandler(Handler):
    key = "native"
    label = "Browser-native"
    native = True

    def render(self, context: RenderContext) -> str:
        body = f'<section class="surface surface-pad"><p>This file is served directly to the browser. <a class="button" href="{context.raw_url(context.path)}">Open native view</a></p></section>'
        return page(context, context.label, "Browser-native file", body, subtitle="NovaHost does not convert or execute this file.")
