"""
JSON view-model builders for the Next.js frontend.

Every function here reads already-computed values from `sess.state`
(the real LangGraph state dict produced by src/graph/workflow.py),
`sess.tracker` (the real ApplicationTrackerService), or `sess.interrupt`
(a real interrupt payload) and reshapes them into JSON-friendly dicts.
Nothing here computes a score, a match, a verification result, or an
analytics figure — that is 100% src/services + src/agents work, already
done by the time these functions run. This module is the JSON analogue of
src/ui/mission_control.py's pure-presentation helpers.
"""

from __future__ import annotations

from typing import Any

from api.engine import Session, outcome_analytics_for, stage_status_map

TRUTH_STATUS_LABELS = {
    "VERIFIED": "VERIFIED",
    "PARTIALLY_SUPPORTED": "PARTIALLY SUPPORTED",
    "UNSUPPORTED": "BLOCKED — UNSUPPORTED",
    "NEEDS_HUMAN_CONFIRMATION": "NEEDS HUMAN CONFIRMATION",
}


def _jsonable(obj: Any) -> Any:
    """Best-effort conversion of pydantic models / nested structures to
    plain JSON-safe values, without altering any values."""
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def agent_activity_rows(sess: Session) -> list[dict]:
    """Direct port of app.py's _agent_activity_rows — identical derivation
    rules, reshaped as JSON rows instead of Streamlit widgets."""
    s = sess.state or {}
    interrupt = sess.interrupt
    profile = s.get("candidate_profile")
    counts = s.get("counts", {}) or {}
    deduped = s.get("deduped_jobs", [])
    match_analyses = s.get("match_analyses", {})
    proposed_mods = s.get("proposed_modifications", [])
    rejected_mods = s.get("rejected_modifications", [])
    tg_results = s.get("truth_guard_results", {})
    insights = sess.tracker.list_strategy_insights()

    rows: list[dict] = []

    if profile:
        rows.append({"name": "Profile Agent", "status": "COMPLETE", "note": f"{len(profile.get('skills', []))} skill(s) identified from resume."})
    else:
        rows.append({"name": "Profile Agent", "status": "WAITING", "note": "Awaiting a resume upload / demo start."})

    if counts.get("ingested"):
        rows.append({"name": "Job Scout", "status": "COMPLETE", "note": f"{counts.get('ingested', 0)} job(s) ingested, {len(deduped)} after dedup."})
    else:
        rows.append({"name": "Job Scout", "status": "WAITING", "note": "No search run yet."})

    if match_analyses:
        rows.append({"name": "Match Analyst", "status": "COMPLETE", "note": f"Top {len(match_analyses)} opportunity(ies) analyzed."})
    elif s.get("opportunity_scores"):
        rows.append({"name": "Match Analyst", "status": "WORKING", "note": "Scoring complete; deep analysis pending."})
    else:
        rows.append({"name": "Match Analyst", "status": "WAITING", "note": "No opportunities scored yet."})

    if proposed_mods:
        rows.append({"name": "Resume Tailor", "status": "COMPLETE", "note": f"{len(proposed_mods)} modification(s) proposed."})
    elif s.get("selected_job_id"):
        rows.append({"name": "Resume Tailor", "status": "WORKING", "note": "Opportunity selected; tailoring in progress."})
    else:
        rows.append({"name": "Resume Tailor", "status": "WAITING", "note": "No opportunity selected yet."})

    needs_human = bool(interrupt and ("clarification_required" in interrupt or "modifications" in interrupt))
    if needs_human:
        rows.append({"name": "Truth Guard", "status": "NEEDS REVIEW", "note": "A claim needs human confirmation or approval before it can proceed."})
    elif tg_results:
        verified = sum(1 for r in tg_results.values() if r["status"] == "VERIFIED")
        rows.append({"name": "Truth Guard", "status": "COMPLETE", "note": f"{verified} verified, {len(rejected_mods)} rejected of {len(tg_results)} checked."})
    else:
        rows.append({"name": "Truth Guard", "status": "WAITING", "note": "No claims submitted for verification yet."})

    if insights:
        rows.append({"name": "Learning Agent", "status": "COMPLETE", "note": f"{len(insights)} strategy insight(s) generated."})
    else:
        rows.append({"name": "Learning Agent", "status": "WAITING", "note": "No outcomes recorded yet."})

    return rows


