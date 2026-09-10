"""Explicit application errors translated by the API boundary."""


class MiaError(Exception):
    """Base class for expected MIA failures."""


class ConfigurationError(MiaError):
    """Required local configuration or pinned standards data is unavailable."""


class ExtractionError(MiaError):
    """A deterministic source extraction could not be completed."""


class TemplateError(MiaError):
    """An official template cannot be located or normalized."""


class MappingError(MiaError):
    """A mapping does not refer to the selected authoritative template."""


class CompilationError(MiaError):
    """Approved mappings cannot be compiled into an AAS artifact."""


class DeploymentError(MiaError):
    """A validated artifact could not be stored in the configured AAS runtime."""
