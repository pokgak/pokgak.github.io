---
title: "Scale down your instances, cut down your AWS bills"
date: 2025-04-29T14:14:00+08:00
tags: [aws, ec2, autoscaling, karpenter, keda]
---

I joined a webinar from Platformatic on the best practices of running nodejs services in production and one of the suggestion is to give each of the pod 1 full CPU core. All went well, our latency metrics seems to have improved, case closed. Little did I know that at the end of the month I would get hit by 3x increase in our monthly AWS bills. So I started optimizing.

## Know your workload patterns

Our company mainly serves restaurants so the traffic to our services has a predictable pattern; it starts ramping up at around breakfast time and peaks at around lunch and dinner. We have a few customers that operates until midnight but they're the minority so during those ours incoming traffic to our services it at the minimum. This pattern is something I noticed early when I first joined as possible optimization area but never got to it until now.

Our workloads run on AWS EKS and mainly using managed node groups provisioned statically with no cluster-autoscaler configured to add or remove nodes. There is also not HorizontalPodAutoscaler (HPA) setup for our Pods. This decision is done mainly to simplify operations. Just add more replicas and more nodes when the pods are getting overwhelmed by requests. It works at a smaller scale since the AWS bills is still manageable but we went through a growth phase recently and our infra costs also jumped. We figured that we have to tackle this now instead of pushing it back for later.

## Know your tools

When talking about autoscaling in kubernetes-land, there's the HorizontalPodAutoscaler (HPA). HPA allows you to scale your pods based on cpu, memory, or in the more recent versions, any custom metrics. The custom metrics autoscaling works but the UX leaves much to be desired. That's why I chose to use KEDA instead.

