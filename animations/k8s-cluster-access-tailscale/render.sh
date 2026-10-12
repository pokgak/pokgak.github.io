#!/usr/bin/env bash
set -euo pipefail

animation_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
output="${animation_dir}/../../static/videos/k8s-cluster-access-tailscale.mp4"
poster_output="${animation_dir}/../../static/images/k8s-cluster-access-tailscale-poster.png"
raw_output="/tmp/k8s-cluster-access-tailscale-raw.mp4"
poster_source="/tmp/k8s-cluster-access-tailscale-poster-source.png"

cleanup() {
  rm -f "${raw_output}" "${raw_output%.mp4}".storyboard*.png "${poster_source}"
}
trap cleanup EXIT

mkdir -p "$(dirname -- "${output}")"
mkdir -p "$(dirname -- "${poster_output}")"
cd "${animation_dir}"
uv run --frozen --python 3.14 manimgx inspect scene.py KubernetesAccessFlow \
  -o /tmp/k8s-cluster-access-tailscale-storyboard.png
uv run --frozen --python 3.14 manimgx render scene.py KubernetesAccessFlow \
  -r 1280x720 \
  --fps 30 \
  --preset slow \
  --crf 18 \
  -o "${raw_output}"
ffmpeg -y -loglevel error \
  -i "${raw_output}" \
  -an \
  -c:v libx264 \
  -preset slow \
  -b:v 600k \
  -pix_fmt yuv420p \
  -r 30 \
  -fps_mode cfr \
  -movflags +faststart \
  "${output}"
ffmpeg -y -loglevel error \
  -ss 18.2 \
  -i "${output}" \
  -frames:v 1 \
  "${poster_source}"
magick "${poster_source}" \
  -strip \
  -colors 256 \
  -define png:compression-level=9 \
  "PNG8:${poster_output}"
