"""Native browser audio/video players with NovaHost controls."""

from __future__ import annotations

from novahost.core.models import RenderContext
from novahost.handlers.base import Handler
from novahost.ui.shell import esc, human_size, page


class AudioHandler(Handler):
    key = "audio"
    label = "Audio"

    def render(self, context: RenderContext) -> str:
        src = context.file_url(context.path)
        body = f"""
<section class="surface" data-media>
  <div class="media-stage"><div class="player"><div class="brand-mark" style="margin:auto;width:60px;height:60px;font-size:28px">♫</div>
    <h2>{esc(context.label)}</h2><audio src="{src}" controls preload="metadata"></audio><p class="muted" data-video-metadata>Duration appears when the browser loads audio metadata.</p>
    <p class="notice error" data-media-error hidden>This browser cannot decode this audio format. Try downloading the original file.</p>
  </div></div>
  <div class="media-controls"><button type="button" data-loop>Loop off</button><label>Speed
    <select data-speed aria-label="Playback speed"><option>0.75</option><option selected>1</option><option>1.25</option><option>1.5</option><option>2</option></select>
  </label><a class="button" href="{src}" download>Download</a></div>
  <div class="media-meta">{human_size(context.size)} · Playback support depends on your browser and installed codecs.</div>
</section>"""
        return page(context, context.label, "Audio", body, subtitle="Local browser playback · no upload or remote service.")


class VideoHandler(Handler):
    key = "video"
    label = "Video"

    def render(self, context: RenderContext) -> str:
        src = context.file_url(context.path)
        body = f"""
<section class="surface" data-media>
  <div class="media-stage"><video src="{src}" controls playsinline preload="metadata"></video>
    <p class="notice error" data-media-error hidden>This browser could not decode this video. Codec support varies; the original remains available to download.</p>
  </div>
  <div class="media-controls"><button type="button" data-loop>Loop off</button><label>Speed
    <select data-speed aria-label="Playback speed"><option>0.5</option><option>0.75</option><option selected>1</option><option>1.25</option><option>1.5</option><option>2</option></select>
  </label><button type="button" data-theater>Theater mode</button><button type="button" data-fullscreen>Fullscreen</button>
    <button type="button" onclick="document.querySelector('video').requestPictureInPicture?.()">Picture in picture</button>
    <a class="button" href="{src}" download>Download</a></div>
  <div class="media-meta">{human_size(context.size)} · <span data-video-metadata>Dimensions and duration appear when metadata loads.</span> · Container support does not guarantee the embedded codec can play.</div>
</section>"""
        return page(context, context.label, "Video", body, subtitle="Local browser playback · unsupported codecs are reported, not converted.")
