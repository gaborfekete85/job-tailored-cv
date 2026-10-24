"""Pydantic models: the CV database, the job requirements and the graph state."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


# --- CV database (parsed from cv.md, no LLM involved) -----------------------


class Highlight(BaseModel):
    id: str = Field(description="Stable reference, e.g. 'role2.h5'")
    theme: str | None = Field(default=None, description="Sub-heading the bullet sits under")
    text: str
    incomplete: bool = Field(
        default=False, description="True when [fill: ...] placeholders were stripped from the text"
    )
    clarified: bool = Field(
        default=False, description="True for the candidate's own clarification answer (cv/clarifications.md)"
    )


class Role(BaseModel):
    id: str
    title: str
    company: str | None = None
    customer: str | None = None
    start: str
    end: str
    highlights: list[Highlight] = []


class Certification(BaseModel):
    name: str
    issuer: str | None = None
    status: str | None = None


class Education(BaseModel):
    institution: str
    field: str | None = None
    start_year: str | None = None
    end_year: str | None = None


class CvDatabase(BaseModel):
    """The full union of experience — a source of evidence, not the final CV."""

    name: str
    headline: str
    contact: dict[str, str] = {}
    personal: dict[str, str] = {}
    roles: list[Role] = []
    skills: list[str] = []
    certifications: list[Certification] = []
    education: list[Education] = []
    interests: list[str] = []


# --- Job requirements (extracted by the LLM) ---------------------------------


class Requirement(BaseModel):
    id: str = Field(description="'M1', 'M2', ... for must-have; 'N1', 'N2', ... for nice-to-have")
    text: str = Field(description="The requirement, close to the wording of the job ad")
    keywords: list[str] = Field(description="Key terms a recruiter would scan for")


class JobRequirements(BaseModel):
    company: str
    role: str
    location: str | None = None
    description: str = Field(
        description="The job ad itself as clean markdown (role, responsibilities, requirements, "
        "offer) without site navigation, cookie banners or other listings"
    )
    responsibilities: list[str] = Field(
        description="What the person will do in the role (the 'your responsibilities' part)"
    )
    must_have: list[Requirement]
    nice_to_have: list[Requirement]


# --- CV writer sub-agent output ------------------------------------------------


class RequirementMatch(BaseModel):
    requirement_id: str
    strength: Literal["strong", "partial", "none"]
    evidence_ids: list[str] = Field(description="Highlight ids from the CV database that prove it")
    rationale: str = Field(description="One sentence: why this evidence satisfies the requirement")


class RequirementMapping(BaseModel):
    matches: list[RequirementMatch]


class RequirementBullet(BaseModel):
    requirement_id: str
    bullet: str | None = Field(
        description="Goal-oriented bullet (action + situation + result) proving this requirement "
        "with evidence from THIS role only; null when the role has no evidence for it"
    )
    source_ids: list[str] = Field(default=[], description="Highlight ids of this role it is based on")
    recommended: bool = Field(
        description="True if the bullet should go into the final CV: strong evidence, "
        "not a duplicate of another bullet in this role, keeps the CV within 4 pages"
    )


class TailoredRole(BaseModel):
    role_id: str = Field(description="Id of the role in the CV database")
    title: str = Field(description="Role title only, aligned to the target job title where honest")
    items: list[RequirementBullet] = Field(description="Exactly one item per job requirement")


class TailoredCv(BaseModel):
    headline: str
    my_contribution: str = Field(description="4-5 sentence value statement")
    my_profile: list[str] = Field(description="4-6 bullets, each condensing one claim of My Contribution")
    roles: list[TailoredRole] = Field(description="Every role from the database, most recent first")
    core_skills: list[str]


class ClarifyingQuestions(BaseModel):
    questions: list[str] = Field(description="3-5 short, concrete questions")


class RefinedBullet(BaseModel):
    bullet: str
    source_ids: list[str] = []


# --- Graph state -------------------------------------------------------------


class CvState(BaseModel):
    cv_path: Path
    job_path: Path | None = None
    job_url: str | None = None
    output_dir: Path = Path("output")

    cv: CvDatabase | None = None
    job_text: str | None = None
    requirements: JobRequirements | None = None
    mapping: RequirementMapping | None = None
    tailored_cv: TailoredCv | None = None
    output_path: Path | None = None
