"""SQLite persistence for jobs, tailored CVs, clarifications and application status."""

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from state import CvState

DB_PATH = Path(os.getenv("DB_PATH", "data/cv.db"))

STATUSES = ["incoming", "tailored", "submitted", "sent_to_rav"]  # in pipeline order
LEGACY_STATUSES = {
    "draft": "incoming",
    "applied": "submitted",
    "interview": "submitted",
    "offer": "submitted",
    "rejected": "submitted",
    "withdrawn": "submitted",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY,
    url           TEXT,
    company       TEXT,
    role          TEXT,
    location      TEXT,
    description   TEXT,
    pasted_text   TEXT,
    status        TEXT NOT NULL DEFAULT 'incoming',
    interview_scheduled INTEGER NOT NULL DEFAULT 0,
    stage         TEXT NOT NULL DEFAULT 'queued',
    error         TEXT,
    submitted_at  TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_analysis (
    job_id             INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    requirements_json  TEXT NOT NULL,
    mapping_json       TEXT NOT NULL,
    headline           TEXT NOT NULL,
    my_contribution    TEXT NOT NULL,
    my_profile_json    TEXT NOT NULL,
    core_skills_json   TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_roles (
    job_id    INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    role_id   TEXT NOT NULL,
    title     TEXT NOT NULL,
    position  INTEGER NOT NULL,
    PRIMARY KEY (job_id, role_id)
);
CREATE TABLE IF NOT EXISTS role_items (
    id               INTEGER PRIMARY KEY,
    job_id           INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    role_id          TEXT NOT NULL,
    requirement_id   TEXT NOT NULL,
    bullet           TEXT,
    source_ids_json  TEXT NOT NULL DEFAULT '[]',
    selected         INTEGER NOT NULL DEFAULT 0,
    position         INTEGER NOT NULL,
    updated_at       TEXT NOT NULL,
    UNIQUE (job_id, role_id, requirement_id)
);
CREATE TABLE IF NOT EXISTS clarifications (
    id              INTEGER PRIMARY KEY,
    item_id         INTEGER NOT NULL REFERENCES role_items(id) ON DELETE CASCADE,
    questions_json  TEXT NOT NULL,
    answers_json    TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cv_documents (
    id          INTEGER PRIMARY KEY,
    job_id      INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    markdown    TEXT NOT NULL,
    path        TEXT,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS status_history (
    id          INTEGER PRIMARY KEY,
    job_id      INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    status      TEXT NOT NULL,
    changed_at  TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA)
        with conn:  # commit on success, roll back on error
            yield conn


def migrate() -> None:
    """Bring a database created by an older version up to date."""
    with connect() as conn:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}
        if "interview_scheduled" not in columns:
            conn.execute("ALTER TABLE jobs ADD COLUMN interview_scheduled INTEGER NOT NULL DEFAULT 0")
        for old, new in LEGACY_STATUSES.items():
            conn.execute("UPDATE jobs SET status = ? WHERE status = ?", (new, old))


# --- jobs ----------------------------------------------------------------------


def create_job(url: str | None, pasted_text: str | None) -> int:
    with connect() as conn:
        cur = conn.execute(
            # Explicit status: databases created before the pipeline change still default to 'draft'.
            "INSERT INTO jobs (url, pasted_text, status, created_at, updated_at) VALUES (?, ?, 'incoming', ?, ?)",
            (url, pasted_text, now(), now()),
        )
        conn.execute(
            "INSERT INTO status_history (job_id, status, changed_at) VALUES (?, 'incoming', ?)",
            (cur.lastrowid, now()),
        )
        return cur.lastrowid


def list_jobs() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, url, company, role, location, status, interview_scheduled, stage, submitted_at, "
            "created_at FROM jobs ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [_job(r) for r in rows]


def get_job(job_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _job(row) if row else None


def _job(row: sqlite3.Row) -> dict[str, Any]:
    job = dict(row)
    job["interview_scheduled"] = bool(job["interview_scheduled"])
    return job


def update_job(job_id: int, **fields: Any) -> None:
    if not fields:
        return
    with connect() as conn:
        if "status" in fields:
            current = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if current and current["status"] != fields["status"]:
                conn.execute(
                    "INSERT INTO status_history (job_id, status, changed_at) VALUES (?, ?, ?)",
                    (job_id, fields["status"], now()),
                )
        columns = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(
            f"UPDATE jobs SET {columns}, updated_at = ? WHERE id = ?",
            (*fields.values(), now(), job_id),
        )


def delete_job(job_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))


def status_history(job_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT status, changed_at FROM status_history WHERE job_id = ? ORDER BY id", (job_id,)
        ).fetchall()
    return [dict(r) for r in rows]


# --- analysis --------------------------------------------------------------------


def save_analysis(job_id: int, state: CvState) -> None:
    """Persist a finished graph run; replaces any earlier analysis of the job."""
    req, tailored = state.requirements, state.tailored_cv
    order = {r.id: n for n, r in enumerate(req.must_have + req.nice_to_have)}
    with connect() as conn:
        conn.execute(
            "UPDATE jobs SET company = ?, role = ?, location = ?, description = ?, updated_at = ? "
            "WHERE id = ?",
            (req.company, req.role, req.location, req.description, now(), job_id),
        )
        conn.execute(
            "INSERT OR REPLACE INTO job_analysis VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job_id,
                req.model_dump_json(),
                state.mapping.model_dump_json(),
                tailored.headline,
                tailored.my_contribution,
                json.dumps(tailored.my_profile),
                json.dumps(tailored.core_skills),
                now(),
            ),
        )
        conn.execute("DELETE FROM job_roles WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM role_items WHERE job_id = ?", (job_id,))
        for position, role in enumerate(tailored.roles):
            conn.execute(
                "INSERT INTO job_roles VALUES (?, ?, ?, ?)", (job_id, role.role_id, role.title, position)
            )
            for item in role.items:
                conn.execute(
                    "INSERT OR REPLACE INTO role_items (job_id, role_id, requirement_id, bullet, "
                    "source_ids_json, selected, position, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        job_id,
                        role.role_id,
                        item.requirement_id,
                        item.bullet,
                        json.dumps(item.source_ids),
                        int(bool(item.bullet and item.recommended)),
                        order.get(item.requirement_id, 999),
                        now(),
                    ),
                )


def get_analysis(job_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM job_analysis WHERE job_id = ?", (job_id,)).fetchone()
    if not row:
        return None
    return {
        "requirements": json.loads(row["requirements_json"]),
        "mapping": json.loads(row["mapping_json"]),
        "headline": row["headline"],
        "my_contribution": row["my_contribution"],
        "my_profile": json.loads(row["my_profile_json"]),
        "core_skills": json.loads(row["core_skills_json"]),
    }


def update_analysis(job_id: int, **fields: Any) -> None:
    columns = {
        "headline": ("headline", lambda v: v),
        "my_contribution": ("my_contribution", lambda v: v),
        "my_profile": ("my_profile_json", json.dumps),
        "core_skills": ("core_skills_json", json.dumps),
    }
    updates = {columns[k][0]: columns[k][1](v) for k, v in fields.items() if k in columns}
    if not updates:
        return
    with connect() as conn:
        assignments = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE job_analysis SET {assignments}, updated_at = ? WHERE job_id = ?",
            (*updates.values(), now(), job_id),
        )


def role_titles(job_id: int) -> dict[str, str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT role_id, title FROM job_roles WHERE job_id = ? ORDER BY position", (job_id,)
        ).fetchall()
    return {r["role_id"]: r["title"] for r in rows}


def update_role_title(job_id: int, role_id: str, title: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE job_roles SET title = ? WHERE job_id = ? AND role_id = ?", (title, job_id, role_id)
        )


# --- role items & clarifications -----------------------------------------------


def _item(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["source_ids"] = json.loads(item.pop("source_ids_json"))
    item["selected"] = bool(item["selected"])
    questions, answers = item.pop("questions_json", None), item.pop("answers_json", None)
    item["clarification"] = (
        {"questions": json.loads(questions), "answers": json.loads(answers) if answers else None}
        if questions
        else None
    )
    return item


ITEM_SELECT = """
SELECT i.*, c.questions_json, c.answers_json
FROM role_items i
LEFT JOIN clarifications c ON c.id = (
    SELECT MAX(id) FROM clarifications WHERE item_id = i.id
)
"""


def list_items(job_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(f"{ITEM_SELECT} WHERE i.job_id = ? ORDER BY i.position", (job_id,)).fetchall()
    return [_item(r) for r in rows]


def get_item(job_id: int, item_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(f"{ITEM_SELECT} WHERE i.job_id = ? AND i.id = ?", (job_id, item_id)).fetchone()
    return _item(row) if row else None


def create_item(job_id: int, role_id: str, requirement_id: str) -> int:
    """Insert an empty item unless the role already has one for the requirement; returns its id."""
    with connect() as conn:
        position = conn.execute(
            "SELECT MIN(position) FROM role_items WHERE job_id = ? AND requirement_id = ?",
            (job_id, requirement_id),
        ).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO role_items (job_id, role_id, requirement_id, position, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (job_id, role_id, requirement_id, 999 if position is None else position, now()),
        )
        row = conn.execute(
            "SELECT id FROM role_items WHERE job_id = ? AND role_id = ? AND requirement_id = ?",
            (job_id, role_id, requirement_id),
        ).fetchone()
        return row["id"]


def update_item(item_id: int, **fields: Any) -> None:
    if "source_ids" in fields:
        fields["source_ids_json"] = json.dumps(fields.pop("source_ids"))
    if "selected" in fields:
        fields["selected"] = int(fields["selected"])
    if not fields:
        return
    with connect() as conn:
        columns = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(
            f"UPDATE role_items SET {columns}, updated_at = ? WHERE id = ?", (*fields.values(), now(), item_id)
        )


def save_questions(item_id: int, questions: list[str]) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO clarifications (item_id, questions_json, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (item_id, json.dumps(questions), now(), now()),
        )


def save_answers(item_id: int, answers: list[dict[str, str]]) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE clarifications SET answers_json = ?, updated_at = ? "
            "WHERE id = (SELECT MAX(id) FROM clarifications WHERE item_id = ?)",
            (json.dumps(answers), now(), item_id),
        )


# --- exported documents ----------------------------------------------------------


def save_document(job_id: int, markdown: str, path: str | None) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO cv_documents (job_id, markdown, path, created_at) VALUES (?, ?, ?, ?)",
            (job_id, markdown, path, now()),
        )
        return cur.lastrowid


def latest_document(job_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, markdown, path, created_at FROM cv_documents WHERE job_id = ? ORDER BY id DESC LIMIT 1",
            (job_id,),
        ).fetchone()
    return dict(row) if row else None
