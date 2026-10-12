# OpenTelemetry Slack integration animation

This scene was authored for ManimGX 0.1.1. It is silent and sets its output to
1280×720 at 30 fps in the source as well as in the render command.

From the repository root:

```sh
uvx --from manimgx==0.1.1 manimgx inspect \
  animations/otel-slack-integration/scene.py OtelSlackIntegration

uvx --from manimgx==0.1.1 manimgx render \
  animations/otel-slack-integration/scene.py OtelSlackIntegration \
  -r 1280x720 --fps 30 \
  --crf 18 \
  -o animations/otel-slack-integration/OtelSlackIntegration.manimgx.mp4

ffmpeg -y \
  -i animations/otel-slack-integration/OtelSlackIntegration.manimgx.mp4 \
  -vf "fps=30,tpad=stop_mode=clone:stop_duration=1.8" \
  -an -c:v libx264 -preset slow -crf 10 -pix_fmt yuv420p \
  -movflags +faststart static/videos/otel-slack-integration.mp4

ffmpeg -loglevel error -ss 13.08 \
  -i static/videos/otel-slack-integration.mp4 \
  -frames:v 1 -f image2pipe -vcodec png - \
  | magick png:- -strip -colors 256 \
      -define png:compression-level=9 -define png:compression-filter=5 \
      static/images/otel-slack-integration-poster.png
```

The final ffmpeg pass preserves the ManimGX render at a constant 30 fps, retains the
scene's 1.8-second final hold, strips any audio stream, and moves MP4 metadata to the
front for web playback. The poster captures the completed lifecycle with the span
ended and removed from the store. Generated MP4s and inspection storyboards in this
directory are build artifacts; only `scene.py`, this README, the site video, and its
poster are intended for version control.
