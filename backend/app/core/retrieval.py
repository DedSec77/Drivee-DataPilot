from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import chromadb
import yaml
from chromadb.api import Collection
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.core.semantic import SemanticModel, get_semantic


@dataclass
class Retrieved:
    entities: list[dict[str, Any]]
    measures: list[dict[str, Any]]
    dimensions: list[dict[str, Any]]
    metrics: list[dict[str, Any]]
    fewshots: list[dict[str, Any]]
    best_sem_distance: float = 2.0
    """Minimum cosine distance among semantic hits.
    0.0 = perfect match, ~1.0 = unrelated, 2.0 = opposite.
    Used as an off-topic gate: values > 0.85 usually mean the question
    is either random text or clearly outside the domain."""
    best_few_distance: float = 2.0


class Retriever:
    def __init__(
        self,
        semantic: SemanticModel,
        embedding_model_name: str,
        chroma_path: Path,
        fewshots_path: Path,
    ):
        self.semantic = semantic
        self.embedder = SentenceTransformer(embedding_model_name)
        self.chroma = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.sem_col = self._index_semantic()
        self.few_col = self._index_fewshots(fewshots_path)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return self.embedder.encode(texts, normalize_embeddings=True).tolist()

    def _index_semantic(self) -> Collection:
        col = self.chroma.get_or_create_collection("semantic", metadata={"hnsw:space": "cosine"})
        if col.count() == 0:
            items = self.semantic.retrievable_items()
            if not items:
                return col
            ids = [f"sem-{i}" for i in range(len(items))]
            docs = [it["phrase"] for it in items]
            metas = [{"kind": it["kind"], "name": it["name"], "fact": it.get("fact", "")} for it in items]
            embs = self._embed(docs)
            col.add(ids=ids, documents=docs, metadatas=metas, embeddings=embs)
        return col

    def _index_fewshots(self, fewshots_path: Path) -> Collection:
        col = self.chroma.get_or_create_collection("fewshots", metadata={"hnsw:space": "cosine"})
        if col.count() == 0 and fewshots_path.exists():
            data = yaml.safe_load(fewshots_path.read_text(encoding="utf-8")) or {}
            items = data.get("examples", [])
            if not items:
                return col
            ids = [f"fs-{i}" for i in range(len(items))]
            docs = [it["nl_ru"] for it in items]
            metas = [{"sql": it["sql"], "tags": ",".join(it.get("tags", []))} for it in items]
            embs = self._embed(docs)
            col.add(ids=ids, documents=docs, metadatas=metas, embeddings=embs)
        return col

    def add_approved_fewshot(self, report_id: int, nl_ru: str, sql: str, tags: str = "approved") -> None:
        try:
            embedding = self._embed([nl_ru])
            self.few_col.upsert(
                ids=[f"tpl-{report_id}"],
                documents=[nl_ru],
                metadatas=[{"sql": sql, "tags": tags}],
                embeddings=embedding,
            )
        except Exception as e:
            from loguru import logger

            logger.warning(f"[retrieval] add_approved_fewshot({report_id}) failed: {e}")

    def retrieve(self, nl_question: str, k_sem: int = 8, k_few: int = 4) -> Retrieved:
        q_emb = self._embed([nl_question])[0]

        sem_res = self.sem_col.query(query_embeddings=[q_emb], n_results=k_sem)
        sem_hits = []
        sem_distances: list[float] = list(sem_res.get("distances", [[]])[0] or [])
        for i in range(len(sem_res.get("ids", [[]])[0])):
            sem_hits.append(
                {
                    "kind": sem_res["metadatas"][0][i]["kind"],
                    "name": sem_res["metadatas"][0][i]["name"],
                    "fact": sem_res["metadatas"][0][i].get("fact", ""),
                    "phrase": sem_res["documents"][0][i],
                }
            )

        def _pick(kind: str) -> list[dict[str, Any]]:
            seen: set[str] = set()
            out: list[dict[str, Any]] = []
            for h in sem_hits:
                if h["kind"] == kind and h["name"] not in seen:
                    out.append(h)
                    seen.add(h["name"])
            return out

        fs_out: list[dict[str, Any]] = []
        few_distances: list[float] = []
        try:
            fs_res = self.few_col.query(query_embeddings=[q_emb], n_results=k_few)
            few_distances = list(fs_res.get("distances", [[]])[0] or [])
            for i in range(len(fs_res.get("ids", [[]])[0])):
                fs_out.append(
                    {
                        "nl_ru": fs_res["documents"][0][i],
                        "sql": fs_res["metadatas"][0][i]["sql"],
                    }
                )
        except Exception:
            pass

        best_sem = min(sem_distances) if sem_distances else 2.0
        best_few = min(few_distances) if few_distances else 2.0

        return Retrieved(
            entities=_pick("entity"),
            measures=_pick("measure"),
            dimensions=_pick("dimension"),
            metrics=_pick("metric"),
            fewshots=fs_out,
            best_sem_distance=float(best_sem),
            best_few_distance=float(best_few),
        )


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    return Retriever(
        semantic=get_semantic(),
        embedding_model_name=settings.embedding_model,
        chroma_path=settings.chroma_path,
        fewshots_path=settings.fewshots_path,
    )
