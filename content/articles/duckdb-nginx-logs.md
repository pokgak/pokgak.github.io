---
title: "Using DuckDB to analyze NGINX logs"
date: 2024-10-27T18:15:00+08:00
tags: [security, duckdb, analytics, ingress-nginx, k8s]
---

As part of my recent [DDoS mitigation effort](https://pokgak.xyz/articles/we-got-ddosed/), I had to go through millions of nginx logs to identify patterns that I can use to further improve our custom WAF rules on Cloudflare. This article shows what I did to be able to run some analysis on the logs using DuckDB.

## Making the hard things easy

### Changing the log format

> "To solve a problem that is difficult, you must first make it easy."

The default nginx access logs format looks something like this:

```
'$remote_addr - $remote_user [$time_local] ''"$request" $status $body_bytes_sent ' '"$http_referer" "$http_user_agent"'
```

Parsing it is definitely possible using regex as shown by [this article](https://www.alibabacloud.com/help/en/sls/user-guide/parse-nginx-logs) but why bother when you have the option to change the format and make it easier to parse using DuckDB. To do so we will be configuring ingress-nginx controller in our cluster to log in JSON format. You can set the custom log format using the `log-format-upstream` config and set `log-format-escape-json` to make sure that the variables are escaped properly for use in as JSON variables.

This is the log format that I'm currently using:
```
'{"timestamp": "$time_iso8601", "requestID": "$req_id", "proxyUpstreamName": "$proxy_upstream_name", "proxyAlternativeUpstreamName": "$proxy_alternative_upstream_name","upstreamStatus": "$upstream_status", "upstreamAddr": "$upstream_addr","method": "$request_method", "host": "$host", "uri": "$uri", "uriNormalized": "$uri_normalized", "uriWithParams": "$request_uri", "status": $status,"requestSize": "$request_length", "responseSize": "$upstream_response_length", "userAgent": "$http_user_agent", "remoteIp": "$remote_addr", "referer": "$http_referer", "latency": "$upstream_response_time s", "protocol":"$server_protocol"}'
```

### Mapping customer IDs to generic placeholder

One thing I don't know how to do with DuckDB is normalizing URIs. Given a URI path containing user ID 12345678 like `/users/1234567/info`. How do I group by path where I ignore the middle section and group it as if all the URIs are like `/users/:userId/info`. I tried regex and patterns but couldn't get it to work. If you know how to do it please DM me on Twitter, I'd really appreciate it.

I found a way to do it in nginx instead. It works but its definitely not scalable. I use the `ngx_http_map_module` module to match URIs with certain paths and then convert it to a generic version of that path.

```
map $uri $uri_normalized {
    "~^/user/(.*)$" "/user/:ID";
    default $uri;
}
```

This snippet will do the following: for each of the variable `$uri`, map it to a new variable `$uri_normalized`. When `$uri` value matches the regex `^/user/(.*)$`, the replace the value with new value `/users/ID`. If no matching regex found, then use default to the value of `$uri`.

With those configured, you can proceed to ship the logs to your logging backend of choice to retrieve later.

## Fetching the logs from Loki

I'm using Loki as my logging backend. Loki provides an API endpoint you can use to fetch the logs and to make things easier they also have an CLI tool called [logcli](https://grafana.com/docs/loki/latest/query/logcli/).

To fetch all nginx logs from my production cluster, this is the command that I used:

```
$ logcli query -oraw --from="2024-10-24T00:00:00+08:00" --to="2024-10-24T22:00:00+08:00" --part-path-prefix="logs" --parallel-max-workers=100 --parallel-duration=15m '{namespace="ingress-nginx", cluster="production"} | json | __error__=``'
```

* `-oraw` is to set the output format of the logs. I'm using the raw format here so that I can get the same JSON input that I sent to Loki
* `--from` and `--to` are self-explanatory but I did have some problem specifying the correct format that the tool will accept and the official docs was quite confusing
* `--part-path-prefix` use this prefix to name the files when downloading multiple files in parallel
* `--parallel-max-workers` sets the max parallel workers to be used. Note that the actual workers used depends also on the available tasks based on the parallel duration configured
* `--parallel-duration` is the duration size to use for each file. combined with the `--from` and `--to` option, this option determines how many files will be created e.g. for 1 hour duration and you've specified the `--parallel-duration` there will be 4 files created, each containing logs from specific 15 minutes section.

## Loading the logs into DuckDB

I'm using the CLI version of duckdb but you can also do this using the embedded library in other languages of your choice.

To read the files we've pulled from Loki and create a table with it I used this command:

```
create table logs as select * from read_json('logs_*.part', format='auto', columns={timestamp: 'TIMESTAMP', method: 'VARCHAR', host: 'VARCHAR', uri: 'VARCHAR', uriNormalized: 'VARCHAR', status:'INT', remoteIp: 'VARCHAR', is_authed: 'BOOLEAN', userAgent: 'VARCHAR'});
```

`read_json` can automatically create all the columns based on the keys in the JSON files but I want it to treat certain columns as specific data types so that's why I'm specifying the columns manually here.

After loading the columns into the table you can check the number of rows using this commands:

```
select count() from logs;
```

In my case, for a day's worth of logs from nginx, I have around 60 million rows. On idle, its using around 8GBs of RAM. If you have longer periods of logs to analyze, then definitely opt for a beefier machine or else DuckDB will crash.

## Running queries

Its the fun part. Here's some queries that I find useful:

### Highest requests per minute grouped by IP

I use this information to set the proper value to use in our Cloudflare rate limiting rule. By looking at existing request rate I'm reducing the chance of rate limiting our actual customers.

```
select
        (hour(timestamp) + 8) % 24 as hour,
        minute(timestamp) as minute,
        remoteIp,
        count() as total
from logs
where remoteIp not in ('X.X.X.X', 'Y.Y.Y.Y', 'Z.Z.Z.Z') --production NAT gateway IPs
and remoteIp not like '162.158.192.%'   --cloudflare IPs
group by all
order by total desc
limit 5;
```

### IP address with the highest number of request to a particular host

```
select remoteIp, count() as total from logs where host = 'subdomain.example.com' group by all order by total desc limit 10;
```

### Checking the paths an IP have been sending requests to

I'm including the result from the query here since it shows that this particular IP most likely are using a scanner to find vulnerable endpoints on our service.

```
select uri, count() as total from logs where remoteIp = '152.32.189.70' group by all order by total desc limit 20;
┌─────────────────────────────────────────────────────────────────┬───────┐
│                               uri                               │ total │
│                             varchar                             │ int64 │
├─────────────────────────────────────────────────────────────────┼───────┤
│ /                                                               │    10 │
│ /favicon.ico                                                    │     6 │
│ /api/user/ismustmobile                                          │     6 │
│ /h5/                                                            │     4 │
│ /m/                                                             │     4 │
│ /api                                                            │     4 │
│ /app/                                                           │     3 │
│ /api/config                                                     │     3 │
│ /leftDao.php?callback=jQuery183016740860980352856_1604309800583 │     2 │
│ /public/static/home/js/moblie/login.js                          │     2 │
│ /static/home/css/feiqi-ee5401a8e6.css                           │     2 │
│ /client/static/icon/hangqingicon.png                            │     2 │
│ /admin/webadmin.php?mod=do&act=login                            │     2 │
│ /static/images/auth/background.png                              │     2 │
│ /index/index/home?business_id=1                                 │     2 │
│ /stage-api/common/configKey/all                                 │     2 │
│ /Public/home/common/js/index.js                                 │     2 │
│ /ws/index/getTheLotteryInitList                                 │     2 │
│ /app/static/picture/star.png                                    │     2 │
│ /resource/home/js/common.js                                     │     2 │
├─────────────────────────────────────────────────────────────────┴───────┤
│ 20 rows                                                       2 columns │
└─────────────────────────────────────────────────────────────────────────┘
```

## Conclusion

This has been an adhoc task and when I was told to do some analysis on the logs I immediately think of the tools I'm familiar with which is DuckDB to do the analysis. I'm aware there are better tools out there and we are currently evaluating using OpenSearch Security Analytics to automatically do this kind of detection in the future. Hopefully, I can talk about it soon. If any of you data analyst/data engineer out there got better ways to do the things I'm doing feel free to tweet me @pokgak73 on Twitter.