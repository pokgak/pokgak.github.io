package controller

// GoodSinglePatchReconciler: same as GoodPatchReconciler but MaxConcurrentReconciles: 1.
// Isolates the Patch vs Update effect at single-worker throughput.

import (
	"context"
	"time"

	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller"
	"sigs.k8s.io/controller-runtime/pkg/predicate"

	benchmarkv1alpha1 "github.com/pokgak/agent-skills/experiments/k8s-controller-benchmark/api/v1alpha1"
)

type GoodSinglePatchReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

func (r *GoodSinglePatchReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
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

	time.Sleep(10 * time.Millisecond)

	base := widget.DeepCopy()
	now := metav1.Now()
	widget.Status.Phase = "Ready"
	widget.Status.ProcessedCount = widget.Spec.Count
	widget.Status.LastUpdated = &now
	if err := r.Status().Patch(ctx, widget, client.MergeFrom(base)); err != nil {
		return ctrl.Result{}, err
	}

	logger.Info("Widget reconciled successfully", "phase", "Ready")
	return ctrl.Result{}, nil
}

func (r *GoodSinglePatchReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&benchmarkv1alpha1.Widget{}).
		WithEventFilter(predicate.GenerationChangedPredicate{}).
		WithOptions(controller.Options{
			MaxConcurrentReconciles: 1,
		}).
		Complete(r)
}
