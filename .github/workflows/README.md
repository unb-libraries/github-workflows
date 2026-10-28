# UNB Libraries Reusable Workflows

These workflows are consumed by downstream repositories via
`uses: unb-libraries/github-workflows/.github/workflows/<name>@1.x`.

**`1.x` is a moving branch.** Any change merged here goes live for every consumer on the
next push. Additive, optional inputs whose defaults preserve current behavior are the only
safe way to change a workflow's interface.

They were extracted from `unb-libraries/dockworker`, which is being deprecated. Nothing
here requires PHP, composer, or the dockworker package, except the opt-in `build-themes`, which
runs the application's own dockworker.

## Entry points

| Workflow | Use |
|---|---|
| `build-push.yaml` | Build and push an image. Called directly, or via an orchestrator below. |
| `publish-image.yaml` | Build/push, with Slack start + conclusion notifications, and no deploy. For base and service images that other repositories consume. |
| `build-push-notify.yaml` | **Deprecated** (remove in 2.x): wraps `publish-image.yaml` unchanged. Repoint `uses:` to `publish-image.yaml`; inputs and secrets are identical. |
| `build-push-deploy-notify.yaml` | Build/push, deploy to Kubernetes, prune, notify. The common case. |

Supporting workflows (`deploy.yaml`, `notify-start.yaml`, `notify-conclusion.yaml`) are
called by the orchestrators and are not usually invoked directly.

## Recommended caller shape

```yaml
name: Deploy example.lib.unb.ca

on:
  # Bare `on: push` double-builds every push that has an open PR, and mints a GHCR branch
  # tag for every feature branch. Restricting push to the deployable branches keeps PR
  # validation -- which pushes only the immutable hash tag -- while halving CI spend.
  push:
    branches: [dev, prod]
  pull_request:
  workflow_dispatch:

# Two rapid pushes to a deploy branch otherwise race in `kubectl set image`, and the older
# build can land last.
concurrency:
  group: deploy-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  deploy:
    uses: unb-libraries/github-workflows/.github/workflows/build-push-deploy-notify.yaml@1.x
    with:
      branch-env-map: '{"dev":"dev","prod":"prod"}'
      deploy-branches: '["dev","prod"]'
      image-name: 'ghcr.io/unb-libraries/example.lib.unb.ca'
      k8s-deployment-name: 'example-lib-unb-ca'
      platforms: 'linux/amd64'
    secrets:
      KUBE_CONFIG: ${{ secrets.KUBE_CONFIG_DATA }}
      SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
      GH_CONTAINER_REGISTRY_USER: ${{ secrets.GH_CONTAINER_REGISTRY_USER }}
      GH_CONTAINER_REGISTRY_TOKEN: ${{ secrets.GH_CONTAINER_REGISTRY_TOKEN }}
```

`branch-env-map` maps a branch name to the **Kubernetes namespace** it deploys into.
`deploy-branches` gates the deploy job; every other branch and every PR still builds and
pushes the immutable tag.

## Migrating from `dockworker@6.x`

Secret names, workflow filenames and job names are unchanged, so a caller keeps its
`secrets:` block verbatim and its status checks keep their identities. Repoint the `uses:`
line and remove the inputs below.