KEDA builts on top of HPA, providing a simplified interface. You also have more options to scale on metrics from almost anywhere using the available [Scalers](https://keda.sh/docs/2.17/scalers/). For my use case, I'll be using the [Cron](https://keda.sh/docs/2.17/scalers/cron/) and [Prometheus](https://keda.sh/docs/2.17/scalers/prometheus/) scalers.

Additional note for why to use KEDA is that it supports scaling down pods to 0 and scaling back up. This is called [Activation](https://keda.sh/docs/2.17/concepts/scaling-deployments/#activating-and-scaling-thresholds) inside KEDA where the pod replicas goes from 0 to 1 and vice versa. This doesn't apply to our use case since we still have to keep some pods running during midnight but if your workload allows it this will definitely gives you more savings.

### Setting up the cron scaler

As mentioned above, we have a regular and predictable traffic pattern for our workloads, starts at 7AM and peaks during lunch and dinner time. So, the cron scaler fits perfectly for this use case. We set a schedule to scale up our services during those hours and for the rest of the hours, scale it back down to the minimum possible. KEDA uses a custom resource called [ScaledObject](https://keda.sh/docs/2.17/reference/scaledobject-spec/) to specify the definition for the autoscaling.

In my setup, I'll configure it to scale based on the following rule:
- 7AM - 11AM: 10 replicas
- 11AM - 2PM: 20 replicas
- 2PM - 6PM: 10 replicas
- 6PM - 10PM: 20 replicas
- outside of those hours, scale down to minimum replica count which is 1

This is how the manifest looks like:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: backend-service
spec:
  maxReplicaCount: 30
  minReplicaCount: 1
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backend-service
  triggers:
    - metadata:
        desiredReplicas: '10'
        start: 0 7 * * *
        end: 0 11 * * *
        timezone: Asia/Singapore
      type: cron
    - metadata:
        desiredReplicas: '20'
        start: 0 11 * * *
        end: 0 14 * * *
        timezone: Asia/Singapore
      type: cron
    - metadata:
        desiredReplicas: '10'
        start: 0 14 * * *
        end: 0 18 * * *
        timezone: Asia/Singapore
      type: cron
    - metadata:
        desiredReplicas: '20'
        start: 0 18 * * *
        end: 0 22 * * *
        timezone: Asia/Singapore
      type: cron
```

### Combining cron and prometheus scalers

Cron and prometheus scalers on its own is not enough. If I'm using cron alone, what if suddenly one day the traffic suddenly higher than usual? This where prometheus scalers comes in. It looks at the actual metrics and scale accordingly.

Then you might think, why not just use prometheus scalers on its own then? It depends. If your traffic always grows slowly and gradually then ya it might work. New pods starting up can catchup to the traffic coming in but during rush hours the traffic can increase really fast and to avoid waiting for our pods to scale up which might take some time, we just decided to pre-scale up our pods during the expected rush hours. With this setup, the prometheus scaler can supplements the pods if the configured cron autoscaling is not enough.

### Setting up the prometheus scalers

For the prometheus scalers, we decided to scale our pods based on the response latency served from the service. This is based on the [RED method](https://grafana.com/blog/2018/08/02/the-red-method-how-to-instrument-your-services/). The "D" inside "RED" stands for Duration - or latency. This is a great metric to measure the performance of our service since it directly correlates to the experience faced by the user when using that service. High latency means your customer needs to wait longer, which is bad.

This latency metrics however does not come out of the box. In our setup, we generate this metrics from the traces emitted by our service which is instrumented using [OpenTelemetry (otel)](https://opentelemetry.io/). All the traces are sent to Tempo, our backend for storing traces, and Tempo will generate the metric `traces_spanmetrics_latency` from it. Generating the metrics on Tempo is out of the scope for this article but you can refer to the [Tempo docs](https://grafana.com/docs/tempo/latest/metrics-generator/span_metrics/).

## Issues arising from autoscaling

If you think once the autoscaling is rolled out then all is good.. then you're dead wrong - so was I. The first day we rolled out the autoscaling, we monitor the service closely for any increase in errors and error it did. First, it was just not enough capacity. The original capacity we put in for autoscaling is not enough. Easy fix just add more capacity. Then, we were scaling up too late and scaling down too early. Also easy fix, just move the scaling up period higher and scaling down period later.

### Connections being terminated prematurely

The not so obvious one tho is that, every time the we scales down by half we see a lot of errors from the service coming from the service. Those errors mostly related to the connection being terminated prematurely. There are two ways to reduce this but I'll explain the one way we took for now which is configuring the HPA behavior.

The first one is that HPA by default scales down too fast for us. This cause the service to scale down fast, then notice that the resource is not enough and it scales back up - rinse and repeat. In autoscaling we call this behavior as "flapping" and we don't want that. We want our service to be stable. This is the modification I've done to our above ScaledObject - adding `stabilizationWindowSeconds` and set it to remove pods one by one.

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: backend-service
spec:
  advanced:
    horizontalPodAutoscalerConfig:
      behavior:
        scaleDown:
          stabilizationWindowSeconds: 600 # wait 10 minutes before scaling down
          policies:
            - type: Pods
              value: 2
              periodSeconds: 180  # remove two pods every 3 minutes
```

#### HPA config: stabilizationWindowSeconds

KEDA allows you to configure the underlying HPA object directly from the ScaledObject. First, we'll configure the HPA [stabilization window](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/#stabilization-window) so that it will look at the last 10 minutes of recommendations by the HPA and only apply the highest value. This means if within the last 10 minutes your HPA recommended to scale down from 10 to 8, then a few minutes later to 5. Then it will scale down to 8 only and not 5 directly. It'll have to wait until the recommedation to scale down to 8 is outside of the window then only it'll scale down to 5.

#### HPA config: pod scale down policy

HPA allows configuring the [scaling policies](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/#scaling-policies) separately for scaling up and down. By default, HPA will scale down by up to 100% of the available replicas every 15s. This means, if you have 20 replicas, HPA will immediately terminates half the pods from 20 to 10 when scaling down. If the HPA recommendation says it should go down further to 1, then after 15s it will scale down further to 5.

In this above snippet, we changed it to be less aggressive by allowing only 2 pods to scale down every 3 minutes. We've seen massive reductions in the number of connections being terminated. I started with only 1 pod per minute but find it too fast then increase it to the current amount.

## Scaling down your nodes using Karpenter

After the pods has been scaled down, your kubernetes nodes would be running underutilized. You can use any cluster autoscaler of your choice for scaling down underutilized nodes but in my case I used Karpenter since I'm already running on EKS and Karpenter was built for it originally. For this part there is less suprise tho I do plan to write more on running Karpenter in production, hopefully it will come out soon. Ping me on my socials if it is not out yet after 3 months you're reading this (random deadline for myself lol).

## Summary

After all this autoscaling exercise we actually reduced our AWS spending for EC2 instances used by EKS clusters by approximately 50%. This is a huge amount for us and my boss was defnitely happy (promotion soon?). Hope this helps anyone going on this journey :)

On how to tackle the disconnect issues, you can also configure graceful shutdown for your pods. I'll link to this detailed article from learnk8s on how to do [graceful shutdown in kubernetes](https://learnk8s.io/graceful-shutdown).
