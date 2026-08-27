from src.services.decision_trace import DecisionTrace


def test_add_appends_event_with_message():
    trace = DecisionTrace()
    trace.add("ingestion", "ingest_jobs", "15 jobs ingested.")
    trace.add("dedup", "dedupe_jobs", "3 duplicate postings removed.", metadata={"removed": 3})

    assert len(trace.events) == 2
    assert trace.events[0].message == "15 jobs ingested."
    assert trace.events[1].metadata == {"removed": 3}


def test_as_lines_renders_human_readable_sequence():
    trace = DecisionTrace()
    trace.add("ingestion", "ingest_jobs", "15 jobs ingested.")
    trace.add("dedup", "dedupe_jobs", "3 duplicate postings removed.")
    trace.add("quality", "score_job_quality", "2 jobs flagged for review.")

    assert trace.as_lines() == [
        "15 jobs ingested.",
        "3 duplicate postings removed.",
        "2 jobs flagged for review.",
    ]


def test_as_dicts_is_json_serializable_shape():
    trace = DecisionTrace()
    trace.add("scoring", "score_opportunity", "10 opportunities scored.")

    dicts = trace.as_dicts()
    assert len(dicts) == 1
    assert dicts[0]["step"] == "scoring"
    assert dicts[0]["action"] == "score_opportunity"
    assert dicts[0]["message"] == "10 opportunities scored."
    assert "timestamp" in dicts[0]
