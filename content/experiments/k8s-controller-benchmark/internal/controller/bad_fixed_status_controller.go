package controller

// BadFixedStatusReconciler keeps all anti-patterns from BadConcurrentReconciler
// EXCEPT the status update method is fixed to use r.Status().Update().
// This isolates the impact of the GenerationChangedPredicate + annotation loop
// from the status update correctness bug.
//
// Anti-patterns still present:
//  1. No GenerationChangedPredicate → infinite reconcile loop
//  3. No RetryOnConflict
//  4. IsNotFound not handled
//  6. Annotation mutation on every reconcile
//
// Fixed:
//  2. r.Status().Update() used correctly → widgets WILL reach Ready
//  5. MaxConcurrentReconciles: 5

import (
	"context"
	"fmt"
	"time"

	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller"

	benchmarkv1alpha1 "github.com/pokgak/agent-skills/experiments/k8s-controller-benchmark/api/v1alpha1"
)

type BadFixedStatusReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

func (r *BadFixedStatusReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := ctrl.LoggerFrom(ctx)
	logger.Info("Reconciling")

	widget := &benchmarkv1alpha1.Widget{}
	if err := r.Get(ctx, req.NamespacedName, widget); err != nil {
		if apierrors.IsNotFound(err) {
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	time.Sleep(10 * time.Millisecond)

	// Anti-pattern: annotation mutation — still drives infinite reconcile loop
	if widget.Annotations == nil {
		widget.Annotations = make(map[string]string)
	}
	widget.Annotations["bad-controller/last-seen"] = fmt.Sprintf("%d", time.Now().UnixNano())
	if err := r.Update(ctx, widget); err != nil {
		return ctrl.Result{}, err
	}

	// Fixed: status via correct subresource endpoint — widgets WILL reach Ready
	// No RetryOnConflict — still an anti-pattern, but isolated
	now := metav1.Now()
	widget.Status.Phase = "Ready"
	widget.Status.ProcessedCount = widget.Spec.Count
	widget.Status.LastUpdated = &now
	if err := r.Status().Update(ctx, widget); err != nil {
		return ctrl.Result{}, err
	}

	return ctrl.Result{}, nil
}

func (r *BadFixedStatusReconciler) SetupWithManager(mgr ctrl.Manager) error {
	// Still missing GenerationChangedPredicate → infinite loop continues
	return ctrl.NewControllerManagedBy(mgr).
		For(&benchmarkv1alpha1.Widget{}).
		WithOptions(controller.Options{
			MaxConcurrentReconciles: 5,
		}).
		Complete(r)
}