def truth_guard_summary(sess: Session) -> dict:
    s = sess.state or {}
    tg_results = s.get("truth_guard_results", {})
    counts = {"VERIFIED": 0, "PARTIALLY_SUPPORTED": 0, "UNSUPPORTED": 0, "NEEDS_HUMAN_CONFIRMATION": 0}
    for r in tg_results.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    modifications = {m["modification_id"]: m for m in s.get("proposed_modifications", [])}
    rejected = {r["modification_id"]: r for r in s.get("rejected_modifications", [])}
    example_rejected = next(iter(rejected.values()), None)
    example_verified_id = next((mid for mid, r in tg_results.items() if r.get("status") == "VERIFIED"), None)

    blocked_card = None
    if example_rejected:
        mod = modifications.get(example_rejected["modification_id"])
        blocked_card = {
            "claim": example_rejected.get("claim") or (mod["proposed_text"] if mod else example_rejected["modification_id"]),
            "reason": example_rejected.get("reason", ""),
            "result": "UNSUPPORTED",
        }

    verified_card = None
    if example_verified_id:
        v_mod = modifications.get(example_verified_id, {})
        v_result = tg_results[example_verified_id]
        verified_card = {
            "claim": v_mod.get("proposed_text", example_verified_id),
            "evidence": ", ".join(v_result.get("evidence_ids", [])) or "none",
            "result": "VERIFIED",
        }

    return {
        "counts": {
            "verified": counts["VERIFIED"],
            "blocked": counts["UNSUPPORTED"],
            "review": counts["NEEDS_HUMAN_CONFIRMATION"] + counts["PARTIALLY_SUPPORTED"],
        },
        "blocked_example": blocked_card,
        "verified_example": verified_card,
    }


def kpis(sess: Session) -> list[dict]:
    s = sess.state or {}
    scores = s.get("opportunity_scores", {})
    ranked = s.get("ranked_job_ids", [])
    high_priority = sum(1 for jid in ranked if scores.get(jid, {}).get("recommendation") == "HIGH_PRIORITY")
    analytics = outcome_analytics_for(sess)
    total_interviews = sum(g.interviews for g in analytics.by_role_family.values())
    interview_rate = (total_interviews / analytics.total_resolved) if analytics.total_resolved else 0.0

    return [
        {"icon": "search", "value": str(len(scores)), "label": "Opportunities Found"},
        {"icon": "star", "value": str(high_priority), "label": "High Priority"},
        {"icon": "send", "value": str(analytics.total_applications), "label": "Applications"},
        {"icon": "mic", "value": str(total_interviews), "label": "Interviews"},
        {"icon": "chart", "value": f"{interview_rate * 100:.1f}%", "label": "Interview Rate"},
    ]


def top_opportunity(sess: Session) -> dict | None:
    s = sess.state or {}
    scores = s.get("opportunity_scores", {})
    if not scores:
        return None
    deduped_by_id = {j["job_id"]: j for j in s.get("deduped_jobs", [])}
    top_id = max(scores, key=lambda jid: scores[jid]["final_score"])
    top = scores[top_id]
    job = deduped_by_id.get(top_id, {})
    analysis = s.get("match_analyses", {}).get(top_id)

    interrupt = sess.interrupt
    selectable = bool(
        interrupt
        and "eligible_selections" in interrupt
        and top_id in {item["job_id"] for item in interrupt["eligible_selections"]}
    )

    return {
        "job_id": top_id,
        "title": job.get("title", "?"),
        "company": job.get("company", "?"),
        "location": job.get("location") or "Location unknown",
        "work_mode": job.get("work_mode"),
        "score": top["final_score"],
        "recommendation": top["recommendation"],
        "confidence": top["confidence"],
        "strengths": (analysis or {}).get("strengths", [])[:3],
        "gaps": (analysis or {}).get("gaps", [])[:3],
        "selectable": selectable,
    }


def latest_insight(sess: Session) -> dict | None:
    insights = sess.tracker.list_strategy_insights()
    if not insights:
        return None
    return _jsonable(insights[0])


def recent_activity(sess: Session, limit: int = 8) -> list[dict]:
    s = sess.state or {}
    events = s.get("decision_trace", [])
    out = []
    for event in events[-limit:][::-1]:
        out.append({"message": event.get("message"), "timestamp": event.get("timestamp")})
    return out


