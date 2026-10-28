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
| `update.yaml` | Scheduled composer updates, opened as a pull request. See [Updaters](#updaters). |
| `update-nuxt.yaml` | Scheduled pnpm updates for Nuxt applications, opened as a pull request. |
| `update-ckeditor5.yaml` | Scheduled updates of a Drupal site's CKEditor 5 plugin modules, opened as a pull request. |

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

# Cancels superseded builds of the same branch or PR. Deploys are additionally queued, never
# cancelled, inside deploy.yaml, so the older image can never land last.
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
| `build-themes: true` | Unchanged. Now the [`build-themes` action](#build-themes), run once per build; the app's own `vendor/bin/dockworker` still does the build. |
| `php-version` | Unchanged (default `8.4`); used only by `build-themes`. |
| `composer-version` | **Removed.** Composer is pinned to 2.10.2 inside `build-themes`. |
| `run-log-check` | Replaced by `check-logs` (**defaults false**). Set `log-check-profile: drupal` to get dockworker-drupal's exceptions. The check is the PHP-free `check-logs` action, not `vendor/bin/dockworker logs:check-file`; see [Deployment log check](#deployment-log-check). |
| `push-branches`, `push-all-branches` | **Removed.** Already declared-but-ignored in 6.x; every branch is tagged by its sanitized branch name. |
| — | `pre-build-command` and `pre-build-outputs` (new; see [`pre-build-command`](#pre-build-command)) |
| — | `collect-logs` (new; was slaved to `run-log-check`, now independent and **defaults false**) |
| — | `log-settle-seconds` (new, default `60`, the 6.x wait) |
| — | `rollout-timeout` (new, default `10m`) and `deploy-timeout-minutes` (new, default `30`) |
| — | `kubectl-version` (new, default `v1.31.0`) |
| — | `distribute`, `arm64-runner`, `amd64-runner`, `compression` (same names and defaults as 6.x) |
| — | `build-cache` (new, default true) |
| `GH_NPM_TOKEN` secret | Unchanged: optional, exposed to the image build as the `npmrc` build secret. |

### Behaviour changes from 6.x

These fix defects that 6.x shares; a caller that worked on 6.x is affected only if it relied
on one of them.

- **A failed `kubectl set image` fails the deploy.** 6.x wrapped the rollout in
  `if ! ( set -e; ... )`, where bash ignores `set -e`, so a failed `set image` (for example
  a container not named after its deployment) was reported as success whenever the existing
  rollout was healthy.
- **A deploy branch missing from `branch-env-map` fails the deploy.** 6.x deployed to a
  namespace literally named `null`.
- **Logs come from every pod and container** of the deployment, including init containers
  and, for a container that restarted, its previous instance. 6.x read one container of one
  pod. See [Deployment log check](#deployment-log-check).
- **The log check also runs after a failed deploy**, to display the logs; only a successful
  deploy is scanned.
- **`build-themes` verifies its output.** dockworker ignores Sass failures, so 6.x shipped
  stale or missing CSS silently. See [`build-themes`](#build-themes).
- **Every job has a timeout.**

Workflows deliberately **not** carried over: `test-unit`, `test-e2e`, `test-api`,
`test-logs` (replaced by the `check-logs` action), `update-docker-compose`, `install-test`, `workflow-os`,
`trim-registry-images` (deprecated in favour of `unb-libraries/container-image-pruner`),
and `build-push-test-deploy-notify` (zero consumers, and its `needs:` chain is broken --
`build-push-images` hard-depends on a job that skips whenever `test` omits `unit`).

## Updaters

The three updaters are called from a scheduled workflow in each application and open (or
refresh) one pull request with the changes; nothing is pushed to a deploy branch directly.
Each takes `pr-branch` (the pull request's branch), `git-author` and `git-committer`, and the
`PAT_TOKEN` secret, as in dockworker 6.x.

```yaml
on:
  schedule:
    - cron: '44 6 * * 1,4'
  workflow_dispatch:

jobs:
  update:
    uses: unb-libraries/github-workflows/.github/workflows/update.yaml@1.x
    secrets:
      PAT_TOKEN: ${{ secrets.UNBLIBBOT_PAT_TOKEN }}
```

### `update.yaml`

Updates the composer dependencies of each target in `.dockworker/dockworker.yml`, the same
configuration the local `dockworker update` command reads:

```yaml
dockworker:
  update:
    targets:
      - dir: build
        type: composer
```

The update runs **inside the application's own base image** -- by default the image named by
the first `FROM` in `Dockerfile`; set `composer-image` (or `dockerfile`) to override -- so
dependencies resolve against the PHP version the application actually runs, using the
Composer that image ships. The `composer` type runs
`composer update --no-install --no-scripts --no-plugins --ignore-platform-req=ext-*`: the PHP
version is checked strictly, extension requirements are not (the application's Dockerfile
installs its extensions). Inline `command`, `lockfile`, `manifest` and `commit_paths` keys on a
target override the type's preset, and also run in that image.

The pull request stages each target's `composer.json` and `composer.lock` (or its
`commit_paths`; `add-paths` overrides all of them). Its description names the image and PHP
version, lists changed direct dependencies (a `dev-*` branch shows its commit), and counts the
changed transitive packages.

Differences from dockworker 6.x:

- No PHP, Composer or dockworker is installed on the runner, and `docker compose pull` is gone.
  `php-version` and `composer-version` are **removed**; remove them from callers.
- 6.x always resolved with PHP 8.4 (or the caller's `php-version`), whatever the application
  ran. A PHP 8.2 site therefore failed every update (lib.unb.ca, since at least 2026-10-08),
  or worse, could be offered packages its runtime cannot load.
- `add-paths` is optional; the derived paths are the same as 6.x's.

### `update-nuxt.yaml` and `update-ckeditor5.yaml`

Ported unchanged from dockworker 6.x apart from the `pr-branch` input, a timeout and the link
in the pull request description. `update-nuxt.yaml` runs `pnpm update` (`latest: true` for
`--latest`); `update-ckeditor5.yaml` pins each module's `ckeditor5` to the range the site's
Drupal core ships and rebuilds the plugins.

## Deployment log check

With `check-logs: true`, `build-push-deploy-notify.yaml` collects the post-rollout container
logs (`collect-logs` is implied) and the `Check New Deployment Logs` job fails the run if any
line is an error. It runs after a successful deploy, and after a failed one too, where it
only displays the logs (the run is already red). It is skipped on non-deploy branches.
`Notify Conclusion` waits for it.

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
  Each pattern is validated on its own: an invalid one fails the check naming its source and
  line.

The collected log (artifact `deployment-logs`, file `deployment_logs.txt`) is laid out as:

```
=== Logs for deployment/<name> ===
--- pod/<pod> container <container>
<log lines, verbatim>
--- previous instance of pod/<pod> container <container> (restarts: N)   # only after a restart
...
```

Pods being deleted are skipped, so after a completed rollout only the new pods are read.
Previous-instance logs are scanned: a container that crashed during the deploy fails the
check even if its replacement started. Log lines are not prefixed, so exceptions anchored to
the start or end of a line still apply. Because the header lines carry deployment, pod and
container names, a name containing one of the error words above would fail the check.

`log-settle-seconds` (default 60) waits after the rollout before reading, so output written
just after the pod became ready is included.

Run the tests from the action directory: `python3 -m unittest -v test_check_logs.py`.

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

Runs the `build-themes` action (`.github/actions/build-themes`) **once**, in the
`Prepare Build` job on `ubuntu-latest`, before `pre-build-command`. Each platform build then
unpacks the same files (see [Platform builds](#platform-builds)), so every image ships
identical CSS. The action:

1. installs PHP `php-version` (default 8.4) and Composer 2.10.2 with `shivammathur/setup-php`,
   which also authenticates Composer's GitHub downloads with the workflow token;
2. installs Dart Sass 1.62.1 and checks the binary runs;
3. runs `composer install --no-scripts`, then the application's own
   `vendor/bin/dockworker theme:build-all`;
4. verifies the output without PHP, using dockworker-drupal's own discovery rules: each
   directory under `custom/themes` holding a `*info.yml` is a theme, and every `*.scss` in it
   whose name does not start with `_` must have produced a non-empty
   `dist/css/<name>.css` **during this build** (a stale stylesheet committed to git does not
   count) that is not Sass's error stylesheet. When a compile fails, Dart Sass writes a
   stylesheet starting `/* Error: ` that displays the error at the top of every page, so a
   size check alone passes it. dot-directories and `dist/` are not sources.

The step fails, naming each stylesheet and showing the Sass error, if any stylesheet was not
built -- dockworker itself ignores Sass failures, so on 6.x a broken stylesheet deployed that
error banner with a green build -- and also if there is nothing to build at all, which means the
caller should not set `build-themes: true`. The theme build logic stays in dockworker; this
repository only provisions and checks it.

Only `build-push-deploy-notify.yaml` (and `build-push.yaml`) expose `build-themes`;
`publish-image.yaml` does not, because base images have no Drupal themes.

## `pre-build-command`

A general hook for any other asset build. It runs **once**, in the repository root under
`bash`, in the `Prepare Build` job on an amd64 runner, after `build-themes`. Declare what it
produces in `pre-build-outputs`; only those paths are carried into the platform builds:

```yaml
    with:
      pre-build-command: 'npm ci && npm run build:assets'
      pre-build-outputs: |
        web/dist
        web/manifest.json
```

`pre-build-outputs` takes newline-separated, repository-relative paths or bash globs
(`**` included). It is required when `pre-build-command` is set, and each entry must match
something. Because the command runs on one architecture, its outputs must be
architecture-neutral; build native code in the Dockerfile instead.

It interpolates into a `run:` block, so it is deliberately reachable only through
`workflow_call`. **Never expose it through a `workflow_dispatch` input.**

The built files land in each platform job's workspace, which is why `build-context` must
never be empty -- see below.

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

`build-push.yaml` reads and writes a BuildKit layer cache in the registry by default, as
`<image-name>:buildcache-<branch>-<platform>` (for example
`…/lib.unb.ca:buildcache-dev-linux-amd64`). `cache-to` uses `mode=max`, so the intermediate
stages of a multi-stage build are cached too.

- A push or manual run reads its branch's cache, then the **default branch's**, and writes
  only its own branch's. So `prod`, or a long-lived feature branch whose `build/` differs
  from `dev`'s, never overwrites `dev`'s cache, and a new branch starts from `dev`'s layers.
- A pull request reads its base branch's cache, then the default branch's, and never writes.
- Tag names are sanitized like the branch tag and capped at 128 characters.

A caller that builds every branch on push (rather than the recommended `[dev, prod]`) leaves
one cache tag per feature branch and platform; `container-image-pruner` never deletes text
tags, so remove those with the branch. The cache's final
layers are byte-identical to the image's, so the registry stores them once (on hit, the
cache tag is the same 23 layers / 186 MB as the image). `container-image-pruner` never
deletes text tags, so the cache tags persist. Set `build-cache: false` to opt out.

Measured on hit.lib.unb.ca (single-stage Drupal image, 13 s `RUN build.sh`), image-build
step in seconds, amd64 / arm64:

| Backend | Cold | Warm, no change | `build/` changed |
|---|---|---|---|
| `type=gha` (the previous default) | 38 / 21 | 32 / 26 | 24 / 24 |
| registry (now the default) | 28 / 26 | 20 / 19 | 23 / 20 |
| none | 22 / 21 | 24 / 24 | 20 / 18 |

The Actions cache was slower than no cache in every case: a hit downloaded ~100 MB from the
Actions cache to skip a 13 s step, and every run paid ~9 s to export to it, out of the
repository's 10 GB Actions budget. The registry cache is within noise of no cache on an image
this cheap to build. It is the default because it costs nothing measurable there and pays
off where the cached step is expensive -- `RUN build.sh` takes 35-67 s on larger Drupal
sites, and Nuxt builds cache their install stage. No multi-stage image was measured.

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

`build-themes` and `pre-build-command` run once, in `Prepare Build`, which packs their
output into the `build-push-assets` artifact (kept 3 days; internal, not a consumer contract).
Each platform job unpacks it into its workspace before building. If a re-run fails because
that artifact expired, re-run all jobs.

Job timeouts: `Prepare Build` 20 minutes; `Build Image` 90 minutes, or 360 when
`distribute: false` emulates platforms; `Merge Platform Images` 10; the deploy
`deploy-timeout-minutes` (default 30); the log check 10; pruning 30; notifications 5.

Layers are pushed with `compression: zstd` by default (OCI media types), which needs
containerd 1.5+ / Docker 23+ wherever the image is pulled. Set `compression: gzip` for older
runtimes.

The build job's check name includes its platform, e.g. `Build Image (linux/amd64)`.

## Single-image assumptions

**Read this before attempting to build N images from one caller.**

The pipeline assumes exactly one image per repository per run. The scalar `dockerfile` /
`build-context` inputs are shaped to become per-entry keys of a future JSON `images` input
(`[{key, image-name, dockerfile, build-context}]`), where today's scalars normalize into a
one-element list and the existing per-platform `build-image` matrix gains an image
dimension. These are the couplings that must be resolved first:

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

**Watch status-check names.** The leaf check is already `Build Image (<platform>)`; adding an
image dimension would rename it again, stranding any required status check configured on a
consumer's branch protection. Re-check with `gh api repos/unb-libraries/<repo>/rulesets`
across the fleet immediately before that migration.

**Related lever, deliberately deferred:** a `target` input (multi-stage `--target`) would let
a single Dockerfile yield several images without N Dockerfiles. Revisit alongside `images`.

## Deliberately out of scope

GitOps (Argo CD / Flux). The deploy here is an imperative in-place image swap on a
pre-existing Deployment; Helm releases are installed and upgraded out of band from
`unb-libraries/kubernetes-metadata`.
