---
title: "Wrapping my head around conftest and OPA"
date: 2022-11-12T13:00:00+08:00
tags: [OPA, conftest, policy]
---

I started using OPA at my $dayJob recently and there are some parts that I think is not intuitive to grok for beginners.

First, what is the relationship between OPA, Rego, and conftest? Rego is a declarative language used to write OPA policies. Then, OPA is the engine that takes in the policies written in Rego and evaluates it, producing a set of documents called "rules". You can use OPA and the Rego language directly to write policies for your config files but using conftest will make the DX much better.

## Rego Basics

The Rego language focuses on querying the input to look for a given condition. If the input satisfies the query, then it will produce the document. 

### Variable Assignments

Variable assignment in Rego works the same like in other language. The expression `foo := "hello"` will assign the value `"hello"` to the variable `foo`. 

One difference in Rego is that it implicitly assigns value `true` to the document if the condition given evaluates to `true`. In the example below, there's two ways to write the Rego expression. Rego actually implicitly assigns the value `true` so we can also remove 

```opa
foo := "hello"

# first way: explicitly assigns `true` to `result` when condition is satisfied
result := true if foo == "hello"

# Rego implicitly assigns `true` to `result` when condition is satisfied
result if foo == "hello"
```

Let's bring this up to next level. Most of the time, the condition you're checking is not as straight forward as checking the value against a static value. You might also need to evaluate expressions in between and save the intermediary values in a variable to help improve readability. In previous example we only used a one-liner for the rule body but you can also have more complex rule body like the following using curly braces.

### Declarative Rego Language

The Rego language is declarative and useful to query data structures for any value. Consider the following example ([Rego playground link](https://play.openpolicyagent.org/p/gZcwi6zzAA)):

Let's assume our input is an array of object, each containing the keys "id" and "name". In this policy we're checking that the objects doesn't have any forbiden value for "name".

```opa
forbidden_names := ["foobar", "john"]

user_forbidden if input.users[i].name == forbidden_names[j]
```

This code would look something like this in Python:

```python
users = [{"name": "foo"}, {"name": "bar"}]
forbidden_names = ["foobar", "john"]

user_forbidden = []
for i in range(len(input.users):
  for j in range(len(forbidden_names)):
    user_forbidden.push(input.users[i].name == forbidden_names[j])

return any(user_forbidden)
```

For both codes, `user_forbidden` will evaluate to `true` if one of the user name is included in the `forbidden_names` list. In the Python code, we used `for` loops with the `any()` function to check that none of the value is true. In the Rego code, we don't have to use any for loop or iterate through the user list. `forbidden_names[i]` means "for any of the values in `forbidden_names`. So in our Rego code, we essentially tells OPA, if any of the value in `input.users` is the same as any of the value in `forbidden_name`, then return set the value of `user_forbidden` to `true`.

In this case, since we are not using the index `i` and `j` to reference the value at those index anywhere in the policy, we can simplify it more by using `_` (underscore) instead for the index. `_` is like a throwaway value and we don't care about the index, we just care if one of the values is the same in `user.input` and `forbidden_names`.

```opa
user_forbidden if input.users[_].name == forbidden_names[_]
```

### More complex policies

Before this our policies are all simple one liner but Rego also supports writing the rule body in multiple lines. In the example below, we are adding an exception to the rule that the previous rule doesn't apply to user with `id == 5`. So if one our user `name` value is `john` but have `id == 5` then `user_forbidden` won't evaluate to `true`. Note that we are using the same index `i` when accessing the `name` and `id` property. This means we are referring to the same user. If we use `_` or a different index when accessing the `name` and `id`, the rule will evaluate to `true`.

If any of the expressions inside the rule body evaluates to `false` or `undefined` then it will stop evaluating the rule body and return `undefined` for `user_forbidden`.

```opa
forbidden_names := ["foobar", "john"]

user_forbidden if {
    input.users[i].name == forbidden_names[_]
    input.users[i].id != 5

    false
    print("this will not be printed")
}
```

## Using conftest

Previously, we used arbitrary names for our rules but conftest introduces a few keywords that we must use so that it can detect any failed rules and includes it in the output. Conftest will pick up any rules with name `deny`, `warn`, or `violation` and the summary will be shown in conftest output.

```
➜ tree conftest
conftest
├── input.json
└── policy
    └── names.rego
```

```
# input.json
{
    "users": [
        {
            "id": 1,
            "name": "john"
        },
        {
            "id": 2,
            "name": "bar"
        },
        {
            "id": 3,
            "name": "foobar"
        }
    ]
}
```

```opa
# policy/names.rego
package main

import future.keywords.contains
import future.keywords.if

deny contains msg if {
    forbidden_names := ["john"]
    name := input.users[_].name
    name == forbidden_names[_]
    
    msg := sprintf("username %v is not allowed", [name])
}

warn contains msg if {    
    id := input.users[_].id
    id == 2
    
    msg := sprintf("id %v is not allowed", [id])
}
```

Run conftest against our input file:
```
➜ conftest test input.json --policy policy/ 
WARN - input.json - main - id 2 is not allowed
FAIL - input.json - main - username john is not allowed

2 tests, 0 passed, 0 warnings, 2 failures, 0 exceptions
```

Note the values output here, the `deny` rule will be output as `FAIL` if the rule passes while the `warn` rule is counted as `WARN`. Here, conftest takes the output values from the OPA engine and formats the output for us to make it easier to interpret or integrate with other tools. You can also change the output format of conftest by passing in the `--output` flag. I like the `github` output since it will automatically prints the output in a format that Github Actions understoods and will surface error in Github UI approriately. You can also output it as JSON, which is great if you want to process the result output using tools like `jq`.

```
➜ conftest test --help
[...]
  -o, --output string         Output format for conftest results - valid options are: [stdout json tap table junit github] (default "stdout")
```

JSON output:
```
➜ conftest test input.json --output json
[
  {
    "filename": "input.json",
    "namespace": "main",
    "successes": 0,
    "warnings": [
      {
        "msg": "id 2 is not allowed"
      }
    ],
    "failures": [
      {
        "msg": "username john is not allowed"
      }
    ]
  }
]
```

### parsers: using other format as input files

Until now all our input has been in JSON format but conftest also has built-in parsers that can automatically detect the input format and converts it to JSON for us. Example is for HCL2 code used for Terraform:

```hcl2
# input.tf
resource "aws_imaginary_resource" "this" {
  name = "this"
  instance_type = "r5.4xlarge"
  security_groups = ["12345", "45678"]
}

resource "aws_imaginary_resource" "that" {
  name = "that"
  instance_type = "t3.medium"
  
  ingress {
    port = 1234
    cidr = ["0.0.0.0/0"]
  }
}
```

We can use `conftest parse` to see how conftest will parse the Terraform file and then write our policy based on the parsed input.

```
➜ conftest parse input.tf
{
  "resource": {
    "aws_imaginary_resource": {
      "that": {
        "ingress": {
          "cidr": [
            "0.0.0.0/0"
          ],
          "port": 1234
        },
        "instance_type": "t3.medium",
        "name": "that"
      },
      "this": {
        "instance_type": "r5.4xlarge",
        "name": "this",
        "security_groups": [
          "12345",
          "45678"
        ]
      }
    }
  }
}
```


