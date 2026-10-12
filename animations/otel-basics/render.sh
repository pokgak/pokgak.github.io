#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCENE="$ROOT/animations/otel-basics/scene.py"
OUTPUT="$ROOT/static/videos/otel-basics.mp4"
POSTER="$ROOT/static/images/otel-basics-poster.png"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

MANIMGX=(uvx --python 3.14 --from manimgx==0.1.1 manimgx)

"${MANIMGX[@]}" inspect "$SCENE" OtelTraceWaterfall \
  -o "$WORK/otel-basics-inspect.png"

"${MANIMGX[@]}" render "$SCENE" OtelTraceWaterfall \
  -r 1280x720 \
  --fps 30 \
  --preset ultrafast \
  --crf 1 \
  -o "$WORK/otel-basics.mp4"

ffmpeg -hide_banner -loglevel error -y \
  -ss 10.09 \
  -i "$WORK/otel-basics.mp4" \
  -frames:v 1 \
  -compression_level 9 \
  "$WORK/otel-basics-poster.png"

mkdir -p "$(dirname "$OUTPUT")"
mkdir -p "$(dirname "$POSTER")"
install -m 0644 "$WORK/otel-basics.mp4" "$OUTPUT"
install -m 0644 "$WORK/otel-basics-poster.png" "$POSTER"

printf 'Wrote %s (%s bytes)\n' "$OUTPUT" "$(stat -c %s "$OUTPUT")"
printf 'Wrote %s (%s bytes)\n' "$POSTER" "$(stat -c %s "$POSTER")"
