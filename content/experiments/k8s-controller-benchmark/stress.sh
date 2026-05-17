#!/usr/bin/env bash
set -euo pipefail
export KUBECONFIG=/tmp/widget-baseline-kubeconfig.yaml

N=${1:-50}
OBSERVE_SECS=${2:-60}
TIMESTAMP=$(date +%Y%m%dT%H%M%S)
METRICS_DIR="metrics/${TIMESTAMP}-N${N}"

VARIANTS=("good:19090" "good-single:19091" "bad-fixed-status:19092" "bad-fixed-single:19093")
NAMESPACES=(good good-single bad-fixed-status bad-fixed-single)

SCRAPER="$(dirname "$0")/bin/scraper"
if [ ! -x "$SCRAPER" ]; then echo "error: run 'make build-scraper'" >&2; exit 1; fi

mkdir -p "$METRICS_DIR"
echo "=== Widget Controller Benchmark (N=$N, ${OBSERVE_SECS}s) ==="
echo "Metrics dir: $METRICS_DIR"

echo "Restarting controllers..."
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

# wait until all four endpoints respond before starting scrapers
echo "Waiting for metrics endpoints..."
for entry in "${VARIANTS[@]}"; do
  port="${entry##*:}"
  for i in $(seq 1 15); do
    curl -sf --max-time 1 "http://localhost:${port}/metrics" >/dev/null 2>&1 && break
    sleep 1
  done
done
echo "  ✓ all endpoints ready"

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
sleep 1  # let scrapers write the first row (t=0 baseline)

