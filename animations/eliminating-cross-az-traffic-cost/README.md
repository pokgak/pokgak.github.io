# Cross-AZ traffic optimization animation

The scene is rendered with ManimGX 0.1.1 at 1280×720 and 30 fps. It is silent;
all meaning is carried by visible labels, path geometry, and the article's text
alternative.

```bash
uv tool install --python 3.14 'manimgx==0.1.1'

manimgx inspect animations/eliminating-cross-az-traffic-cost/scene.py CrossAzOptimization

manimgx render animations/eliminating-cross-az-traffic-cost/scene.py CrossAzOptimization \
  --resolution 1280x720 --fps 30 --preset slow --crf 11 \
  --output static/videos/eliminating-cross-az-traffic-cost.mp4

ffmpeg -y -ss 14.80 \
  -i static/videos/eliminating-cross-az-traffic-cost.mp4 -frames:v 1 \
  /tmp/eliminating-cross-az-traffic-cost-poster.png
magick /tmp/eliminating-cross-az-traffic-cost-poster.png -strip -colors 256 \
  PNG8:static/images/eliminating-cross-az-traffic-cost-poster.png
```

The exact dependency version is also pinned in `requirements.txt`.
