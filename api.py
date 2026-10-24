"""FastAPI backend for the CV tailoring UI.

Run:  uv run uvicorn api:app --reload --port 8432
"""

from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, model_validator

import cv_pdf
import db
import nodes
from graph import graph
from state import CvDatabase, CvState, JobRequirements, TailoredCv, TailoredRole

ROOT = Path(__file__).parent
CV_PATH = ROOT / "cv" / "cv.md"
OUTPUT_DIR = ROOT / "output"
FRONTEND_DIST = ROOT / "frontend" / "dist"

# Stage shown while the graph runs: the node that runs after the one that just finished.
NEXT_STAGE = {
    "load_cv": "load_job",
    "load_job": "extract_requirements",
    "extract_requirements": "map_requirements",
    "map_requirements": "write_cv",
    "write_cv": "render_cv",
    "render_cv": "saving",
}
FINISHED_STAGES = {"done", "error"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.migrate()
    for job in db.list_jobs():  # runs die with the server; don't leave them spinning
        if job["stage"] not in FINISHED_STAGES:
            db.update_job(job["id"], stage="error", error="Interrupted by a server restart — run again.")
    yield


app = FastAPI(title="Job-tailored CV", lifespan=lifespan)


def load_cv() -> CvDatabase:
    return nodes.load_cv_database(CV_PATH)


def require_job(job_id: int) -> dict:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


def require_analysis(job_id: int) -> dict:
    analysis = db.get_analysis(job_id)
    if not analysis:
        raise HTTPException(409, "The job has not been analyzed yet")
    return analysis


# --- analysis run ------------------------------------------------------------------


async def analyze(job_id: int) -> None:
    job = require_job(job_id)
    db.update_job(job_id, stage="load_cv", error=None)
    state = CvState(cv_path=CV_PATH, job_url=job["url"], job_text=job["pasted_text"], output_dir=OUTPUT_DIR)
    final = None
    try:
        async for namespace, mode, data in graph.astream(
            state, stream_mode=["updates", "values"], subgraphs=True
        ):
            if mode == "updates":
                for node in data:
                    if node in NEXT_STAGE:
                        db.update_job(job_id, stage=NEXT_STAGE[node])
            elif not namespace:
                final = data
        result = CvState.model_validate(final)
        db.save_analysis(job_id, result)
        db.save_document(job_id, result.output_path.read_text(encoding="utf-8"), str(result.output_path))
        db.update_job(job_id, stage="done")
    except Exception as exc:  # surfaced in the UI; the job stays retryable
        db.update_job(job_id, stage="error", error=f"{type(exc).__name__}: {exc}")


# --- read models ---------------------------------------------------------------------


def job_detail(job_id: int) -> dict:
    job = require_job(job_id)
    job.pop("pasted_text", None)
    job["status_history"] = db.status_history(job_id)
    analysis = db.get_analysis(job_id)
    roles = []
    if analysis:
        cv = load_cv()
        titles = db.role_titles(job_id)
        items_by_role = defaultdict(list)
        for item in db.list_items(job_id):
            items_by_role[item["role_id"]].append(item)
        roles = [
            {
                "role_id": role.id,
                "period": nodes.format_period(role),
                "employer": nodes.format_employer(role),
                "original_title": role.title,
                "title": titles.get(role.id, role.title),
                "items": items_by_role.get(role.id, []),
                "baseline": nodes.baseline_bullets(role),
            }
            for role in cv.roles
        ]
    return {
        "job": job,
        "statuses": db.STATUSES,
        "analysis": analysis,
        "roles": roles,
        "document": db.latest_document(job_id),
    }


# --- jobs ----------------------------------------------------------------------------


class CreateJob(BaseModel):
    url: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def url_or_description(self):
        self.url = (self.url or "").strip() or None
        self.description = (self.description or "").strip() or None
        if not self.url and not self.description:
            raise ValueError("Give a job URL or paste the job description")
        return self


class UpdateJob(BaseModel):
    status: Literal["incoming", "tailored", "submitted", "sent_to_rav"] | None = None
    interview_scheduled: bool | None = None
    submitted_at: str | None = None
    company: str | None = None
    role: str | None = None
    location: str | None = None
    url: str | None = None


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    return db.list_jobs()


@app.post("/api/jobs", status_code=201)
def create_job(body: CreateJob, background: BackgroundTasks) -> dict:
    job_id = db.create_job(body.url and nodes.normalize_job_url(body.url), body.description)
    background.add_task(analyze, job_id)
    return job_detail(job_id)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int) -> dict:
    return job_detail(job_id)


