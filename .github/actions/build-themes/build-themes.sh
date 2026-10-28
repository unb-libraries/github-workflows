#!/usr/bin/env bash
# Builds the Drupal theme assets (custom/themes/*/dist) in the repository root, before the
# image build. Runs once in each platform job, on GitHub-hosted amd64 and arm64 runners.
set -euo pipefail

# The distribution's PHP (dockworker needs 8.3+) plus the extensions it requires; ext-yaml is
# not on the stock runner image. Unversioned packages, because the amd64 and arm64 runners can
# be on different Ubuntu releases (ubuntu-latest is 26.04; ubuntu-24.04-arm is 24.04).
sudo apt-get update -q
sudo apt-get install -y -q --no-install-recommends \
    php-cli php-curl php-gd php-mbstring php-xml php-yaml php-zip unzip
if ! command -v composer >/dev/null; then
    sudo apt-get install -y -q --no-install-recommends composer
fi
php --version
composer --version

case "$(uname -m)" in
    x86_64) sass_arch=x64 ;;
    aarch64) sass_arch=arm64 ;;
    *) echo "::error title=Unsupported runner::No Dart Sass build for $(uname -m)."; exit 1 ;;
esac
curl -fsSL "https://github.com/sass/dart-sass/releases/download/$SASS_VERSION/dart-sass-$SASS_VERSION-linux-$sass_arch.tar.gz" \
    | tar -xz -C "$RUNNER_TEMP"

composer install --prefer-dist --no-progress

# dockworker requires a TTY; script(1) provides one.
SASS_PATH="$RUNNER_TEMP/dart-sass/sass" script -q -e -c "vendor/bin/dockworker theme:build-all"

# Fail if a repository with custom themes built no CSS, rather than shipping an unstyled image.
if [ -d custom/themes ]; then
    ls custom/themes/*/dist/css/*.css
fi
