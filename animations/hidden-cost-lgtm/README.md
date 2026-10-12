# Hidden cost of LGTM animation

The scene uses ManimGX 0.1.1 and contains no audio. From this directory:

```sh
uvx --python 3.14 --from manimgx==0.1.1 manimgx inspect scene.py HiddenCostLGTM
uvx --python 3.14 --from manimgx==0.1.1 manimgx render scene.py HiddenCostLGTM \
  -o ../../static/videos/hidden-cost-lgtm.mp4 \
  -r 1280x720 --fps 30 --preset slow --crf 18
ffmpeg -y -i ../../static/videos/hidden-cost-lgtm.mp4 -ss 16.0 \
  -frames:v 1 -c:v png -compression_level 9 \
  ../../static/images/hidden-cost-lgtm-poster.png
magick ../../static/images/hidden-cost-lgtm-poster.png -strip -colors 256 \
  -define png:compression-level=9 PNG8:../../static/images/hidden-cost-lgtm-poster.optimized.png
mv ../../static/images/hidden-cost-lgtm-poster{.optimized,}.png
```

The animation follows one illustrative telemetry batch twice: first with default
routing, then with availability-zone affinity and topology-aware service routing.
It does not present the example transfer count as a universal multiplier.
