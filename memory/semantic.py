"""
AuraOS · Semantic Memory
========================
ChromaDB-backed vector store for fuzzy recall.

What gets stored here:
  - Project summaries (so "that ML project" finds "fake-news-detection")
  - Context snapshot summaries (searchable by natural language)
  - Session highlights ("when did I last work on BERT?")

ChromaDB runs fully locally — no network calls, no API keys.
Default embedding model: all-MiniLM-L6-v2 (ships with chromadb,
runs on CPU, fast enough for personal use).

Design decisions:
  - One collection per document type for clean separation
  - Metadata stored alongside vectors for filtering
  - IDs are deterministic where possible (project_id, snapshot_id)
    so upserts are idempotent
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import uuid4

import chromadb
from chromadb.config import Settings


# ─────────────────────────────────────────────────────────────
# SemanticMemory
# ─────────────────────────────────────────────────────────────

class SemanticMemory:
    """
    Usage:
        sm = SemanticMemory()                       # default data/chroma/
        sm = SemanticMemory(path=":memory:")         # for tests

        sm.upsert_project("fake-news-detection",
                          "ML project for classifying fake news using BERT",
                          metadata={"path": "~/projects/fake-news"})

        results = sm.search_projects("that machine learning NLP thing")
        # → [{"id": "fake-news-detection", "score": 0.87, "metadata": {...}}, ...]
    """

    PROJECTS_COLLECTION  = "aura_projects"
    SNAPSHOTS_COLLECTION = "aura_snapshots"
    SESSIONS_COLLECTION  = "aura_sessions"

    def __init__(self, path: str | Path = None):
        if path is None:
            default = Path(__file__).parent.parent / "data" / "chroma"
            default.mkdir(parents=True, exist_ok=True)
            path = str(default)

        if str(path) == ":memory:":
            self._client = chromadb.EphemeralClient()
            suffix = uuid4().hex
            projects_collection = f"{self.PROJECTS_COLLECTION}_{suffix}"
            snapshots_collection = f"{self.SNAPSHOTS_COLLECTION}_{suffix}"
            sessions_collection = f"{self.SESSIONS_COLLECTION}_{suffix}"
        else:
            self._client = chromadb.PersistentClient(
                path=str(path),
                settings=Settings(anonymized_telemetry=False),
            )
            projects_collection = self.PROJECTS_COLLECTION
            snapshots_collection = self.SNAPSHOTS_COLLECTION
            sessions_collection = self.SESSIONS_COLLECTION

        self._projects = self._client.get_or_create_collection(projects_collection)
        self._snapshots = self._client.get_or_create_collection(snapshots_collection)
        self._sessions = self._client.get_or_create_collection(sessions_collection)


    # ── Projects ──────────────────────────────────────────────

    def upsert_project(
        self,
        project_id: str,
        text: str,
        metadata: dict = None,
    ):
        """
        Store or update a project's searchable text.

        `text` should be a rich description:
            "fake-news-detection: ML project for classifying misinformation
             using NLP and BERT. Python, scikit-learn, transformers."

        Called on startup for every project in projects.yaml.
        """
        payload = dict(
            ids=[project_id],
            documents=[text],
        )
        if metadata:
            payload["metadatas"] = [metadata]
        self._projects.upsert(**payload)

    def search_projects(
        self,
        query: str,
        n_results: int = 3,
    ) -> list[dict]:
        """
        Fuzzy search across all project descriptions.
        Returns ranked list with similarity scores.
        """
        if self._projects.count() == 0:
            return []

        n = min(n_results, self._projects.count())
        results = self._projects.query(
            query_texts=[query],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )
        return self._format_results(results)

    def delete_project(self, project_id: str):
        try:
            self._projects.delete(ids=[project_id])
        except Exception:
            pass


    # ── Snapshots ─────────────────────────────────────────────

    def upsert_snapshot(
        self,
        snapshot_id: str,
        text: str,
        metadata: dict = None,
    ):
        """
        Store a context snapshot summary as a searchable vector.

        `text` example:
            "fake-news-detection 2025-06-14: Working on improving F1 score.
             Implemented TF-IDF baseline. Next: try BERT embeddings.
             Blocked on tokenizer memory issue."
        """
        payload = dict(
            ids=[snapshot_id],
            documents=[text],
        )
        if metadata:
            payload["metadatas"] = [metadata]
        self._snapshots.upsert(**payload)

    def search_snapshots(
        self,
        query: str,
        project_id: str = None,
        n_results: int = 3,
    ) -> list[dict]:
        """
        Search snapshot summaries. Optionally filter by project.
        Useful for: "when was I last working on BERT?"
        """
        if self._snapshots.count() == 0:
            return []

        n = min(n_results, self._snapshots.count())
        where = {"project_id": project_id} if project_id else None

        results = self._snapshots.query(
            query_texts=[query],
            n_results=n,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        return self._format_results(results)


    # ── Sessions ──────────────────────────────────────────────

    def upsert_session_highlight(
        self,
        session_id: str,
        text: str,
        metadata: dict = None,
    ):
        """
        Store a session highlight — what happened in this session.
        Used for "what did I work on last Tuesday?" queries.
        """
        payload = dict(
            ids=[session_id],
            documents=[text],
        )
        if metadata:
            payload["metadatas"] = [metadata]
        self._sessions.upsert(**payload)

    def search_sessions(
        self,
        query: str,
        n_results: int = 5,
    ) -> list[dict]:
        if self._sessions.count() == 0:
            return []

        n = min(n_results, self._sessions.count())
        results = self._sessions.query(
            query_texts=[query],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )
        return self._format_results(results)


    # ── Convenience ───────────────────────────────────────────

    def identify_project(self, user_input: str) -> Optional[str]:
        """
        Given free-form user input, return the best-matching project_id.
        Returns None if confidence is too low (distance > 1.0).

        Used by the intent classifier:
            "continue my fake news project" → "fake-news-detection"
            "open that NLP thing"           → "fake-news-detection"
        """
        results = self.search_projects(user_input, n_results=1)
        if not results:
            return None
        best = results[0]
        # ChromaDB distances are L2; lower = better.
        # 1.0 threshold is intentionally permissive for personal use.
        if best["distance"] > 1.0:
            return None
        return best["id"]

    def stats(self) -> dict:
        return {
            "projects":  self._projects.count(),
            "snapshots": self._snapshots.count(),
            "sessions":  self._sessions.count(),
        }


    # ── Internal ──────────────────────────────────────────────

    @staticmethod
    def _format_results(raw: dict) -> list[dict]:
        """
        Flatten ChromaDB's nested result format into a clean list.

        Input (ChromaDB format):
            {
                "ids":       [["id1", "id2"]],
                "documents": [["doc1", "doc2"]],
                "metadatas": [[{...}, {...}]],
                "distances": [[0.12, 0.45]],
            }

        Output:
            [
                {"id": "id1", "document": "doc1", "metadata": {...}, "distance": 0.12},
                {"id": "id2", "document": "doc2", "metadata": {...}, "distance": 0.45},
            ]
        """
        ids       = raw.get("ids", [[]])[0]
        docs      = raw.get("documents", [[]])[0]
        metas     = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]

        return [
            {
                "id":       ids[i],
                "document": docs[i] if i < len(docs) else "",
                "metadata": (metas[i] or {}) if i < len(metas) else {},
                "distance": distances[i] if i < len(distances) else None,
            }
            for i in range(len(ids))
        ]
