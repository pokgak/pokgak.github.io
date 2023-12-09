---
title: "Terraform modules: be opinionated"
date: 2023-12-08T17:21:59+08:00
tags:
  - opinions
  - terraform
  - design
---

> Modules are containers for multiple resources that are used together.

Terraform modules is a way to bundle a bunch of Terraform resources into one group. Although not explicitly mentioned in the definition, it is also a way to provide an **abstraction** to the resources inside the module and only expose inputs and outputs that are relevant to the users of the module.

## Terraform Module as an Abstraction Layer

A Terraform resource usually tends to be generic in that it allows you to configure it multiple ways through the input variables that it can accept. For example, the `aws_mskconnect_connector` resource has [3 options](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/mskconnect_connector#worker_log_delivery-configuration-block) for log delivery: CloudWatch Logs, Kinesis Data Firehose, or S3. In most cases, your module **shouldn't** expose all 3 options to your users. Your organization probably already has some standard place where you send you logs to e.g. S3 for example where it gets forwarded to another logs search service for later use.

Therefore, your module should only expose the S3 option and leave out CloudWatch Logs and Kinesis Data Firehose from your module. By doing this you eliminate the choice from the user and they don't have to think which one to use. Your Terraform code can be a lot simpler too.

## Module Abstraction in Action

Here's an example module code when including all 3 options:

```terraform
variable "log_delivery_s3" {
  type = object({
    bucket_arn = string
    prefix     = optional(string, "mskconnect-logs")
  })

  default = null
}

variable "log_delivery_cloudwatch_logs" {
  type = object({
    log_group = string
  })

  default = null
}

variable "log_delivery_firehose" {
  type = object({
    delivery_stream = string
  })

  default = null
}

resource "aws_mskconnect_connector" "example" {
  name = "example"

  log_delivery {
    worker_log_delivery {
      dynamic "s3" {
        for_each = var.log_delivery_s3 != null ? [1] : []

        enabled    = true
        bucket_arn = var.log_delivery_s3.bucket_arn
        prefix     = var.log_delivery_s3.prefix
      }

      dynamic "cloudwatch_logs" {
        for_each = var.log_delivery_cloudwatch_logs != null ? [1] : []

        enabled   = true
        log_group = var.log_delivery_cloudwatch_logs.log_group
      }

      dynamic "firehose" {
        for_each = var.log_delivery_firehose != null ? [1] : []

        enabled         = true
        delivery_stream = var.log_delivery_firehose.delivery_stream
      }
    }
  }
}
```

And here's an example when we only offer S3 option:

```terraform
variable "log_delivery_s3" {
  type = object({
    bucket_arn = string
    prefix     = optional(string, "mskconnect-logs")
  })

  default = null
}

resource "aws_mskconnect_connector" "example" {
  name = "example"

  log_delivery {
    worker_log_delivery {
      s3 {
        enabled    = var.log_delivery_s3 != null
        bucket_arn = var.log_delivery_s3.bucket_arn
        prefix     = var.log_delivery_s3.prefix
      }
    }
  }
}
```

See how simple and shorter the code become? No need to use those `dynamic` blocks just to conditionally add or remove the log delivery option block anymore.

## But I might need to use that other option in the future...

[YAGNI.](https://martinfowler.com/bliki/Yagni.html)
