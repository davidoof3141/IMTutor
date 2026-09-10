"""Named constants for control-vector parameter names.

Used instead of string literals wherever a parameter name is referenced
(rules, clauses, attribution keys, override keys) so a typo becomes a
NameError instead of a silently-ignored key.
"""

EXPLANATION_DEPTH = "explanation_depth"
EXAMPLE_DENSITY = "example_density"
CONCRETENESS = "concreteness"
EXAMPLE_DOMAIN = "example_domain"
REGISTER = "register"
ASSESSMENT_FREQUENCY = "assessment_frequency"

PARAMETER_NAMES = (
    EXPLANATION_DEPTH,
    EXAMPLE_DENSITY,
    CONCRETENESS,
    EXAMPLE_DOMAIN,
    REGISTER,
    ASSESSMENT_FREQUENCY,
)

DEFAULT_ATTRIBUTION = "default"

CURRENT_RULESET_VERSION = "v1"
CURRENT_PLANNER_VERSION = "v1"
