---
title: "Docker's lesser known command: buildx bake"
date: 2024-11-16T00:52:00+08:00
tags: [docker, container, multiplatform, bake, buildx]
---

Have you seen someone use `docker buildx bake` before? Me neither... until I need to build a multiplatform image for our services. In this blog post I'll walk through the reason why I ended up being forced to use `docker buildx bake`.

## Background

I am on a journey to run our services on Graviton on AWS and Gravitons CPU is using arm64 architecture. To make this migration smooth I decided there will be a transionary period where there might be both architecture running on separate environments. This means I need to make sure that we're building both the `linux/amd64` and `linux/arm64` variant of the images.

We're using one monorepo per team for our services (don't ask me how we got there). For each monorepo there will be codebase for multiple services side by side and the Dockerfile are also managed together in one folder. To avoid code duplication, we have one `base.Dockerfile` that will generate a local `base` image which will be referred to when building other services.

For reference, this is how the files look like:

```Dockerfile
# ./cicd/docker/base.Dockerfile
FROM node:21-alpine as base
...
RUN pnpm install --production
...
```

```Dockerfile
# ./cicd/docker/serviceA.Dockerfile
FROM node:21-alpine
WORKDIR /app
COPY --from=backend-builder /usr/src/app /app
...
```

```yaml
# ./cicd/docker/docker-compose.yaml
services:
  base:
    build:
      dockerfile: ./cicd/docker/base.Dockerfile
  serviceA:
    build:
      dockerfile: ./cicd/docker/serviceA.Dockerfile
  serviceB:
    build:
      dockerfile: ./cicd/docker/serviceB.Dockerfile
```

When building the service we run the following command:

```
$ docker compose -f ./cicd/docker/docker-compose.yaml build base
$ docker compose -f ./cicd/docker/docker-compose.yaml build serviceA
```

This will first build the `base` image and then use that image to build `serviceA`. It works without issue.

## Adding Multi-platform support

The Docker Compose specification supports specifying the we want to build for using the `platforms` key. So, adding that to our `docker-compose.yaml`, it'll now look like this with multi-platform support:

```yaml
# ./cicd/docker/docker-compose.yaml
services:
  base:
    build:
      dockerfile: ./cicd/docker/base.Dockerfile
      platforms:
        - linux/amd64
        - linux/arm64
  serviceA:
    build:
      dockerfile: ./cicd/docker/serviceA.Dockerfile
      platforms:
        - linux/amd64
        - linux/arm64
  serviceB:
    build:
      dockerfile: ./cicd/docker/serviceB.Dockerfile
      platforms:
        - linux/amd64
        - linux/arm64
```

Now let's run the same `docker-compose build` command like before and we get...

```
[+] Building 0.0s (0/0)
Multi-platform build is not supported for the docker driver.
Switch to a different driver, or turn on the containerd image store, and try again.
Learn more at https://docs.docker.com/go/build-multi-platform/
```

Damn it.

## Using the docker-container build driver

After some reading, I learnt that the default build driver when you use docker is the `docker` driver which doesn't have support for multi-platform images. You can read more on Docker build drivers on this [page](https://docs.docker.com/build/builders/drivers/).

I need to use the `docker-container` driver which has support for building multi-platform images. To do that I need to create a new builder using the following command:

```
$ docker buildx create --driver docker-container --name multiplatform --use
$ docker buildx install
```

The first command creates the builder using the `docker-container` driver and sets it as the default while the second command creates a shell alias so that I can just use `docker build` instead of having to specify `docker buildx build` on the CLI.

Now, I should be able to run my docker-compose command right...?

```
# `--builder multiplatform` to tell docker-compose to use the docker-container builder we just created
$ docker compose -f ./cicd/docker/docker-compose.yaml build --builder multiplatform serviceA
...
failed to solve: base: failed to resolve source metadata for docker.io/library/base:latest: pull access denied, repository does not exist or may require authorization: server message: insufficient_scope: authorization failed
```

Now the builder cannot find the `base` image that we've built used before. Why? This section from the Docker build drivers page answered it:

> Unlike when using the default docker driver, images built using other drivers aren't automatically loaded into the local image store. If you don't specify an output, the build result is exported to the build cache only.

I did use the `--load` and the `--driver-opt default-load=true` to automatically load the image into the local image store but it didn't work. So what's next?

## Enter docker buildx bake

At this point, I've almost exhausted all my options and just browsing through the Docker documentation in hope of something and I found it!

At first the docker buildx bake command just looks like a different syntax for specifying the docker compose file to me but when my eyes caught on to one of the properties: [`target.contexts`](https://docs.docker.com/build/bake/reference/#targetcontexts). It allows you to pass in more contexts in addition to the folder content context that we're used to with normal docker build that can be used in the Dockerfile.

These are the things you can specify under the `target.contexts` property:
- Container image: docker-image://alpine@sha256:0123456789
- Git URL: https://github.com/user/proj.git
- HTTP URL: https://example.com/files
- Local directory: ../path/to/src
- Bake target: target:base

The first four are cool but the last one stood out to me: `Bake target: target:bake`.

```yaml
# ./cicd/docker/docker-compose.yaml
services:
  base:
    build:
      dockerfile: ./cicd/docker/base.Dockerfile
  serviceA:
    build:
      dockerfile: ./cicd/docker/serviceA.Dockerfile
  serviceB:
    build:
      dockerfile: ./cicd/docker/serviceB.Dockerfile
```

Bake 101 crash course: remember in `docker-compose.yaml` we have services? In Bake format, those services are called targets. Let's recall my original docker-compose.yaml file again, I have a `base` service used to build the shared image used in the Dockerfiles of `serviceA` and `serviceB`. In other words, the `base` service is also a **target**. This means, I can pass it on as extra contexts to my build!

## Putting it all together

The Bake specification allows you to write the file in 3 languages: HCL (Terraform, anyone?), JSON, and YAML (through docker-compose.yaml syntax). To be less disruptive I chose YAML. To use Bake specification with YAML, the CLI can parse existing docker-compose.yaml files but for Bake-specific syntax you have to put it under the property `x-bake`. This is how it looks like in my case:

```yaml
# ./cicd/docker/docker-compose.yaml
services:
  base:
    build:
      dockerfile: ./cicd/docker/base.Dockerfile
  serviceA:
    build:
      dockerfile: ./cicd/docker/serviceA.Dockerfile
      x-bake:
        contexts:
            base: target:base
  serviceB:
    build:
      dockerfile: ./cicd/docker/serviceB.Dockerfile
      x-bake:
        contexts:
            base: target:base
```

To run the build we need to use our friend `docker buildx bake`:

```
$ docker buildx bake --file ./cicd/docker/docker-compose.yaml serviceA

DONE
```

Finally, we managed to build a multiplatform image using docker buildx bake!

## well ackshually, you can just use docker multi-stage build

![](images/well-ackchyually.png)

I know. You're right. I chose not do that to avoid making big changes to the code. Just let me suffer.

## Recap

TLDR here's what I had to do to get multi-platform build working when using multiple Dockerfiles:

1. Setup a new Docker builder using the `docker-container` driver
2. Add the `base` image as extra contexts using Bake `x-bake` syntax
3. Build the image using `docker buildx bake`

This use case is quite niche tbh and like I've said it is avoidable by using multi-stage builds but it is what it is. Hope you've learnt something new as I have.


