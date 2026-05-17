#!/usr/bin/env bash
export KUBECONFIG=/tmp/widget-fg-kubeconfig.yaml
export RUN_TAG="fg-patch"
exec bash "$(dirname "$0")/stress-patch.sh" "$@"
