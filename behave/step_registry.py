# -*- coding: UTF-8 -*-
"""
Provides a step registry and step decorators.
The step registry allows to match steps (model elements) with
step implementations (step definitions). This is necessary to execute steps.
"""

from __future__ import absolute_import, print_function
import sys

from behave.matchers import make_matcher
from behave.textutil import text as _text

# limit import * to just the decorators
# pylint: disable=undefined-all-variable
# names = "given when then step"
# names = names + " " + names.title()
# __all__ = names.split()
__all__ = [     # noqa: F822
    "given", "when", "then", "step",    # PREFERRED.
    "Given", "When", "Then", "Step"     # Also possible.
]


class AmbiguousStep(ValueError):
    pass


class BadStepDefinitionErrorHandler(object):
    BAD_STEP_DEFINITION_MESSAGE = """\
BAD-STEP-DEFINITION: {step}
  LOCATION: {step_location}
""".strip()
    BAD_STEP_DEFINITION_MESSAGE_WITH_ERROR = BAD_STEP_DEFINITION_MESSAGE + """
RAISED EXCEPTION: {error.__class__.__name__}:{error}"""

    def __init__(self):
        self.bad_step_definitions = []

    def clear(self):
        self.bad_step_definitions = []

    def on_error(self, step_matcher, error):
        self.bad_step_definitions.append(step_matcher)
        self.print(step_matcher, error)

    def print_all(self):
        print("BAD STEP-DEFINITIONS[%d]:" % len(self.bad_step_definitions))
        for index, bad_step_definition in enumerate(self.bad_step_definitions):
            print("%d. " % index, end="")
            self.print(bad_step_definition, error=None)

    # -- CLASS METHODS:
    @classmethod
    def print(cls, step_matcher, error=None):
        message = cls.BAD_STEP_DEFINITION_MESSAGE_WITH_ERROR
        if error is None:
            message = cls.BAD_STEP_DEFINITION_MESSAGE

        print(message.format(step=step_matcher.describe(),
                             step_location=step_matcher.location,
                             error=error), file=sys.stderr)

    @classmethod
    def raise_error(cls, step_matcher, error):
        cls.print(step_matcher, error)
        raise error


class StepRegistry(object):
    BAD_STEP_DEFINITION_HANDLER_CLASS = BadStepDefinitionErrorHandler
    RAISE_ERROR_ON_BAD_STEP_DEFINITION = False

    def __init__(self):
        self.steps = dict(given=[], when=[], then=[], step=[])
        self.error_handler = self.BAD_STEP_DEFINITION_HANDLER_CLASS()

    def clear(self):
        """
        Forget any step-definitions (step-matchers) and
        forget any bad step-definitions.
        """
        self.steps = dict(given=[], when=[], then=[], step=[])
        self.error_handler.clear()

    @staticmethod
    def same_step_definition(step, other_pattern, other_location):
        return (step.pattern == other_pattern and
                step.location == other_location and
                other_location.filename != "<string>")

    def on_bad_step_definition(self, step_matcher, error):
        # -- STEP: Select on_error() function
        on_error = self.error_handler.on_error
        if self.RAISE_ERROR_ON_BAD_STEP_DEFINITION:
            on_error = self.error_handler.raise_error

        on_error(step_matcher, error)

    def is_good_step_definition(self, step_matcher):
        """
        Check if a :param:`step_matcher` provides a good step definition.

        PROBLEM:
        * :func:`Parser.parse()` may always raise an exception
          (cases: :exc:`NotImplementedError` caused by :exc:`re.error`, ...).
        * regex errors (from :mod:`re`) are more enforced since Python >= 3.11

        :param step_matcher:  Step-matcher (step-definition) to check.
        :return: True, if step-matcher is good to use; False, otherwise.
        """
        try:
            step_matcher.compile()
            return True
        except Exception as error:
            self.on_bad_step_definition(step_matcher, error)
        return False

    def add_step_definition(self, keyword, step_text, func):
        new_step_type = keyword.lower()
        step_text = _text(step_text)
        new_step_matcher = make_matcher(func, step_text, new_step_type)
        if not self.is_good_step_definition(new_step_matcher):
            # -- CASE: BAD STEP-DEFINITION -- Ignore it.
            return

        # -- CURRENT:
        step_location = new_step_matcher.location
        step_definitions = self.steps[new_step_type]
        for existing in step_definitions:
            if self.same_step_definition(existing, step_text, step_location):
                # -- EXACT-STEP: Same step function is already registered.
                # This may occur when a step module imports another one.
                return

            if existing.matches(step_text):
                # WHY: existing.step_type = new_step_type
                message = u"%s has already been defined in\n  existing step %s"
                new_step = new_step_matcher.describe()
                existing_step = existing.describe(existing.SCHEMA_AT_LOCATION)
                raise AmbiguousStep(message % (new_step, existing_step))
        step_definitions.append(new_step_matcher)

    def find_step_definition(self, step):
        candidates = self.steps[step.step_type]
        more_steps = self.steps["step"]
        if step.step_type != "step" and more_steps:
            # -- ENSURE: self.step_type lists are not modified/extended.
            candidates = list(candidates)
            candidates += more_steps

        for step_definition in candidates:
            if step_definition.match(step.name):
                return step_definition
        return None

    def find_match(self, step):
        candidates = self.steps[step.step_type]
        more_steps = self.steps["step"]
        if step.step_type != "step" and more_steps:
            # -- ENSURE: self.step_type lists are not modified/extended.
            candidates = list(candidates)
            candidates += more_steps

        for step_definition in candidates:
            result = step_definition.match(step.name)
            if result:
                return result

        return None

    def make_decorator(self, step_type):
        def decorator(step_text):
            def wrapper(func):
                self.add_step_definition(step_type, step_text, func)
                return func
            return wrapper
        return decorator


registry = StepRegistry()

# -- Create the decorators
# pylint: disable=redefined-outer-name
def setup_step_decorators(run_context=None, registry=registry):
    if run_context is None:
        run_context = globals()
    for step_type in ("given", "when", "then", "step"):
        step_decorator = registry.make_decorator(step_type)
        run_context[step_type.title()] = run_context[step_type] = step_decorator

# -----------------------------------------------------------------------------
# MODULE INIT:
# -----------------------------------------------------------------------------
setup_step_decorators()
