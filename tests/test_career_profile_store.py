"""CareerProfileStore persistence tests — a genuinely separate SQLite DB."""

from __future__ import annotations

from src.models.career_profile import CareerProfile, PersonalInfo
from src.services import career_profile_store as store_module


def _store():
    conn = store_module.get_connection(":memory:")
    store_module.init_schema(conn)
    return store_module.CareerProfileStore(conn)


def test_get_by_owner_returns_none_when_absent():
    store = _store()
    assert store.get_by_owner("nobody") is None


def test_get_or_create_creates_and_persists():
    store = _store()
    profile = store.get_or_create("user-1")
    assert profile.owner_id == "user-1"
    fetched = store.get_by_owner("user-1")
    assert fetched is not None
    assert fetched.profile_id == profile.profile_id


def test_save_round_trips_nested_fields():
    store = _store()
    profile = store.get_or_create("user-2")
    profile.personal_info = PersonalInfo(first_name="Jane", last_name="Doe", professional_email="jane@example.com")
    store.save(profile)

    fetched = store.get_by_owner("user-2")
    assert fetched.personal_info.first_name == "Jane"
    assert fetched.personal_info.professional_email == "jane@example.com"


def test_save_is_upsert_keyed_by_owner_not_duplicate_rows():
    store = _store()
    p1 = store.get_or_create("user-3")
    p1.professional_summary = "first"
    store.save(p1)
    p2 = store.get_by_owner("user-3")
    p2.professional_summary = "second"
    store.save(p2)

    row_count = store._conn.execute(
        "SELECT COUNT(*) as c FROM career_profiles WHERE owner_id = ?", ("user-3",)
    ).fetchone()["c"]
    assert row_count == 1
    assert store.get_by_owner("user-3").professional_summary == "second"


def test_two_owners_are_fully_independent():
    store = _store()
    a = store.get_or_create("owner-a")
    a.professional_summary = "A's summary"
    store.save(a)
    b = store.get_or_create("owner-b")
    assert b.professional_summary == ""


def test_pending_upload_staging_lifecycle():
    store = _store()
    store.save_pending_upload("user-4", "upload-1", "resume.pdf", {"foo": "bar"})
    pending = store.get_pending_upload("upload-1")
    assert pending is not None
    assert pending["foo"] == "bar"
    assert pending["_original_filename"] == "resume.pdf"

    store.mark_upload_applied("upload-1")
    assert store.get_pending_upload("upload-1") is None
