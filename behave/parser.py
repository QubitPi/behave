# -*- coding: UTF-8 -*-
# pylint: disable=consider-using-f-string,redundant-u-string-prefix
# pylint: disable=super-with-arguments,useless-object-inheritance
# pylint: disable=line-too-long
"""
Gherkin parser with `Gherkin v6 grammar`_ (and Gherkin v5 or older).

Gherkin v6 grammar extensions:

* Rule keyword added
* Aliases for Scenario, ScenarioOutline to better correspond to `Example Mapping`_

A Rule (or: business rule) allows to group multiple Scenarios::

    # -- RULE GRAMMAR PSEUDO-CODE:
    @tag1 @tag2
    Rule: Optional Rule Title...
        Description?        #< CARDINALITY: 0..1 (optional)
        Background?         #< CARDINALITY: 0..1 (optional)
        Scenario*           #< CARDINALITY: 0..N (many)
        ScenarioOutline*    #< CARDINALITY: 0..N (many)

Keyword aliases:

    | Concept          | Gherkin v6         | Alias (Gherkin v5) |
    | Scenario         | Example            | Scenario           |
    | Scenario Outline | Scenario Template  | Scenario Outline   |

.. seealso::

    * `Gherkin v6 grammar`_

    EXAMPLE MAPPING:

    * Cucumber: `Example Mapping`_
    * Cucumber: `Example Mapping Webinar`_
    * https://docs.cucumber.io/bdd/example-mapping/

.. _`Gherkin v6 grammar`: https://github.com/cucumber/cucumber/blob/master/gherkin/gherkin.berp
.. _`Example Mapping`: https://cucumber.io/blog/example-mapping-introduction/
.. _`Example Mapping Webinar`: https://cucumber.io/blog/example-mapping-webinar/
"""
# pylint: enable=line-too-long

from __future__ import absolute_import, with_statement
from enum import Enum
import logging
import os
import re
import sys
import six

from behave._types import require_type, require_not_none
from behave import model, i18n
from behave.textutil import text as _text
from behave._types import NoneType


# -----------------------------------------------------------------------------
# CONSTANTS
# -----------------------------------------------------------------------------
DEFAULT_LANGUAGE = "en"
BEHAVE_STRIP_STEPS_WITH_TRAILING_COLON = os.environ.get(
    "BEHAVE_STRIP_STEPS_WITH_TRAILING_COLON", "no") == "yes"


# -----------------------------------------------------------------------------
# GHERKIN PARSE FUNCTIONS:
# -----------------------------------------------------------------------------
def parse_file(filename, language=None):
    with open(filename, "rb") as f:
        # file encoding is assumed to be utf8. Oh, yes.
        data = f.read().decode("utf8")
    return parse_feature(data, language, filename)


def parse_feature(text, language=None, filename=None):
    # ALL data operated on by the parser MUST be unicode
    require_type(text, six.text_type)

    try:
        result = Parser(language).parse(text, filename)
    except ParserError as e:
        e.filename = filename
        raise

    return result


def parse_rule(text, language=None, filename=None):
    """
    Parse a rule with its background and scenario(s).

    :param text: Multi-line text with rule to parse (as unicode).
    :param language:  i18n language identifier (optional).
    :param filename:  Filename (optional).
    :return: Rule object (if successful).
    """
    require_type(text, six.text_type)
    try:
        parser = Parser(language, variant="rule")
        result = parser.parse_rule(text, filename)
    except ParserError as e:
        e.filename = filename
        raise
    return result


def parse_scenario(text, language=None, filename=None):
    """
    Parse a scenario with its stepss.

    :param text: Multi-line text with scenario to parse (as unicode).
    :param language:  i18n language identifier (optional).
    :param filename:  Filename (optional).
    :return: Scenario object (if successful).
    """
    require_type(text, six.text_type)
    try:
        parser = Parser(language, variant="scenario")
        result = parser.parse_scenario(text, filename)
    except ParserError as e:
        e.filename = filename
        raise
    return result


def parse_steps(text, language=None, filename=None):
    """
    Parse a number of steps a multi-line text from a scenario.
    Scenario line with title and keyword is not provided.

    :param text: Multi-line text with steps to parse (as unicode).
    :param language:  i18n language identifier (optional).
    :param filename:  Filename (optional).
    :return: List of Step objects (if successful).
    """
    require_type(text, six.text_type)
    try:
        parser = Parser(language, variant="steps")
        result = parser.parse_steps(text, filename)
    except ParserError as e:
        e.filename = filename
        raise
    return result