def candidate_first_name(sess: Session) -> str | None:
    s = sess.state or {}
    profile = s.get("candidate_profile")
    if not profile or not profile.get("name"):
        return None
    return str(profile["name"]).strip().split()[0]


def mission_control_view(sess: Session) -> dict:
    """The single JSON payload the Next.js Mission Control page consumes."""
    s = sess.state or {}
    stage_status = stage_status_map(sess)
    return {
        "demo_mode": sess.settings.demo_mode,
        "candidate_first_name": candidate_first_name(sess),
        "has_run": bool(s.get("opportunity_scores")),
        "stage_status": stage_status,
        "kpis": kpis(sess) if s.get("opportunity_scores") else [],
        "top_opportunity": top_opportunity(sess),
        "latest_insight": latest_insight(sess),
        "agent_activity": agent_activity_rows(sess),
        "truth_guard_summary": truth_guard_summary(sess),
        "recent_activity": recent_activity(sess),
        "interrupt": _jsonable(sess.interrupt),
    }


def opportunities_view(sess: Session) -> dict:
    s = sess.state or {}
    scores = s.get("opportunity_scores", {})
    deduped_by_id = {j["job_id"]: j for j in s.get("deduped_jobs", [])}
    quality_by_id = s.get("job_quality_results", {})
    analyses = s.get("match_analyses", {})
    interrupt = sess.interrupt
    eligible_ids = {item["job_id"] for item in interrupt["eligible_selections"]} if interrupt and "eligible_selections" in interrupt else set()

    rows = []
    for job_id, score in scores.items():
        job = deduped_by_id.get(job_id, {})
        quality = quality_by_id.get(job_id, {})
        analysis = analyses.get(job_id)
        rows.append(
            {
                "job_id": job_id,
                "title": job.get("title", "?"),
                "company": job.get("company", "?"),
                "location": job.get("location") or "Location unknown",
                "work_mode": job.get("work_mode"),
                "source": job.get("source"),
                "url": job.get("url"),
                "score": score["final_score"],
                "recommendation": score["recommendation"],
                "confidence": score["confidence"],
                "scoring_version": score.get("scoring_version"),
                "components": score.get("components", {}),
                "requirement_completeness": quality.get("requirement_completeness"),
                "strengths": (analysis or {}).get("strengths", []),
                "gaps": (analysis or {}).get("gaps", []),
                "risks": (analysis or {}).get("risks", []),
                "explanation": (analysis or {}).get("explanation", ""),
                "selectable": job_id in eligible_ids,
            }
        )
    rows.sort(key=lambda r: -r["score"])
    return {"opportunities": rows, "counts": s.get("counts", {})}


def opportunity_detail_view(sess: Session, job_id: str) -> dict | None:
    """Read-only detail view for a single opportunity. Reshapes the same
    already-computed OpportunityScore / MatchAnalysis / JobQualityResult /
    JobPosting objects that opportunities_view already reads — nothing
    here recomputes a score, a match, or a quality figure. Adds the
    discover -> unique -> scored -> analyzed funnel (from the real
    `counts` dict + len(match_analyses)) for the detail page's "Behind
    The Decision" section."""
    s = sess.state or {}
    scores = s.get("opportunity_scores", {})
    if job_id not in scores:
        return None

    score = scores[job_id]
    deduped_by_id = {j["job_id"]: j for j in s.get("deduped_jobs", [])}
    job = deduped_by_id.get(job_id, {})
    quality = s.get("job_quality_results", {}).get(job_id, {})
    analyses = s.get("match_analyses", {})
    analysis = analyses.get(job_id)
    interrupt = sess.interrupt
    eligible_ids = {item["job_id"] for item in interrupt["eligible_selections"]} if interrupt and "eligible_selections" in interrupt else set()
    counts = s.get("counts", {}) or {}

    return {
        "job_id": job_id,
        "title": job.get("title", "?"),
        "company": job.get("company", "?"),
        "location": job.get("location") or "Location unknown",
        "work_mode": job.get("work_mode"),
        "source": job.get("source"),
        "url": job.get("url"),
        "score": score["final_score"],
        "recommendation": score["recommendation"],
        "confidence": score["confidence"],
        "scoring_version": score.get("scoring_version"),
        "components": score.get("components", {}),
        "listing_confidence": quality.get("confidence"),
        "requirement_completeness": quality.get("requirement_completeness"),
        "quality_score": quality.get("quality_score"),
        "quality_flags": quality.get("flags", []),
        "strengths": (analysis or {}).get("strengths", []),
        "gaps": (analysis or {}).get("gaps", []),
        "risks": (analysis or {}).get("risks", []),
        "explanation": (analysis or {}).get("explanation", ""),
        "selectable": job_id in eligible_ids,
        "funnel": {
            "discovered": counts.get("ingested", 0),
            "unique_after_dedup": counts.get("unique_after_dedup", 0),
            "scored": counts.get("scored", 0),
            "analyzed": len(analyses),
        },
    }


