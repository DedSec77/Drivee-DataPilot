from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import chromadb
from loguru import logger
from psycopg import sql
from sentence_transformers import SentenceTransformer

from app.core.semantic import SemanticModel, ValueLinkingColumn, get_semantic
from app.db.session import raw_psycopg

_EMBEDDING_DISTANCE_THRESHOLD = 0.45

_MAX_NGRAM = 3

_MIN_TOKEN_LEN = 2


@dataclass(frozen=True)
class ValueLink:
    token: str
    column: str
    alias: str
    db_value: str
    distance: float
    method: str


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("ё", "е").replace("Ё", "Е")
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


_TOKEN_RE = re.compile(r"[\w\-]+", re.UNICODE)


def _ngrams(text: str, n_max: int = _MAX_NGRAM) -> list[str]:
    words = [w.lower() for w in _TOKEN_RE.findall(text) if len(w) >= _MIN_TOKEN_LEN]
    seen: set[str] = set()
    out: list[str] = []
    for n in range(1, n_max + 1):
        for i in range(len(words) - n + 1):
            ng = " ".join(words[i : i + n])
            if ng not in seen:
                seen.add(ng)
                out.append(ng)
    return out


@dataclass
class _AliasEntry:
    db_value: str
    column: str
    alias: str


class ValueLinker:
    def __init__(
        self,
        semantic: SemanticModel,
        embedder: SentenceTransformer,
        chroma_client: chromadb.api.ClientAPI,
    ):
        self.semantic = semantic
        self.embedder = embedder
        self.chroma = chroma_client
        self.col = self.chroma.get_or_create_collection("db_values", metadata={"hnsw:space": "cosine"})

        self._exact: dict[str, list[_AliasEntry]] = {}

        self._unaccent: dict[str, list[_AliasEntry]] = {}
        self._stats: dict[str, int] = {}
        self._indexed = False

    def index(self, force: bool = False) -> int:
        if self._indexed and not force:
            return self.col.count()

        if force:
            try:
                self.chroma.delete_collection("db_values")
            except Exception as e:
                logger.warning(f"[value-link] couldn't drop db_values: {e}")
            self.col = self.chroma.get_or_create_collection("db_values", metadata={"hnsw:space": "cosine"})
            self._exact.clear()
            self._unaccent.clear()
            self._stats.clear()

        total = 0
        for vlcol in self.semantic.value_linking_columns:
            try:
                added = self._index_one_column(vlcol)
                total += added
                self._stats[vlcol.alias] = added
            except Exception as e:
                logger.warning(f"[value-link] {vlcol.alias}: indexing failed - {e}")
                self._stats[vlcol.alias] = 0

        self._indexed = True
        logger.info(
            f"[value-link] indexed {total} value(s) across "
            f"{len(self.semantic.value_linking_columns)} column(s): "
            f"{self._stats}"
        )
        return total

    def _index_one_column(self, vlcol: ValueLinkingColumn) -> int:
        qualified_col = f"{vlcol.table}.{vlcol.column}"

        col_ident = sql.Identifier(vlcol.column)
        tbl_ident = sql.Identifier(vlcol.table)
        query = sql.SQL(
            "SELECT DISTINCT {col} FROM {tbl} WHERE {col} IS NOT NULL ORDER BY {col} LIMIT %s"
        ).format(col=col_ident, tbl=tbl_ident)

        distinct_values: list[str] = []
        with raw_psycopg() as conn, conn.cursor() as cur:
            cur.execute(query, (vlcol.max_distinct,))
            for (val,) in cur.fetchall():
                if val is None:
                    continue
                distinct_values.append(str(val))

        synonyms_map: dict[str, list[str]] = dict(vlcol.synonyms)
        if vlcol.synonyms_from == "cities_canonical_ru":
            inverted: dict[str, list[str]] = {}
            for alias, canon in self.semantic.cities_canonical_ru.items():
                inverted.setdefault(canon, []).append(alias)
            synonyms_map = inverted

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for v in distinct_values:
            ids.append(f"vl-{vlcol.alias}-canon-{v}")
            documents.append(v)
            metadatas.append(
                {
                    "db_value": v,
                    "column": qualified_col,
                    "alias": vlcol.alias,
                    "source": "canonical",
                }
            )
            entry = _AliasEntry(db_value=v, column=qualified_col, alias=vlcol.alias)
            self._exact.setdefault(v.lower(), []).append(entry)
            self._unaccent.setdefault(_normalize(v), []).append(entry)

        for canon, alias_list in synonyms_map.items():
            for alt in alias_list:
                ids.append(f"vl-{vlcol.alias}-syn-{canon}-{alt}")
                documents.append(alt)
                metadatas.append(
                    {
                        "db_value": canon,
                        "column": qualified_col,
                        "alias": vlcol.alias,
                        "source": "synonym",
                    }
                )
                entry = _AliasEntry(
                    db_value=canon,
                    column=qualified_col,
                    alias=vlcol.alias,
                )
                self._exact.setdefault(alt.lower(), []).append(entry)
                self._unaccent.setdefault(_normalize(alt), []).append(entry)

        if not documents:
            return 0

        embeddings = self.embedder.encode(documents, normalize_embeddings=True).tolist()

        self.col.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
        return len(documents)

    def link(self, nl_question: str, *, max_links: int = 8) -> list[ValueLink]:
        if not self._indexed:
            self.index()

        ngrams = _ngrams(nl_question)
        merged: dict[tuple[str, str], ValueLink] = {}

        for ng in ngrams:
            for entry in self._exact.get(ng, []):
                _merge(
                    merged,
                    ValueLink(
                        token=ng,
                        column=entry.column,
                        alias=entry.alias,
                        db_value=entry.db_value,
                        distance=0.0,
                        method="exact",
                    ),
                )

        for ng in ngrams:
            normalised = _normalize(ng)
            if not normalised:
                continue
            for entry in self._unaccent.get(normalised, []):
                _merge(
                    merged,
                    ValueLink(
                        token=ng,
                        column=entry.column,
                        alias=entry.alias,
                        db_value=entry.db_value,
                        distance=0.05,
                        method="unaccent",
                    ),
                )

        try:
            q_emb = self.embedder.encode([nl_question], normalize_embeddings=True).tolist()[0]
            res = self.col.query(query_embeddings=[q_emb], n_results=10)
            distances = (res.get("distances") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            documents = (res.get("documents") or [[]])[0]
            for dist, meta, doc in zip(distances, metas, documents, strict=False):
                if dist > _EMBEDDING_DISTANCE_THRESHOLD:
                    continue
                _merge(
                    merged,
                    ValueLink(
                        token=doc,
                        column=meta["column"],
                        alias=meta["alias"],
                        db_value=meta["db_value"],
                        distance=float(dist),
                        method="embedding",
                    ),
                )
        except Exception as e:
            logger.warning(f"[value-link] embedding query failed: {e}")

        ordered = sorted(
            merged.values(),
            key=lambda v: (v.distance, -len(v.token), v.token),
        )
        return ordered[:max_links]

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)


def _merge(
    bag: dict[tuple[str, str], ValueLink],
    candidate: ValueLink,
) -> None:
    key = (candidate.column, candidate.db_value)
    existing = bag.get(key)
    if existing is None:
        bag[key] = candidate
        return
    if candidate.distance < existing.distance:
        bag[key] = candidate
        return
    if candidate.distance == existing.distance and len(candidate.token) > len(existing.token):
        bag[key] = candidate


@lru_cache(maxsize=1)
def get_value_linker() -> ValueLinker:
    from app.core.retrieval import get_retriever

    r = get_retriever()
    return ValueLinker(
        semantic=get_semantic(),
        embedder=r.embedder,
        chroma_client=r.chroma,
    )