def parse_step(text, language=None, filename=None):
    """
    Parse one step as multi-line text.

    :param text: Multi-line text with step to parse (as unicode).
    :param language:  i18n language identifier (optional).
    :param filename:  Filename (optional).
    :return: Step object (if successful).
    """
    steps = parse_steps(text, language=language, filename=filename)
    if not (len(steps) == 1):
        raise ParserError("MULTIPLE STEPS: Expected one")
    return steps[0]


def parse_tags(text):
    """
    Parse tags from text (one or more lines, as string).

    :param text: Multi-line text with tags to parse (as unicode).
    :return: List of tags (if successful).
    """
    # require_type(text, unicode)
    if not text:
        return []
    return Parser(variant="tags").parse_tags(text)


# -----------------------------------------------------------------------------
# GHERKIN PARSER
# -----------------------------------------------------------------------------
class ParserError(Exception):
    @staticmethod
    def make_annotated(message, line_number, line_text=None, reason=None):
        """Make annotated message enriched w/ line_number, line_text."""
        if line_number:
            message += u" at line %d" % line_number
        if line_text:
            message += u': "%s"' % line_text.strip()
        if reason:
            message += u"\nREASON: %s" % reason
        return message

    def __init__(self, message, line, filename=None, line_text=None,
                 reason=None, use_annotated_message=True):
        if use_annotated_message:
            message = self.make_annotated(message, line, line_text, reason)

        super(ParserError, self).__init__(message)
        self.line = line    # Line number of parse failure.
        self.line_text = line_text
        self.filename = filename

    def __str__(self):
        arg0 = _text(self.args[0])
        if self.filename:
            filename = _text(self.filename, sys.getfilesystemencoding())
            return u'Failed to parse "%s": %s' % (filename, arg0)
        # -- OTHERWISE:
        return u"Failed to parse <string>: %s" % arg0

    if six.PY2:
        # pylint: disable=unnecessary-lambda-assignment
        __unicode__ = __str__
        __str__ = lambda self: self.__unicode__().encode("UTF-8")  # noqa: E731


class State(Enum):
    """Parser States"""
    INITIAL = 0
    FEATURE = 1
    RULE = 2
    BACKGROUND = 3
    SCENARIO = 4
    TAGGABLE_STATEMENT = 5
    STEPS = 6
    STEP = 7
    MULTILINE_TEXT = 8
    TABLE = 9


