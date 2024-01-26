---
title: "Using Steampipe + DuckDB for VPC Flow Logs Analysis"
date: 2024-01-26T20:00:00+08:00
tags: [duckdb, steampipe, aws, cloud, tools, data, sql]
---

As a so called [Tech Janitor](https://x.com/tevanraj/status/1747920076203057273?s=20), I've been tasked to clean up one of our AWS accounts at work and that account have a bunch of EC2 instances that no one knows what they all do. So, I've decided to use one of AWS features, VPC Flow Logs, to first identify which EC2 instances are still being used and which are not.

## Setting up the VPC Flow Logs and query using DuckDB

For our purpose, I've setup VPC flow logs to send all the traffic data to a S3 bucket that we'll refer to as `vpc-flow-logs-bucket` in this post. The flow logs are stored in a Parquet format for querying later using [DuckDB](https://duckdb.org).

Once the flow logs file are sent to S3, I'll be able to query them using DuckDB. To do that we will need to install the `aws` and `httpfs` extensions.

From DuckDB shell:
```
> INSTALL aws;
> INSTALL httpfs;
```

We also need to load our AWS credentials into DuckDB. Luckily, DuckDB has a built-in command to do that:

```
> CALL load_aws_credentials();
┌──────────────────────┬──────────────────────────┬──────────────────────┬───────────────┐
│ loaded_access_key_id │ loaded_secret_access_key │ loaded_session_token │ loaded_region │
│       varchar        │         varchar          │       varchar        │    varchar    │
├──────────────────────┼──────────────────────────┼──────────────────────┼───────────────┤
│ <redacted>           │ <redacted>               │                      │ eu-west-1     │
└──────────────────────┴──────────────────────────┴──────────────────────┴───────────────┘
```

This will look for your AWS credentials based on the standard AWS credentials file location. If you have multiple profiles in your credentials file, you can specify which profile to use by passing the profile name as an argument to the `load_aws_credentials` function.

Now it's time to load our VPC flow logs from S3 into a table in DuckDB. You can replace the `year/month/day/hour` with the actual date and hour of the flow logs that you want to load or use `*` for any or all of them to load all the flow logs. I'll be loading all the flow log records into a table `flow_logs` in DuckDB.

This might take a while since DuckDB will have to download the Parquet files from S3 and load them into memory. It took several minutes to finish loading in my case.

```
> CREATE TABLE flow_logs AS SELECT * from read_parquet('s3://vpc-flow-logs-bucket/AWSLogs/<aws-account-id>/vpcflowlogs/<region>/<year>/<month>/<day>/<hour>/*.parquet')
```

Now we can see that the flow logs records only contains the network interface ID (ENI) of the EC2 instance but not the EC2 instance ID or name itself. That won't be enough for my use case since I want to identify which traffic is flowing to which EC2 instance. Therefore, we need to correlate the ENI with the EC2 instance ID and here's where Steampipe comes in.

## Steampipe: directly query your APIs from SQL

[Steampipe](https://steampipe.io) is a tool that allows you to query APIs from SQL. It supports a lot of different APIs from AWS, GCP, Azure, Github, etc. You can also write your own plugins to support other APIs. I'll be using it to query my AWS account for the EC2 instance ID and name based on the ENI ID from the VPC flow logs.

## Life before Steampipe

Usually to do the things I'm about to show below, I'll pull the data from AWS using the aws-cli and then massage it using `jq/yq/awk/sed`, if I'm desperate maybe Python. Then I'll use some other tools to visualize it or export to CSV. With Steampipe, pulling the data from AWS is so simple and using SQL to correlate the data with other information source is a breeze.

## Steampipe is just Postgresql

Under the hood, Steampipe is running PostgreSQL and it even allows you to run it as a standalone instance running in the background and allows [connecting to it from any third-party tools](https://steampipe.io/docs/query/third-party) that can connect to a Postgresql instance. Here's where it gets interesting, DuckDB has the capability to connect to any PostgreSQL database and query it as if all the data inside that database is coming from the DuckDB. This means that we can use Steampipe as a data source for DuckDB and access all of the AWS resources data available in Steampipe.

## Setting up Steampipe and DuckDB connection

To run Steampipe as a service mode, you'll need to run the following command to start the PostgreSQL instance and get the credentials for connecting to it:

```
$ steampipe service start
Database:

  Host(s):            127.0.0.1, ::1, 2606:4700:110:8818:e17b:f78c:6c52:dccb, 172.16.0.2, 2001:f40:909:8e2:207a:634a:2070:d99d, 2001:f40:909:8e2:1cdb:75da:2a70:4b05, 192.168.100.23, 127.0.2.3, 127.0.2.2
  Port:               9193
  Database:           steampipe
  User:               steampipe
  Password:           ********* [use --show-password to reveal]
  Connection string:  postgres://steampipe@127.0.0.1:9193/steampipe
```

Then inside DuckDB shell, you can connect to the Steampipe PostgreSQL instance using the following command:

```
> ATTACH 'dbname=steampipe user=steampipe password=23e2_4853_bd96 host=127.0.0.1 port=9193' AS steampipe (TYPE postgres);
> use steampipe.aws;
> SHOW tables;
show tables;
┌─────────────────────────────────────────────┐
│                    name                     │
│                   varchar                   │
├─────────────────────────────────────────────┤
│ aws_accessanalyzer_analyzer                 │
│ aws_account                                 │
│ aws_account_alternate_contact               │
...
```

Now we can see all the tables from the Steampipe Postgresql instance. For my use case I'll be using the `aws_ec2_network_interface` table which contains both the network interface ID (ENI) and the EC2 instance ID that I can use `JOIN` together with the VPC flow logs records to map the records to the EC2 instance ID.

## JOIN-ing it all together

Here's an example query that will give me the count of all incoming traffic to the instances grouped by the port number:
```
select
    i.title,
    fl.dstport,
    count(fl.dstaddr) traffic
from network_interfaces ni
left join flow_logs fl on fl.interface_id = ni.network_interface_id
left join instances i on i.instance_id = ni.attached_instance_id
where
    fl.dstaddr = i.private_ip_address
group by i.instance_name, fl.dstport
order by traffic desc, dstport asc
```

From this information I'll be able to guess which service is running on those instances and take the next step towards migrating or depecrating the instances.

## Conclusion

It is kinda mindblowing that I can do all this using SQL. Both Steampipe and DuckDB are great products and the flexibility of those tools allows me to
pick and choose the best tool for the job. I first came across Steampipe in one of the podcasts that I listen to but haven't really used it much. Now, after having the opportunity to use it to solve one of my problems, I'll definitely pay more attention to it to make my tech janitor life easier in the future ;)
