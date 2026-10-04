"""Image viewer with zoom, rotate, pan, fit, and fullscreen controls."""

from __future__ import annotations

from novahost.core.models import RenderContext
from novahost.handlers.base import Handler
from novahost.ui.shell import esc, human_size, page


class ImageHandler(Handler):
    key = "image"
    label = "Image"

    def render(self, context: RenderContext) -> str:
        src = context.file_url(context.path)
        body = f"""
<section class="surface">
  <div class="toolbar">
    <span class="pill" data-image-dimensions>Loading dimensions</span><span class="pill">{human_size(context.size)}</span>
    <div class="actions" style="margin-left:auto">
      <button data-image-action="out" aria-label="Zoom out">−</button><button data-image-action="fit">Fit</button>
      <button data-image-action="actual">100%</button><button data-image-action="in" aria-label="Zoom in">+</button>
      <button data-image-action="rotate">Rotate</button><button data-image-action="reset">Reset</button>
      <button type="button" onclick="document.querySelector('.media-stage').requestFullscreen?.()">Fullscreen</button>
    </div>
  </div>
  <div class="media-stage" style="overflow:hidden"><img data-image-viewer src="{src}" alt="{esc(context.label)}" draggable="false"></div>
  <div class="media-meta">Drag to pan · + / − to zoom · R to rotate · 0 to reset</div>
</section>"""
        return page(context, context.label, "Image", body, subtitle="Inspect at your preferred scale. Original file remains unchanged.")
