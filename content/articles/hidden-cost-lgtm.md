---
title: "The hidden cost of running your own observability stack"
date: 2024-06-24T13:00:00+08:00
tags: [grafana, loki, mimir, tempo, observability, aws]
---

At my latest $job, I was tasked of setting up the LGTM stack (Loki, Grafana, Tempo, Mimir) for observability. Fast forward a few months, I noticed there's a hidden aspect to running the stack that I was not expecting before and that is the network cost, specifically the network transfer cost for cross AZ traffic. At one point we were paying more than $100 per day just for the cross AZ network traffic.

Update: since this article was written, I've found out that the official Loki helm chart have a section addressing the cross-az issue in the values file. It does not recommend running Loki across multiple AZs on the cloud.

> Note: This can be used to run Loki over multiple cloud provider availability zones however this is not currently
> recommended as Loki is not optimized for this and cross zone network traffic costs can become extremely high
> extremely quickly. Even with zone awareness enabled, it is recommended to run Loki in a single availability zone.

## Cross AZ Traffic Amplification

While investigating where does the traffic coming from I compared the load balancer "Processed Bytes" metrics with the Cost Explorer usage for cross AZ traffic and noticed that there's a 10x increase in the reported values by the load balancer to the actual charged traffic. It baffled me a bit and made me step back and take a deeper look at the possible points where I'm getting charged.

1. Collector to load balancer node
2. load balancer node to ingress controller pod 
3. ingress controller pod to distributor
4. distributor to ingester

### Collector to Load Balancer Node: client routing policy

In my setup, the services are exposed through a load balancer and given a DNS name like `loki.example.com`. The collectors are configured to send the telemetry data to that URL. Here is my fist mistake, I didnt' enable "Availability Zone affinity" for the client routing policy. When enabled, this will route traffic from the collector to the load balancer node in the same AZ avoiding being charged for cross AZ traffic.

The load balancer node will then forward the traffic to the ingress controller pod in the same AZ.

### Ingress controller pod to distributor: Kubernetes Topology Aware Routing

From the load balancer node, the traffic will be forwarded to the k8s pod through the k8s service. The default behavior of service in k8s is it will route the traffic using the round-robin algorithm. This means that from the ingress controller pod to the distributor pod the traffic will go cross AZ. If you have 3 distributor pods, this means 2 out of 3 connections will be routed to pods in different AZ.

To avoid the traffic from crossing AZ, we can use [kubernetes topology aware routing](https://kubernetes.io/docs/concepts/services-networking/topology-aware-routing/) feature. Downside of using this is that we need to have at least 3 pods in each AZ but compute is cheaper in my use case since I'm using spot instances through Karpenter and getting up to 70% discount on the node price.

### Distributor to Ingester: no workaround

This the only part I haven't solved. In the LGTM stack, the distributors uses an [internal discovery mechanism](https://grafana.com/docs/loki/latest/get-started/hash-rings/#about-the-ingester-ring) to get the IP of the ingesters. This means that we cannot use kubernetes topology aware routing here.

To make things worse, depending on the [replication_factor](https://grafana.com/docs/loki/latest/get-started/components/#replication-factor) configuration, each distributor might be sending the logs to multiple ingesters, each one multiplying the cross AZ cost that we have to pay.

## Special use case: getting logs from external source

Other than the above use case, our company also have other use case where the logs comes from external sources instead of from our internal network. In this case, I actually managed to eliminate the cross AZ cost completely by deploying the LGTM stack in just one AZ. The load balancer is also configured to use only one subnet that is in the same AZ.

## Conclusion

All the above factor might explain why the amount I was charged for cross AZ traffic is 10x bigger than the amount that is received at the load balancer. I outlined some the possible points where the cross AZ charges are coming from and how to fix it. Hope it helps!
