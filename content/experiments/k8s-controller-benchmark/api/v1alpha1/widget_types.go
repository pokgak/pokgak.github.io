package v1alpha1

import metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

type WidgetSpec struct {
	Count   int    `json:"count"`
	Message string `json:"message,omitempty"`
}

type WidgetStatus struct {
	Phase          string       `json:"phase,omitempty"`
	ProcessedCount int          `json:"processedCount,omitempty"`
	LastUpdated    *metav1.Time `json:"lastUpdated,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:printcolumn:name="Phase",type="string",JSONPath=".status.phase"
// +kubebuilder:printcolumn:name="Count",type="integer",JSONPath=".spec.count"
// +kubebuilder:printcolumn:name="Age",type="date",JSONPath=".metadata.creationTimestamp"
type Widget struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`
	Spec              WidgetSpec   `json:"spec,omitempty"`
	Status            WidgetStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true
type WidgetList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []Widget `json:"items"`
}

func init() {
	SchemeBuilder.Register(&Widget{}, &WidgetList{})
}