@app.post("/api/jobs/{job_id}/analyze")
def rerun(job_id: int, background: BackgroundTasks) -> dict:
    if require_job(job_id)["stage"] not in FINISHED_STAGES:
        raise HTTPException(409, "Analysis is already running")
    db.update_job(job_id, stage="queued", error=None)
    background.add_task(analyze, job_id)
    return job_detail(job_id)


@app.patch("/api/jobs/{job_id}")
def update_job(job_id: int, body: UpdateJob) -> dict:
    job = require_job(job_id)
    fields = body.model_dump(exclude_unset=True)
    if "url" in fields:
        url = (fields["url"] or "").strip()
        fields["url"] = nodes.normalize_job_url(url) if url else None
    if fields.get("status") == "submitted" and not job["submitted_at"] and "submitted_at" not in fields:
        fields["submitted_at"] = db.now()[:10]
    db.update_job(job_id, **fields)
    return job_detail(job_id)


@app.delete("/api/jobs/{job_id}", status_code=204)
def delete_job(job_id: int) -> None:
    require_job(job_id)
    db.delete_job(job_id)


# --- tailored content -------------------------------------------------------------------


class UpdateAnalysis(BaseModel):
    headline: str | None = None
    my_contribution: str | None = None
    my_profile: list[str] | None = None
    core_skills: list[str] | None = None


class UpdateRole(BaseModel):
    title: str


class UpdateItem(BaseModel):
    bullet: str | None = None
    selected: bool | None = None


class CreateItem(BaseModel):
    role_id: str
    requirement_id: str


class Answer(BaseModel):
    question: str
    answer: str = ""


class Refine(BaseModel):
    answers: list[Answer]


@app.patch("/api/jobs/{job_id}/analysis")
def update_analysis(job_id: int, body: UpdateAnalysis) -> dict:
    require_analysis(job_id)
    db.update_analysis(job_id, **body.model_dump(exclude_none=True))
    return job_detail(job_id)


@app.patch("/api/jobs/{job_id}/roles/{role_id}")
def update_role(job_id: int, role_id: str, body: UpdateRole) -> dict:
    require_analysis(job_id)
    db.update_role_title(job_id, role_id, body.title.strip())
    return job_detail(job_id)