cleanup() {
  echo ""; echo "Stopping scrapers and port-forwards..."
  for pid in "${SCRAPER_PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  for pid in "${PFWD_PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT

# create widgets in ALL namespaces in parallel
echo ""; echo "Creating $N widgets in all namespaces in parallel..."
WIDGET_PIDS=()
for ns in "${NAMESPACES[@]}"; do
  (for i in $(seq 1 "$N"); do
    kubectl apply -f - >/dev/null 2>&1 <<YAML
apiVersion: benchmark.example.com/v1alpha1
kind: Widget
metadata:
  name: widget-$(printf '%04d' $i)
  namespace: $ns
spec:
  count: $i
  message: "benchmark run $i"
YAML
  done
  wait) &   # wait inside the subshell, then exit cleanly
  WIDGET_PIDS+=($!)
done
# wait only for widget-creation subshells, NOT port-forwards or scrapers
for pid in "${WIDGET_PIDS[@]}"; do wait "$pid" 2>/dev/null || true; done
echo "  ✓ $N widgets created in all namespaces"

echo ""
printf '%-6s | %-22s | %-22s | %-22s | %-22s\n' \
  "TIME" "good(5w+pred)" "good-single(1w+pred)" "bad-fix(5w-pred)" "bad-fix-single(1w-pred)"
printf '%s\n' "$(printf '%.0s-' {1..104})"

START=$(date +%s)
while true; do
  ELAPSED=$(( $(date +%s) - START ))
  [ "$ELAPSED" -ge "$OBSERVE_SECS" ] && break
  g5_r=$(kubectl get widgets -n good --no-headers 2>/dev/null | grep -c "Ready" || true)
  g1_r=$(kubectl get widgets -n good-single --no-headers 2>/dev/null | grep -c "Ready" || true)
  b5_r=$(kubectl get widgets -n bad-fixed-status --no-headers 2>/dev/null | grep -c "Ready" || true)
  b1_r=$(kubectl get widgets -n bad-fixed-single --no-headers 2>/dev/null | grep -c "Ready" || true)
  g5_rec=$(kubectl logs -n good -l app=good-controller --tail=-1 2>/dev/null | grep -c '"Reconciling"' || true)
  g1_rec=$(kubectl logs -n good-single -l app=good-single-controller --tail=-1 2>/dev/null | grep -c '"Reconciling"' || true)
  b5_rec=$(kubectl logs -n bad-fixed-status -l app=bad-fixed-status-controller --tail=-1 2>/dev/null | grep -c '"Reconciling"' || true)
  b1_rec=$(kubectl logs -n bad-fixed-single -l app=bad-fixed-single-controller --tail=-1 2>/dev/null | grep -c '"Reconciling"' || true)
  printf '%-6s | %-10s rec=%-8s | %-10s rec=%-8s | %-10s rec=%-8s | %-10s rec=%-8s\n' \
    "${ELAPSED}s" "${g5_r}/${N}" "$g5_rec" "${g1_r}/${N}" "$g1_rec" \
    "${b5_r}/${N}" "$b5_rec" "${b1_r}/${N}" "$b1_rec"
  sleep 5
done

echo ""; echo "=== Final log summary ==="
printf '\n%-30s %-18s %-18s %-18s %-18s\n' "Metric" "good(5w)" "good-1w" "bad-fix(5w)" "bad-fix-1w"
printf '%-30s %-18s %-18s %-18s %-18s\n' "------" "--------" "-------" "-----------" "----------"

log_stats() {
  local ns=$1 app=$2
  local logs; logs=$(kubectl logs -n "$ns" -l "app=${app}" --tail=-1 2>/dev/null)
  printf '%s %s %s %s\n' \
    "$(echo "$logs" | grep -c '"Reconciling"' || true)" \
    "$(echo "$logs" | grep -c 'conflict\|object has been modified' || true)" \
    "$(echo "$logs" | grep -c '"level":"error"' || true)" \
    "$(echo "$logs" | grep -c 'generation unchanged\|skipping\|GenerationChanged' || true)"
}

IFS=' ' read -r g5_rec g5_conf g5_err g5_skip <<< "$(log_stats good good-controller)"
IFS=' ' read -r g1_rec g1_conf g1_err g1_skip <<< "$(log_stats good-single good-single-controller)"
IFS=' ' read -r b5_rec b5_conf b5_err b5_skip <<< "$(log_stats bad-fixed-status bad-fixed-status-controller)"
IFS=' ' read -r b1_rec b1_conf b1_err b1_skip <<< "$(log_stats bad-fixed-single bad-fixed-single-controller)"

g5_r=$(kubectl get widgets -n good --no-headers 2>/dev/null | grep -c "Ready" || true)
g1_r=$(kubectl get widgets -n good-single --no-headers 2>/dev/null | grep -c "Ready" || true)
b5_r=$(kubectl get widgets -n bad-fixed-status --no-headers 2>/dev/null | grep -c "Ready" || true)
b1_r=$(kubectl get widgets -n bad-fixed-single --no-headers 2>/dev/null | grep -c "Ready" || true)

printf '%-30s %-18s %-18s %-18s %-18s\n' "Ready widgets"    "${g5_r}/${N}" "${g1_r}/${N}" "${b5_r}/${N}" "${b1_r}/${N}"
printf '%-30s %-18s %-18s %-18s %-18s\n' "Total reconciles" "$g5_rec" "$g1_rec" "$b5_rec" "$b1_rec"
printf '%-30s %-18s %-18s %-18s %-18s\n' "Conflict errors"  "$g5_conf" "$g1_conf" "$b5_conf" "$b1_conf"
printf '%-30s %-18s %-18s %-18s %-18s\n' "Error-level logs" "$g5_err" "$g1_err" "$b5_err" "$b1_err"
printf '%-30s %-18s %-18s %-18s %-18s\n' "Predicate skips"  "$g5_skip" "$g1_skip" "$b5_skip" "$b1_skip"

echo ""
echo "=== CSV row counts ==="
for f in "$METRICS_DIR"/metrics-*.csv; do
  rows=$(( $(wc -l < "$f") - 1 ))
  printf '  %-40s %d rows\n' "$(basename $f)" "$rows"
done
echo ""
echo "Analyze: duckdb"
echo "  D CREATE VIEW m AS SELECT * FROM read_csv_auto(['${METRICS_DIR}/metrics-*.csv']);"
echo "  D .read queries.sql"
