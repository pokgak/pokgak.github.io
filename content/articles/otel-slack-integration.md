---
title: "Instrumenting a Slack bot with OpenTelemetry"
date: 2022-08-13T17:43:00+08:00
tags: [Observability, otel-slack]
images:
- images/slack-span-lifetime.png
---

*Note: I'm using pseudocode in the code example in this article to keep the article brief. Please refer to the official Slack and OpenTelemetry documentation for the actual code.*

I've talked about the basics of OpenTelemetry in my previous article. In this one, I'll explain more on how we're integrating OpenTelemetry with our Slack-based application.

At the end of this article, this is roughly how the span lifetime and events created will look like:

![Summary of spans and events created](images/slack-span-lifetime.png)

## Slack BoltJS Socket Mode

Compared to the a standard HTTP request/response, we're using BoltJS with socket mode. This gives us the advantage of not having the application exposed publicly to be able to accept requests from Slack but this also means that we cannot just use the auto-instrumentation for HTTP developed by the community.

Socket mode uses WebSocket to establish connection to Slack and exchange messages through that connection. There is no official auto-instrumentation support for the `ws` library that is used by BoltJS socket mode but I found [opentelemetry-instrumentation-ws][1], a 3rd-party library for `ws` library auto-instrumentation. 

Spent a few days integrating it into our application and in the end I concluded that the auto-instrumentation provided by the opentelemetry-instrumentation-ws is too low-level. Our goal is to track user interactions with the application - when they use the bot, which option they choose, what were they trying to do, and whether the interaction ends successfully or with an error. The library, however, created spans when a new connection is established between our application and Slack but no spans or events for user interactions.

So, the conclusion? We'll instrument the application manually.

## Creating and Ending Spans

Since this application is used company-wide, it's highly likely that multiple users will be using it in parallel. To track user interactions independent from each other, we'll also need separate spans for each user. 

I decided to go with an object `spanStore` storing the user spans. Like a singleton pattern, a new span will be created for that user if it doesn't exist yet in `spanStore`, otherwise it will just return the existing user span.

```javascript
spanStore = {}

function getUserSpan(username) {
    if (user in spanStore) {
        return spanStore[username]
    }

    span = startSpan(username)
    spanStore[username] = span

    return span
}
```

Now that we have a function to create the span, when in the lifetime of the incoming event do we create the span? Ideally, as early as possible before anything else so that we can track everything. BoltJS supports setting a [global middleware][2] that will be called before the event handler function are called. This is where I call the `getUserSpan()` function above. For the first event for that user, it will create a new span and for the next events it will just return the existing spans that I can use.

Next, when do you end the span? Due to how the application works, we're assuming that each user can only have one session at one time and at the end there will always be an finishing event triggered when the user finished their interaction with the application. Based on that fact, I wrote an event listener that will respond to this finishing event by calling the OTel function to end the span and remove the span from the `spanStore` object above.

```javascript
app.event({id: 'finishing_event'}, async ({username}) => {
    span = getUserSpan(username)
    span.end()
    removeSpanFromSpanStore(span)
})
```

## Tracking User Actions with Span Events

With these, we have a separate span for each user for the whole duration of their interaction with the application. With only one span, we don't have insights yet into what the user are doing, which actions are taken by the user, so we'll need a way to track user actions.

With Slack BoltJS, we can trigger a listener function on every user interaction. I wrote a function that will create a new span event using the user input id as the event name. I also passed in the whole payload so that the we can see the payload of user actions later when debugging issues. Add this as another global middleware, now we're creating a new event for every user actions.

```javascript
app.action('callback_id', async ({username, action_id, payload}) => {
    span = getUserSpan(username)
    span.addEvent(action_id, {payload})
})
```

## Confession

I'm actually not convinced that my way of doing this is correct. One of the reason is that since I use one root span for the whole interaction for a user, I'm also tracking the duration taken by the user to do the next action. From our perpective, this made the duration of the span tracked is now kinda useless for us since it also includes factors that are not controllable by us (time taken for users to do the next action).

Instead of one root span and creating new span events for every user interaction, maybe a new span for each interaction, linked to the previous span would be better since we only track the duration that we are in control of, not how long the user takes to click a button.

Nevertheless, since I already implemented like this now, let's see how that will turn out. Like the saying, you either die a hero, or you live long enough to see yourself become the villain.

[1]: https://www.npmjs.com/package/opentelemetry-instrumentation-ws
[2]: https://slack.dev/bolt-js/concepts#global-middleware
