# github-workflows

Shared, reusable GitHub Actions workflows for UNB Libraries applications.

```yaml
jobs:
  deploy:
    uses: unb-libraries/github-workflows/.github/workflows/build-push-deploy-notify.yaml@1.x
```

**Read [`.github/workflows/README.md`](.github/workflows/README.md)** before calling or changing anything here.

## Versioning

`1.x` is a **moving branch** and the default branch. Every caller picks up a change on its
next run, so nothing merges without passing `ci.yaml`.

## Layout

| File | |
|---|---|
| `.github/workflows/build-push-deploy-notify.yaml` | Entry point: build → push → deploy → prune → notify |
| `.github/workflows/publish-image.yaml` | Entry point: build → push → notify (no deploy). For base and service images consumed by other repositories |
| `.github/workflows/build-push-notify.yaml` | **Deprecated** wrapper around `publish-image.yaml`, kept for existing callers |
| `.github/workflows/build-push.yaml` | Build and push to GHCR; emits the image tag as an output |
| `.github/workflows/deploy.yaml` | `kubectl set image` + rollout wait, per deployment, in the branch's namespace |
| `.github/actions/build-themes` | Builds and verifies Drupal themes with the app's own dockworker |
| `.github/actions/check-logs` | PHP-free deployment log check |
| `.github/workflows/ci.yaml` | This repository's own CI: actionlint, shellcheck, tests |
| `.github/workflows/notify-start.yaml` | Slack, run start |
| `.github/workflows/notify-conclusion.yaml` | Slack, run conclusion |
| `.github/workflows/update.yaml` | Scheduled composer update pull requests, run in the application's base image |
| `.github/workflows/update-nuxt.yaml` | Scheduled pnpm update pull requests for Nuxt applications |
| `.github/workflows/update-ckeditor5.yaml` | Scheduled CKEditor 5 module update pull requests |

Image pruning is `unb-libraries/container-image-pruner`, which lives in its own repository and understands this tagging scheme.
