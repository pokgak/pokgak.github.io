---
title: "Interview Series: Explain How Kubernetes DNS works"
date: 2023-05-24T23:00:00+08:00
tags: [interview, kubernetes, dns]
---

This will be the first in my interview questions series. I'll compile interesting questions that I got from my experience interviewing for DevOps/SRE role in Malaysia.

## Can you explain to me how DNS works in Kubernetes?

We'll go from the highest to the lowest level in this journey.

### Kubernetes Internal DNS naming

The application layer would be the highest level: service A calling service B using its cluster internal DNS name.

In kubernetes, an application is run inside a resource called Pod. A Pod is usually ephemeral which means it can go away any time and replaced by another pod. Each time a new pod is started, new IP will be assigned to the pod.

### If the IP address always changes, how do I send a request to the correct Pod then?

I present to you the kubernetes Service resource.

A Service in kubernetes helps abstracts a set of Pods running behind it. Instead of the ever changing IP addresss of the Pods, you now only have to keep track of the Service IP.

A Service is given a selector that it will use to know which Pod will be abstracted behind it. This is usually a label on the pod.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: service-a
spec:
  selector:
    app.kubernetes.io/name: service-a
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8080
```

### Different ways to call a service using DNS

Depending on where the services are running inside the cluster, there are few ways the services can call each other. If both services are running inside the same namespace

#### Within same namespace

You can just use the service name directly: `service-a`. By calling this from a pod inside a namespace, you are limiting the DNS query to only the services inside the namespace.

#### Across namespaces

You have to add the namespace after the service name: `service-a.namespace-a`.

## Inside the Pod

kubelet configures `/etc/resolv.conf` for each pod on a node. Here's an sample example content for `/etc/resolv.conf`:

```
nameserver 10.32.0.10
search <namespace>.svc.cluster.local svc.cluster.local cluster.local
options ndots:5
```

The `nameserver` value here will point to the DNS Server running inside the cluster which we will discuss more after this.

The `search` here means the DNS search list for resolving DNS queries. If you just call `service-a` for example, the DNS server will know to add the `search` value suffix so that your given domain can resolve to a fully qualified domain name (FQDN).

## DNS Server

Once you call a service by its cluster-internal DNS name, the request will be sent over to the DNS server running inside the cluster. Nowadays, this will usually be CoreDNS

### CoreDNS

Acts as the DNS server inside the cluster. Since the cluster internal DNS names doesn't exist in external DNS server, CoreDNS resolves all the cluster-internal DNS based on the data from the kubernetes API. The 

## On the node

On each kubernetes there will be at least two components running: the kubelet and the kube-proxy. The kubelet manages the containers running on the node while kube-proxy handles the networking of those containers.

kube-proxy watches the kubernetes API for any changes in the Service and Endpoint objects in the cluster. Once it detects that the resources has changed, it will update the routing rules on the node to correctly forward traffic to the right pod running on the node. There are several ways it can do the routing but by default it will use `iptables`.

More details in this [blog post](https://mayankshah.dev/blog/demystifying-kube-proxy/).


## References

- https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/
- https://kubernetes.io/docs/concepts/services-networking/service/
- https://kubernetes.io/docs/concepts/overview/components/
- https://mayankshah.dev/blog/demystifying-kube-proxy/