from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer

from config.settings import settings
from tools.document_processor import DocumentChunk


# Sector-specific collection names
COLLECTIONS = {
    "IT":     "it_sector_docs",
    "Pharma": "pharma_sector_docs",
    "general": "general_docs",
}


@dataclass
class RetrievedChunk:
    text: str
    source: str
    page: int
    score: float          # cosine distance (lower = more relevant)
    metadata: dict


class VectorStore:
    """
    ChromaDB-backed vector store using sentence-transformers embeddings.
    One persistent client, multiple named collections (one per sector).
    """

    _model: Optional[SentenceTransformer] = None  # lazy-loaded, shared across instances

    def __init__(self):
        Path(settings.chroma_db_path).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=settings.chroma_db_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    @property
    def model(self) -> SentenceTransformer:
        if VectorStore._model is None:
            VectorStore._model = SentenceTransformer("all-MiniLM-L6-v2")
        return VectorStore._model

    def _get_collection(self, collection_name: str) -> chromadb.Collection:
        return self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ── Ingestion ──────────────────────────────────────────────────────────────

    def add_documents(
        self,
        chunks: list[DocumentChunk],
        sector: str = "general",
    ) -> int:
        """
        Embed and store a list of DocumentChunks into the sector collection.

        Returns:
            Number of chunks added
        """
        if not chunks:
            return 0

        collection_name = COLLECTIONS.get(sector, COLLECTIONS["general"])
        collection = self._get_collection(collection_name)

        texts = [c.text for c in chunks]
        embeddings = self.model.encode(texts, show_progress_bar=False).tolist()

        ids = [f"{Path(chunks[0].source).stem}_p{c.page}_c{c.chunk_index}" for c in chunks]
        metadatas = [
            {
                "source": c.source,
                "page": str(c.page),
                "chunk_index": str(c.chunk_index),
                **{k: str(v) for k, v in c.metadata.items()},
            }
            for c in chunks
        ]

        # Upsert to avoid duplicates on re-ingestion
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        return len(chunks)

    # ── Retrieval ──────────────────────────────────────────────────────────────

    def query(
        self,
        question: str,
        sector: str = "general",
        n_results: int = 5,
        where: Optional[dict] = None,
    ) -> list[RetrievedChunk]:
        """
        Semantic search against a sector collection.

        Args:
            question:  Natural language query
            sector:    IT | Pharma | general
            n_results: Number of top chunks to return
            where:     Optional ChromaDB metadata filter e.g. {"company": "Infosys"}

        Returns:
            List of RetrievedChunk sorted by relevance (best first)
        """
        collection_name = COLLECTIONS.get(sector, COLLECTIONS["general"])
        collection = self._get_collection(collection_name)

        if collection.count() == 0:
            return []

        embedding = self.model.encode([question], show_progress_bar=False).tolist()

        kwargs = dict(
            query_embeddings=embedding,
            n_results=min(n_results, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        if where:
            kwargs["where"] = where

        results = collection.query(**kwargs)

        chunks = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            chunks.append(
                RetrievedChunk(
                    text=doc,
                    source=meta.get("source", ""),
                    page=int(meta.get("page", 0)),
                    score=float(dist),
                    metadata=meta,
                )
            )
        return chunks

    def format_for_llm(self, chunks: list[RetrievedChunk]) -> str:
        """Render retrieved chunks as clean text for LLM context injection."""
        if not chunks:
            return "No relevant document passages found."
        parts = []
        for i, c in enumerate(chunks, 1):
            parts.append(
                f"[Doc {i}] Source: {Path(c.source).name} | Page: {c.page}\n{c.text}\n"
            )
        return "\n".join(parts)

    # ── Utilities ──────────────────────────────────────────────────────────────

    def collection_stats(self, sector: str = "general") -> dict:
        """Return count and name of a collection."""
        collection_name = COLLECTIONS.get(sector, COLLECTIONS["general"])
        collection = self._get_collection(collection_name)
        return {"collection": collection_name, "count": collection.count()}

    def delete_collection(self, sector: str) -> None:
        """Wipe and recreate a collection (useful for re-ingestion)."""
        collection_name = COLLECTIONS.get(sector, COLLECTIONS["general"])
        self._client.delete_collection(collection_name)


# Module-level singleton
vector_store = VectorStore()
