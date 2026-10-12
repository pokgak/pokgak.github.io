# Tailscale Kubernetes request flow

This silent ManimGX animation shows how a remote Tailscale client reaches a
Kubernetes Pod through DNS resolution, an advertised cluster CIDR, a subnet
router, and a ClusterIP Service. The separate dashed control-plane lane makes
clear that external-dns creates the DNS record but does not receive request
traffic.

## Reproduce the asset

Install [uv](https://docs.astral.sh/uv/), then run:

```sh
./render.sh
```

The locked environment uses ManimGX 0.1.1. The script runs `manimgx inspect`,
renders at 1280×720, and uses FFmpeg to produce a constant-30-fps H.264 MP4 at
the target web bitrate with no audio. It also extracts the stable result frame
at 18.2 seconds and uses ImageMagick to produce an optimized 256-color poster.
It writes the final assets to `static/videos/k8s-cluster-access-tailscale.mp4`
and `static/images/k8s-cluster-access-tailscale-poster.png`.
