#!/usr/bin/env python3
"""Checks a deployment log for error lines.

A port of dockworker's logs:check-file (LogCheckerTrait::partitionLogLines and
logsHaveErrors, plus dockworker-drupal's exception list) with no PHP dependency.

  1. Lines carrying a non-error Drush severity marker are removed from the scan:
     '[warning]' lines are collected and reported, '[notice]', '[success]', '[ok]',
     '[info]', '[debug]' and '[cancelled]' lines are dropped. The 'drush updatedb'
     pending-updates preview table is dropped too, because its rows print update hook
     descriptions that routinely contain "error" or "fail".
  2. Every remaining line (markerless, or '[error]') matching any error pattern fails
     the check, unless the same line also matches an exception pattern.

Patterns are case-insensitive regular expressions, read one per line from the rules
directory: core.errors always, plus <profile>.exceptions for the chosen profile.

Exit status: 0 when no errors are found, 1 when errors are found or the log is unreadable.
"""

import argparse
import re
import sys
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent / "rules"

ANSI_SGR = re.compile(r"\x1b\[[\d;]*m")
NON_FATAL_SEVERITY = re.compile(r"\[(warning|notice|success|ok|info|debug|cancelled)\]", re.I)

# Stable Drush strings bounding the 'drush updatedb' pending-updates preview. The cap is a
# safety backstop in case the closing confirm never arrives (e.g. a Drush format change).
UPDB_CONFIRM = "Do you wish to run the specified pending updates"
UPDB_PREVIEW_LINE_CAP = 2000


def read_rules(path):
    """Returns the patterns in a rules file, skipping blank and '#' comment lines."""
    patterns = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def compile_alternation(patterns):
    """Joins patterns into one case-insensitive alternation, or None when there are none."""
    if not patterns:
        return None
    return re.compile("(?:" + "|".join(patterns) + ")", re.I)


def is_updb_preview_header(line):
    return "Update ID" in line and "Description" in line


def partition(lines):
    """Splits log lines into the lines to scan and the collected '[warning]' lines."""
    scan = []
    warnings = []
    in_preview = False
    preview_lines = 0
    for line in lines:
        bare = ANSI_SGR.sub("", line)

        if in_preview:
            preview_lines += 1
            if UPDB_CONFIRM in bare:
                # Drush auto-confirms and the scannable update execution begins.
                in_preview = False
                preview_lines = 0
            elif preview_lines > UPDB_PREVIEW_LINE_CAP:
                # Never suppress unbounded.
                in_preview = False
                preview_lines = 0
                scan.append(line)
            continue

        if is_updb_preview_header(bare):
            in_preview = True
            preview_lines = 0
            continue

        severity = NON_FATAL_SEVERITY.search(bare)
        if severity:
            if severity.group(1).lower() == "warning":
                warnings.append(line)
            continue

        scan.append(line)
    return scan, warnings


def find_errors(lines, errors, exceptions):
    """Returns the lines matching an error pattern and no exception pattern."""
    return [
        line
        for line in lines
        if errors.search(line) and not (exceptions and exceptions.search(line))
    ]


def check(text, errors, exceptions):
    """Returns (error lines, unique warning lines) for a complete log."""
    scan, warnings = partition(text.split("\n"))
    unique_warnings = []
    for warning in warnings:
        trimmed = warning.strip()
        if trimmed and trimmed not in unique_warnings:
            unique_warnings.append(trimmed)
    return find_errors(scan, errors, exceptions), unique_warnings


def load_patterns(profile, extra_exceptions=""):
    errors = read_rules(RULES_DIR / "core.errors")
    exceptions = []
    profile_rules = RULES_DIR / f"{profile}.exceptions"
    if profile_rules.exists():
        exceptions += read_rules(profile_rules)
    exceptions += [p for p in extra_exceptions.split("\n") if p.strip()]
    return compile_alternation(errors), compile_alternation(exceptions)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("log_file")
    parser.add_argument(
        "--profile",
        default="generic",
        help="Exception set to apply: generic (none) or drupal. Default generic.",
    )
    parser.add_argument(
        "--extra-exceptions",
        default="",
        help="Additional newline-delimited exception patterns.",
    )
    args = parser.parse_args()

    known = {"generic"} | {p.stem for p in RULES_DIR.glob("*.exceptions")}
    if args.profile not in known:
        print(f"::error title=Unknown profile::'{args.profile}' is not one of: {', '.join(sorted(known))}.")
        return 1

    try:
        text = Path(args.log_file).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"::error title=Unreadable log::Log file [{args.log_file}] is not readable: {e}")
        return 1

    errors, exceptions = load_patterns(args.profile, args.extra_exceptions)
    error_lines, warnings = check(text, errors, exceptions)

    if error_lines:
        print(f"::error title=Errors found in logs::{len(error_lines)} line(s) matched an error pattern.")
        for line in error_lines:
            print(f" * {line}")
        return 1

    if warnings:
        print(f"::warning title=Startup warnings::{len(warnings)} warning(s) were emitted during startup (non-fatal).")
        for warning in warnings:
            print(f" * {warning}")
    print("No errors detected in logs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
