"""mem0 tests (Part U). Never hits live mem0 -- MockMemoryProvider only."""

from src.models.enums import InsightCategory, SampleConfidence
from src.models.learning_insight import LearningInsight
from src.services.memory_service import MemoryService, MockMemoryProvider


def _insight(insight_id="insight-1") -> LearningInsight:
    return LearningInsight(
        insight_id=insight_id,
        category=InsightCategory.ROLE_FAMILY,
        observation="AI Engineer applications show a stronger interview rate.",
        evidence="8 resolved applications: interview_rate=37.5%.",
        sample_size=8,
        confidence=SampleConfidence.MEDIUM,
        recommendation="Continue prioritizing AI Engineer roles.",
    )


# 1. Save preference.
def test_save_preference():
    service = MemoryService(MockMemoryProvider())
    synced, memory_id = service.remember_preference("cand-1", "Candidate prefers remote roles.")
    assert synced is True
    assert memory_id is not None


# 2. Save StrategyInsight.
def test_save_strategy_insight():
    service = MemoryService(MockMemoryProvider())
    synced, memory_id = service.remember_strategy_insight("cand-1", _insight())
    assert synced is True
    assert memory_id is not None


# 3. Retrieve candidate-specific memory.
def test_retrieve_relevant_memory():
    service = MemoryService(MockMemoryProvider())
    service.remember_preference("cand-1", "Candidate prefers remote AI Engineer roles.")

    results = service.get_relevant_memories("cand-1", "remote")
    assert results
    assert "remote" in results[0]["text"].lower()


# 4. Candidate isolation.
def test_candidate_isolation():
    service = MemoryService(MockMemoryProvider())
    service.remember_preference("cand-a", "Candidate A prefers onsite roles in Chicago.")
    service.remember_preference("cand-b", "Candidate B prefers remote roles only.")

    results_a = service.get_relevant_memories("cand-a", "roles")
    results_b = service.get_relevant_memories("cand-b", "roles")

    assert all("Candidate A" in r["text"] for r in results_a)
    assert all("Candidate B" in r["text"] for r in results_b)
    assert not any("Candidate B" in r["text"] for r in results_a)
    assert not any("Candidate A" in r["text"] for r in results_b)


# 5 & 6. mem0 unavailable -- local workflow still succeeds.
def test_mem0_unavailable_does_not_raise():
    service = MemoryService(MockMemoryProvider(healthy=False))

    synced, memory_id = service.remember_strategy_insight("cand-1", _insight())

    assert synced is False
    assert memory_id is None  # no exception raised -- caller can proceed


def test_mem0_unavailable_get_relevant_memories_returns_empty():
    service = MemoryService(MockMemoryProvider(healthy=False))
    assert service.get_relevant_memories("cand-1", "remote") == []


def test_no_provider_configured_degrades_gracefully():
    service = MemoryService(None)
    assert service.remember_preference("cand-1", "text") == (False, None)
    assert service.get_relevant_memories("cand-1", "query") == []
    assert service.health_check() is False


# 7. Duplicate insight -- storing the same insight_id twice does not
# corrupt state (mem0 dedup semantics are provider-specific; at minimum
# our layer must not crash or silently merge across candidates).
def test_storing_same_insight_twice_does_not_crash():
    service = MemoryService(MockMemoryProvider())
    insight = _insight()

    first = service.remember_strategy_insight("cand-1", insight)
    second = service.remember_strategy_insight("cand-1", insight)

    assert first[0] is True
    assert second[0] is True


# 8. Forget memory.
def test_forget_memory():
    service = MemoryService(MockMemoryProvider())
    _, memory_id = service.remember_preference("cand-1", "Candidate prefers remote roles.")

    forgotten = service.forget_memory("cand-1", memory_id)

    assert forgotten is True
    assert service.get_relevant_memories("cand-1", "remote") == []


def test_forget_memory_when_unavailable_returns_false_not_raise():
    service = MemoryService(MockMemoryProvider(healthy=False))
    assert service.forget_memory("cand-1", "mem-1") is False


# 9. Memory never overwrites SQLite facts -- MemoryService has no method
# that touches the business database at all.
def test_memory_service_has_no_database_access():
    import inspect

    source = inspect.getsource(MemoryService)
    assert "sqlite3" not in source
    assert "ApplicationTrackerService" not in source
    assert "get_connection" not in source


def test_memory_stores_only_concise_text_not_full_documents():
    service = MemoryService(MockMemoryProvider())
    service.remember_strategy_insight("cand-1", _insight())

    results = service.get_relevant_memories("cand-1", "AI Engineer")
    assert results
    # A concise strategy-level memory, not a dump of the full analytics/evidence payload.
    assert len(results[0]["text"]) < 500
