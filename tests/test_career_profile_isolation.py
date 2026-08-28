"""
Real/demo session isolation — the single most safety-critical test in this
task (see the task brief's Absolute Constraint #4).

Asserts:
  1. A fresh session defaults to PERSONAL mode with ZERO synthetic
     applications, application events, or strategy insights.
  2. compute_outcome_analytics for a PERSONAL session never mixes in
     data/sample_jobs.json / demo_application_loader-derived synthetic
     records, even when the process-wide settings.demo_mode flag is True
     (the default in this repo's .env).
  3. A CERTIFICATION_DEMO-mode session (and only that mode) is the one
     that may see synthetic demo history.
  4. The new CareerProfile SQLite store is completely separate from
     api/engine.py's in-memory session state -- creating/running sessions
     never creates a CareerProfile row, and a CareerProfile never
     contains, or is derived from, applications/session state.
  5. The certification demo flow itself is unaffected by any of the
     above changes (mode gating is additive; demo_mode's prior
     unconditional gate is a strict subset of the new mode+demo_mode
     gate for a CERTIFICATION_DEMO session).
"""

from __future__ import annotations

from api import engine
from src.services import career_profile_store as store_module


def test_fresh_session_defaults_to_personal_mode():
    sess = engine.create_session()
    assert sess.mode == "PERSONAL"


def test_fresh_session_has_zero_synthetic_applications_and_insights():
    sess = engine.create_session()
    assert sess.tracker.list_applications() == []
    assert sess.tracker.list_strategy_insights() == []
    assert sess.tracker.get_applications_with_history(include_demo_data=False) == []


def test_personal_mode_analytics_never_includes_synthetic_demo_history():
    sess = engine.create_session()
    assert sess.mode == "PERSONAL"
    # settings.demo_mode is True by default in this repo's .env -- the
    # isolation guarantee must hold regardless.
    assert sess.settings.demo_mode is True

    analytics = engine.outcome_analytics_for(sess)
    assert analytics.total_applications == 0


def test_certification_demo_mode_is_the_only_mode_that_can_see_demo_history():
    sess = engine.create_session()
    sess.mode = "CERTIFICATION_DEMO"
    analytics_demo_mode = engine.outcome_analytics_for(sess)

    sess.mode = "PERSONAL"
    analytics_personal_mode = engine.outcome_analytics_for(sess)

    # With settings.demo_mode True, only CERTIFICATION_DEMO mode may pull
    # in the seeded demo_application_history.json records.
    assert analytics_demo_mode.total_applications >= analytics_personal_mode.total_applications
    assert analytics_personal_mode.total_applications == 0


def test_load_certification_demo_sets_certification_demo_mode():
    sess = engine.create_session()
    engine.load_certification_demo(sess)
    assert sess.mode == "CERTIFICATION_DEMO"
    # The workflow stops at the first human interrupt (job selection),
    # exactly as before this task -- unaffected by mode gating.
    assert sess.interrupt is not None
    assert "eligible_selections" in sess.interrupt


def test_two_personal_sessions_do_not_share_state():
    sess_a = engine.create_session()
    sess_b = engine.create_session()
    assert sess_a.session_id != sess_b.session_id
    assert sess_a.tracker is not sess_b.tracker


def test_career_profile_store_is_independent_of_engine_sessions():
    """Creating/running engine sessions never touches the CareerProfile
    store, and vice versa -- they are backed by entirely separate SQLite
    connections/files."""
    conn = store_module.get_connection(":memory:")
    store_module.init_schema(conn)
    profile_store = store_module.CareerProfileStore(conn)

    sess = engine.create_session()
    engine.load_certification_demo(sess)

    # The demo run created real (in-memory, session-scoped) workflow state,
    # but no CareerProfile row exists anywhere unless explicitly created.
    assert profile_store.get_by_owner(sess.session_id) is None
    assert profile_store.get_by_owner("any-owner") is None


def test_career_profile_never_derived_from_demo_session_state():
    """A CareerProfile created for a real user must start empty -- it can
    never be auto-populated from a certification-demo session's state,
    even if one happens to exist in the same process."""
    sess = engine.create_session()
    engine.load_certification_demo(sess)  # populate demo session state

    conn = store_module.get_connection(":memory:")
    store_module.init_schema(conn)
    profile_store = store_module.CareerProfileStore(conn)
    profile = profile_store.get_or_create("real-user-1")

    assert profile.work_experience == []
    assert profile.skills == []
    assert profile.resume_source.uploaded_at is None
