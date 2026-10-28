#!/usr/bin/env python3
"""Regression tests for check_logs.py.

The fixtures are verbatim docker-compose captures from real Drush runs, ported from
dockworker's test/log_classifier_test.php, including the "<slug>  | " prefix.

Run: python3 -m unittest .github/actions/check-logs/test_check_logs.py
"""

import unittest

import check_logs

SCHEMA_SINGLE_LINE = 'loyalist-lib-unb-ca  |  [warning] Schema errors for views.settings with the following errors: views.settings:skip_cache missing schema. These errors mean there is configuration that does not comply with its schema. This is not a fatal error, but it is recommended to fix these issues. For more information on configuration schemas, check out <a href="https://www.drupal.org/docs/drupal-apis/configuration-api/configuration-schemametadata">the documentation</a>.'

SCHEMA_WRAPPED = """\
loyalist-lib-unb-ca  | >  [warning] Message: Schema errors for views.settings with the following errors:
loyalist-lib-unb-ca  | > views.settings:skip_cache missing schema. These errors mean there is
loyalist-lib-unb-ca  | > configuration that does not comply with its schema. This is not a fatal
loyalist-lib-unb-ca  | > error, but it is recommended to fix these issues. For more information on
loyalist-lib-unb-ca  | > configuration schemas, check out the documentation [1].
loyalist-lib-unb-ca  | >
loyalist-lib-unb-ca  | > [1] https://www.drupal.org/docs/drupal-apis/configuration-api/configuration-schemametadata"""

REQUIREMENTS = "loyalist-lib-unb-ca  |  // Requirements check reports errors. Do you wish to continue?: yes."

NOTICE_ERRORS = 'loyalist-lib-unb-ca  |  [notice] Module jquery_scrollup has an entry in the system.schema key/value storage, but is missing. <a href="https://www.drupal.org/node/3137656">More information about this error</a>.'

UPDB_PREVIEW = """\
loyalist-lib-unb-ca  |  // Requirements check reports errors. Do you wish to continue?: yes.
loyalist-lib-unb-ca  |
loyalist-lib-unb-ca  |  ------------------------ ----------- ------- ----------------
loyalist-lib-unb-ca  |   Module                   Update ID   Type    Description
loyalist-lib-unb-ca  |  ------------------------ ----------- ------- ----------------
loyalist-lib-unb-ca  |   file   add_playsinline   post-update   Adds a value for playsinline. This was rolled back due to a
loyalist-lib-unb-ca  |                                                  bug and is kept only to prevent errors when updating.   @see
loyalist-lib-unb-ca  |   views   table_css_class   post-update   Adds a default table CSS class.
loyalist-lib-unb-ca  |  ------------------------ ----------- ------- ----------------
loyalist-lib-unb-ca  |
loyalist-lib-unb-ca  |  // Do you wish to run the specified pending updates?: yes.
loyalist-lib-unb-ca  | >  [notice] Update started: file_post_update_add_playsinline
loyalist-lib-unb-ca  | >  [notice] Update completed: file_post_update_add_playsinline"""

REAL_ERROR = "loyalist-lib-unb-ca  | >  [error] Drupal\\Core\\Database\\DatabaseExceptionWrapper: boom"
MARKERLESS_ERROR = "loyalist-lib-unb-ca  | ERROR 1064 (42000): You have a syntax error"
FAILED_WITH_ERRORS = "loyalist-lib-unb-ca  | Deployment failed with errors:"
PHP_FATAL = "loyalist-lib-unb-ca  | PHP Fatal error:  Uncaught Error: boom"


class DrupalProfileTest(unittest.TestCase):
    def setUp(self):
        self.errors, self.exceptions = check_logs.load_patterns("drupal")

    def assertFatal(self, log, expected):
        error_lines, _ = check_logs.check(log, self.errors, self.exceptions)
        self.assertEqual(bool(error_lines), expected, error_lines)

    def test_schema_warning_single_line(self):
        self.assertFatal(SCHEMA_SINGLE_LINE, False)

    def test_schema_warning_wrapped_block(self):
        self.assertFatal(SCHEMA_WRAPPED, False)

    def test_schema_warning_bare_wrap_tail(self):
        # Drush wraps "...with the following\nerrors:", leaving a bare "errors:" line.
        self.assertFatal("loyalist-lib-unb-ca  |  errors:", False)
        self.assertFatal("errors:", False)
        # Matches dockworker 6.x: the exception does not cover the "| > " prefix.
        self.assertFatal("loyalist-lib-unb-ca  | > errors:", True)

    def test_drush_requirements_auto_continue(self):
        self.assertFatal(REQUIREMENTS, False)

    def test_notice_mentioning_error(self):
        self.assertFatal(NOTICE_ERRORS, False)

    def test_updb_preview_table(self):
        self.assertFatal(UPDB_PREVIEW, False)

    def test_updb_preview_then_real_error(self):
        self.assertFatal(UPDB_PREVIEW + "\nloyalist-lib-unb-ca  | >  [error] Update failed: kaboom", True)

    def test_updb_preview_cap(self):
        # A preview that never confirms stops suppressing after the cap.
        header = "  Module   Update ID   Type    Description"
        filler = ["  row"] * (check_logs.UPDB_PREVIEW_LINE_CAP + 1)
        self.assertFatal("\n".join([header] + filler + ["Fatal error: boom"]), True)

    def test_real_error_line(self):
        self.assertFatal(REAL_ERROR, True)

    def test_markerless_db_error(self):
        self.assertFatal(MARKERLESS_ERROR, True)

    def test_markerless_failed_with_errors(self):
        self.assertFatal(FAILED_WITH_ERRORS, True)

    def test_markerless_php_fatal(self):
        self.assertFatal(PHP_FATAL, True)

    def test_zero_failed_needs_leading_space(self):
        self.assertFatal("Processed 12 items (12 created, 0 updated, 0 failed)", False)
        self.assertFatal("Processed 12 items (12 created, 10 failed)", True)

    def test_ansi_colours_do_not_hide_markers(self):
        self.assertFatal("\x1b[33m[warning]\x1b[0m something failed", False)

    def test_warning_collection(self):
        _, warnings = check_logs.check(SCHEMA_WRAPPED, self.errors, self.exceptions)
        self.assertEqual(len(warnings), 1)

    def test_warnings_are_deduplicated(self):
        log = "[warning] same thing\n  [warning] same thing  \n[warning] other"
        _, warnings = check_logs.check(log, self.errors, self.exceptions)
        self.assertEqual(warnings, ["[warning] same thing", "[warning] other"])


class GenericProfileTest(unittest.TestCase):
    def test_no_exceptions_apply(self):
        errors, exceptions = check_logs.load_patterns("generic")
        self.assertIsNone(exceptions)
        error_lines, _ = check_logs.check(REQUIREMENTS, errors, exceptions)
        self.assertTrue(error_lines)

    def test_extra_exceptions(self):
        errors, exceptions = check_logs.load_patterns("generic", "known noise\n\nother noise\n")
        error_lines, _ = check_logs.check("known noise: failed\nreal failure", errors, exceptions)
        self.assertEqual(error_lines, ["real failure"])


if __name__ == "__main__":
    unittest.main()