def require_item(job_id: int, item_id: int) -> dict:
    item = db.get_item(job_id, item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    return item


@app.post("/api/jobs/{job_id}/items", status_code=201)
def create_item(job_id: int, body: CreateItem) -> dict:
    """An empty slot for a requirement in a work period, to write a bullet into (idempotent)."""
    requirements = JobRequirements.model_validate(require_analysis(job_id)["requirements"])
    if body.requirement_id not in {r.id for r in requirements.must_have + requirements.nice_to_have}:
        raise HTTPException(404, "Requirement not found")
    if body.role_id not in {r.id for r in load_cv().roles}:
        raise HTTPException(404, "Role not found")
    return require_item(job_id, db.create_item(job_id, body.role_id, body.requirement_id))


@app.patch("/api/jobs/{job_id}/items/{item_id}")
def update_item(job_id: int, item_id: int, body: UpdateItem) -> dict:
    require_item(job_id, item_id)
    fields = body.model_dump(exclude_unset=True)
    if "bullet" in fields:
        fields["bullet"] = (fields["bullet"] or "").strip() or None
    db.update_item(item_id, **fields)
    return require_item(job_id, item_id)


@app.post("/api/jobs/{job_id}/items/{item_id}/questions")
async def ask_questions(job_id: int, item_id: int) -> dict:
    item = require_item(job_id, item_id)
    requirements = JobRequirements.model_validate(require_analysis(job_id)["requirements"])
    questions = await nodes.clarifying_questions(
        load_cv(), requirements, item["role_id"], item["requirement_id"], item["bullet"]
    )
    db.save_questions(item_id, questions)
    return require_item(job_id, item_id)


@app.post("/api/jobs/{job_id}/items/{item_id}/refine")
async def refine(job_id: int, item_id: int, body: Refine) -> dict:
    item = require_item(job_id, item_id)
    if not item["clarification"]:
        raise HTTPException(409, "Ask the clarifying questions first")
    answers = [a.model_dump() for a in body.answers]
    db.save_answers(item_id, answers)
    requirements = JobRequirements.model_validate(require_analysis(job_id)["requirements"])
    cv = load_cv()
    # Log the answers before the LLM call, so they are kept as evidence even if it fails.
    requirement = next(r for r in requirements.must_have + requirements.nice_to_have if r.id == item["requirement_id"])
    nodes.log_clarification(
        CV_PATH,
        next(r for r in cv.roles if r.id == item["role_id"]),
        f"{db.now()[:10]} · {requirements.company} — {requirements.role} · {requirement.id}: {requirement.text}",
        answers,
    )
    refined = await nodes.refine_bullet(
        cv, requirements, item["role_id"], item["requirement_id"], item["bullet"], answers
    )
    db.update_item(item_id, bullet=refined.bullet, source_ids=refined.source_ids, selected=True)
    return require_item(job_id, item_id)


def export_inputs(job_id: int) -> tuple[CvDatabase, TailoredCv, dict[str, list[str]], str]:
    """What both exports render: the CV, the tailored texts, the selected bullets and the file slug."""
    analysis = require_analysis(job_id)
    titles = db.role_titles(job_id)
    bullets = defaultdict(list)
    for item in db.list_items(job_id):
        if item["selected"] and item["bullet"]:
            bullets[item["role_id"]].append(item["bullet"])
    tailored = TailoredCv(
        headline=analysis["headline"],
        my_contribution=analysis["my_contribution"],
        my_profile=analysis["my_profile"],
        roles=[TailoredRole(role_id=rid, title=title, items=[]) for rid, title in titles.items()],
        core_skills=analysis["core_skills"],
    )
    slug = nodes.cv_slug(JobRequirements.model_validate(analysis["requirements"]))
    return load_cv(), tailored, bullets, slug


def save_markdown(job_id: int) -> dict:
    cv, tailored, bullets, slug = export_inputs(job_id)
    markdown = nodes.cv_markdown(cv, tailored, bullets)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{slug}-cv.md"
    path.write_text(markdown, encoding="utf-8")
    db.save_document(job_id, markdown, str(path))
    return db.latest_document(job_id)


class ExportPdf(BaseModel):
    template: str


@app.post("/api/jobs/{job_id}/export")
def export(job_id: int) -> dict:
    return save_markdown(job_id)


@app.get("/api/cv-templates")
def cv_templates() -> list[dict]:
    return cv_pdf.list_templates()


@app.post("/api/jobs/{job_id}/export/pdf")
def export_pdf(job_id: int, body: ExportPdf) -> Response:
    """The same CV as the Markdown export (saved alongside it), printed with a reference template."""
    try:
        css = cv_pdf.template_css(body.template)
    except cv_pdf.UnknownTemplate as exc:
        raise HTTPException(404, str(exc)) from exc
    save_markdown(job_id)
    cv, tailored, bullets, slug = export_inputs(job_id)
    try:
        pdf = cv_pdf.to_pdf(cv_pdf.cv_html(cv, tailored, bullets, css))
    except cv_pdf.PdfError as exc:
        raise HTTPException(500, str(exc)) from exc
    path = OUTPUT_DIR / f"{slug}-cv.pdf"
    path.write_bytes(pdf)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{path.name}"', "X-Saved-Path": str(path)},
    )


# Serve the built frontend (bun run build) from the same port, if present.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
