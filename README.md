# github-workflows

Shared, reusable GitHub Actions workflows for UNB Libraries applications.

```yaml
jobs:
  deploy:
    uses: unb-libraries/github-workflows/.github/workflows/build-push-deploy-notify.yaml@1.x
```

**Read [`.github/workflows/README.md`](.github/workflows/README.md)** before calling or changing anything here.

## Versioning

`1.x` is a **moving branch** and the default branch. 

## Layout

| File | |
|---|---|
| `.github/workflows/build-push-deploy-notify.yaml` | Entry point: build → push → deploy → prune → notify |
| `.github/workflows/build-push-notify.yaml` | Entry point: build → push → notify (no deploy) |
| `.github/workflows/build-push.yaml` | Build and push to GHCR; emits the image tag as an output |
| `.github/workflows/deploy.yaml` | `kubectl set image` + rollout wait, per namespace |
| `.github/workflows/notify-start.yaml` | Slack, run start |
| `.github/workflows/notify-conclusion.yaml` | Slack, run conclusion |

Image pruning is `unb-libraries/container-image-pruner`, which lives in its own repository and understands this tagging scheme.
