---
title: "GitOps without Argo/Flux: GitHub Actions OIDC + server-side apply"
date: 2026-07-08T10:00:00+0800
tags: [kubernetes, gitops, github-actions, oidc, k3s]
---

**You don't need Argo CD or Flux to do GitOps.** For a handful of clusters where every change is human-initiated through a PR, a much smaller stack gets you most of the way: GitHub Actions authenticating to the apiserver via **OIDC** (no static kubeconfig), `kubectl apply --server-side` on merge, and — for the platform layer — the **k3s helm-controller** reconciling `HelmChart` CRs in-cluster. No standing CD control plane, no credential store, no UI to operate. The catch, and the whole reason it works, is that **you control the apiserver's auth layer** — which is true on self-managed k3s/kubeadm and *not* true on EKS/GKE. This note is the design, what it buys you, what it costs, and where it stops being portable.

## The setup

Managed inference clusters on k3s. Kubernetes manifests (mostly CRs for an operator) live in a git repo, one directory per cluster. The goal was to retire an Argo CD install that nobody was driving through the UI anymore — the sync-on-merge and diff-preview were the only features actually in use, and both are cheap to reproduce.

Two GitHub Actions workflows do everything:

- **Deploy** — on push to `main`, `kubectl apply --server-side` the changed cluster's manifests.
- **Preview** — on PRs, post a server-side dry-run `kubectl diff` as a PR comment, so you see exactly what an apply would change (a clean **NO-OP** means no pod roll) before merge.

## The key insight: split the platform layer from the app layer

The framing that makes this coherent: **it is not "GitOps without a reconciler."** The k3s helm-controller *is* a pull-based in-cluster reconciler — it ships with k3s for free and continuously converges `HelmChart`/`HelmChartConfig` CRs. What you actually do is put each layer on the tool that suits it:

| Layer | What | Mechanism | Reconciliation |
|---|---|---|---|
| **Platform** | operators, CRDs, istio, monitoring, CSI, secrets | `HelmChart` CRs → **helm-controller** | pull, continuous |
| **App** | the workloads you iterate on | manifests → **GHA `kubectl apply`** | push, on merge |

This split is the good idea, not a compromise. The **app layer** is exactly where you want a human-gated PR + diff preview and *least* want an agent silently auto-syncing a surprise pod roll. The **platform layer** is exactly where you want set-and-forget convergence and never think about it. Splitting them also keeps the credential model clean (below) — nothing in-cluster needs git or registry read to reconcile apps.

## Auth: GitHub OIDC straight to the apiserver, keyless

The part that makes this genuinely nice is that **no static kubeconfig or long-lived token exists anywhere.** GitHub mints a short-lived (~5 min) OIDC token per workflow run; the apiserver trusts it directly as a first-class authenticator.

