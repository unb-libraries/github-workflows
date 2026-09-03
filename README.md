# github-workflows

Shared, reusable GitHub Actions workflows for UNB Libraries applications: build a container
image, push it to GHCR, deploy it to the Kubernetes cluster, and report to Slack.

```yaml
jobs:
  deploy:
    uses: unb-libraries/github-workflows/.github/workflows/build-push-deploy-notify.yaml@1.x
```

**The full contract — every input, every secret, the tagging scheme, and the migration table
from `dockworker@6.x` — is in [`.github/workflows/README.md`](.github/workflows/README.md).**
Read it before calling or changing anything here.

## Why this repository exists

These workflows previously lived inside the `unb-libraries/dockworker` composer package,
which is being deprecated. Nothing in the deploy path ever needed PHP, so it did not need to
ship inside a PHP package. This repository carries the deploy path alone, with the dockworker
coupling removed: no `composer install`, no `vendor/bin/dockworker`, no `setup-php`.

## Versioning

`1.x` is a **moving branch** and the default branch, mirroring the `6.x` convention consumers
already know. Every caller tracks it, so a change here is live everywhere on the next push.
Only additive, optional inputs whose defaults preserve existing behavior are safe.

## Layout

| File | |
|---|---|
| `.github/workflows/build-push-deploy-notify.yaml` | Entry point: build → push → deploy → prune → notify |
| `.github/workflows/build-push-notify.yaml` | Entry point: build → push → notify (no deploy) |
| `.github/workflows/build-push.yaml` | Build and push to GHCR; emits the image tag as an output |
| `.github/workflows/deploy.yaml` | `kubectl set image` + rollout wait, per namespace |
| `.github/workflows/notify-start.yaml` | Slack, run start |
| `.github/workflows/notify-conclusion.yaml` | Slack, run conclusion |

Image pruning is `unb-libraries/container-image-pruner`, which lives in its own repository
and understands this tagging scheme.
