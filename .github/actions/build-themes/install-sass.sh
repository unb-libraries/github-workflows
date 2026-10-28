#!/usr/bin/env bash
# Installs the Dart Sass release for this runner and checks the binary runs. dockworker
# re-prompts forever when SASS_PATH is not an executable (CliToolTrait::getCliToolBinaryPath),
# so a bad download must fail here instead.
set -euo pipefail

case "$RUNNER_ARCH" in
    X64) sass_arch=x64 ;;
    ARM64) sass_arch=arm64 ;;
    *) echo "::error title=Unsupported runner::No Dart Sass build for runner architecture '$RUNNER_ARCH'."; exit 1 ;;
esac

dest="$RUNNER_TEMP/dart-sass-$SASS_VERSION"
mkdir -p "$dest"
curl -fsSL --retry 3 \
    "https://github.com/sass/dart-sass/releases/download/$SASS_VERSION/dart-sass-$SASS_VERSION-linux-$sass_arch.tar.gz" \
    | tar -xz -C "$dest"

bin="$dest/dart-sass/sass"
if [ ! -x "$bin" ]; then
    echo "::error title=Dart Sass unusable::$bin is missing or not executable after extracting release $SASS_VERSION."
    exit 1
fi
# dockworker's own preflight requires the version output to contain "1.".
if ! "$bin" --version | grep -q '^1\.'; then
    echo "::error title=Dart Sass unusable::$bin --version did not report a 1.x release."
    exit 1
fi
echo "Dart Sass $("$bin" --version) at $bin"
echo "path=$bin" >> "$GITHUB_OUTPUT"
