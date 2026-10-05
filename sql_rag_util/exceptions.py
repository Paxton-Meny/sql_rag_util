"""Every exception the package raises.

All errors derive from :class:`SqlRagError` so callers can catch one type.
Errors that an agent can correct carry ``suggestions``: close-match names,
allowed operators, or columns of the right kind.
"""

from __future__ import annotations

__all__ = [
    "SqlRagError",
    "ConfigurationError",
    "DialectDetectionError",
    "UnsupportedDialectError",
    "CapabilityError",
    "IntrospectionError",
    "UnknownTableError",
    "UnknownColumnError",
    "UnknownRelationshipError",
    "UnknownConceptError",
    "UnknownMeasureError",
    "SensitiveColumnError",
    "QuerySpecError",
    "LimitExceededError",
    "MetadataError",
    "MetadataFormatError",
    "MetadataPathError",
    "MetadataConflictError",
    "ToolSpecError",
    "UnknownToolError",
    "ArgumentError",
    "StatementError",
    "ExecutionError",
]


class SqlRagError(Exception):
    """Base class for every error raised by sql_rag_util.

    Parameters
    ----------
    message
        Human-readable description naming the offending input.
    suggestions
        Corrections an agent can apply, such as close-match names.
    """

    def __init__(self, message: str, *, suggestions: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.message = message
        self.suggestions = suggestions

    @property
    def type_name(self) -> str:
        """Return the class name, used as the ``type`` field of error envelopes."""
        return type(self).__name__


class ConfigurationError(SqlRagError):
    """A configuration value is invalid or inconsistent."""


class DialectDetectionError(SqlRagError):
    """The dialect could not be determined from the connection."""


class UnsupportedDialectError(SqlRagError):
    """The requested dialect name is not one the package ships."""


class CapabilityError(SqlRagError):
    """The dialect does not support the requested feature."""


class IntrospectionError(SqlRagError):
    """The catalog could not be read from the database."""


class UnknownTableError(SqlRagError):
    """A table name does not resolve against the catalog."""


class UnknownColumnError(SqlRagError):
    """A column name does not resolve against its table."""


class UnknownRelationshipError(SqlRagError):
    """A relationship name does not resolve against its table."""


class UnknownConceptError(SqlRagError):
    """A concept name is not defined for the table."""


class UnknownMeasureError(SqlRagError):
    """A measure name is not defined for the table."""


class SensitiveColumnError(SqlRagError):
    """A sensitive column was used where it is not allowed."""


class QuerySpecError(SqlRagError):
    """A query spec, filter, measure, or order is malformed or not permitted."""


class LimitExceededError(SqlRagError):
    """A request exceeds a configured cap."""


class MetadataError(SqlRagError):
    """Base class for metadata problems."""


class MetadataFormatError(MetadataError):
    """A metadata file violates the format.

    Parameters
    ----------
    message
        What is wrong.
    path
        The file, as given to the parser.
    line
        The one-based line number, or ``None`` when the problem is file-wide.
    """

    def __init__(self, message: str, *, path: str, line: int | None = None) -> None:
        location = f"{path}:{line}" if line is not None else path
        super().__init__(f"{location}: {message}")
        self.path = path
        self.line = line


class MetadataPathError(MetadataError):
    """A metadata or cache path escapes its root."""


class MetadataConflictError(MetadataError):
    """The metadata on disk changed after it was loaded, so an edit was refused."""


class ToolSpecError(SqlRagError):
    """A command's argument type cannot be turned into a tool definition."""


class UnknownToolError(SqlRagError):
    """A dispatched tool name is not registered or not in the exposed tier."""


class ArgumentError(SqlRagError):
    """Tool arguments do not fit the tool's schema."""


class StatementError(SqlRagError):
    """A statement cannot be assembled or rendered."""


class ExecutionError(SqlRagError):
    """The database raised while executing a statement."""
