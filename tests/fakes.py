"""
Fake LLMProvider implementations for deterministic client/retry/fallback
testing. These are test doubles, not the MockLLMProvider used for demo/dev
purposes — they let a test script exactly which failures happen on which
call.
"""

from __future__ import annotations

from typing import Callable

from src.llm.base import LLMProvider, LLMResult, SchemaT
from src.llm.errors import HireLoopLLMError, LLMErrorType
from src.models.evidence import Evidence
from src.models.evidence_retrieval import EvidenceSearchResult, RetrievalSource
from src.services.vector_service import EvidenceVectorIndex, VectorServiceError


class ScriptedProvider(LLMProvider):
    """A provider whose behavior is a scripted sequence of actions, one per
    call to invoke()/structured_output(). Each action is either an
    LLMErrorType (raise that error) or a callable returning the value to
    return. Exhausting the script raises AssertionError (test bug, not
    product behavior)."""

    def __init__(self, name: str, script: list[LLMErrorType | Callable[[], object]]) -> None:
        self.name = name
        self._script = list(script)
        self.call_count = 0
        self.health_check_result = True

    def _next_action(self):
        if not self._script:
            raise AssertionError(f"ScriptedProvider({self.name}) script exhausted")
        self.call_count += 1
        return self._script.pop(0)

    def invoke(self, prompt: str, *, system: str | None = None, temperature: float = 0.0) -> LLMResult:
        action = self._next_action()
        if isinstance(action, LLMErrorType):
            raise HireLoopLLMError(action, f"scripted failure on {self.name}", provider=self.name)
        text = action() if callable(action) else action
        return LLMResult(text=text, provider=self.name, model="scripted-model")

    def structured_output(
        self,
        prompt: str,
        schema: type[SchemaT],
        *,
        system: str | None = None,
        temperature: float = 0.0,
    ) -> tuple[SchemaT, LLMResult]:
        action = self._next_action()
        if isinstance(action, LLMErrorType):
            raise HireLoopLLMError(action, f"scripted failure on {self.name}", provider=self.name)
        instance = action() if callable(action) else action
        return instance, LLMResult(text=instance.model_dump_json(), provider=self.name, model="scripted-model")

    def health_check(self) -> bool:
        return self.health_check_result


class InMemoryVectorIndex(EvidenceVectorIndex):
    """In-process fake implementing EvidenceVectorIndex's namespace-isolation
    contract, so tests can verify candidate isolation and Pinecone-fallback
    behavior without a real Pinecone connection. A trivial token-overlap
    score stands in for a real embedding similarity search -- good enough
    to exercise ranking/ordering behavior deterministically."""

    def __init__(self, healthy: bool = True, fail_on_search: bool = False) -> None:
        self.healthy = healthy
        self.fail_on_search = fail_on_search
        self._namespaces: dict[str, dict[str, Evidence]] = {}

    def index_candidate_evidence(self, candidate_id: str, evidence: list[Evidence]) -> None:
        namespace = self._namespaces.setdefault(candidate_id, {})
        for item in evidence:
            namespace[item.evidence_id] = item

    def search_candidate_evidence(self, candidate_id: str, query: str, top_k: int = 5) -> list[EvidenceSearchResult]:
        if self.fail_on_search:
            raise VectorServiceError("simulated Pinecone query failure")
        namespace = self._namespaces.get(candidate_id, {})
        query_lower = query.lower()
        scored = []
        for item in namespace.values():
            overlap = sum(1 for token in query_lower.split() if token in item.source_text.lower())
            if query_lower in item.source_text.lower():
                overlap += 1
            if overlap > 0:
                scored.append((overlap, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1].evidence_id))
        return [
            EvidenceSearchResult(evidence_id=item.evidence_id, score=float(score), source=RetrievalSource.PINECONE)
            for score, item in scored[:top_k]
        ]

    def delete_candidate_evidence(self, candidate_id: str) -> None:
        self._namespaces.pop(candidate_id, None)

    def health_check(self) -> bool:
        return self.healthy
