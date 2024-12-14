---
title: "Eliminating cross-AZ traffic cost on AWS"
date: 2024-12-14T17:23:06+08:00
tags: [aws, eks, network, nlb, k8s, cost, finops]
---

Imagine going through your AWS bills and noticing that **APS1-DataTransfer-Regional-Bytes** is 1/3 of your monthly AWS cost. After reading a bit more on [how AWS charges for network traffic](https://docs.aws.amazon.com/cur/latest/userguide/cur-data-transfers-charges.html) you know that this is referring to the cost incurred when your traffic crosses an availability zone (AZ). This article will go walk you through what you can do to eliminate this cross-AZ traffic cost.

**Disclaimer**: this is not necessarily the best practice. I try my best to highlight the caveat and tradeoff you're making in this article but please make your own judgement before making the changes.

## The Traffic Flow

![](images/cross-az-traffic.png)

In this article I will use the above diagram as our example network flow. Our example scenario will use the AWS Network Load Balancer (NLB) as the load balancer (LB), then routes the traffic to the ingress-nginx pods running inside our cluster. Finally, ingress-controller pods will route the traffic to the backend services serving the API.

The top and bottom part of the diagram will show how the traffic flow will be between the AZ. Once we implemented the steps I will be describing below, you should be able to elimate the cross-AZ traffic in our network.

## Incoming traffic to Load Balancer Nodes

When you provision a load balancer on AWS, you will get a domain name that can be used to resolve to the IP addresses of your LB nodes. Depending on where the DNS resolving happens, this might be the first contributor to your cross-AZ traffic cost.

### Resolving LB Nodes IP from the Internet

There is nothing we can do if the source of the traffic is from the internet. The DNS will resolve to one of the IP addresses of the LB and we wouldn't be charged for it as there is no AZ yet here.

### Resolving LB Nodes IP from within your AWS Network

If the source traffic originates from within your AWS network, there is the possibility that the LB nodes IP resolved is not within the same AZ as your source traffic. To avoid this, on the LB there is an option to set the client routing policy to resolve to LB nodes IP that is within the same AZ.

There is 3 options to choose from:
    * AZ affinity: queries may resolve to other zones if there are no healthy load balancer IP addresses in their own zone
    * Partial AZ affinity: 85% of client DNS queries will favor load balancer IP addresses in their own Availability Zone, remaining resolves to any zone
    * Any Availability Zone (default)

In my opinion, it is safe to always set the LB to use the AZ affinity policy because the DNS queries will automatically resolve to other healthy LB IP in other zones when the one in the same zone is down.

## Load Balancer Nodes to ingress-nginx pods

Once the traffic reaches the LB node, the LB now have to decide to which target to send the traffic to. To improve our reliability, we have the option to enable cross-zone load balancing. With this enabled, the LB node can also send the traffic to targets in other zones. It is disabled by default.

There is a tradeoff between reliability and cost here. If cross-zone load balancing is disabled, you have to make sure that the target(s) in each zone are healthy. If there are no healthy target in the zone, the request might fail. This means your service can be less reliable but if you enabled cross-zone load balancing you might incur cross-AZ traffic cost. So do your research and decide what's best for you.

## ingress-nginx pods to backend services pods

### Kubernetes 1.31 Service traffic distribution

After the ingress-nginx pods, the traffic will be routed to the backend services pods. Kubernetes version 1.31 introuced a new [traffic distribution mechanism](https://kubernetes.io/docs/concepts/services-networking/service/#traffic-distribution) for Service resources which will influence how traffic is routed to your pods. You can now set the Service `.spec.trafficDistribution` to `PreferClose` to route the traffic to endpoints that are "topologically proximate". The details of what that means depends on the implementation but for kube-proxy this means sending the traffic to endpoints that are within the same zone when available. This means we can achive our goal here to avoid the cross-AZ traffic cost. To understand more please refer to the [Kubernetes documentation](https://kubernetes.io/docs/reference/networking/virtual-ips/#traffic-distribution) and [KEP-4444](https://github.com/kubernetes/enhancements/tree/master/keps/sig-network/4444-service-traffic-distribution#preferclose).

**CAVEAT**: as mentioned in the [Risks and Mitigation](https://github.com/kubernetes/enhancements/tree/master/keps/sig-network/4444-service-traffic-distribution#risks-and-mitigations) section of KEP-4444, enabling this feature might cause the pods in one AZ getting overloaded with traffic if the originating traffic is skewed towards one AZ.

### ingress-nginx default routing behaviour

NOTE: please be extra careful with this section as this influences the routing of traffic to pods within your cluster. Do test this out on a non-production environment and make sure your workloads are still running fine before introducing it in production.

That alone is not enough though due to how ingress-nginx works. In the Ingress configuration, you specified the Service that ingress-nginx should route the traffic to but I was suprised to know that, by default, ingress-nginx does not actually uses the Service ClusterIP. It will actually search for the Endpoint of the services and get the IP of the pods behind the service. Then, it will distribute the traffic to the pod IPs using the round robin algorithm.

To leverage the newly introuduced traffic distribution feature I mentioned above, we need to make ingress-nginx routes the traffic using the ClusterIP of the Service. To do this globally for the ingress controller we can set `service-upstream: true` in the ingress-nginx configmap. This alone is not enough though because by default ingress-nginx tries to keep a long connection between the ingress-nginx pods and the backend services pods to reduce resource usage using keepalives. To configure ingress-nginx not to use this, you can add another config `upstream-keepalive-requests: "0"` to the ingress-nginx configmap but beware that this might increase the resource of your ingress-nginx pods as it now needs to maintains a new connection for each requests coming in.

## Conclusion

With the above steps, you should be able to avoid cross-AZ traffic in your AWS network for workloads hosted using NLB, EKS and ingress-nginx. Since this optimization might affect your production system, please make sure you test properly before rolling it out.
