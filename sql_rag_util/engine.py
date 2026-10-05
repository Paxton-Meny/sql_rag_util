"""The :class:`SqlRag` facade: one connection, one catalog, one set of tools."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sql_rag_util.commands import default_registry
from sql_rag_util.commands.arguments import build_arguments
from sql_rag_util.commands.dispatch import Dispatcher
from sql_rag_util.commands.instructions import instructions
from sql_rag_util.config import Config
from sql_rag_util.dialects import load
from sql_rag_util.dialects.detect import detect
from sql_rag_util.exceptions import ConfigurationError, SqlRagError
from sql_rag_util.executor import Executor
from sql_rag_util.metadata.annotate import annotate
from sql_rag_util.metadata.model import Metadata
from sql_rag_util.metadata.store import MetadataStore
from sql_rag_util.query.spec import Filter
from sql_rag_util.retrieval.cache import JsonCache
from sql_rag_util.retrieval.pack import Retriever
from sql_rag_util.schema.introspect import introspect
from sql_rag_util.sql.render import PARAMSTYLES

if TYPE_CHECKING:
    import os

    from sql_rag_util.commands.spec import CommandResult, ToolSpec
    from sql_rag_util.config import Limits
    from sql_rag_util.dialects.base import Dialect
    from sql_rag_util.metadata.annotate import AnnotatedCatalog
    from sql_rag_util.schema.model import Catalog, TableInfo

__all__ = ["SqlRag"]


class SqlRag:
    """Everything an application or an agent framework needs, on one connection.

    Parameters
    ----------
    connection
        A PEP 249 connection. The package never opens or closes it and never commits.
    dialect
        Dialect name; detected from the driver when omitted, required for
        drivers that connect to several databases.
    paramstyle
        Overrides the driver's reported paramstyle.
    metadata_root
        Directory of metadata files, or ``None`` for none.
    cache_dir
        Directory for value and embedding caches. Defaults to ``.cache``
        under the metadata root; ``None`` with no metadata root disables caching.
    schemas
        Namespaces to load; ``None`` loads the dialect default.
    config
        Behavior switches and limits.
    """

    def __init__(
        self,
        connection: object,
        *,
        dialect: str | None = None,
        paramstyle: str | None = None,
        metadata_root: str | os.PathLike[str] | None = None,
        cache_dir: str | os.PathLike[str] | None = None,
        schemas: tuple[str, ...] | None = None,
        config: Config = Config(),
    ) -> None:
        detected = detect(connection, dialect=dialect)
        self._dialect: Dialect = load(detected.dialect)
        style = paramstyle or detected.paramstyle or self._dialect.default_paramstyle
        if style not in PARAMSTYLES:
            raise ConfigurationError(f"unknown paramstyle {style!r}; expected one of {sorted(PARAMSTYLES)}")
        self._config = config
        self._schemas = schemas
        self._executor = Executor(connection, style, on_statement=config.on_statement)
        self._store = MetadataStore(metadata_root) if metadata_root is not None else None
        if cache_dir is None and self._store is not None:
            cache_dir = self._store.path(".cache")
        self._cache = JsonCache(cache_dir) if cache_dir is not None else None
        self._registry = default_registry()
        self._annotated: AnnotatedCatalog
        self._retriever: Retriever | None = None
        self.refresh()

    def refresh(self) -> None:
        """Re-read the catalog and the metadata; retrieval indexes rebuild on next use.

        A failure leaves the engine exactly as it was.
        """
        raw_catalog = introspect(self._executor, self._dialect, schemas=self._schemas, include_row_estimates=self._config.include_row_estimates)
        metadata = self._store.load() if self._store is not None else Metadata()
        annotated = annotate(raw_catalog, metadata, self._dialect, max_join_depth=self.limits.max_join_depth)
        self._raw_catalog, self._annotated, self._retriever = raw_catalog, annotated, None

    @property
    def retriever(self) -> Retriever:
        """Return the retrieval indexes, building them on first use."""
        if self._retriever is None:
            self._retriever = Retriever(self._executor, self._dialect, self._annotated, embed=self._config.embed, cache=self._cache)
        return self._retriever

    @property
    def retriever_ready(self) -> bool:
        """Return whether the retrieval indexes have been built since the last refresh."""
        return self._retriever is not None

    @property
    def dialect(self) -> Dialect:
        """Return the dialect in use."""
        return self._dialect

    @property
    def executor(self) -> Executor:
        """Return the executor bound to the connection."""
        return self._executor

    @property
    def config(self) -> Config:
        """Return the configuration."""
        return self._config

    @property
    def limits(self) -> Limits:
        """Return the configured limits."""
        return self._config.limits

    @property
    def annotated(self) -> AnnotatedCatalog:
        """Return the catalog with metadata applied."""
        return self._annotated

    @property
    def catalog(self) -> Catalog:
        """Return the catalog, including renamed and declared relationships."""
        return self._annotated.catalog

    @property
    def raw_catalog(self) -> Catalog:
        """Return the catalog as introspected, before metadata was applied."""
        return self._raw_catalog

    def validate_metadata(self, metadata: Metadata) -> None:
        """Raise unless ``metadata`` annotates the raw catalog cleanly."""
        annotate(self._raw_catalog, metadata, self._dialect, max_join_depth=self.limits.max_join_depth)

    @property
    def store(self) -> MetadataStore | None:
        """Return the metadata store, or ``None`` without a metadata root."""
        return self._store

    @property
    def schema_version(self) -> str:
        """Return the hash agents use to detect stale knowledge."""
        return self._annotated.version

    def scope_filters(self, table: TableInfo) -> tuple[Filter, ...]:
        """Return the developer's scope predicates for ``table``."""
        if self._config.scope is None:
            return ()
        try:
            return tuple(build_arguments(Filter, dict(item)) for item in self._config.scope(table.ref.qualified))
        except (SqlRagError, TypeError, ValueError) as exc:
            raise ConfigurationError(f"scope filters for {table.ref.qualified} are invalid: {exc}") from None

    def tool_specs(self, *, tier: str = "standard") -> tuple[ToolSpec, ...]:
        """Return the tools exposed at ``tier``; writers only when writes are allowed."""
        return self._registry.specs(tier=tier, include_mutating=self._config.allow_metadata_writes)

    def dispatcher(self, *, tier: str = "standard") -> Dispatcher:
        """Return a dispatcher exposing ``tier``."""
        return Dispatcher(self._registry, self, tier=tier, include_mutating=self._config.allow_metadata_writes)

    def dispatch(self, name: str, arguments: dict[str, Any], *, tier: str = "standard") -> dict[str, Any]:
        """Run a tool by name and return its JSON envelope."""
        return self.dispatcher(tier=tier).call(name, arguments)

    def dispatch_text(self, name: str, arguments: dict[str, Any], *, tier: str = "standard") -> str:
        """Run a tool by name and return its compact text."""
        return self.dispatcher(tier=tier).call_text(name, arguments)

    def instructions(self) -> str:
        """Return the system-prompt block describing the workflow for this database."""
        return instructions(self)

    def run(self, name: str, arguments: dict[str, Any]) -> CommandResult:
        """Run a tool by name and return the raw result; errors propagate."""
        return self.dispatcher(tier="full").run(name, arguments)
