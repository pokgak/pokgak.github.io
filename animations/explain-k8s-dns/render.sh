#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
OUTPUT="$REPO_ROOT/static/videos/explain-k8s-dns.mp4"
POSTER="$REPO_ROOT/static/images/explain-k8s-dns-poster.png"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

MANIMGX=(uvx --from manimgx==0.1.1 --python 3.14 manimgx)

"${MANIMGX[@]}" inspect \
  "$SCRIPT_DIR/scene.py" KubernetesDnsJourney \
  -o "$WORK_DIR/KubernetesDnsJourney.storyboard.png"

"${MANIMGX[@]}" render \
  "$SCRIPT_DIR/scene.py" KubernetesDnsJourney \
  --resolution 1280x720 \
  --fps 30 \
  --preset slow \
  --crf 21 \
  --output "$WORK_DIR/explain-k8s-dns.mp4"

ffmpeg -v error -y \
  -ss 10.0 \
  -i "$WORK_DIR/explain-k8s-dns.mp4" \
  -frames:v 1 \
  -compression_level 9 \
  "$WORK_DIR/explain-k8s-dns-poster.png"

mkdir -p "$(dirname -- "$OUTPUT")"
mkdir -p "$(dirname -- "$POSTER")"
cp "$WORK_DIR/explain-k8s-dns.mp4" "$OUTPUT"
cp "$WORK_DIR/explain-k8s-dns-poster.png" "$POSTER"
printf 'Wrote %s\nWrote %s\n' "$OUTPUT" "$POSTER"
