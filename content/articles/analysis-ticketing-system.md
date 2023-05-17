---
title: "Analysis Ticketing System"
date: 2023-05-18T00:37:00+08:00
tags: [architecture, opinion]
draft: true
---

I kinda have an idea how you can scale the backend service of a ticketing system but I'm still stuck on the seating choice locking.

As some Twitter users have highlighted in the thread, it's not as simple as infinitely scaling the backend service using serverless functions or Kubernetes. The bottleneck usually lies on the DB tier.

Let's review the scenario:

An announcement was made that users can start buying ticket at 10AM. Before reaching 10AM, a bunch of users already ready with their devices (most use more than one for higher probability of getting the ticket). Once the clock reached 10AM, they'll start accessing the link to buy the ticket (some may started spamming the link before 10AM). (Reminds me of DDoS). 

Requirement: one seat can only be purchased by exactly one user. To simplify my analysis, one user can only buy maximum 1 seat/ticket.

## Waiting Room Queue

Based on the tweets that I saw, the ticketing vendor implemented a waiting room queue before you can enter the seat selection page. User @zulhhandyplast suggested they use Cloudflare product, Waiting Room, instead of rolling out your own waiting room implementation. How does a waiting room works? Here's a snippet from the Cloudflare Waiting room [landing page](https://www.cloudflare.com/en-gb/waiting-room/):

> Cloudflare Waiting Room allows organizations to route excess users to a custom-branded waiting room, helping preserve customer experience and protect origin servers from being overwhelmed with requests.

"...protect origin servers from being overwhelmed with requests." I think this is the most important part, which leads to improved reliability and consequently, user happiness.

Implementing a waiting room yourself seems quite hard. Will be nice if I can revisit this in the future and write more about this.

### How does a waiting room queue works?

From the [whitepaper](https://cf-assets.www.cloudflare.com/slt3lc6tev37/IydVtIa13olmKwJ1Dv8KW/43dc4e3cc26f9a2578750fab360172be/2_Pager___Layout_A_-_Standard_Cloudflare_-_A4.pdf):

> The Cloudflare Waiting Room limits the number of users allowed in the application while placing excess traffic into a virtual queue to provide a smoother, more predictable user experience.

The number of users allowed in the room is capped and tracked using session cookies. Once the user leaves the application or the session cookies expired, new users will be allowed in until the max cap is reached. So, instead of users accidentally DDoSing the origin servers by continously refreshing the page in the browser, the incoming traffic never hits the origin server. With experience handling large scale DDoS, it's a given that we can trust Cloudflare to be able to handle the traffic coming to our ticketing platform.

## I got into the room, now what?

Once the user manage to get into the room, they now need to "fight" with other users who can get the best seats first. Now we need figure out how can we lock a seat for a user so that once the seat is selected, no other user can select the same seat. If the user completes the purchase, now the seat is no longer available. When should we release the lock on the seat?

In the frontend, should there be a difference between a seat that is locked but not purchased yet and seats that's already taken and paid for?

### Real-time locking or refresh-based?

Should the user refresh the page to know the current status of the seat whether it is still locked or released already? As a customer, I would prefer if the status of the seats are updated in real-time without me having to refresh the page. If not real-time, there can be cases where the user selects a seat because it is shown as available but only after selecting the seat will the user be informed that the seat is no longer available or temporarily locked. Then it's a game of refreshing the page as fast as possilbe and randomly choosing a seat, which will significantly increase the load on the server.

Making this real-time means we will need to maintain a connection for each user accessing the page. Maintaining these connections is expensive and webservers usually have a limit how many connections it can keep track of at a time. Assuming the waiting room from before is working, we already set the max number of users that will be accessing the page, so there is already a hard cap in number of connections that we have to handle so we can already preprovision our hardware to handle the load.

### How do we keep track status of the seats?

Instead of maintaining the status of seats in RDBMS like PostgreSQL or MySQL, I think it is better to use in-memory data store like Redis. The [EXPIRE](https://redis.io/commands/expire/) command seems like a perfect choice for locking the seat for a certain period and automatically releasing the lock after the period ended. How can the backend knows when a key expired so that it can push a new message to the frontend to update the seat status? Keyword: [keyspace notification](https://redis.io/docs/manual/keyspace-notifications/).

I'm leaning on having a separate service handling this real-time seat status update. Once a user loads the page, it'll start a websocket connection to this seat status service which will set the seat number as key in Redis with a expiry time. Once the key expired, this service will be notified by Redis and in turn it will send a message through the websocket connection that it maintained to update the status of the seat on the frontend.


### Payment processor as the bottleneck?

What can we do if 3rd-party payment processor not behaving?

### I manage to lock a seat!

Congrats! Now since the seat is locked, user will be given a fixed duration to finish the transaction and pay for the ticket. Once payment is confirmed, we can update the DB and then tell the seat locking service to update status of the seat lock to "taken".

Once we booked the user seat, we can dispatch a background job to send an email to the user as confirmation and also includes the ticket details. It's okay to use a background job here so that user can get instant response instead of having to wait longer. In the instant response that is sent to user, we should manage their expectations and inform them that it may take a few minutes for the ticket to be sent to their email.

## The Plan

TLDR

- waiting room queue
- websocket for real-time connections to update seat status
- redis for keeping track of seat status (available, locked, taken)
- rdbms for persisting seating record after payment is done
- background job for non-time sensitive tasks like sending email
