"""SQLite persistence against a throwaway database."""

import pytest

import db


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "cv.db")


def test_job_lifecycle_records_status_history():
    job_id = db.create_job("https://example.com/job", None)
    assert db.get_job(job_id)["status"] == "incoming"

    db.update_job(job_id, status="tailored", interview_scheduled=1)
    db.update_job(job_id, status="tailored")  # unchanged status adds no history entry

    job = db.get_job(job_id)
    assert job["status"] == "tailored"
    assert job["interview_scheduled"] is True
    assert [h["status"] for h in db.status_history(job_id)] == ["incoming", "tailored"]
    assert [j["id"] for j in db.list_jobs()] == [job_id]

    db.delete_job(job_id)
    assert db.get_job(job_id) is None
    assert db.status_history(job_id) == []


def test_migrate_maps_legacy_statuses():
    job_id = db.create_job(None, "pasted ad")
    with db.connect() as conn:
        conn.execute("UPDATE jobs SET status = 'applied' WHERE id = ?", (job_id,))
    db.migrate()
    assert db.get_job(job_id)["status"] == "submitted"


def test_items_and_clarifications():
    job_id = db.create_job(None, "pasted ad")
    item_id = db.create_item(job_id, "role1", "M1")
    assert db.create_item(job_id, "role1", "M1") == item_id  # idempotent

    db.update_item(item_id, bullet="Did a thing", source_ids=["role1.h1"], selected=True)
    db.save_questions(item_id, ["How big?"])
    db.save_answers(item_id, [{"question": "How big?", "answer": "Huge"}])

    item = db.get_item(job_id, item_id)
    assert item["bullet"] == "Did a thing"
    assert item["source_ids"] == ["role1.h1"]
    assert item["selected"] is True
    assert item["clarification"] == {
        "questions": ["How big?"],
        "answers": [{"question": "How big?", "answer": "Huge"}],
    }
    assert [i["id"] for i in db.list_items(job_id)] == [item_id]


def test_documents_latest_wins():
    job_id = db.create_job(None, "pasted ad")
    assert db.latest_document(job_id) is None
    db.save_document(job_id, "# v1", None)
    db.save_document(job_id, "# v2", "output/v2.md")
    assert db.latest_document(job_id)["markdown"] == "# v2"