def resume_studio_view(sess: Session) -> dict:
    s = sess.state or {}
    interrupt = sess.interrupt
    tg_results = s.get("truth_guard_results", {})
    counts = {"VERIFIED": 0, "PARTIALLY_SUPPORTED": 0, "UNSUPPORTED": 0, "NEEDS_HUMAN_CONFIRMATION": 0}
    for r in tg_results.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    modifications = {m["modification_id"]: m for m in s.get("proposed_modifications", [])}
    rejected = {r["modification_id"]: r for r in s.get("rejected_modifications", [])}

    mods_out = []
    for mid, mod in modifications.items():
        result = tg_results.get(mid, {})
        status = result.get("status", "?")
        mods_out.append(
            {
                "modification_id": mid,
                "section": mod.get("section", "—"),
                "original_text": mod.get("original_text"),
                "proposed_text": mod["proposed_text"],
                "reason": mod.get("reason", ""),
                "evidence_ids": result.get("evidence_ids", []),
                "status": status,
                "status_label": TRUTH_STATUS_LABELS.get(status, status),
                "explanation": result.get("explanation", ""),
            }
        )

    rejected_out = []
    for r in rejected.values():
        mod = modifications.get(r["modification_id"])
        rejected_out.append(
            {
                "modification_id": r["modification_id"],
                "label": r.get("claim") or (mod["proposed_text"] if mod else r["modification_id"]),
                "reason": r["reason"],
            }
        )

    return {
        "selected_job_id": s.get("selected_job_id"),
        "counts": counts,
        "modifications": mods_out,
        "rejected": rejected_out,
        "interrupt": _jsonable(interrupt),
        "current_resume_version_id": s.get("current_resume_version_id"),
        "approved_modification_ids": s.get("approved_modification_ids", []),
    }


def applications_view(sess: Session) -> dict:
    interrupt = sess.interrupt
    interrupt_out = None
    if interrupt and "application" in interrupt and "modifications" not in interrupt:
        interrupt_out = _jsonable(interrupt["application"])

    # Application (src/models/application.py) intentionally has no
    # title/company field of its own (see that model's docstring) -- those
    # live on the JobPosting already held in session state. Look them up
    # here purely for display; nothing about the Application record itself
    # changes.
    s = sess.state or {}
    deduped_by_id = {j["job_id"]: j for j in s.get("deduped_jobs", [])}

    apps = []
    for application in sess.tracker.list_applications():
        history = sess.tracker.get_application_history(application.application_id)
        job = deduped_by_id.get(application.job_id, {})
        app_json = _jsonable(application)
        app_json["title"] = job.get("title")
        app_json["company"] = job.get("company")
        apps.append(
            {
                "application": app_json,
                "history": _jsonable(history),
            }
        )
    return {"pending_application_interrupt": interrupt_out, "applications": apps}


def strategy_view(sess: Session) -> dict:
    analytics = outcome_analytics_for(sess)
    insights = sess.tracker.list_strategy_insights()
    return {
        "demo_mode": sess.settings.demo_mode,
        "analytics": _jsonable(analytics),
        "insights": _jsonable(insights),
    }


def system_view(sess: Session) -> dict:
    settings = sess.settings
    llm_client = sess.llm_client
    return {
        "demo_mode": settings.demo_mode,
        "llm_provider": {
            "name": llm_client.primary.name,
            "status": "MOCK" if llm_client.primary.name == "mock" else "AVAILABLE",
        },
        "fallback_llm": (
            {"name": llm_client.fallback.name, "status": "CONFIGURED"} if llm_client.fallback else {"name": "none configured", "status": "UNAVAILABLE"}
        ),
        "evidence_retrieval": "MOCK" if settings.demo_mode else "AVAILABLE",
        "you_search": "AVAILABLE" if (settings.you_search_enabled and settings.ydc_api_key) else "UNAVAILABLE",
    }
