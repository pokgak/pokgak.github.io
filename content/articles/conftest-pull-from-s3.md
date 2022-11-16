---
title: "Atlantis: run policy check using policies from S3"
date: 2022-11-16T22:00:00+08:00
tags: [atlantis, opa, conftest, policy, s3, terraform]
---

[Atlantis](https://www.runatlantis.io) is an application used for collaborating on a Terraform code base using pull requests and one of the feature that it has is to run [conftest](conftest.dev) and test a set of defined OPA policies. At the moment I'm writing this article, Atlantis only supports using local sources i.e. local filesystem as the source of the policy. In this article, I'll show an example of how to use an S3 bucket instead as the source for the policies.

## Custom workflow and `run` step

Atlantis supports using [custom workflows](https://www.runatlantis.io/docs/custom-workflows.html) to override the default commands that it runs and as part of that feature, it supports defining any [custom commands](https://www.runatlantis.io/docs/custom-workflows.html#running-custom-commands) to run as part of the steps for each stage. We will be ~abusing~using this feature to override the default `conftest` command that Atlantis uses and specify our policy through the `--update` flag of `conftest`

## conftest `--update` flag

By using `--update` you can tell `conftest` to pull the policy first every time it wants to run the tests. We will be using an S3 bucket as our source but before we can pull from S3, you have to make sure that wherever the Atlantis server is running, it can access and have permission to pull objects from the bucket. In my case, Atlantis is running as a StatefulSet inside a Kubernetes cluster so I have already configured the IAM permission needed for it to access the bucket.

`conftest` is using the [go-getter package](https://github.com/hashicorp/go-getter) underneath to pull these packages so technically it should be possible to also pull from other sources that `go-getter` supports, other than just S3.

## Result

Combining both of the features described above, here's an example of a simplified [repo config](https://www.runatlantis.io/docs/server-side-repo-config.html) that I use:

```yaml
# minimal config for brevity; you might need to configure more options to make atlantis works properly
repos:
  - id: github.com/$ORG/$REPO
    workflow: custom

workflows:
  custom:
    policy_check:
      steps:
        - show # important don't skip this step
        - run: conftest test $SHOWFILE --update s3::https://s3-us-east-1.amazonaws.com/$BUCKET_NAME/policy

policies:
  policy_sets:
    - name: policy-from-s3
      path: /home/atlantis/policy
      source: local
```

In the example above, under the `workflows` key, I'm defining a custom workflow named `custom` and inside that custom workflow, I'm overriding the default `policy_check` steps with my own. My custom `policy_check` steps consists of the `show` step and the custom `run` step. The `show` step is crucial since this is when Atlantis will run `terraform show` to convert your Terraform planfile to a JSON formatted file.

When using the custom `run` step, Atlantis will store the path to this JSON formatted file in variable `$SHOWFILE` so when I ran my conftest command you can see that I'm using `$SHOWFILE` to run `conftest` against the file. Optional: if you want to run `conftest` against the Terraform files too, you can add `*.tf` after `$SHOWFILE` and it will include all the `*tf` files in that project directory.

Next comes the `--update` flag, to specify the S3 bucket, I'm using a URL format that is [specified by the `go-getter` package](https://github.com/hashicorp/go-getter#s3-bucket-examples) replacing `$BUCKET_NAME` with the bucket name that I have configured with the correct permission and network access. Inside the S3 bucket, this is how I structured the files. I put all the OPA policies inside a folder `policy` since `conftest` complains when I just put all the policies directly at the root level inside the bucket. YMMV.

```
$BUCKET_NAME/
├─ policy/
│  ├─ stop_it.rego
│  ├─ dont_kill_server.rego

```

After defining our custom workflow, we can specify the custom worklow as the default workflow for a repo. This is done by setting the `repos[].workflow` value to the name of our custom workflow, in my case it's `custom`. 

Next, as part of the using the policy check feature in Atlantis, you are required to set the `policies` values. You can refer to the [docs](https://www.runatlantis.io/docs/server-side-repo-config.html#policies) for the full configuration required. Inside the `policies` key, there is a required `policy_check` key that is used to specify where Atlantis can find the OPA policies to use when running `conftest`. Usually, this is a folder on a local filesystem already containing the policies but in our case, since we're using the `--update` flag, we just need to specify any folder on the local filesystem that will be writable by the Atlantis user. You can see in the example above that I'm using `/home/atlantis/policy`.


## Conclusion

That's all you need to do configure to make Atlantis pulls policies from S3 (and include Terraform source code files in your `contest` run). Shoutout to a [DoorDash engineering blog post](https://doordash.engineering/2022/09/20/how-doordash-ensures-velocity-and-reliability-through-policy-automation/) which mentioned briefly that they pulled their policies from S3 and made me curios how to do the same using Atlantis. You can mention me on Twitter (@pokgak73) if this article has helped you. That would most definitely made my day :)