| `dockworker@6.x` input | Here |
|---|---|
| `build-themes: true` | Unchanged. Now the [`build-themes` action](#build-themes); the app's own `vendor/bin/dockworker` still does the build. |
| `php-version`, `composer-version` | **Removed.** `build-themes` uses the runner distribution's PHP and Composer. |
| `run-log-check` | Replaced by `check-logs` (**defaults false**). Set `log-check-profile: drupal` to get dockworker-drupal's exceptions. The check is the PHP-free `check-logs` action, not `vendor/bin/dockworker logs:check-file`; see [Deployment log check](#deployment-log-check). |
| `push-branches`, `push-all-branches` | **Removed.** Already declared-but-ignored in 6.x; every branch is tagged by its sanitized branch name. |
| — | `pre-build-command` (new) |
| — | `collect-logs` (new; was slaved to `run-log-check`, now independent and **defaults false**) |
| — | `rollout-timeout` (new, default `10m`) |
| — | `distribute`, `arm64-runner`, `amd64-runner`, `compression` (same names and defaults as 6.x) |
| — | `build-cache` (new, default true) |

Workflows deliberately **not** carried over: `test-unit`, `test-e2e`, `test-api`,
`test-logs` (replaced by the `check-logs` action), `update`, `update-docker-compose`, `install-test`, `workflow-os`,
`trim-registry-images` (deprecated in favour of `unb-libraries/container-image-pruner`),
and `build-push-test-deploy-notify` (zero consumers, and its `needs:` chain is broken --
`build-push-images` hard-depends on a job that skips whenever `test` omits `unit`).
`update.yaml` remains in dockworker: it is a `vendor/bin/dockworker update` wrapper and
belongs to that package's local-development surface.

## Deployment log check

With `check-logs: true`, `build-push-deploy-notify.yaml` collects the post-rollout container
logs (`collect-logs` is implied) and the `Check New Deployment Logs` job fails the run if any
line is an error. It runs only when the deploy did, and `Notify Conclusion` waits for it.

```yaml
    with:
      check-logs: true
      log-check-profile: drupal
      log-check-exceptions: |
        Some known-benign line that says failed
```

The check is `.github/actions/check-logs`, a stdlib-only Python port of dockworker's
`logs:check-file`, with byte-identical verdicts on 135 real 6.x deployment logs:

- Drush severity markers are honoured: `[warning]` lines are reported but never fail the
  check; `[notice]`, `[success]`, `[ok]`, `[info]`, `[debug]` and `[cancelled]` lines are
  ignored; the `drush updatedb` pending-updates preview table is ignored.
- Any other line containing `error`, `fail`, `fatal`, `unable`, `unavailable`,
  `unrecognized`, `unresolved`, `unsuccessful` or `unsupported` (case-insensitive) fails the
  check, unless it matches an exception pattern.
- Exception patterns come from the profile (`rules/drupal.exceptions`; `generic` has none)
  plus `log-check-exceptions`. Add an app-specific exception there rather than to a profile.

Run the tests with `python3 -m unittest .github/actions/check-logs/test_check_logs.py`
from the action directory.

## Image tagging

Two tags per build, both computed in `build-push.yaml`:

- `<short-sha>-<UTC timestamp>` -- **always** pushed, and the tag the Kubernetes deploy
  pins. Immutable.
- The sanitized branch name (`dev`, `prod`, `11.x`) -- pushed only on `push` or
  `workflow_dispatch` of a real branch, never for a pull request ref. Mutable; this is what
  a Helm chart's `image.tag` names for a cold start.

`build-push.yaml` exposes both as workflow outputs:

```yaml
    outputs:
      image-tag:        # abc1234-20260903091600
      image-full-name:  # ghcr.io/unb-libraries/example:abc1234-20260903091600
```

`deploy.yaml` takes `image-full-name` as an input, so the orchestrator wires them with
`needs.build-push-images.outputs.image-full-name`. No artifact round-trip is involved.

`build-push.yaml` also still uploads the `build-image-tag` artifact containing a flat
`/tmp/image_tag.env` (`BUILD_IMAGE_TAG=`, `BUILD_IMAGE_FULL_NAME=`). **That artifact name
and format are a consumer contract** for repositories that call `build-push.yaml`
standalone and read it themselves -- do not "clean it up".

### One consequence worth knowing

`kubectl set image` mutates the Deployment's pod template to the immutable tag, so pod
restarts and downscaler rescales replay it safely. A **`helm upgrade` re-renders the pod
template from the chart** and therefore reverts the Deployment to the mutable branch tag.
That is benign when one repository owns that tag, and it is why a `helm upgrade` should be
followed by a re-run of the deploy workflow whenever more than one repository pushes to the
same image name.

## `build-themes`

```yaml
    with:
      build-themes: true
```

Runs the `build-themes` action (`.github/actions/build-themes`) after checkout and before
`pre-build-command`. It installs the runner distribution's PHP (with `ext-yaml`), Composer and
Dart Sass 1.62.1, runs `composer install`, then runs the application's own
`vendor/bin/dockworker theme:build-all` under a pseudo-TTY. When the repository has
a `custom/themes` directory, the step fails if no `custom/themes/*/dist/css/*.css` exists
afterwards. The theme build logic stays in dockworker;
this repository only provisions the toolchain.

## `pre-build-command`

A general hook for any other asset build. It runs in the repository root, under `bash`,
after checkout and before the image build:

```yaml
    with:
      pre-build-command: 'npm ci && npm run build:assets'
```

It interpolates into a `run:` block, so it is deliberately reachable only through
`workflow_call`. **Never expose it through a `workflow_dispatch` input.**

Anything it writes lands in the workspace, which is why `build-context` must never be empty
-- see below.

## Configuring the image source

`build-push.yaml` builds `./Dockerfile` with the repository root as its context by default.
Two optional inputs override that, and both orchestrators forward them:

| Input | Default | Meaning |
|---|---|---|
| `dockerfile` | `''` | Path to the Dockerfile, relative to the repository root. |
| `build-context` | `'.'` | Docker build context, relative to the repository root. |

Building an app that lives in a subdirectory:

```yaml
    with:
      image-name: ghcr.io/unb-libraries/example
      build-context: ./scoreboard
      # dockerfile omitted -> buildx uses ./scoreboard/Dockerfile
```

Three things to know:

- **`dockerfile` defaults to empty on purpose.** An empty value makes buildx use
  `<build-context>/Dockerfile`, so it tracks `build-context` automatically. Setting only
  `build-context` does the obviously-right thing instead of pairing a subdirectory context
  with the root Dockerfile.
- **`dockerfile` is resolved relative to the repository root, not to `build-context`.** They
  are independent. Set both explicitly if the Dockerfile lives outside its context.
- **`.dockerignore` is read from inside the context directory.** A root `.dockerignore` does
  *not* apply once `build-context` points at a subdirectory, so a subdirectory build may
  start shipping `node_modules`, `vendor` and `.git` into the build. Add a `.dockerignore`
  inside the new context.

`build-context` must never be empty. `docker/build-push-action` declares no default for
`context` and falls back to the **remote Git context**
(`https://github.com/<owner>/<repo>.git#<ref>`) when it is unset -- which builds from
committed source and silently discards anything written into the workspace, including the
output of `pre-build-command`. `build-push.yaml` coalesces an empty value back to `.` inline
at the build step; do not remove that guard.

## Build cache

`build-push.yaml` reads and writes a BuildKit layer cache (`type=gha`) by default. The
Actions cache is scoped to the **calling** repository, so caches never mix between repos --
but they do consume that repository's 10GB Actions cache budget, and `cache-to` uses
`mode=max` (every intermediate layer, not just the final ones). Set `build-cache: false` to
opt a repository out.

Each platform job writes its own cache scope (`buildkit-linux-amd64`,
`buildkit-linux-arm64-v8`), so the parallel jobs below never overwrite each other's cache.

A cache only helps if the Dockerfile is layered so that expensive steps precede the
frequently-changing `COPY`. A Dockerfile that copies the whole repository before installing
dependencies re-installs them on every commit no matter what the cache does.

## Platform builds

With the default `distribute: true`, `build-push.yaml` builds each platform in its own job on
a native runner -- `linux/arm64*` on `arm64-runner` (default `ubuntu-24.04-arm`), everything
else on `amd64-runner` (default `ubuntu-latest`) -- pushes each by digest, and a
`Merge Platform Images` job tags the combined manifest list. A single platform skips the merge
and pushes its tags directly. `distribute: false` builds every platform in one job, emulating
non-amd64 platforms under QEMU. At most four platforms can be distributed.

`build-themes` and `pre-build-command` run once in **each** platform job, on that job's runner.

Layers are pushed with `compression: zstd` by default (OCI media types), which needs
containerd 1.5+ / Docker 23+ wherever the image is pulled. Set `compression: gzip` for older
runtimes.

The build job's check name includes its platform, e.g. `Build Image (linux/amd64)`.

## Single-image assumptions

**Read this before attempting to build N images from one caller.**

The pipeline assumes exactly one image per repository per run. The scalar `dockerfile` /
`build-context` inputs are shaped to become per-entry keys of a future JSON `images` input
(`[{key, image-name, dockerfile, build-context}]`), where today's scalars normalize into a
one-element list and `build-image` becomes a `strategy.matrix`. These are the couplings that
must be resolved first:

1. **`deploy.yaml` maps one image onto N deployments.** `image-full-name` is invariant across
   the `k8s-deployment-name` CSV, and the `kubectl set image` call assumes the pod container
   name equals the deployment name. Multi-image needs a mapping structure rather than a CSV.
2. **Pruning keys on a scalar.** The orchestrator uses
   `concurrency: group: prune-${{ inputs.image-name }}`; matrix legs would serialize against
   each other or collide across runs.
3. **The `build-image-tag` artifact name is a literal.** Under `actions/upload-artifact@v4+`,
   two matrix legs uploading the same name is a hard failure, not a merge, and the file
   inside is always `/tmp/image_tag.env`.
4. **The workflow outputs are scalars.** `image-tag` / `image-full-name` describe one image;
   with N images they would need to become a JSON map.

**Prefer an additive migration.** Each matrix leg uploads `build-image-tag-<key>` and
publishes keyed outputs, while the primary leg *also* publishes today's scalars, so existing
callers keep working while multi-image callers opt in.

**Watch status-check names.** Converting `build-image` to a matrix renames the leaf check
from `Build Image` to `Build Image (…)`, which would strand any required status check
configured on a consumer's branch protection. Re-check with
`gh api repos/unb-libraries/<repo>/rulesets` across the fleet immediately before that
migration.

**Related lever, deliberately deferred:** a `target` input (multi-stage `--target`) would let
a single Dockerfile yield several images without N Dockerfiles. Revisit alongside `images`.

## Deliberately out of scope

GitOps (Argo CD / Flux). The deploy here is an imperative in-place image swap on a
pre-existing Deployment; Helm releases are installed and upgraded out of band from
`unb-libraries/kubernetes-metadata`.
