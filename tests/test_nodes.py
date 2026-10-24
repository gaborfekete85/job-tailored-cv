"""Deterministic (no LLM) parts of the tailoring flow."""

from pathlib import Path

import nodes
from state import JobRequirements, Role

CV_MD = """\
# Jane Doe

## Headline

Senior Software Engineer

## Contact

- **Email:** jane@example.com
- **Phone:**

## Professional Experience

### Platform Engineer

- **Company:** Acme
- **Customer:** Globex
- **Start:** 2021-03
- **End:** present

**Highlights:**

* Infrastructure
- Migrated 40 services to Kubernetes, cutting deploy time by 70%.
- Built the CI pipeline [fill: number of teams] for the platform group.
- Too short.

### Developer

- **Company:** Initech
- **Start:** 2018-01
- **End:** 2021-02

**Highlights:**

- Shipped the billing service used by 2M customers every month.

## Core Skills & Competencies

- Python
- Kubernetes
"""


def test_parse_cv_sections_and_roles():
    cv = nodes.parse_cv(CV_MD)

    assert cv.name == "Jane Doe"
    assert cv.headline == "Senior Software Engineer"
    assert cv.contact == {"Email": "jane@example.com"}  # empty values are dropped
    assert cv.skills == ["Python", "Kubernetes"]
    assert [r.id for r in cv.roles] == ["role1", "role2"]

    role = cv.roles[0]
    assert (role.title, role.company, role.customer, role.start, role.end) == (
        "Platform Engineer", "Acme", "Globex", "2021-03", "present",
    )
    assert [h.id for h in role.highlights] == ["role1.h1", "role1.h2"]  # short bullet skipped
    assert role.highlights[0].theme == "Infrastructure"
    assert not role.highlights[0].incomplete
    assert role.highlights[1].text == "Built the CI pipeline for the platform group."
    assert role.highlights[1].incomplete


def test_clarifications_round_trip(tmp_path: Path):
    cv_path = tmp_path / "cv.md"
    cv_path.write_text(CV_MD, encoding="utf-8")
    role = nodes.parse_cv(CV_MD).roles[0]

    answers = [{"question": "How many teams?", "answer": "- Five teams\n- 30 engineers"}]
    nodes.log_clarification(cv_path, role, "Platform Engineer", answers)
    nodes.log_clarification(cv_path, role, "Platform Engineer", answers)  # duplicate is ignored

    log = (tmp_path / nodes.CLARIFICATIONS_FILE).read_text(encoding="utf-8")
    assert log.count("How many teams?") == 1

    cv = nodes.load_cv_database(cv_path)
    clarified = [h for h in cv.roles[0].highlights if h.clarified]
    assert [(h.id, h.text) for h in clarified] == [("role1.c1", "Five teams"), ("role1.c2", "30 engineers")]
    assert nodes.baseline_bullets(cv.roles[0]) == [cv.roles[0].highlights[0].text]


def test_split_bullets():
    text = "- First bullet\n  continues here\n\n•Second\n-Third"
    assert nodes.split_bullets(text) == ["First bullet continues here", "Second", "Third"]
    assert nodes.split_bullets("plain line") == ["plain line"]


def test_role_formatting():
    role = Role(id="role1", title="Dev", company="Acme", customer="Globex", start="2021-03", end="present")
    assert nodes.format_period(role) == "03/21 – today"
    assert nodes.format_employer(role) == "Acme (client: Globex)"
    assert nodes.format_employer(role.model_copy(update={"company": None})) == "Globex"


def test_linkedin_urls():
    search = "https://www.linkedin.com/jobs/search/?currentJobId=4012345678&keywords=python"
    view = "https://www.linkedin.com/jobs/view/senior-engineer-at-acme-4012345678/"
    assert nodes.linkedin_job_id(search) == "4012345678"
    assert nodes.linkedin_job_id(view) == "4012345678"
    assert nodes.normalize_job_url(search) == "https://www.linkedin.com/jobs/view/4012345678"
    assert nodes.normalize_job_url("https://example.com/jobs/1") == "https://example.com/jobs/1"


def test_cv_slug():
    req = JobRequirements(
        company="Acme AG", role="Senior Engineer (Python)", description="", responsibilities=[],
        must_have=[], nice_to_have=[],
    )
    assert nodes.cv_slug(req) == "acme-ag-senior-engineer-python"
