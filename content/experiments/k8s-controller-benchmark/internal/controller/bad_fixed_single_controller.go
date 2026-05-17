package controller

// BadFixedSingleReconciler is identical to BadFixedStatusReconciler with MaxConcurrentReconciles: 1.
// Used to isolate the effect of worker count from the predicate.
// Anti-patterns still present: no GenerationChangedPredicate, annotation loop, no RetryOnConflict.

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

type BadFixedSingleReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

func (r *BadFixedSingleReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
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

	if widget.Annotations == nil {
		widget.Annotations = make(map[string]string)
	}
	widget.Annotations["bad-controller/last-seen"] = fmt.Sprintf("%d", time.Now().UnixNano())
	if err := r.Update(ctx, widget); err != nil {
		return ctrl.Result{}, err
	}

	now := metav1.Now()
	widget.Status.Phase = "Ready"
	widget.Status.ProcessedCount = widget.Spec.Count
	widget.Status.LastUpdated = &now
	if err := r.Status().Update(ctx, widget); err != nil {
		return ctrl.Result{}, err
	}

	return ctrl.Result{}, nil
}

func (r *BadFixedSingleReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&benchmarkv1alpha1.Widget{}).
		WithOptions(controller.Options{
			MaxConcurrentReconciles: 1,
		}).
		Complete(r)
}
