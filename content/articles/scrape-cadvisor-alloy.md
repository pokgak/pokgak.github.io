---
title: "Scrape cAdvisor using Grafana Alloy"
date: 2024-07-0T17:45:00+08:00
tags: [grafana, alloy, cadvisor, observability, metrics]
---

I was having some issues figuring out how to scrape cAdvisor metrics using Grafana Alloy. After googling I came across this k8s-monitoring helm chart and inside there is a configuration for scraping the built-in cAdvisor on the k8s kubelet.

I ran Alloy as a single pod Deployment and it'll scrape all the nodes in the cluster. Here's the config that I used to get the metrics:

```hcl
prometheus.remote_write "default" {
  endpoint {
    url = "https://mimir.example.com/api/v1/push"
  }
}

discovery.kubernetes "nodes" {
  role = "node"
}

discovery.relabel "cadvisor" {
  targets = discovery.kubernetes.nodes.targets

  rule {
    replacement   = "/metrics/cadvisor"
    target_label  = "__metrics_path__"
  }
}

prometheus.scrape "cadvisor" {
  job_name   = "integrations/kubernetes/cadvisor"
  targets    = discovery.relabel.cadvisor.output
  scheme     = "https"
  scrape_interval = "60s"
  bearer_token_file = "/var/run/secrets/kubernetes.io/serviceaccount/token"
  tls_config {
    insecure_skip_verify = true
  }

  forward_to = [prometheus.remote_write.default.receiver]
}
```

### Alloy cadvisor exporter

Alloy provides the `prometheus.exporter.cadvisor` components that can be used to start a new cadvisor on the nodes. This is not required if the kubelet running on your nodes already runs cadvisor. This is the case for me on EKS running on Bottlerocket.
