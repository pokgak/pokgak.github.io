package controller

import (
	"context"
	"time"

	apierrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/runtime"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/util/retry"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller"
	"sigs.k8s.io/controller-runtime/pkg/predicate"

	benchmarkv1alpha1 "github.com/pokgak/agent-skills/experiments/k8s-controller-benchmark/api/v1alpha1"
)

type GoodReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

func (r *GoodReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := ctrl.LoggerFrom(ctx)
	logger.Info("Reconciling")

	widget := &benchmarkv1alpha1.Widget{}
	if err := r.Get(ctx, req.NamespacedName, widget); err != nil {
		if apierrors.IsNotFound(err) {
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	if !widget.DeletionTimestamp.IsZero() {
		return ctrl.Result{}, nil
	}

	// Simulate work
	time.Sleep(10 * time.Millisecond)

	// Correct: use Status().Update() with RetryOnConflict + re-fetch
	err := retry.RetryOnConflict(retry.DefaultRetry, func() error {
		current := &benchmarkv1alpha1.Widget{}
		if err := r.Get(ctx, req.NamespacedName, current); err != nil {
			return err
		}
		now := metav1.Now()
		current.Status.Phase = "Ready"
		current.Status.ProcessedCount = current.Spec.Count
		current.Status.LastUpdated = &now
		return r.Status().Update(ctx, current)
	})
	if err != nil {
		return ctrl.Result{}, err
	}

	logger.Info("Widget reconciled successfully", "phase", "Ready")
	return ctrl.Result{}, nil
}

func (r *GoodReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&benchmarkv1alpha1.Widget{}).
		WithEventFilter(predicate.GenerationChangedPredicate{}).
		WithOptions(controller.Options{
			MaxConcurrentReconciles: 5,
		}).
		Complete(r)
}
