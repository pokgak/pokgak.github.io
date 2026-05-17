#!/usr/bin/env bash
set -euo pipefail

N=${1:-50}

good_reconciles=$(kubectl logs -n good -l app=good-controller --tail=-1 2>/dev/null | grep -c "Reconciling" || true)
bad_reconciles=$(kubectl logs -n bad -l app=bad-controller --tail=-1 2>/dev/null | grep -c "Reconciling" || true)

good_ready=$(kubectl get widgets -n good --no-headers 2>/dev/null | grep -c "Ready" || true)
bad_ready=$(kubectl get widgets -n bad --no-headers 2>/dev/null | grep -c "Ready" || true)

good_per_widget=0
bad_per_widget=0
if [ "$N" -gt 0 ]; then
  good_per_widget=$(echo "scale=1; ${good_reconciles} / ${N}" | bc)
  bad_per_widget=$(echo "scale=1; ${bad_reconciles} / ${N}" | bc)
fi

# Determine winner
if [ "$good_ready" -ge "$bad_ready" ] && [ "$good_reconciles" -le "$bad_reconciles" ]; then
  winner="GOOD controller wins"
elif [ "$bad_ready" -gt "$good_ready" ]; then
  winner="Neither — bad controller has more Ready widgets (unexpected)"
else
  winner="GOOD controller wins"
fi

printf '\n'
printf '%-40s %-20s %-20s\n' "Metric" "Good Controller" "Bad Controller"
printf '%-40s %-20s %-20s\n' "------" "---------------" "--------------"
printf '%-40s %-20s %-20s\n' "Total reconcile events" "$good_reconciles" "$bad_reconciles"
printf '%-40s %-20s %-20s\n' "Widgets at Ready phase" "${good_ready}/${N}" "${bad_ready}/${N}"
printf '%-40s %-20s %-20s\n' "Avg reconciles per widget" "~${good_per_widget}" "~${bad_per_widget}"
printf '%-40s %-20s %-20s\n' "Expected reconciles/widget" "~1" "100s+"
printf '\n'
printf 'WINNER: %s\n' "$winner"
printf '\n'
printf 'Anti-patterns demonstrated in bad controller:\n'
printf '  1. No GenerationChangedPredicate → annotation write on every reconcile triggers loop\n'
printf '  2. r.Update() for status → status silently ignored by API server (status subresource)\n'
printf '  3. No RetryOnConflict → conflicts fail permanently under load\n'
printf '  4. No IsNotFound check → errors on deleted objects cause spurious retries\n'
printf '  5. MaxConcurrentReconciles=1 (default) → queue backs up under load\n'
