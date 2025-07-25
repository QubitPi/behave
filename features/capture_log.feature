@logging
@capture
Feature: Capture log output

  As a tester
  I want that log output is captured
  But log-records are only shown when failures/errors occur
  So that failure diagnostics are simplified

  . SPECIFICATION:
  .  * capture_log mode is enabled per default
  .  * capture_log mode can be defined on command-line
  .  * capture_log mode can be defined in behave configuration file
  .  * In capture_log mode: Captured log-records are only shown if a scenario fails
  .
  . RELATED:
  .  * capture_log.*.feature
  .  * logging.*.feature

  Background:
    Given a new working directory
    And a file named "features/steps/use_behave4cmd_steps.py" with:
        """
        import behave4cmd0.log_steps
        import behave4cmd0.failing_steps
        import behave4cmd0.passing_steps
        """
    And a file named "features/environment.py" with:
        """
        from behave.capture import capture_output

        @capture_output(show_on_success=True)
        def before_all(context):
            context.config.setup_logging()
            # -- SAME-AS:
            # import logging
            # logging.basicConfig(level=context.config.logging_level)
        """
    And  a file named "features/example.log_and_pass.feature" with:
        """
        Feature:
          Scenario: Passing
            Given I create log records with:
                | category | level   | message |
                | root     |  FATAL  | Hello Alice  |
                | foo      |  ERROR  | Hello Bob    |
                | foo.bar  |  WARN   | Hello Charly |
                | bar      |  INFO   | Hello Dora   |
                | baz      |  DEBUG  | Hello Emily  |
            When another step passes
        """
    And  a file named "features/example.log_and_fail.feature" with:
        """
        Feature:
          Scenario: Failing
            Given I create log records with:
                | category | level   | message |
                | root     |  FATAL  | Hello Alice  |
                | foo      |  ERROR  | Hello Bob    |
                | foo.bar  |  WARN   | Hello Charly |
                | bar      |  INFO   | Hello Dora   |
                | baz      |  DEBUG  | Hello Emily  |
            When another step fails
        """

  Rule: Use Capture log

    Scenario: Captured log is suppressed if scenario passes
        When I run "behave -f plain -T --capture-log features/example.log_and_pass.feature"
        Then it should pass with:
            """
            1 scenario passed, 0 failed, 0 skipped
            2 steps passed, 0 failed, 0 skipped
            """
        And the command output should contain:
            """
            Scenario: Passing
              Given I create log records with: ... passed
                | category | level | message      |
                | root     | FATAL | Hello Alice  |
                | foo      | ERROR | Hello Bob    |
                | foo.bar  | WARN  | Hello Charly |
                | bar      | INFO  | Hello Dora   |
                | baz      | DEBUG | Hello Emily  |
              When another step passes ... passed
            """
        And the command output should not contain "CAPTURED LOG:"
        But the command output should not contain the following log records:
            | category | level   | message |
            | root     |  FATAL  | Hello Alice  |
            | foo      |  ERROR  | Hello Bob    |
            | foo.bar  |  WARN   | Hello Charly |
            | bar      |  INFO   | Hello Dora   |
            | baz      |  DEBUG  | Hello Emily  |


    Scenario: Captured log is shown up to first failure if scenario fails
        Given I use "LOG.%(levelname)s:%(name)s: %(message)s" as log record format
        And a file named "behave.ini" with:
          """
          [behave]
          logging_format = LOG.%(levelname)s:%(name)s: %(message)s
          """
        When I run "behave -f plain -T --capture-log features/example.log_and_fail.feature"
        Then it should fail with:
            """
            Failing scenarios:
              features/example.log_and_fail.feature:2  Failing

            0 features passed, 1 failed, 0 skipped
            0 scenarios passed, 1 failed, 0 skipped
            1 step passed, 1 failed, 0 skipped
            """
        And the command output should contain:
            """
            Feature:
              Scenario: Failing
                Given I create log records with: ... passed
                  | category | level | message      |
                  | root     | FATAL | Hello Alice  |
                  | foo      | ERROR | Hello Bob    |
                  | foo.bar  | WARN  | Hello Charly |
                  | bar      | INFO  | Hello Dora   |
                  | baz      | DEBUG | Hello Emily  |
                When another step fails ... failed
            ASSERT FAILED: EXPECT: Failing step
            """
        And the command output should contain:
            """
            LOG.CRITICAL:root: Hello Alice
            LOG.ERROR:foo: Hello Bob
            LOG.WARNING:foo.bar: Hello Charly
            LOG.INFO:bar: Hello Dora
            """
        And the command output should contain the following log records:
            | category | level   | message |
            | root     |  FATAL  | Hello Alice  |
            | foo      |  ERROR  | Hello Bob    |
            | foo.bar  |  WARN   | Hello Charly |
            | bar      |  INFO   | Hello Dora   |
        But the command output should not contain the following log records:
            | category | level   | message     | Comment |
            | baz      |  DEBUG  | Hello Emily | Log-level too low: filtered-out |


    Scenario: Captured log is shown up to first failure if log_record.level is not too low

      Ensure that only log-records are shown that exceed the logging-level.

        Given I use "LOG.%(levelname)s:%(name)s: %(message)s" as log record format
        And a file named "behave.ini" with:
          """
          [behave]
          logging_format = LOG.%(levelname)s:%(name)s: %(message)s
          """
        When I run "behave -f plain --capture-log --logging-level=ERROR features/example.log_and_fail.feature"
        Then it should fail
        And the command output should contain the following log records:
            | category | level   | message |
            | root     |  FATAL  | Hello Alice  |
            | foo      |  ERROR  | Hello Bob    |
        But the command output should not contain the following log records:
            | category | level   | message |
            | foo.bar  |  WARN   | Hello Charly |
            | bar      |  INFO   | Hello Dora   |
            | baz      |  DEBUG  | Hello Emily  |


  Rule: Enable/Disable Capture-log Mode
    Scenario: Capture-log mode is enabled per default
      When I run "behave -f plain features/example.log_and_fail.feature"
      Then it should fail
      And the command output should contain "CAPTURED LOG:"


    Scenario: Capture-log mode can be enabled on command-line
      When I run "behave -f plain --capture-log features/example.log_and_fail.feature"
      Then it should fail
      And the command output should contain "CAPTURED LOG:"


    Scenario: Capture-log mode can be disabled on command-line
      When I run "behave -f plain --no-logcapture features/example.log_and_fail.feature"
      Then it should fail
      And the command output should not contain "CAPTURED LOG:"


    Scenario: Capture-log mode can be enabled in configfile
      Given a file named "behave.ini" with:
          """
          [behave]
          capture_log = true
          """
      When I run "behave -f plain features/example.log_and_fail.feature"
      Then it should fail
      And the command output should contain "CAPTURED LOG:"


    Scenario: Capture-log mode can be disabled in configfile
      Given a file named "behave.ini" with:
          """
          [behave]
          capture_log = false
          """
      When I run "behave -f plain features/example.log_and_fail.feature"
      Then it should fail
      And the command output should not contain "CAPTURED LOG:"
