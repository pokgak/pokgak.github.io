#!/usr/bin/env bash
set -euo pipefail

N=${1:-1000}
OBSERVE_SECS=${2:-180}
BATCH=50           # widgets per kubectl apply call
PARALLEL_BATCH=20  # concurrent apply batches per namespace
TIMESTAMP=$(date +%Y%m%dT%H%M%S)
METRICS_DIR="metrics/${TIMESTAMP}-${RUN_TAG:-good}-N${N}"

VARIANTS=(${VARIANTS_OVERRIDE:-"good:19090" "good-single:19091" "good-patch:19092" "good-single-patch:19093"})
NAMESPACES=(${NAMESPACES_OVERRIDE:-good good-single good-patch good-single-patch})

SCRAPER="$(dirname "$0")/bin/scraper"
if [ ! -x "$SCRAPER" ]; then echo "error: run 'make build-scraper'" >&2; exit 1; fi

mkdir -p "$METRICS_DIR"
echo "=== Good-only Benchmark (N=$N, ${OBSERVE_SECS}s, batch=${BATCH}) ==="
echo "Metrics dir: $METRICS_DIR"

# scale bad controllers to 0 so they don't add API server noise
echo "Pausing bad controllers..."
kubectl scale deployment bad-fixed-status-controller -n bad-fixed-status --replicas=0 >/dev/null 2>&1 || true
kubectl scale deployment bad-fixed-single-controller -n bad-fixed-single --replicas=0 >/dev/null 2>&1 || true

echo "Restarting good controllers..."
for ns in "${NAMESPACES[@]}"; do kubectl rollout restart deployment/${ns}-controller -n $ns >/dev/null 2>&1; done
for ns in "${NAMESPACES[@]}"; do kubectl rollout status deployment/${ns}-controller -n $ns --timeout=40s >/dev/null 2>&1; done

echo "Clearing old widgets..."
for ns in "${NAMESPACES[@]}"; do kubectl delete widgets --all -n $ns --ignore-not-found --timeout=30s >/dev/null 2>&1 || true; done
sleep 2

echo "Setting up port-forwards..."
PFWD_PIDS=()
for entry in "${VARIANTS[@]}"; do
  variant="${entry%%:*}"; port="${entry##*:}"
  kubectl port-forward -n $variant deployment/${variant}-controller ${port}:9090 >/dev/null 2>&1 &
  PFWD_PIDS+=($!)
done

echo "Waiting for metrics endpoints..."
for entry in "${VARIANTS[@]}"; do
  port="${entry##*:}"
  for i in $(seq 1 15); do
    curl -sf --max-time 1 "http://localhost:${port}/metrics" >/dev/null 2>&1 && break || sleep 1
  done
done
echo "  ✓ endpoints ready"

echo "Starting scrapers..."
SCRAPER_PIDS=()
for entry in "${VARIANTS[@]}"; do
  variant="${entry%%:*}"; port="${entry##*:}"
  csv="$METRICS_DIR/metrics-${variant}.csv"
  "$SCRAPER" --url "http://localhost:${port}/metrics" --output "$csv" \
    --controller "$variant" --interval 1s 2>"$METRICS_DIR/scraper-${variant}.log" &
  SCRAPER_PIDS+=($!)
  echo "  ✓ scraper '$variant' → $csv"
done
sleep 1

