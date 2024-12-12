---
title: "Exploring AWS ALB for EKS"
date: 2024-12-12T17:07:00+08:00
tags: [aws, eks, load balancer, network, alb, nlb, ingress controller]
---

Recently, [my company got DDoS'ed](https://pokgak.xyz/articles/we-got-ddosed/) and during the attack I noticed that the first thing that went down is the ingress-nginx pods. With this information, I was thinking if I could eliminate ingress-nginx and rely on AWS load balancers directly for routing the traffic to our services. AWS load balancer comes in two flavors: the L4 Network Load Balancer (NLB) and the L7 Application Load Balancer. The NLB doesn't support the same feature as ingress-nginx for routing HTTP requests as it operates on the L4 layer only so we'll be looking at the ALB in this article.

## Current Setup

![AWS NLB with ingress-nginx](images/lb-nlb-ingress-nginx.png)

Our current setup uses a AWS NLB per country to accepts the connection from the internet. The NLB then forwards the requests to a target group consisting all the ingress-nginx controller pods. The ingress-nginx pods will then route the traffic from NLB to the backend services based on the configured Ingress configurations.

For arguments sake, let's assume that AWS NLB is reliable and can scale infinitely. Our bottleneck then is the ingress-nginx pods. We can setup the ingress-nginx pods to autoscale based on the traffic but I've seen issues with connections getting disrupted when the autoscaling happens. What if we can eliminate this bottleneck altogether and just route directly from AWS LB to our backend services?

## Proposed Setup

![AWS ALB without ingress-nginx](images/lb-alb.png)

Our proposed setup uses the ALB directly and route traffic to the backend services through its listener rules. By default the aws-load-balancer controller will provision one ALB for each Ingress resource but we can share the ALB for multiple Ingress by specifying the same `alb.ingress.kubernetes.io/group.name`. In my case there will be one group name for each country resulting in separate ALB created for each respectively. Each Ingress resource will create a separate listener rule based on the host and path configuration specified in the Ingress.

## ALB Quotas and Limitations

Since we now rely on AWS ALB directly to route requests to our backend services, we must pay attention to the [limitations](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-limits.html) set by AWS. For ALB there is a soft-limit of 100 rules per ALB. Assuming we need one listener rule per backend service, the maximum number of backend services that can be served by one ALB is 100. There are workarounds you can do to overcome this grouping separate backend services together by team or other attributes and each will get one ALB.

## Pricing: ALB vs NLB

This is the part that I'm most interested in: how much more will it cost us if we migrate to ALB?

Based on the [AWS ELB pricing page](https://aws.amazon.com/elasticloadbalancing/pricing/), the per-hour cost of the LB instance itself is the same for ALB and NLB. What differs is the (N)LCU-hour cost. ALB LCU-hour is around 30% more expensive than NLB. It might seem like that's the only difference but if you read further on the ELB pricing page you will notice that an LCU-hour for ALB is not the same as NLB.

### Rule Evaluations

For ALB, the LCU-hour has an extra dimension measured which is the rule evaluations. You get 10 free rules per ALB. The formula given for calculating this dimension is `Rule evaluations = Request rate * (Number of rules processed - 10 free rules)`. Since ALB adds new rule for each Ingress and having separate path for defined in the Ingress spec will also create new rule, your LCU-hour cost might increase the more Ingress and paths you have in your cluster.

### New Connections

Another difference is the included new connections count per second. For NLB there are different values depending on whether you're using TCP, UDP, or TLS but for our comparison with ALB, lets look at the TLS pricing.

NLB with TLS includes 50 new TLS connections per second while ALB only includes half of that amount. We already calculated that ALB LCU-hour is already 30% more expensive than NLB but assuming you have the same amount of new connections, ALB will incur more LCU-hour than NLB.

To get a better comparison let's calculate the cost per connection for each LCU-hour. For NLB this is $0.006/50 connections = $0.00012 and for ALB it's $0.008/25 connections = $0.00032. So, comparing cost per connection, $0.00032/$0.00012, **ALB is 2.7x more expensive than NLB**.

### LCU-hour pricing

> You are charged only on the dimension with the highest usage.

LCU-hour is charged based on the highest dimension from all the dimensions measured so this means it depends on which is higher for both the rule evaluations and new connections dimension above. Let's say you don't have that many services so your listening rules also not that many causing you to not exceed the rule evaluations per second for ALB, you will still be charged 2.7x more compared to when you're using NLB.

## Conclusion

I started this thought experiment thinking it might be better for us to migrate to ALB and eliminate ingress-nginx but after doing this research I think for our current workload we are better suited sticking with NLB + ingress-nginx. Hope this is useful for others too.
