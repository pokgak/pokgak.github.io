---
title: "We got DDoSed"
date: 2024-10-27T14:37:00+08:00
tags: [security, ddos, cloudflare, aws, ingress-nginx]
---

Recently at $work we've been hit by a series of DDoS attacks. In this post, I'm gonna describe the steps we've taken to protect our services from these attacks in the future and also what works and what don't.

## Detection

The first attack was around 10PM on a Sunday. I was at home at the time and was notified that our ingress-nginx pods were repeatedly crashing. I've seen this happen before and my initial thought was that our service was getting more customers this night so I added more nodes into our cluster and increased the replica count for the ingress-nginx pods. That did nothing. Our pods are still crashing and customers still cannot use our service.

Then, one of my colleagues showed me the metrics for new connections to our load balancer. We're getting 10x our usual traffic in a minute. That's a DDoS for sure.

![New connections to load balancer](images/ddos-lb-active-flow.png)

## Rate limiting from the ingress-controller

Ingress-nginx supports a whole set of [rate limiting features](https://kubernetes.github.io/ingress-nginx/user-guide/nginx-configuration/annotations/#rate-limiting). So we decided to start there but we first need to know which endpoint is being hit. For this, the logs from the ingress-nginx pods was really helpful. The incoming logs was coming in fast but we can see that most of the log lines contain the same hostname. So we put the `nginx.ingress.kubernetes.io/limit-rps` annotation to the ingress that is used by that hostname. Then, we wait and monitor whether this annotation helps stabilize our crashing pods. It didn't.

From the logs, I can see that ingress-nginx is rate-limiting the request but because it still has to process the request first and keep counting it, it cannot keep up with the amount of incoming traffic. Rate limiting on the ingress-nginx level is useless because our infra is not enough to even receive and block all the request. We have an option to add more replicas to our ingress-nginx pods but thats gonna be costly. So, we started looking for other solutions.

## Cloudflare to the rescue

I've always have known that people uses Cloudflare to protect against it I've never done it myself personally. After the initial response was proven not effective, I remember we're using Cloudflare to point the domain to our load balancer but why does Cloudflare not blocking all this DDoS traffic?

Our first mistake was that we didn't [proxy the traffic through Cloudflare](https://developers.cloudflare.com/dns/manage-dns-records/reference/proxied-dns-records/).

After proxying the traffic through Cloudflare though, there is a delay to when all the traffic will be routed to Cloudflare Anycast IP due to the TTL settings which is 300 seconds by default. So, again, we wait...and the request still coming in after a while. Meanwhile, I've enabled the [Under Attack mode](https://developers.cloudflare.com/fundamentals/reference/under-attack-mode/) but honestly I'm not sure if this actually helps. After a while the requests was still not going down. It might take a while before Cloudflare can kick in to automatically mitigate the attack. In the meantime, we need to do something.

### Using the WAF Rules

On the WAF page on Cloudflare, there's three types of rules you can configure: Custom rules, Rate limiting rules and Managed rules.

### Managed rules

After enabling the Under Attack mode, we also enabled the [Managed rules](https://developers.cloudflare.com/waf/managed-rules/) but it didn't help much in our case. Managed rules block commonly used attacks but it our case it doesn't block any of the DDoS attacks because the attack is targeting our API endpoint specifically with requests path that wasn't included in the managed ruleset. We leave it turned on regardless since it might protect against other attacks in the future.

### Custom rules: blocking by country

After all the above doesn't seem to work, we need a way to differentiate DDoS traffic from valid traffic. I know that we only operate in several countries in Southeast Asia. This means that all the traffic that's coming from outside those countries are bots (read more below to see why this is not true). So, we added a Custom rule to only whitelist the traffic coming from the countries that we operate in and that works, sorta. The request hitting our LB reduced to around half but its still higher than usual and our ingress pods are still being overwhelmed.

Then, we noticed from the Security Analytics page in Cloudflare that the requests that are still hitting the LB passed the rule because its coming from one of the whitelisted countries. We can remove that country from our whitelist but that also means that we'll be blocking valid traffic from our customers from those countries. So, we need to come up with new rule to block the DDoS traffic. What does a valid request have that the requests from the attacker doesn't have?

### Custom rules: blocking using query params, headers, and user agent

We went through nginx logs and noticed that the requests from the attacker are always using the same query params so we created a new rule blocking rqeuests with that query params and it worked! The requests hitting our LB dropped back to normal levels and we declared the incident finished. This doesn't last long tho. The next time we were hit with the attack, we noticed that the attacker now uses a different query param. Luckily, we had also added other rules in place.

After the first attack, we analysed our valid requests and came up with other rules based on the **Referer** and the **X-Requested-With** headers. We also check the User-Agent and block if its similar to the one that came from the attacker based on past attacks. So far this has been the most effective at blocking the attack. However, we know that this is not the final solution. If the attacker is determined enough, they can still look at valid requests and then spoof the values in their attack but so far we haven't seen this happening yet.

### Custom rules: blocking known attacker IPs

After several rounds of attacks we noticed that the DDoS attacks were all coming from the same set of IPs, so we created a list of known attacker IPs on Cloudflare and block future requests coming from those IPs. Looking back, this rule was only effective for a little while. Once the attacker noticed that all their requests were blocked, they will change the IP so the process will just keep repeating over and over again.

### Rate limiting rule

After we put in the custom rules, we also turned on the rate limiting rules. Unless you are on the Enterprise plan (its expensive XXXX), the rate limiting rule is pretty restricted. You can only rate limit by IP but I think it is good enough. The rate limiting rules will act as the last line of defense after the requests passes all your other configured custom rules. Here is the [rule execution order](https://developers.cloudflare.com/waf/concepts/#rule-execution-order) for your reference.

On a free plan, you get 10 second counting period but if you pay for other plans you'll get more options. To me, the bigger counting period helps prevent from blocking valid requests. There might be a burst of activity from your users that causes the IP to hit the rate limit within 10 seconds but if measured within a longer period its still within a normal range. So, paying more is definitely worth it here.

I definitely think that rate limiting rule is a must if you're fighting against DDoS. So, make sure to configure this.

## Bonus

### Blocking our own IPs

This is one of those facepalm moments in my life. After the attacks passed, I spent some time exploring the events in Cloudflare Security Analytics to see if I can find any insights. From the requests that were not blocked by Cloudflare, I grouped the requests by IP and checked the requests. Requests from the top two IPs looks good, it has all the headers and referers we were expecting them to have but the requests coming from a datacenter in Singapore. What makes it more suspicious was that all the requests had user agents from mobile devices eventhough the IP shows that they're coming from a datacenter. So, I informed my team and proceed to block the requests. After a while complaints started coming in saying our customers requests were blocked. One of my colleagues suspects that those are actually our IPs.

We have NAT Gateways configured in our network which means that if the requests were actually from our own network it will have one of those IPs from the NAT Gateway...and after comparing, they are indeed our NAT Gateway IPs. Apparently, one of the services proxies all the requests from the customers back to another service, complete with all the headers and user-agents that why it was showing mobile device user agents eventhough the IP was coming from a datacenter.

After this incident, we created a [list on Cloudflare](https://developers.cloudflare.com/waf/tools/lists/) containing all our known IPs and skip blocking to avoid confusion in the future.

![Slack message](images/slack-suspicious-ips.png)

### Blocking accessibility bots (from US)

We also put in place rate limiting rule for all the requests that was categorized as [Verified Bots](https://radar.cloudflare.com/traffic/verified-bots) by Cloudflare. After putting in all these rules, I try to regularly review the block requests to make sure they're not false positives - valid requests that was blocked - to further optimize our rules. There was a bunch of requests coming from the US, which we already put in custom rule to block but after looking at their user agent it seems a bit unusual - it contains the string `Google-Read-Aloud`. After some googling, I found out that Google uses that user agent for their [text-to-speech feature](https://developers.google.com/search/docs/crawling-indexing/read-aloud-user-agent) for accessibility purposes.

Having this user-agent does not necessarily mean that the requests are 100% valid because attackers can still [spoof their user agent](https://cheq.ai/blog/user-agent-spoofing/). So, I'll leave it up to you to decide if this is something that should be blocked but I think this is worth mentioning since in our fervor to prevent attackers from bringing down our systems we might also be hurting valid customers and affecting the accessibility of our service.

### Silly mistake: external-dns

Fast forward a few days, we got hit again with a DDoS attack but this time it was during lunch time, which was the peak hour for our customers. I thought, "Did the rule from last time not working anymore?". We checked the Security Analytics page on Cloudflare and noticed that Cloudlfare wasn't blocking any requests even though we already had the rule from last time.

I scratched my head for a bit wondering what we missed when my colleague pointed out that the DNS record for that domain wasn't proxied. So, I turned it back on but after a while it was turned back off. Then, I remember that we're using [external-dns](https://github.com/kubernetes-sigs/external-dns) to automate the creation of our records on Cloudflare and it was configured to disable the proxy option. So, whenever we enabled the proxy option, external-dns reverted it back as its supposed to. We end up turning off external-dns to make sure the proxy option would not get reverted. Read more below to know how you can turn on the proxy option on a per-ingress basis.

### Using annotation to proxy traffic through Cloudflare per Ingress

To enable proxying requests through Cloudflare on a per-Ingress basis when using external-dns, you can add the annotation `external-dns.alpha.kubernetes.io/cloudflare-proxied: "true"` to the Ingress. If you have multiple Ingress that all points to the same host, make sure to add the annotation to all of them. If not, external-dns will keep fighting itself, turning the proxy option onn and off forever.

## Conclusion

I've outlined several steps you can take if you're facing DDoS attacks in the future. Despite the success in mitigating the attacks so far, we know that there is no forever solution to DDoS. We have to keep up with the attacker and play Whac-A-Mole until they are bored and stop the attacks. When fighting DDoS attacks, I find it helpful to log the requests and review it regularly to avoid false-positives. It has been an eye opening experience for me and next time I'm asked how to protect from a DDoS, I can definitely say more than just put it behind Cloudflare.