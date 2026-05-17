#!/usr/bin/env bash
# Feature-gate cluster run: good (5w+Update) vs good-single (1w+Update) only.
# Compares baseline patterns against the feature-gate Kind cluster to isolate
# the effect of ConcurrentWatchObjectDecode and WatchListClient.
export KUBECONFIG=/tmp/widget-fg-kubeconfig.yaml
export RUN_TAG="fg-good"
# override to only 2 variants (skip patch controllers)
export VARIANTS_OVERRIDE="good:19090 good-single:19091"
export NAMESPACES_OVERRIDE="good good-single"
exec bash "$(dirname "$0")/stress-good.sh" "$@"
