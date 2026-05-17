package controller

// BadConcurrentReconciler is identical to BadReconciler with one change:
// MaxConcurrentReconciles is set to 5 (same as GoodReconciler).
// All other anti-patterns remain:
//  1. No GenerationChangedPredicate
//  2. r.Update() for status (silently ignored by API server)
//  3. No RetryOnConflict
//  4. IsNotFound not handled
//  6. Annotation mutation on every reconcile (guarantees infinite loop)

import (
	"context"
	"fmt"
	"time"

	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller"

	benchmarkv1alpha1 "github.com/pokgak/agent-skills/experiments/k8s-controller-benchmark/api/v1alpha1"
)

type BadConcurrentReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

func (r *BadConcurrentReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := ctrl.LoggerFrom(ctx)
	logger.Info("Reconciling")

	widget := &benchmarkv1alpha1.Widget{}
	if err := r.Get(ctx, req.NamespacedName, widget); err != nil {
		return ctrl.Result{}, err
	}

	time.Sleep(10 * time.Millisecond)

	if widget.Annotations == nil {
		widget.Annotations = make(map[string]string)
	}
	widget.Annotations["bad-controller/last-seen"] = fmt.Sprintf("%d", time.Now().UnixNano())

	widget.Status.Phase = "Ready"
	widget.Status.ProcessedCount = widget.Spec.Count
	if err := r.Update(ctx, widget); err != nil {
		return ctrl.Result{}, err
	}

	return ctrl.Result{}, nil
}

func (r *BadConcurrentReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&benchmarkv1alpha1.Widget{}).
		WithOptions(controller.Options{
			MaxConcurrentReconciles: 5, // only change from BadReconciler
		}).
		Complete(r)
}
