"""
MemoryService — durable, personalized strategy memory across sessions.

Business SQLite remains authoritative for everything (docs/DECISIONS.md
#5, #7, LEARNING_LOOP.md). mem0 only ever holds concise, candidate-
namespaced strategy-level text: preferences, learned strategy
observations, and pointers to LearningInsights already persisted in
SQLite. It never holds raw job listings, application events, full
resumes, OpportunityScores, or database rows — those stay in SQLite.

mem0 failure must never stop HireLoop: every method here is wrapped so a
provider error degrades to "memory sync pending" rather than raising.
Candidate isolation is enforced by namespacing every call on candidate_id.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from src.models.learning_insight import LearningInsight


class MemoryServiceError(Exception):
    """Any mem0-layer failure. Callers must treat this as recoverable —
    never a reason to fail the workflow or lose an insight (it's already
    durably persisted to SQLite before this is ever called)."""


class MemoryProvider(ABC):
    """Backend abstraction so MemoryService isn't hardwired to the mem0
    SDK. MockMemoryProvider (below) is used in all tests/CI; a thin real
    mem0-backed provider can implement the same interface."""

    @abstractmethod
    def add(self, candidate_id: str, text: str, metadata: dict) -> str: ...

    @abstractmethod
    def search(self, candidate_id: str, query: str, top_k: int) -> list[dict]: ...

    @abstractmethod
    def delete(self, candidate_id: str, memory_id: str) -> None: ...

    @abstractmethod
    def health_check(self) -> bool: ...


class MockMemoryProvider(MemoryProvider):
    """Deterministic, in-process, network-free provider for tests/CI/demo
    fallback. Namespaced per candidate_id exactly like a real backend
    would be — candidate A's memories are stored in a separate bucket from
    candidate B's and a search can never cross that boundary."""

    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy
        self._store: dict[str, dict[str, dict]] = {}
        self._next_id = 0

    def add(self, candidate_id: str, text: str, metadata: dict) -> str:
        if not self.healthy:
            raise MemoryServiceError("simulated mem0 outage")
        self._next_id += 1
        memory_id = f"mem-{self._next_id}"
        self._store.setdefault(candidate_id, {})[memory_id] = {"text": text, "metadata": metadata}
        return memory_id

    def search(self, candidate_id: str, query: str, top_k: int) -> list[dict]:
        if not self.healthy:
            raise MemoryServiceError("simulated mem0 outage")
        namespace = self._store.get(candidate_id, {})
        query_lower = query.lower()
        scored = [
            (sum(1 for token in query_lower.split() if token in mem["text"].lower()), mem_id, mem)
            for mem_id, mem in namespace.items()
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [{"memory_id": mem_id, **mem} for _, mem_id, mem in scored[:top_k]]

    def delete(self, candidate_id: str, memory_id: str) -> None:
        if not self.healthy:
            raise MemoryServiceError("simulated mem0 outage")
        self._store.get(candidate_id, {}).pop(memory_id, None)

    def health_check(self) -> bool:
        return self.healthy


class Mem0Provider(MemoryProvider):
    """Thin wrapper over the real mem0 SDK. Lazily imports `mem0` inside
    __init__ (never at module import time) so this module stays importable
    without the package installed, matching the Pinecone integration
    pattern (src/services/vector_service.py). Not exercised by any
    automated test — real mem0 calls require network/API credentials."""

    def __init__(self, api_key: str | None = None) -> None:
        try:
            from mem0 import MemoryClient
        except ImportError as exc:  # pragma: no cover - dependency always declared in requirements.txt
            raise MemoryServiceError("mem0ai is not installed") from exc
        try:
            self._client = MemoryClient(api_key=api_key) if api_key else MemoryClient()
        except Exception as exc:  # noqa: BLE001
            raise MemoryServiceError(f"failed to initialize mem0 client: {exc}") from exc

    def add(self, candidate_id: str, text: str, metadata: dict) -> str:
        try:
            result = self._client.add(text, user_id=candidate_id, metadata=metadata)
            return str(result.get("id", "")) if isinstance(result, dict) else str(result)
        except Exception as exc:  # noqa: BLE001
            raise MemoryServiceError(f"mem0 add failed: {exc}") from exc

    def search(self, candidate_id: str, query: str, top_k: int) -> list[dict]:
        try:
            results = self._client.search(query, user_id=candidate_id, limit=top_k)
            return [{"memory_id": r.get("id"), "text": r.get("memory", ""), "metadata": r.get("metadata", {})} for r in results]
        except Exception as exc:  # noqa: BLE001
            raise MemoryServiceError(f"mem0 search failed: {exc}") from exc

    def delete(self, candidate_id: str, memory_id: str) -> None:
        try:
            self._client.delete(memory_id)
        except Exception as exc:  # noqa: BLE001
            raise MemoryServiceError(f"mem0 delete failed: {exc}") from exc

    def health_check(self) -> bool:
        try:
            self._client.search("health-check", user_id="__health_check__", limit=1)
            return True
        except Exception:  # noqa: BLE001 - health checks must never raise
            return False


class MemoryService:
    def __init__(self, provider: MemoryProvider | None = None) -> None:
        self.provider = provider

    def remember_preference(self, candidate_id: str, preference_text: str) -> tuple[bool, str | None]:
        """Returns (synced, memory_id)."""
        return self._safe_add(candidate_id, preference_text, {"type": "preference"})

    def remember_strategy_insight(self, candidate_id: str, insight: LearningInsight) -> tuple[bool, str | None]:
        # Store only a concise pointer/observation -- never the full
        # analytics payload or database rows.
        text = f"[{insight.category.value}] {insight.observation} Recommendation: {insight.recommendation}"
        return self._safe_add(
            candidate_id,
            text,
            {"type": "strategy_insight", "insight_id": insight.insight_id, "category": insight.category.value},
        )

    def get_relevant_memories(self, candidate_id: str, query: str, top_k: int = 5) -> list[dict]:
        if self.provider is None:
            return []
        try:
            if not self.provider.health_check():
                return []
            return self.provider.search(candidate_id, query, top_k)
        except MemoryServiceError:
            return []

    def forget_memory(self, candidate_id: str, memory_id: str) -> bool:
        if self.provider is None:
            return False
        try:
            self.provider.delete(candidate_id, memory_id)
            return True
        except MemoryServiceError:
            return False

    def health_check(self) -> bool:
        if self.provider is None:
            return False
        try:
            return self.provider.health_check()
        except MemoryServiceError:
            return False

    def _safe_add(self, candidate_id: str, text: str, metadata: dict) -> tuple[bool, str | None]:
        if self.provider is None:
            return False, None
        try:
            if not self.provider.health_check():
                return False, None
            memory_id = self.provider.add(candidate_id, text, {**metadata, "recorded_at": datetime.now(timezone.utc).isoformat()})
            return True, memory_id
        except MemoryServiceError:
            return False, None
