# OpenTelemetry trace waterfall animation

The scene uses ManimGX 0.1.1 to render a silent 1280×720, 30 fps MP4. It shows
one request entering `entryPoint`, nested and sibling spans opening and closing,
and the resulting trace waterfall.

From the repository root, render and inspect it with:

```sh
bash animations/otel-basics/render.sh
```

The script uses `uvx` with an exact ManimGX version, runs layout inspection at
representative states, writes `static/videos/otel-basics.mp4`, and extracts the
fully rendered final frame to `static/images/otel-basics-poster.png`.
