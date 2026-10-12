# ALB ingress-controller animation

This scene is rendered with ManimGX 0.1.1 at 1280×720 and 30 fps. It has no
audio track.

```bash
uv tool install --python 3.14 'manimgx==0.1.1'
manimgx inspect animations/exploring-alb-ingress-controller/scene.py
manimgx render animations/exploring-alb-ingress-controller/scene.py \
  -r 1280x720 --fps 30 --preset slow --crf 18 \
  -o "$(pwd)/static/videos/exploring-alb-ingress-controller.mp4"
ffmpeg -y -v error -ss 14.23 \
  -i static/videos/exploring-alb-ingress-controller.mp4 -frames:v 1 \
  -vf "scale=1152:648:flags=lanczos,pad=1280:720:64:0:color=0x08111F" \
  -compression_level 9 -pred mixed \
  static/images/exploring-alb-ingress-controller-poster.png
```

ManimGX resolves relative output paths beside the scene, so the command derives
an absolute output path from the repository root. The command-line resolution
and frame rate intentionally repeat the values in `scene.py`, making the
checked-in render settings explicit and reproducible. The poster is the stable,
fully composed direct-routing frame immediately before the trade-off cards. It
is inset on the scene background so native controls do not obscure its labels.
