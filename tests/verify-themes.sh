#!/usr/bin/env bash
# Tests .github/actions/build-themes/verify-themes.sh. Fixtures are generated here rather
# than committed, because the check depends on file times, which git does not preserve.
set -euo pipefail

verify="$(cd "$(dirname "$0")/.." && pwd)/.github/actions/build-themes/verify-themes.sh"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
failures=0

# new_repo <name>: an empty repository root with a marker older than anything built after it.
new_repo() {
    repo="$work/$1"
    mkdir -p "$repo"
    touch -d '2000-01-01' "$repo.marker"
}

# theme <name> <scss>...: a theme with an info file and the given scss sources.
theme() {
    local dir="$repo/custom/themes/$1" scss
    shift
    mkdir -p "$dir"
    touch "$dir/$(basename "$dir").info.yml"
    for scss in "$@"; do
        mkdir -p "$dir/$(dirname "$scss")"
        echo 'a { b: c; }' > "$dir/$scss"
    done
}

# built <theme> <css>...: non-empty stylesheets newer than the marker.
built() {
    local dir="$repo/custom/themes/$1/dist/css" css
    shift
    mkdir -p "$dir"
    for css in "$@"; do
        echo 'a{b:c}' > "$dir/$css"
    done
}

# expect <0|1> <description> [<text the output must contain>]
expect() {
    local want="$1" description="$2" needle="${3:-}" status=0 output
    output="$(bash "$verify" "$repo" "$repo.marker" "$repo.out" 2>&1)" || status=$?
    if [ "$status" -ne "$want" ] || { [ -n "$needle" ] && [[ "$output" != *"$needle"* ]]; }; then
        echo "FAIL: $description (exit $status, wanted $want)"
        printf '%s\n' "$output" | sed 's/^/    /'
        failures=$((failures + 1))
    else
        echo "ok: $description"
    fi
}

new_repo pass
theme front src/scss/style.scss src/scss/_partial.scss src/scss/print.scss
theme admin src/scss/style.scss
built front style.css print.css
built admin style.css
expect 0 "every entry point built, across two themes"
if [ "$(cat "$repo.out")" != "$(printf '%s\n' custom/themes/admin/dist custom/themes/front/dist)" ]; then
    echo "FAIL: dist directory list"; failures=$((failures + 1))
else
    echo "ok: dist directory list"
fi

new_repo missing
theme front src/scss/style.scss src/scss/print.scss
built front style.css
expect 1 "one stylesheet missing" "file=custom/themes/front/src/scss/print.scss"

new_repo empty
theme front src/scss/style.scss
built front
: > "$repo/custom/themes/front/dist/css/style.css"
expect 1 "empty stylesheet"

new_repo sasserror
theme front src/scss/style.scss
built front
printf '/* Error: expected "}".\n *   src/scss/style.scss 1:2  root stylesheet */\n\nbody::before { content: "Error"; }\n' \
    > "$repo/custom/themes/front/dist/css/style.css"
expect 1 "Sass error stylesheet (--error-css) rejected" "Stylesheet failed to compile"

new_repo stale
theme front src/scss/style.scss
built front style.css
touch -d '1999-01-01' "$repo/custom/themes/front/dist/css/style.css"
expect 1 "stylesheet older than the marker (stale, committed to git)"

new_repo nothemedir
expect 1 "no custom/themes directory" "No themes to build"

new_repo noinfo
mkdir -p "$repo/custom/themes/front/src/scss"
expect 1 "custom/themes without any *info.yml" "No themes to build"

new_repo partials
theme front src/scss/_only.scss
expect 1 "only partials" "No stylesheets to build"

new_repo skipped
theme front src/scss/style.scss .hidden/x.scss dist/css/stray.scss
built front style.css
expect 0 "dot-directories and dist/ are not sources"

new_repo nested
theme front src/scss/components/card.scss
built front card.css
expect 0 "nested entry point compiles to dist/css/<name>.css"

if [ "$failures" -gt 0 ]; then
    echo "$failures test(s) failed"
    exit 1
fi
echo "All verify-themes tests passed"
