---
title: "Access your kubernetes service from anywhere using Tailscale"
date: 2023-09-12T02:05:00+08:00
tags: [kubernetes, tailscale, external-dns, networking]
images:
- "images/k8s-external-dns-tailscale.png"
---

![Full flow](images/k8s-external-dns-tailscale.png)

I recently setup a local kubernetes in my home network to play with and one of the issues that I faced is that it is hard to access the services inside the cluster from my laptop. I don't have a load-balancer in my setup so everytime I want to access a service from my laptop, I'll have to run `kubectl port-forward` first before using the localhost address to access it. It works but it's annoying.

Usually in cloud environments like AWS, you would setup an [ingress-controller](https://kubernetes.io/docs/concepts/services-networking/ingress-controllers/) that will provision a load balancer for you and use that load balancer to expose your services inside the cluster to the internet using Ingress resources. Your incoming traffic from the internet will then be routed through the load balancer into your cluster onto your pods. Unfortunately, you don't get the same thing when hosting your cluster locally outside of the cloud environment. You have to manually configure your network to allow access from the internet.

### So what options do we have?

One way we can do it is to use a Service with type NodePort to use the host port and access the pods using the host IP, this will allow access to services inside the cluster to your local network but still not from the internet. To allow access from the internet, you'll have to open a port on your router to route to the host IP from the NodePort service.

I'm not a fan of opening my home network to the internet. Home routers is infamous for being vulnerable and easily exploitable. I don't want mine to be part of a new legion of botnets that will [break a new record for biggest DDoS attack](https://blog.cloudflare.com/cloudflare-mitigates-record-breaking-71-million-request-per-second-ddos-attack/). Using the NodePort service type also is not that great. With NodePort service, you'll have to specify the node IP to access along with the port assigned and your traffic will always go to that node and the pods running on it. More reason on why NodePort is a bad idea on [StackOverflow](https://devops.stackexchange.com/a/17084).

What other option do we have? [Tailscale](https://tailscale.com)!

### Tailscale Subnet Router

Tailscale is a mesh VPN built on top of [Wireguard](https://www.wireguard.com/). I've been using it for a long time for accessing my personal servers at home while I'm outside and I love it. It is so simple to setup you don't have to know any networking magic to use it. Tailscale will create a peer-to-peer network from your client to your other Tailscale devices and it is also really smart in figuring out a way to punch a hole through your home network ([see the Resources section](#resources)) to connect to the internet so you don't have to open a port on your home router anymore. Bot legion problem solved!

One of the ways you can use Tailscale is by configuring a Tailscale node as a **subnet router**. Usually, when you have 10 devices in your network, you'll have to install Tailscale on each of those devices to connect it to your VPN network but with a subnet router only one Tailscale node in that network is enough, as long as that subnet router node have network access to all the devices in that network. You'll have to configure your subnet router to advertise the route of the internal cluster network that the subnet router is in using CIDR range e.g. `10.43.0.0/16` so that other devices outside of that network will know to look for the subnet router if they want to access the IP address from that CIDR range.

#### ELI5: subnet router advertisement

You're a postman trying to deliver a parcel. Your parcel destination is set to unit A-1-2-3 in the TRX Exchange 106 building. You've never been to TRX before so you don't know which floor the office actually is but you noticed there's a big signboard at the reception saying "Come here if you have parcel for unit A-1-0-0 to A-9-9-9". So, you went the reception and then the nice lady at the reception gave you the direction to reach the office unit A-1-2-3 for you to deliver your parcel.

The reception here is like our subnet router. All the traffic meant for the network have to go through the subnet router first, then they're passed through to the actual packet destination.

### I don't want to remember all this IP addresses

With a subnet router, you can now reach any of the services inside the cluster using the ClusterIP of that service but IP address is not human-friendly and you don't want to (you can't!) memorize all the IP addresses for all the services inside the cluster. So, now we need something that will map our IP addresses to a human-friendly format. Sounds familiar? We can use DNS records.

You can definitely create DNS records manually and map it to each of the ClusterIP for your services. That's what I did for testing when validating this setup actually. At scale, that won't work tho. You don't want to be the one to manually go to your DNS registrar and create the records one by one. Luckily, in kubernetes there is an application called external-dns.

### external-dns to the rescue

external-dns is an application that runs inside your kubernetes cluster and it periodically queries the kubernetes API for the list of all Service and Ingress resources. From the list, it checks whether it should create a DNS record for the resources based on the resource annotation. It supports a lot of DNS providers like AWS Route53, Cloudflare, Google Cloud DNS and more. For my setup I'm using Cloudflare.

By default, external-dns will only create DNS records for Ingress resource or Service with type LoadBalancer. For my setup, since I'm self-hosting the cluster inside my home network and don't have access to a load balancer, I have to [add an extra configuration parameter](https://github.com/pokgak/gitops/blob/0a880ec3e08481a7c50e67995fd4092dfb3c92f4/system/external-dns.yaml#L18) to external-dns so that it will create DNS records for ClusterIP Service type. On the Service resource itself, usually external-dns searches for the [`external-dns.alpha.kubernetes.io/hostname` annotation ](https://github.com/kubernetes-sigs/external-dns/blob/master/docs/annotations/annotations.md#external-dnsalphakubernetesiohostname) but since we're using it with ClusterIP, I have to change it to [`external-dns.alpha.kubernetes.io/internal-hostname`](https://github.com/kubernetes-sigs/external-dns/blob/master/docs/annotations/annotations.md#external-dnsalphakubernetesiointernal-hostname).


### Tailscale + external-dns = ❤️

```
➜ dig prometheus.k8s.pokgak.xyz +short
10.43.170.163
```

With those changes applied. All new Service resources in my kubernetes cluster that have the annotation will get one DNS record on Cloudflare. Now, if I try to resolve a name for a service inside the cluster, it will return me an internal ClusterIP. Combined with the Tailscale subnet-router we've configured earlier, now you can access services inside your cluster from any of your Tailscale devices from any part of the world.

With tailscale, you'll also have an additional layer of authentication. Only users in your Tailscale networks can access the exposed services. For others, they might be able to guess what you have running in your cluster from your DNS records but they won't be able to access it since all the IPs will be private IPs. 

For the next part, I'm looking into exposing some service inside my cluster to the internet **fully** without having to be in the Tailscale network. Tailscale Funnel suppose to do just that but I still haven't tested if it's working with services inside kubernetes.

### Resources

- [How Tailscale Works](https://tailscale.com/blog/how-tailscale-works/): explanation on how Tailscale uses Wireguard to create a mesh VPN network architecture.
- [How NAT traversal works](https://tailscale.com/blog/how-nat-traversal-works/): recommended read even if you're not a networking geek. You'll learn a thing or two about networking for sure.
- [Full cofiguration for external-dns helm chart](https://github.com/pokgak/gitops/blob/0a880ec3e08481a7c50e67995fd4092dfb3c92f4/system/external-dns.yaml)
- [external-dns annotation for the services](https://github.com/pokgak/gitops/blob/0a880ec3e08481a7c50e67995fd4092dfb3c92f4/system/kube-prometheus-stack.yaml#L20)