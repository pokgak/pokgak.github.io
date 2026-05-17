package controller

// GoodPatchReconciler uses r.Status().Patch() with a merge patch instead of
// r.Status().Update() + RetryOnConflict. A merge patch doesn't require the
// object's resourceVersion to match the server's current version — the server
// applies the patch on top of whatever is current. This eliminates the class
// of conflicts that good (5w) hits at smaller N.
//
// All other patterns identical to GoodReconciler:
//   - GenerationChangedPredicate
//   - MaxConcurrentReconciles: 5
//   - IsNotFound handling, DeletionTimestamp check, ctrl.LoggerFrom

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

type GoodPatchReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

func (r *GoodPatchReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
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

	// Patch instead of Update — no resourceVersion conflict possible
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

func (r *GoodPatchReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&benchmarkv1alpha1.Widget{}).
		WithEventFilter(predicate.GenerationChangedPredicate{}).
		WithOptions(controller.Options{
			MaxConcurrentReconciles: 5,
		}).
		Complete(r)
}
