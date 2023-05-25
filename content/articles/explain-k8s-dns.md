---
title: "Interview Series: Explain How Kubernetes DNS works"
date: 2023-05-24T23:00:00+08:00
tags: [interview, kubernetes, dns, networking]
---

This will be the first in my interview questions series. I'll compile interesting questions that I got from my experience interviewing for DevOps/SRE role in Malaysia.

![](images/k8s-dns.png)

## Calling a service by its cluster-internal DNS

We'll go from the highest to the lowest level in this journey. So let's go through the scenario a bit: you have two services, foo and bar. those two services live in the same namespace `app` in your cluster. Now, inside service foo code, it makes a HTTP request to service bar. Probably something like so:

```
http.get("https://bar/")
```

What happens behind the scene from when the request is made to service bar and until the response is received back by service foo?

## What is that weird DNS format?

You might've noticed that we're just calling the service bar by the name using a weird name. Instead of the usual something.com domain, we're just using `bar` directly. How is this possible?

Kubernetes allows you to call other services by using the service resource name directly. It does this by automatically appending the full DNS domain to the given service name. So for example here, when you make a request to `bar`, the application will make a DNS request to the local DNS server. The DNS server then notices that the domain that it received is not "complete" so it automatically appends the rest of the domain name based on the configuration that was given to it. If the service is running inside the namespace `app`, it will turn `bar` into `bar.app.svc.cluster.local`.

This automatic appending to complete the domain name is called "search domain". In our example the seach domain is configured as `app.svc.cluster.local`. So, whenever the service makes a call to `bar` it will automatically try to append the search domain and tries to resolve the domain name.

## How (and where) is this configured?

Every pods in kubernetes has a file `/etc/resolv.conf` that is configured by the kubelete when starting the pod. This file will contain the info where to find the DNS server inside the cluster and also what to use as the search domain. Here's an example of the file ([source][1]):

```
nameserver 10.32.0.10
search <namespace>.svc.cluster.local svc.cluster.local cluster.local
options ndots:5
```

## Which IP will be returned by the DNS query?

The DNS query will return us a virtual service IP. Why virtual? It's because this IP doesn't actually points to a pod that runs our services.

In kubernetes, pods can come and go at any time which also means that their IP will change all the time. How do we know then where to send our requests to? The Service resource is used to abstract dynamic nature of pod IPs and provide a consistent IP that your application can use to send requests to it.

## How does the service IP maps to pod IPs?

The Service resource always comes with its pair, the Endpoint (or EndpointSlice) resource. This Endpoint resource tracks the pod IPs and also have information which pod IP is ready to receive traffic. This information can be queried using the kubernetes API. On the node where the pod runs, there is a program called kube-proxy that runs and updates the routing to map from service IP to pod IP. This routing can be done in multiple ways but currently the default is using iptables.

## When does this routing happens?

When a request is first sent from the application code, its destination will be set to the service IP but before the request is sent out over the network, iptables modifies the destination and changes the service IP to pod IP. If there are multiple pods that sits behind a service, the pod IP will be selected randomly. Once the destination IP is changed, the packet is then sent out over the network.

## How do you know which node to send the packet to?

A kubernetes cluster can contain a lot of nodes. Sending the packet to the correct node is important. To know which node to send the packet to, the router in your network will need to know which node to send this packet to. If you setup your own cluster ala kubernetes-the-hard-way, you might need to [configure these routes yourself][2] but if you're using kubernetes on top of any cloud providers, they usually will do these setup for you and you don't have to do anything here. Once that is sorted, your packet now can reach the correct node and the packet is sent to the correct pod on the node based on the destination pod IP set in the packet header. The response then will be sent to the source pod IP in the request packet header.

## Response now sent back to the source node. All done?

Not yet. There's one more last thing to do. Remember when we sent the request originally, iptables had rewrote the destination from service IP to pod IP? Now for the response packet to be received back by the pod, the pod IP that we rewrote before needs to be converted back to the service IP. This is needed because as far as the application knows, it sends a request to the service IP and not the pod IP. If it suddenly receives a response from a pod IP that it doesn't know of, then it will just drop the response. So, here iptable will have to remember what it did before and convert pod IP on the response packet back to service IP. Finally, our foo service can receive the response that it wants from the bar service.

[1]: https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/
[2]: https://github.com/kelseyhightower/kubernetes-the-hard-way/blob/master/docs/11-pod-network-routes.md
