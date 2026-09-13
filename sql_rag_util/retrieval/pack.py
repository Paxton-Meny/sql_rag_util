"""The context pack: ranked schema cards for a question, within a token budget."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sql_rag_util.retrieval.cards import card_text, summary_text, table_card, table_summary
from sql_rag_util.retrieval.embed import EmbeddingIndex, build_embedding_index
from sql_rag_util.retrieval.lexical import Bm25Index, Document
from sql_rag_util.retrieval.rank import reciprocal_rank_fusion
from sql_rag_util.retrieval.tokenize import tokenize
from sql_rag_util.retrieval.values import ValueIndex, build_value_index
from sql_rag_util.schema.resolve import agent_name

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sql_rag_util.dialects.base import Dialect
    from sql_rag_util.executor import Executor
    from sql_rag_util.metadata.annotate import AnnotatedCatalog
    from sql_rag_util.retrieval.cache import JsonCache
    from sql_rag_util.schema.model import TableInfo

__all__ = ["Retriever", "ContextPack"]

_FIELD_WEIGHTS = {"name": 3.0, "synonyms": 2.5, "purpose": 1.5, "columns": 1.0, "description": 0.7, "glossary": 1.0, "concepts": 1.0, "relationships": 0.5}
_SOURCE_WEIGHTS = {"lexical": 1.0, "values": 1.5, "embed": 1.0}
_CHARS_PER_TOKEN = 4
_MAX_RANKED = 20


@dataclass(frozen=True, slots=True)
class ContextPack:
    """What ``get_context`` returns."""

    data: dict[str, Any]
    text: str


def _documents(annotated: AnnotatedCatalog) -> tuple[Document, ...]:
    glossary_by_table: dict[str, list[str]] = {}
    for entry in annotated.metadata.glossary:
        text = " ".join((entry.term, *entry.synonyms, entry.definition))
        for table in entry.tables:
            glossary_by_table.setdefault(table, []).append(text)
    documents = []
    for table in annotated.catalog.tables:
        name = agent_name(annotated.catalog, table.ref)
        meta = annotated.table_meta.get(table.ref)
        visible = annotated.policy.visible(table.ref, table.columns)
        column_text = []
        for column in visible:
            column_text.append(column.name)
            if meta and (cm := meta.column(column.name)):
                column_text.extend((cm.text, *cm.synonyms, *cm.values))
        documents.append(
            Document(
                name,
                {
                    "name": " ".join([name, table.ref.name]),
                    "synonyms": " ".join(meta.synonyms) if meta else "",
                    "purpose": meta.purpose if meta else "",
                    "description": meta.description if meta else "",
                    "columns": " ".join(column_text),
                    "glossary": " ".join(glossary_by_table.get(name, [])),
                    "concepts": " ".join(f"{c.name} {c.text}" for c in (meta.concepts if meta else ())),
                    "relationships": " ".join(r.name for r in annotated.catalog.relationships_of(table.ref)),
                },
            )
        )
    return tuple(documents)


class Retriever:
    """Indexes over one annotated catalog.

    Parameters
    ----------
    embed
        Optional developer function from texts to vectors.
    cache
        Optional cache for the value and embedding indexes.
    """

    def __init__(
        self,
        executor: Executor,
        dialect: Dialect,
        annotated: AnnotatedCatalog,
        *,
        embed: Callable[[Sequence[str]], Sequence[Sequence[float]]] | None = None,
        cache: JsonCache | None = None,
    ) -> None:
        self._annotated = annotated
        self._embed = embed
        documents = _documents(annotated)
        self._lexical = Bm25Index(documents, _FIELD_WEIGHTS)
        self.values: ValueIndex = build_value_index(executor, dialect, annotated, cache=cache)
        self._embedding: EmbeddingIndex | None = None
        if embed is not None:
            texts = [(d.id, " ".join(v for v in d.fields.values() if v)) for d in documents]
            self._embedding = build_embedding_index(embed, texts, annotated.version, cache=cache)

    def rank(self, question: str) -> tuple[str, ...]:
        """Return table names for ``question``, best first, fusing every source."""
        rankings, weights = [], []
        lexical = [i for i, _ in self._lexical.search(question, limit=_MAX_RANKED)]
        if lexical:
            rankings.append(lexical)
            weights.append(_SOURCE_WEIGHTS["lexical"])
        hits = self.values.match(question)
        if hits:
            rankings.append(list(dict.fromkeys(h.table for h in hits)))
            weights.append(_SOURCE_WEIGHTS["values"])
        if self._embedding is not None and self._embed is not None:
            vector = self._embed([question])[0]
            rankings.append([i for i, _ in self._embedding.search(vector, limit=_MAX_RANKED)])
            weights.append(_SOURCE_WEIGHTS["embed"])
        return tuple(i for i, _ in reciprocal_rank_fusion(rankings, weights=weights))

    def _table(self, name: str) -> TableInfo | None:
        return next((t for t in self._annotated.catalog.tables if agent_name(self._annotated.catalog, t.ref) == name), None)

    def _neighbors(self, names: Sequence[str]) -> list[str]:
        out: list[str] = []
        for name in names:
            table = self._table(name)
            if table is None:
                continue
            for relationship in self._annotated.catalog.relationships_of(table.ref):
                target = agent_name(self._annotated.catalog, relationship.target)
                if target not in names and target not in out:
                    out.append(target)
        return out

    def pack(self, question: str, *, budget_tokens: int) -> ContextPack:
        """Return cards for the tables that matter, within ``budget_tokens``."""
        ranked = list(self.rank(question))
        candidates = ranked + self._neighbors(ranked)
        budget = budget_tokens * _CHARS_PER_TOKEN
        cards: list[dict[str, Any]] = []
        more: list[dict[str, Any]] = []
        lines: list[str] = []
        used = 0
        for name in candidates:
            table = self._table(name)
            if table is None:
                continue
            card = table_card(self._annotated, table, full=False)
            text = card_text(card, full=False)
            if used + len(text) <= budget:
                cards.append(card)
                lines.append(text)
                used += len(text)
                continue
            summary = table_summary(self._annotated, table)
            line = summary_text(summary)
            if used + len(line) <= budget:
                more.append(summary)
                lines.append(f"also: {line}")
                used += len(line)
        hits = [{"table": h.table, "column": h.column, "value": h.value, "matched": h.matched} for h in self.values.match(question)]
        if hits:
            lines.append("values: " + " | ".join(f"{h['table']}.{h['column']} = {h['value']!r} (from {h['matched']!r})" for h in hits))
        tokens = set(tokenize(question))
        glossary = [
            {"term": e.term, "definition": e.definition}
            for e in self._annotated.metadata.glossary
            if tokens & set(tokenize(" ".join((e.term, *e.synonyms))))
        ]
        if glossary:
            lines.append("glossary: " + " | ".join(f"{g['term']}: {g['definition']}" for g in glossary))
        data = {"question": question, "tables": cards, "more": more, "value_hits": hits, "glossary": glossary, "budget_tokens": budget_tokens, "used_tokens": used // _CHARS_PER_TOKEN}
        return ContextPack(data, "\n".join(lines))
