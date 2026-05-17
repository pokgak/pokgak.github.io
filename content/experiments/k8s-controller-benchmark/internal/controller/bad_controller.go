package controller

// BadReconciler intentionally demonstrates anti-patterns for benchmark comparison.
// Anti-patterns present:
//  1. No GenerationChangedPredicate → status updates trigger infinite reconcile loops
//  2. r.Update() for status → with status subresource enabled, status is silently ignored
//  3. No RetryOnConflict → conflicts fail permanently under load
//  4. IsNotFound not handled → returns error on deleted objects, causing spurious retries
//  5. MaxConcurrentReconciles not set → defaults to 1, queue backs up under load
//  6. Annotation mutation on every reconcile → combined with no predicate, guarantees
//     an infinite update loop even when the API server strips the status field

import (
	"context"
	"fmt"
	"time"

	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"

	benchmarkv1alpha1 "github.com/pokgak/agent-skills/experiments/k8s-controller-benchmark/api/v1alpha1"
)

type BadReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

func (r *BadReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := ctrl.LoggerFrom(ctx)
	logger.Info("Reconciling")

	widget := &benchmarkv1alpha1.Widget{}
	// Anti-pattern 4: no IsNotFound check — returns error on deleted objects
	if err := r.Get(ctx, req.NamespacedName, widget); err != nil {
		return ctrl.Result{}, err
	}

	// Simulate work
	time.Sleep(10 * time.Millisecond)

	// Anti-pattern 6: mutate an annotation every reconcile — guarantees update loop
	if widget.Annotations == nil {
		widget.Annotations = make(map[string]string)
	}
	widget.Annotations["bad-controller/last-seen"] = fmt.Sprintf("%d", time.Now().UnixNano())

	// Anti-pattern 2: r.Update() instead of r.Status().Update()
	// With status subresource enabled, the API server silently ignores the status field.
	// Anti-pattern 3: no RetryOnConflict — conflicts fail permanently under load.
	widget.Status.Phase = "Ready"
	widget.Status.ProcessedCount = widget.Spec.Count
	// Anti-pattern 1 (compounded by 6): no GenerationChangedPredicate + annotation write
	// causes every reconcile to produce a new resource version, which triggers another reconcile.
	if err := r.Update(ctx, widget); err != nil {
		return ctrl.Result{}, err
	}

	return ctrl.Result{}, nil
}

func (r *BadReconciler) SetupWithManager(mgr ctrl.Manager) error {
	// Anti-pattern 1: no GenerationChangedPredicate
	// Anti-pattern 5: no MaxConcurrentReconciles (defaults to 1)
	return ctrl.NewControllerManagedBy(mgr).
		For(&benchmarkv1alpha1.Widget{}).
		Complete(r)
}