cleanup() {
  echo ""; echo "Stopping scrapers and port-forwards..."
  for pid in "${SCRAPER_PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  for pid in "${PFWD_PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  # resume bad controllers
  kubectl scale deployment bad-fixed-status-controller -n bad-fixed-status --replicas=1 >/dev/null 2>&1 || true
  kubectl scale deployment bad-fixed-single-controller -n bad-fixed-single --replicas=1 >/dev/null 2>&1 || true
}
trap cleanup EXIT

# batch widget creation: write BATCH-sized YAML files, apply in parallel
create_widgets_batched() {
  local ns=$1
  local total=$2
  local tmpdir; tmpdir=$(mktemp -d)
  local pids=()

  for start in $(seq 1 $BATCH $total); do
    local end=$(( start + BATCH - 1 ))
    [ $end -gt $total ] && end=$total
    local batchfile="$tmpdir/batch-${start}.yaml"
    # write batch YAML
    for i in $(seq $start $end); do
      cat >> "$batchfile" << YAML
apiVersion: benchmark.example.com/v1alpha1
kind: Widget
metadata:
  name: widget-$(printf '%06d' $i)
  namespace: $ns
spec:
  count: $i
  message: "good-only benchmark $i"
---
YAML
    done
    kubectl apply -f "$batchfile" >/dev/null 2>&1 &
    pids+=($!)

    # throttle: wait when PARALLEL_BATCH batches are in flight
    if [ ${#pids[@]} -ge $PARALLEL_BATCH ]; then
      for pid in "${pids[@]}"; do wait "$pid" 2>/dev/null || true; done
      pids=()
    fi
  done
  # wait for remaining batches
  for pid in "${pids[@]}"; do wait "$pid" 2>/dev/null || true; done
  rm -rf "$tmpdir"
}

echo ""; echo "Creating $N widgets in both namespaces in parallel (batch=$BATCH, parallel=$PARALLEL_BATCH)..."
WIDGET_PIDS=()
for ns in "${NAMESPACES[@]}"; do
  (create_widgets_batched "$ns" "$N") &
  WIDGET_PIDS+=($!)
done
for pid in "${WIDGET_PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done
echo "  ✓ $N widgets created in good + good-single"

echo ""
printf '%-8s | %-28s | %-28s\n' "TIME" "good (5w + pred)" "good-single (1w + pred)"
printf '%s\n' "$(printf '%.0s-' {1..70})"

START=$(date +%s)
while true; do
  ELAPSED=$(( $(date +%s) - START ))
  [ "$ELAPSED" -ge "$OBSERVE_SECS" ] && break
  g5_r=$(kubectl get widgets -n good --no-headers 2>/dev/null | grep -c "Ready" || true)
  g1_r=$(kubectl get widgets -n good-single --no-headers 2>/dev/null | grep -c "Ready" || true)
  gp5_r=$(kubectl get widgets -n good-patch --no-headers 2>/dev/null | grep -c "Ready" || true)
  gp1_r=$(kubectl get widgets -n good-single-patch --no-headers 2>/dev/null | grep -c "Ready" || true)
  g5_q=$(tail -1 "$METRICS_DIR/metrics-good.csv" 2>/dev/null | cut -d',' -f3 || echo "?")
  g1_q=$(tail -1 "$METRICS_DIR/metrics-good-single.csv" 2>/dev/null | cut -d',' -f3 || echo "?")
  gp5_q=$(tail -1 "$METRICS_DIR/metrics-good-patch.csv" 2>/dev/null | cut -d',' -f3 || echo "?")
  gp1_q=$(tail -1 "$METRICS_DIR/metrics-good-single-patch.csv" 2>/dev/null | cut -d',' -f3 || echo "?")
  printf '%-8s | %-10s q=%-8s | %-10s q=%-8s | %-10s q=%-8s | %-10s q=%-8s\n' \
    "${ELAPSED}s" "${g5_r}/${N}" "$g5_q" "${g1_r}/${N}" "$g1_q" \
    "${gp5_r}/${N}" "$gp5_q" "${gp1_r}/${N}" "$gp1_q"
  sleep 10
done

echo ""; echo "=== Final Results (N=$N) ==="
printf "\n%-22s %-10s %-10s %-8s %-8s %-8s\n" "controller" "success" "avg_lat" "retries" "errors" "q_depth"
printf "%-22s %-10s %-10s %-8s %-8s %-8s\n" "----------" "-------" "-------" "-------" "------" "-------"
for f in "$METRICS_DIR"/metrics-*.csv; do
  ctrl=$(basename $f .csv | sed 's/metrics-//')
  rows=$(( $(wc -l < "$f") - 1 ))
  last=$(tail -1 "$f")
  q=$(echo "$last" | cut -d',' -f3)
  adds=$(echo "$last" | cut -d',' -f4)
  retries=$(echo "$last" | cut -d',' -f5)
  success=$(echo "$last" | cut -d',' -f6)
  errors=$(echo "$last" | cut -d',' -f7)
  lat_sum=$(echo "$last" | cut -d',' -f11)
  lat_cnt=$(echo "$last" | cut -d',' -f12)
  avg_lat=$(python3 -c "c=float('$lat_cnt'); print(f'{float(\"$lat_sum\")/c*1000:.1f}' if c>0 else '0')" 2>/dev/null)ms
  printf "  %-20s %-10s %-10s %-8s %-8s %-8s\n" \
    "$ctrl" "$success" "$avg_lat" "$retries" "$errors" "$q"
done

echo ""
echo "=== CSV files ==="
ls -lh "$METRICS_DIR"/metrics-*.csv
echo ""
echo "Analyze: duckdb"
echo "  D CREATE VIEW m AS SELECT * FROM read_csv_auto(['${METRICS_DIR}/metrics-good.csv','${METRICS_DIR}/metrics-good-single.csv']);"