class Parser(object):
    """Feature file parser for behave."""
    # pylint: disable=too-many-instance-attributes
    STRIP_STEPS_WITH_TRAILING_COLON = BEHAVE_STRIP_STEPS_WITH_TRAILING_COLON

    def __init__(self, language=None, variant=None):
        if not variant:
            variant = "feature"
        self.language = language
        self.variant = variant

        # -- SAME AS: self.reset()
        language = self.language or DEFAULT_LANGUAGE
        self.keywords = i18n.languages[language]

        self.state = State.INITIAL
        self.line = 0
        self.last_step_type = None
        self.multiline_start = None
        self.multiline_leading = None
        self.multiline_terminator = None

        self.filename = None
        self.scenario_container = None  # Feature or Rule.
        self.feature = None
        self.rule = None
        self.parent = None
        self.statement = None
        self.tags = []
        self.lines = []
        self.table = None
        self.examples = None
        self.keywords = None
        if self.language:
            self.keywords = i18n.languages[self.language]
        # NOT-NEEDED: self.reset()

    def reset(self, filename=None):
        self.language = self.language or DEFAULT_LANGUAGE
        self.keywords = i18n.languages[self.language]

        self.state = State.INITIAL
        self.line = 0
        self.last_step_type = None
        self.multiline_start = None
        self.multiline_leading = None
        self.multiline_terminator = None

        self.filename = filename
        self.scenario_container = None  # Feature or Rule.
        self.feature = None
        self.rule = None
        self.parent = None
        self.statement = None
        self.tags = []
        self.lines = []
        self.table = None
        self.examples = None

    def _parse_loop(self, text, initial_state=None, filename=None):
        """Core parsing loop to simplify use for multiple start points.

        SUPPORTS:

        * Parse a feature (file)
        * Parse a rule
        * Parse a scenario
        * Parse many steps
        * Parse one step
        """
        require_type(text, six.string_types)
        require_type(initial_state, (State, NoneType))
        self.reset(filename=filename)
        if initial_state is not None:
            self.state = initial_state
        if self.state == State.STEPS:
            # WAS: keyword = self.match_keyword(u"scenario", line=u"Scenario:")
            keyword = self.keywords["scenario"][0]
            self._build_scenario_statement(keyword, line=u"{0}:".format(keyword))

        for line in text.splitlines():
            self.line += 1
            if not line.strip() and self.state != State.MULTILINE_TEXT:
                # -- SKIP EMPTY LINES, except in multiline string args.
                continue
            self.action(line)

        if self.table is not None:
            self.action_table("")

    def parse(self, text, filename=None):
        self._parse_loop(text, filename=filename)
        feature = self.feature
        if feature:
            feature.parser = self
        return feature

    def _build_feature(self, keyword, line):
        name = line[len(keyword) + 1:].strip()
        language = self.language or DEFAULT_LANGUAGE
        feature = model.Feature(self.filename, self.line, keyword, name,
                                tags=self.tags, language=language)
        self.feature = feature
        self.scenario_container = feature
        self.rule = None
        # -- RESET STATE:
        self.tags = []

    def _build_rule_statement(self, keyword, line):
        name = line[len(keyword) + 1:].strip()
        rule = model.Rule(self.filename, self.line, keyword, name,
                          tags=self.tags)
        self.rule = rule
        self.scenario_container = rule
        self.statement = rule
        if self.feature is not None:
            self.feature.add_rule(self.statement)

        # -- RESET STATE:
        self.tags = []

    def _build_background_statement(self, keyword, line):
        if self.tags:
            msg = u"Background supports no tags: @%s" % (u" @".join(self.tags))
            raise ParserError(msg, self.line, self.filename, line)
        if self.scenario_container and self.scenario_container.background:
            if self.scenario_container.background.steps:
                # -- HINT: Rule may have default background w/o steps.
                msg = u"Second Background (can have only one)"
                raise ParserError(msg, self.line, self.filename, line)
        name = line[len(keyword) + 1:].strip()
        background = model.Background(self.filename, self.line, keyword, name)
        self.scenario_container.add_background(background)
        self.statement = background

    def _build_scenario_statement(self, keyword, line):
        name = line[len(keyword) + 1:].strip()
        scenario = model.Scenario(self.filename, self.line, keyword, name,
                                  tags=self.tags)
        self.statement = scenario
        if self.scenario_container:
            self.scenario_container.add_scenario(scenario)
        # OLD: self.feature.add_scenario(self.statement)
        # -- RESET STATE:
        self.tags = []

    def _build_scenario_outline_statement(self, keyword, line):
        # pylint: disable=C0103
        #   C0103   Invalid name "build_scenario_outline_statement", too long.
        name = line[len(keyword) + 1:].strip()
        template = model.ScenarioOutline(self.filename, self.line, keyword, name,
                                         tags=self.tags)
        self.statement = template
        self.scenario_container.add_scenario(template)

        # -- RESET STATE:
        self.tags = []

    def _build_examples(self, keyword, line):
        if not isinstance(self.statement, model.ScenarioOutline):
            message = u"Examples must only appear inside scenario outline"
            raise ParserError(message, self.line, self.filename, line)
        name = line[len(keyword) + 1:].strip()
        self.examples = model.Examples(self.filename, self.line,
                                       keyword, name, tags=self.tags)
        # pylint: disable=E1103
        #   E1103   Instance of "Background" has no "examples" member
        #           (but some types could not be inferred).
        self.statement.examples.append(self.examples)

        # -- RESET STATE:
        self.tags = []

    def diagnose_feature_usage_error(self):
        if self.feature:
            return "Multiple features in one file are not supported."
        # -- OTHERWISE:
        return "Feature should not be used here."

    @staticmethod
    def diagnose_rule_usage_error():
        return "Rule should not be used here."

    def diagnose_background_usage_error(self):
        if self.scenario_container and self.scenario_container.scenarios:
            # -- CASE: Feature or Rule
            return "Background may not occur after Scenario/ScenarioOutline."
        if self.tags:
            return "Background does not support tags."
        # -- OTHERWISE:
        return "Background should not be used here."

    def diagnose_scenario_usage_error(self):
        if not self.scenario_container:
            return "Scenario may not occur before Feature."
        # -- OTHERWISE:
        return "Scenario should not be used here."

    def diagnose_scenario_outline_usage_error(self): # pylint: disable=invalid-name
        if not self.scenario_container:
            return "ScenarioOutline may not occur before Feature."
        # -- OTHERWISE:
        return "ScenarioOutline should not be used here."

    def ask_parse_failure_oracle(self, line):
        """
        Try to find the failure reason when a parse failure occurs:

            Oracle, oracle, ... what went wrong?

        :param line:  Text line where parse failure occurred (as string).
        :return: Reason (as string) if an explanation is found.
                 Otherwise, empty string or None.
        """
        # pylint: disable=too-many-return-statements
        feature_keyword = self.match_keyword("feature", line)
        if feature_keyword:
            return self.diagnose_feature_usage_error()
        rule_keyword = self.match_keyword("rule", line)
        if rule_keyword:
            return self.diagnose_rule_usage_error()
        background_keyword = self.match_keyword("background", line)
        if background_keyword:
            return self.diagnose_background_usage_error()
        scenario_keyword = self.match_keyword("scenario", line)
        if scenario_keyword:
            return self.diagnose_scenario_usage_error()
        scenario_outline_keyword = self.match_keyword("scenario_outline", line)
        if scenario_outline_keyword:
            return self.diagnose_scenario_outline_usage_error()
        # -- OTHERWISE:
        if self.variant == "feature" and not self.feature:
            return "No feature found."
        # -- FINALLY: No glue what went wrong.
        return None

    def _normalize_step_name(self, step):
        if self.STRIP_STEPS_WITH_TRAILING_COLON and step.name.endswith(":"):
            step.name = step.name[:-1]

    def action(self, line):
        if line.strip().startswith("#") and self.state != State.MULTILINE_TEXT:
            if (self.state != State.INITIAL or
                self.tags or self.variant != "feature"):
                return

            # -- DETECT: language comment (at begin of feature file; state=init)
            line = line.strip()[1:].strip()
            if line.lstrip().lower().startswith("language:"):
                language = line[9:].strip()
                self.language = language
                self.keywords = i18n.languages[language]
            return

        state_name = self.state.name.lower()
        func = getattr(self, "action_" + state_name, None)
        if func is None:
            line = line.strip()
            msg = u"Parser in unknown state %s;" % self.state
            raise ParserError(msg, self.line, self.filename, line)

        if not func(line):
            line = line.strip()
            msg = u'\nParser failure in state=%s' % self.state.name.lower()
            reason = self.ask_parse_failure_oracle(line)
            raise ParserError(msg, self.line, self.filename,
                              line_text=line, reason=reason)

    def action_initial(self, line):
        line = line.strip()
        if line.startswith("@"):
            self.tags.extend(self.parse_tags(line))
            return True

        feature_keyword = self.match_keyword("feature", line)
        if feature_keyword:
            self._build_feature(feature_keyword, line)
            self.state = State.FEATURE
            return True
        return False

    # pylint: disable=invalid-name
    def subaction_detect_taggable_statement(self, line):
        """Subaction is used after first tag line is detected.
        Additional lines with tags or taggable_statement follow.

        Taggable statements (excluding Feature) are:
        * Rule
        * Scenario
        * ScenarioOutline
        * Examples (within ScenarioOutline)
        """
        if line.startswith("@"):
            self.tags.extend(self.parse_tags(line))
            self.state = State.TAGGABLE_STATEMENT
            return True

        rule_keyword = self.match_keyword("rule", line)
        if rule_keyword:
            # MAYBE: Finish last rule statement
            self._build_rule_statement(rule_keyword, line)
            self.state = State.RULE
            return True

        scenario_keyword = self.match_keyword("scenario", line)
        if scenario_keyword:
            self._build_scenario_statement(scenario_keyword, line)
            self.state = State.SCENARIO
            return True

        template_keyword = self.match_keyword("scenario_outline", line)
        if template_keyword:
            self._build_scenario_outline_statement(template_keyword, line)
            self.state = State.SCENARIO
            return True

        examples_keyword = self.match_keyword("examples", line)
        if examples_keyword:
            self._build_examples(examples_keyword, line)
            self.state = State.TABLE
            return True

        # -- OTHERWISE:
        return False
    # pylint: enable=invalid-name

    def action_feature(self, line):
        line = line.strip()
        if self.subaction_detect_taggable_statement(line):
            # -- DETECTED: Next Rule, Scenario, ScenarioOutline (or tags)
            return True

        background_keyword = self.match_keyword("background", line)
        if background_keyword:
            self._build_background_statement(background_keyword, line)
            self.state = State.BACKGROUND
            return True

        self.feature.description.append(line)
        return True

    def action_taggable_statement(self, line):
        """
        Entered after first tag for Scenario/ScenarioOutline or
        Examples is detected (= taggable_statement except Feature).

        Taggable statements (excluding Feature) are:
          * Scenario
          * ScenarioOutline
          * Examples (within ScenarioOutline)
        """
        line = line.strip()
        if self.subaction_detect_taggable_statement(line):
            # -- DETECTED: Next Scenario, ScenarioOutline or Examples (or tags)
            return True

        return False

    def action_background(self, line):
        """
        Entered when Background keyword/line is detected.
        Hunts/collects background description lines.

        DETECT:

        * first step of Background
        * next Scenario/ScenarioOutline.
        * any description line after Background keyword
        """
        # -- SAME AS: action_scenario(), only Background is used as self.statement.
        # REUSE: Already existing action.
        return self.action_scenario(line)

    def action_rule(self, line):
        """
        Entered when Rule keyword/line is detected.
        Hunts/collects rule description lines.

        DETECT:

        * any description line after Rule keyword (optional)
        * Backgroup statement (optional)
        * Scenario/ScenarioOutline statements (many)
        """
        # -- SIMILAR TO: action_feature()
        line = line.strip()
        if self.subaction_detect_taggable_statement(line):
            # -- DETECTED: Next Rule, Scenario, ScenarioOutline (or tags)
            return True

        background_keyword = self.match_keyword("background", line)
        if background_keyword:
            self._build_background_statement(background_keyword, line)
            self.state = State.BACKGROUND
            return True

        self.rule.description.append(line)
        return True


    def action_scenario(self, line):
        """
        Entered when Scenario/ScenarioOutline keyword/line is detected.
        Hunts/collects scenario description lines.

        DETECT:

        * any description line after Scenario/ScenarioOutline keyword
        * first step of Scenario/ScenarioOutline
        * next Scenario/ScenarioOutline
        """
        self.last_step_type = None
        line = line.strip()
        step = self.parse_step(line)
        if step:
            # -- FIRST STEP DETECTED: End collection of description-part.
            self.state = State.STEPS
            self.statement.steps.append(step)
            return True

        # -- CASE: Detect next Scenario/ScenarioOutline
        #   * Background/Scenario with description, but without steps.
        #   * Title-only Background/Scenario without description and steps.
        if self.subaction_detect_taggable_statement(line):
            # -- DETECTED: Next Scenario, ScenarioOutline (or tags)
            return True

        # -- OTHERWISE: Add description line.
        # pylint: disable=E1103
        #   E1103   Instance of "Background" has no "description" member...
        self.statement.description.append(line)
        return True

    def action_steps(self, line):
        """
        Entered when first step is detected (or nested step parsing).

        Subcases:
          * step
          * multi-line text (doc-string), following a step
          * table, following a step
          * examples for a ScenarioOutline, after ScenarioOutline steps

        DETECT:
          * next Scenario/ScenarioOutline or Examples (in a ScenarioOutline)
        """
        # pylint: disable=R0911
        #   R0911   Too many return statements (8/6)
        stripped = line.lstrip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            # -- CASE: Multi-line text (docstring) after a step detected.
            # REQUIRE: Multi-line text follows a step.
            if not self.statement.steps:
                raise ParserError("Multi-line text before any step",
                                  self.line, self.filename)

            self.state = State.MULTILINE_TEXT
            self.multiline_start = self.line
            self.multiline_terminator = stripped[:3]
            self.multiline_leading = line.index(stripped[0])
            return True

        line = line.strip()
        step = self.parse_step(line)
        if step:
            self.statement.steps.append(step)
            return True

        if self.subaction_detect_taggable_statement(line):
            # -- DETECTED: Next Scenario, ScenarioOutline or Examples (or tags)
            return True

        if line.startswith("|"):
            # -- CASE: TABLE-START detected for data-table of a step
            if not self.statement.steps:
                raise ParserError("TABLE-START without step detected",
                                  self.line, self.filename)
            self.state = State.TABLE
            return self.action_table(line)

        return False

    def action_multiline_text(self, line):
        """Parse remaining multi-line/docstring text below a step
        after the triple-quotes were detected:

        * triple-double-quotes or
        * triple-single-quotes

        Leading and trailing triple-quotes must be the same.

        :param line:  Parsed line, as part of a multi-line text (as string).
        """
        if line.strip().startswith(self.multiline_terminator):
            # -- CASE: Handle the end of a multi-line text part.
            # Store the multi-line text in the step object (and continue).
            this_step = self.statement.steps[-1]
            text = u"\n".join(self.lines)
            this_step.text = model.Text(text, u"text/plain", self.multiline_start)
            self._normalize_step_name(this_step)

            # -- RESET INTERNALS: For next step
            self.lines = []
            self.multiline_terminator = None
            self.state = State.STEPS  # NEXT-STATE: Accept additional step(s).
            return True

        # -- SPECIAL CASE: Strip trailing whitespace (whitespace normalization).
        # HINT: Required for Windows line-endings, like "\r\n", etc.
        text_line = line[self.multiline_leading:].rstrip()
        self.lines.append(text_line)

        # -- BETTER DIAGNOSTICS: May remove non-whitespace in execute_steps()
        removed_line_prefix = line[:self.multiline_leading]
        if removed_line_prefix.strip():
            message = u"BAD-INDENT in multiline text: "
            message += u"Line '%s' would strip leading '%s'" % \
                        (line, removed_line_prefix)
            raise ParserError(message, self.line, self.filename)
        return True

    def action_table(self, line):
        """Parse a table, with pipe-separated columns:

        * Data table of a step (after the step line)
        * Examples table of a ScenarioOutline
        """
        line = line.strip()
        if not line.startswith("|"):
            # -- CASE: End-of-table detected
            if self.examples:
                # -- CASE: Examples table of a ScenarioOutline
                self.examples.table = self.table
                self.examples = None
            else:
                # -- CASE: Data table of a step
                step = self.statement.steps[-1]
                step.table = self.table
                self._normalize_step_name(step)

            # -- RESET: Parameters for parsing the next step(s).
            self.table = None
            self.state = State.STEPS
            return self.action_steps(line)

        if not re.match(r"^(|.+)\|$", line):
            logger = logging.getLogger("behave")
            logger.warning(u"Malformed table row at %s: line %i",
                           self.feature.filename, self.line)

        # -- SUPPORT: Escaped-pipe(s) in Gherkin cell values.
        #    Search for pipe(s) that are not preceded with an escape char.
        cells = [cell.replace("\\|", "|").strip()
                 for cell in re.split(r"(?<!\\)\|", line[1:-1])]
        if self.table is None:
            # -- CASE: First row of the table
            headings = cells
            self.table = model.Table(headings, line=self.line)
        else:
            # -- CASE: Following rows of the table
            if len(cells) != len(self.table.headings):
                raise ParserError(u"Malformed table", self.line, self.filename)
            self.table.add_row(cells, self.line)
        return True

    def match_keyword(self, keyword, line):
        if not self.keywords:
            self.language = DEFAULT_LANGUAGE
            self.keywords = i18n.languages[DEFAULT_LANGUAGE]
        for alias in self.keywords[keyword]:
            if line.startswith(alias + ":"):
                return alias
        return None

    def parse_rule(self, text, filename=None):
        """
        Parse rule with optional background and scenario(s).

        :param text:  Text that contains 1 rule w/ multiple scenarios.
        :return: Parsed rule (as :class:`~behave.model:Rule` object).
        """
        self._parse_loop(text, initial_state=State.RULE, filename=filename)
        return self.rule

    def parse_scenario(self, text, filename=None):
        self._parse_loop(text, initial_state=State.SCENARIO ,filename=filename)
        scenario = self.statement
        return scenario

    def parse_tags(self, line):
        """
        Parse a line with one or more tags:

          * A tag starts with the AT sign.
          * A tag consists of one word without whitespace chars.
          * Multiple tags are separated with whitespace chars
          * End-of-line comment is stripped.

        :param line:   Line with one/more tags to process.
        :raise ParserError: If syntax error is detected.
        """
        if not line.startswith("@"):
            message = "BAD_TAG-LINE: %s (location: %s:%s)"
            raise ParserError(message % (line, self.filename, self.line))

        tags = []
        for word in line.split():
            if word.startswith("@"):
                tags.append(model.Tag(word[1:], self.line))
            elif word.startswith("#"):
                break   # -- COMMENT: Skip rest of line.
            else:
                # -- BAD-TAG: Abort here.
                message = u"tag: %s (line: %s)" % (word, line)
                raise ParserError(message, self.line, self.filename)
        return tags

    def parse_step(self, line):
        for step_type in ("given", "when", "then", "and", "but"):
            for kw in self.keywords[step_type]:
                # try to match the keyword; also attempt a purely lowercase
                # match if that'll work
                if not (line.startswith(kw) or
                        line.lower().startswith(kw.lower())):
                    # -- CASE: Line does not start w/ a step-keyword.
                    continue

                # -- HINT: Trailing SPACE is used for most keywords.
                # BUT: Keywords in some languages (like Chinese, Japanese, ...)
                #      do not need a whitespace as word separator.
                step_text_after_keyword = line[len(kw):].strip()
                if kw.startswith("*") and self.last_step_type:
                    # -- CASE: Generic steps and Given/When/Then steps are mixed.
                    # HINT: Inherit step type from last step.
                    step_type = self.last_step_type
                elif step_type in ("and", "but"):
                    if not self.last_step_type:
                        # -- BEST-EFFORT: Try to use last background.step.
                        self.last_step_type = self._select_last_background_step_type()
                        if not self.last_step_type:
                            msg = u"{step_type}-STEP REQUIRES: An previous Given/When/Then step."
                            raise ParserError(msg.format(step_type=step_type.upper()),
                                              self.line, self.filename)

                    require_not_none(self.last_step_type, name="last_step_type")
                    step_type = self.last_step_type
                    require_not_none(step_type, name="step_type")
                else:
                    self.last_step_type = step_type

                keyword = kw.rstrip()  # HINT: Strip optional trailing SPACE.
                step = model.Step(self.filename, self.line,
                                  keyword, step_type, step_text_after_keyword)
                return step
        return None

    def _select_last_background_step_type(self):
        # -- CASES:
        # * CASE 1: With background.steps/background.inherited_steps
        #   - Feature with Background and background.steps
        #   - Rule with Background and background.steps
        #   - Rule with Background w/o background.steps but w/ inherited steps
        #
        # * CASE 2: No background.steps
        #   - Feature without Background
        #   - Feature with Background but w/o background.steps
        #   - Rule without Background
        #   - Rule with Background w/o background.steps and w/o inherited steps
        last_background_step_type = None
        if self.scenario_container and self.scenario_container.background:
            # -- HINT: Consider background.steps and inherited steps.
            this_background = self.scenario_container.background
            this_background_steps = (this_background.steps or
                                     this_background.inherited_steps)
            if this_background_steps:
                # -- HINT: Feature/Rule may have background w/o steps.
                last_background_step = this_background_steps[-1]
                last_background_step_type = last_background_step.step_type
        return last_background_step_type

    def parse_steps(self, text, filename=None):
        """Parse support for execute_steps() functionality that
        supports step with:

        * multiline text
        * table

        :param text:  Text that contains 0..* steps
        :return: List of parsed steps (as model.Step objects).
        """
        require_type(text, six.text_type)
        if not self.language:
            self.language = DEFAULT_LANGUAGE
        self.reset()
        self.filename = filename
        self.statement = model.Scenario(filename, 0, u"scenario", u"")
        self.state = State.STEPS

        for line in text.splitlines():
            self.line += 1
            if not line.strip() and self.state != State.MULTILINE_TEXT:
                # -- SKIP EMPTY LINES, except in multiline string args.
                continue
            self.action(line)

        # -- FINALLY:
        if self.table is not None:
            self.action_table("")

        self._parse_loop(text, initial_state=State.STEPS, filename=filename)
        steps = self.statement.steps
        return steps