On k3s this is Kubernetes [Structured Authentication Configuration](https://kubernetes.io/docs/reference/access-authn-authz/authentication/) (KEP-3331, GA in 1.30) — a file the apiserver reads via `--authentication-config`:

```yaml
apiVersion: apiserver.config.k8s.io/v1
kind: AuthenticationConfiguration
jwt:
  - issuer:
      url: https://token.actions.githubusercontent.com
      audiences: [gha-deploy://my-cluster]      # unique per cluster
    claimMappings:
      username:
        expression: '"gha:" + claims.sub'         # sub → k8s username
    claimValidationRules:
      - expression: 'claims.repository_owner == "my-org"'
```

Then bind that username with ordinary RBAC. Two properties fall out:

- **Two identities, one per GitHub event, told apart by the token `sub`.** A `main` push gets `sub: repo:org/repo:ref:refs/heads/main`; a PR gets `sub: repo:org/repo:pull_request`. Map each to a different k8s user and bind them separately: only the `main` identity can `apply`; the PR identity can only dry-run. A CEL `claimValidationRules` OR-rule accepts both subs through one authenticator.
- **Per-cluster audience** (`gha-deploy://<cluster>`) so a token minted for one cluster can't be replayed against another.

k8s ≥1.30 **hot-reloads** the config file — no apiserver restart. The only fiddly part: it's **per-control-plane-node local file state, not a cluster object**, so the identical file must be on every control-plane node (a request the LB routes to a node without it fails auth). That per-node requirement is the price of not running a proxy.

## Server-side apply + the preview diff

**Why `--server-side` specifically, not plain `kubectl apply`.** Client-side apply computes a 3-way merge *on the client* against a `last-applied-configuration` annotation it stashes on the object. Server-side apply moves the merge into the apiserver, which tracks **field ownership** in `managedFields` — each manager (this workflow, the operator, a stray `kubectl edit`) owns exactly the fields it set. Three concrete wins here:

- **Adoption of out-of-band resources.** A resource created by the operator or a manual `kubectl create` has *no* `last-applied-configuration` annotation, so a client-side apply onto it does a surprising 2-way merge. SSA has no such dependency — the workflow's field manager cleanly takes over the fields it declares, so an already-running resource comes under the repo with zero disruption (a no-op when the manifest matches live). `--force-conflicts` grants that takeover on the first apply instead of erroring on fields another manager currently owns.
- **Coexistence with the operator.** The operator legitimately owns fields the workflow never sets (defaulted spec fields, injected sidecars). SSA leaves those alone and reconciles only the fields in the committed manifest; client-side apply's annotation-diffing is blunter and can fight the operator.
- **A trustworthy preview.** `kubectl diff --server-side` runs the manifest through the real apiserver merge + defaulting + admission path, so the PR diff is byte-for-byte what an apply would produce — including mutations a webhook or the operator would apply. A client-side diff can't see any of that, which is what makes the NO-OP signal actually mean "no pod roll."

**Preview safety, via `pull_request_target`.** The diff runs on PRs but the *workflow definition* comes from `main` (trusted); the PR contributes only manifest files as data, fed to `kubectl diff -f`. You never check out and execute PR code. Note that **server-side dry-run authorizes as a write** (the apiserver runs the same RBAC check as a real apply), so the preview identity isn't "read-only" — its safety comes entirely from the trust boundary: the workflow only ever runs `diff`, never `apply`, and only a `main` token mints the deploy `sub`.

## What it buys you

- **No standing CD control plane** to run, secure, upgrade, or track CVEs on — beyond the helm-controller k3s already ships.
- **No credential honeypot.** Argo typically stores a kubeconfig/SA token for every managed cluster in one place. Here there is no standing credential at all — a ~5 min OIDC token, scoped per-cluster, RBAC-limited, minted per run.
- **Legible.** Two workflow files and two directories, readable end-to-end in 15 minutes, versus Application/ApplicationSet/AppProject/App-of-Apps + sync policies.
- **Clean rollback** — it's just `git revert` + re-merge → re-apply. Auditable by construction.
- **Adoption without disruption** — SSA identity-keying means you can bring existing live resources under management incrementally.

## What you give up (and how much it matters)

- **Continuous drift correction (self-heal).** The big one. GHA applies only on push, so a live `kubectl edit` or an operator mutation isn't pulled back until a PR happens to touch that file. *Mitigation:* the preview `kubectl diff` is already a drift **detector** — run it on a schedule (cron, matrix over all targets) and alert on any non-empty diff. That's ~80% of Argo's drift value (you find out) without a control plane. Auto-*correction* is only worth chasing if many hands have cluster write access.
- **Pruning / GC.** Apply-only: deleting a manifest file orphans the live resource — you must `kubectl delete` by hand. `--prune -l <selector>` exists but is the classic way to nuke more than you meant. At low resource counts, manual delete with a loud runbook is safer.
- **Aggregated sync/health UI.** No single "everything in-sync and healthy" pane. If you'd stopped using the UI anyway, this is moot; the scheduled-diff job doubles as it.
- **Ordering / sync waves.** `kubectl apply -R` gives you kubectl's kind sort and nothing more; helm-controller has no cross-chart dependency ordering either. You lean on operator/eventual convergence. Fine for a namespace + a few CRs; the first thing to bite if the platform layer grows real inter-chart dependencies.

## The portability boundary: this is a self-managed-only pattern

The whole thing hinges on owning `kube-apiserver`'s flags. The managed clouds don't hand you that, and they diverge sharply:

| | Native structured auth | Apiserver trusts the GitHub JWT *directly*? |
|---|---|---|
| **k3s / kubeadm / RKE2 / Talos** | ✅ full KEP-3331 | ✅ yes |
| **EKS** | ❌ never exposed | ⚠️ via the legacy single-OIDC-provider association |
| **GKE** | ❌ never exposed | ❌ no supported mode |

- **EKS** has no `--authentication-config`, but its legacy "OIDC identity provider association" *can* trust GitHub's issuer directly — **one provider cluster-wide, one audience, exact-match `requiredClaims` only, no CEL.** So the pattern survives in spirit but you can't express the two-sub deploy/preview split at the auth layer.
- **GKE** has no way to make the apiserver trust the GitHub JWT at all. GKE Identity Service is an in-cluster impersonating proxy that only supports interactive browser login (dead end for CI, and deprecated for new orgs from 2025-07-01).

**The cloud-native way to keep the same spirit is to redeem the token one hop earlier — at cloud IAM instead of the apiserver — and it stays keyless.** GitHub OIDC → AWS STS `AssumeRoleWithWebIdentity` (EKS) or GCP Workload Identity Federation (GKE) → then `kubectl` authenticates as that IAM principal (mapped to RBAC via EKS **access entries** / GCP IAM). The trust anchor is unchanged — GitHub OIDC, keyless, sub-pinned, two identities — only the **redemption point** moves. On EKS the two-sub split even comes back cleanly: two IAM roles, each with a trust policy gated on the respective `sub`, each mapped to different RBAC. You never fall back to a long-lived secret on any of them; what you gain is a standing IAM *configuration* (roles/WIF + the IAM→k8s mapping) that lives in your cloud IaC rather than a file on 3 nodes.

## When to use this vs reach for Argo/Flux

Use the lightweight approach when: a handful of clusters, a modest set of deliberately-managed workloads, every change human-initiated via PR, and you have a self-managed control plane (or are willing to redeem at cloud IAM). Reach for Flux/Argo when one of these turns into a hard requirement:

- apps/clusters grow into the dozens–hundreds where ApplicationSet templating + an aggregated status pane pay for themselves;
- automatic drift *correction* (not just detection) is mandatory — compliance, or many people with cluster write access;
- progressive delivery (Argo Rollouts / Flagger);
- multi-team self-service with per-team app boundaries and RBAC.

## Takeaways

- **GitOps ≠ Argo/Flux.** Sync-on-merge and diff-preview — the two features most teams actually use — are reproducible with GitHub Actions + `kubectl` in two workflow files.
- **Split platform (pull-reconciled) from apps (push-applied).** You're not avoiding a reconciler; the helm-controller reconciles the platform. Push-apply the app layer precisely because that's where you want human gating, not silent auto-sync.
- **OIDC makes it keyless.** A short-lived, per-cluster, RBAC-scoped token per run beats a stored kubeconfig — the CD system stops being a credential honeypot. Two identities (main vs PR) fall out of the token `sub`.
- **Server-side apply earns its keep three ways** — field-ownership (`managedFields`) instead of a client-side `last-applied-configuration` annotation lets you adopt out-of-band resources without disruption, coexist with the operator's owned fields, and get a `diff` that's byte-for-byte what apply would do (a real NO-OP = no pod roll). A `pull_request_target` dry-run of that diff is a safe pre-merge check *if* it only ever runs `diff`.
- **Its weaknesses are drift-correction and pruning** — the first is cheaply mitigated with a scheduled diff (detection), the second is low-impact at small scale.
- **It's a self-managed control-plane pattern.** EKS degrades it (single OIDC provider, no CEL); GKE can't trust the JWT directly at all. The portable version keeps GitHub OIDC as the keyless anchor but redeems it at cloud IAM (STS/WIF) instead of the apiserver.

## Where this could go: external infra via Crossplane (untested idea)

Here's the thread I'm still pulling on, not yet validated. Every layer above works because it's *"desired state as CRs, reconciled by an in-cluster controller"* — helm-controller for the platform, the operator for the apps. [Crossplane](https://www.crossplane.io/) makes external infra (buckets, DNS, databases, even whole clusters) fit that same shape: a **Managed Resource** is just another CR, and Crossplane's provider controller reconciles it against the real cloud API. So in principle the *exact* pipeline extends to infra with zero new machinery — GHA OIDC → `kubectl apply --server-side` the infra CRs → Crossplane converges them. Three layers (platform / apps / infra) on one push-apply-plus-in-cluster-reconcile spine, one preview diff, one auth model.

Two things make it more than a curiosity, and two caveats keep me honest:

- It would *close the drift gap* for infra specifically. Crossplane reconciles continuously, so unlike the push-only app layer, external resources would get real self-heal for free.
- The preview diff would extend to infra — a change to a database CR shows up in the same PR comment.
- **Caveat 1:** Crossplane needs cloud credentials in-cluster (`ProviderConfig`), which reintroduces a standing credential — cutting against the "no credential honeypot" win. Mitigated by having the provider use IRSA / Workload Identity so it stays keyless, but it's a real shift in the trust model.
- **Caveat 2:** `kubectl diff --server-side` on a Crossplane CR shows the change to the *desired CR spec*, not a `terraform plan`-style diff of what actually changes in the cloud (the provider reconciles async, after merge). So the preview is weaker than Terraform's for infra — it tells you the intent changed, not the blast radius.

File under "toying with it," not "run this in prod." But if it holds up, the appeal is obvious: apps and their infra managed by one legible pipeline instead of a GitOps tool for k8s plus a separate Terraform/Atlantis stack for the cloud.
