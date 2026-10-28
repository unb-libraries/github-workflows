#!/usr/bin/env bash
# Verifies a dockworker theme build without PHP. dockworker ignores the Sass exit status
# (CliCommandTrait::executeCliCommand), so this is the only check that a build worked.
#
# Usage: verify-themes.sh <repository root> <marker file> <output file>
#
# Mirrors dockworker-drupal's discovery: a theme is the directory of each '*info.yml' under
# custom/themes (DrupalCodeTrait::getCustomModulesThemes), and every '*.scss' in it whose name
# does not start with '_' compiles to dist/css/<name>.css (DrupalThemeCommands::buildThemeScss).
# Like Symfony Finder, dot-files and dot-directories are skipped; dist/ is skipped too. Each
# expected stylesheet must be non-empty and newer than the marker, which is touched before the
# build, so a stale stylesheet committed to git cannot pass. It must also not be Dart Sass's
# error stylesheet: when compiling to a file, Sass replaces the output of a failed compile with
# one starting "/* Error: " that shows the error on every page (--error-css). Compressed
# output never starts with a plain comment, so that prefix only appears on failure.
#
# On success, writes the repository-relative dist directories, one per line, to the output file.
set -euo pipefail

root="${1:?repository root required}"
marker="${2:?marker file required}"
out="${3:?output file required}"
themes_dir="$root/custom/themes"

if [ ! -f "$marker" ]; then
    echo "::error title=Theme check misconfigured::Marker file '$marker' does not exist."
    exit 1
fi
if [ ! -d "$themes_dir" ]; then
    echo "::error title=No themes to build::build-themes is true but there is no custom/themes directory. Remove 'build-themes: true' from the calling workflow."
    exit 1
fi

themes=0
expected=0
missing=0
dist_dirs=()

while IFS= read -r -d '' info; do
    theme="$(dirname "$info")"
    themes=$((themes + 1))
    dist_dirs+=("${theme#"$root/"}/dist")
    while IFS= read -r -d '' scss; do
        expected=$((expected + 1))
        css="$theme/dist/css/$(basename "$scss" .scss).css"
        if [ ! -s "$css" ] || [ ! "$css" -nt "$marker" ]; then
            echo "::error file=${scss#"$root/"},title=Stylesheet not built::${css#"$root/"} was not built from ${scss#"$root/"}. The Sass error is in the Build Themes step log."
            missing=$((missing + 1))
        elif [ "$(head -c 10 "$css")" = "/* Error: " ]; then
            echo "::error file=${scss#"$root/"},title=Stylesheet failed to compile::Sass could not compile ${scss#"$root/"}:"
            sed -n '1,/\*\//p' "$css"
            missing=$((missing + 1))
        fi
    done < <(find "$theme" -mindepth 1 \( -name '.*' -o -path "$theme/dist" \) -prune \
        -o -type f -name '*.scss' ! -name '_*' -print0)
done < <(find "$themes_dir" -mindepth 1 -name '.*' -prune -o -type f -name '*info.yml' -print0)

if [ "$themes" -eq 0 ]; then
    echo "::error title=No themes to build::build-themes is true but no theme (*info.yml) exists under custom/themes. Remove 'build-themes: true' from the calling workflow."
    exit 1
fi
if [ "$expected" -eq 0 ]; then
    echo "::error title=No stylesheets to build::Found $themes theme(s) but no .scss entry point (a name not starting with '_'). Remove 'build-themes: true' from the calling workflow."
    exit 1
fi
if [ "$missing" -gt 0 ]; then
    echo "::error title=Theme build incomplete::$missing of $expected stylesheet(s) were not built."
    exit 1
fi

printf '%s\n' "${dist_dirs[@]}" | sort -u > "$out"
echo "Verified $expected stylesheet(s) in $themes theme(s)."
