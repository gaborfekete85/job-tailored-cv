"""Business logic for every node of the CV tailoring graph."""

import json
import re
from datetime import date
from pathlib import Path

from llm import structured
from state import (
    Certification,
    ClarifyingQuestions,
    CvDatabase,
    CvState,
    Education,
    Highlight,
    JobRequirements,
    RefinedBullet,
    RequirementMapping,
    Role,
    TailoredCv,
)

SKILL_PATH = Path(__file__).parent / "skills" / "cv-writer" / "SKILL.md"

BASELINE_BULLETS = 3  # highlights a role falls back to when no tailored bullet is selected
CLARIFICATIONS_FILE = "clarifications.md"  # lives next to cv.md
CLARIFICATIONS_HEADER = (
    "# Clarifications\n\n"
    "Answers given in the CV tailoring UI, grouped by work period. Every answer is evidence for "
    "future jobs — edit or delete freely. Each `  - ` line under a question is one fact.\n"
)
QUESTION = re.compile(r"^- \*\*Q:\*\*\s*(.+)$")
FACT = re.compile(r"^\s+- (.+)$")
BULLET_START = re.compile(r"^[-•](?:\s+|(?=[A-Za-z]))")

FIELD = re.compile(r"^\s*- \*\*(.+?):\*\*\s*(.*)$")
PLACEHOLDER = re.compile(r"\s*[;,]?\s*\[(?:fill|PLANNED)\b[^\]]*\]", re.IGNORECASE)


# --- 1. Load the CV database ---------------------------------------------------


def load_cv(state: CvState) -> dict:
    return {"cv": load_cv_database(state.cv_path)}


def load_cv_database(cv_path: Path) -> CvDatabase:
    """cv.md plus the clarification answers logged next to it."""
    cv = parse_cv(cv_path.read_text(encoding="utf-8"))
    log = cv_path.with_name(CLARIFICATIONS_FILE)
    if log.exists():
        attach_clarifications(cv, log.read_text(encoding="utf-8"))
    return cv


def parse_cv(markdown: str) -> CvDatabase:
    name = re.search(r"^# (.+)$", markdown, re.MULTILINE).group(1).strip()
    sections = _split(markdown, "## ")
    return CvDatabase(
        name=name,
        headline=_first_line(sections.get("Headline", "")),
        contact=_fields(sections.get("Contact", "")),
        personal=_fields(sections.get("Personal Details", "")),
        roles=_parse_roles(sections.get("Professional Experience", "")),
        skills=_bullets(sections.get("Core Skills & Competencies", "")),
        certifications=[
            Certification(name=title, issuer=f.get("Issuer"), status=f.get("Status"))
            for title, f in _blocks(sections.get("Certifications", ""))
        ],
        education=[
            Education(
                institution=title,
                field=f.get("Field of Study"),
                start_year=f.get("Start Year"),
                end_year=f.get("End Year"),
            )
            for title, f in _blocks(sections.get("Education", ""))
        ],
        interests=_bullets(sections.get("Interests", "")),
    )


def _split(markdown: str, prefix: str) -> dict[str, str]:
    """Split markdown on headings with the given prefix: {heading: body}."""
    parts = re.split(rf"^{re.escape(prefix)}(.+)$", markdown, flags=re.MULTILINE)
    return {parts[i].strip(): parts[i + 1] for i in range(1, len(parts), 2)}


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def _fields(text: str) -> dict[str, str]:
    """`- **Key:** value` lines; empty values are dropped."""
    matches = (FIELD.match(line) for line in text.splitlines())
    return {m.group(1): m.group(2).strip() for m in matches if m and m.group(2).strip()}


def _bullets(text: str) -> list[str]:
    return [line[2:].strip() for line in text.splitlines() if line.startswith("- ")]


def _blocks(text: str) -> list[tuple[str, dict[str, str]]]:
    return [(title, _fields(body)) for title, body in _split(text, "### ").items()]


def _parse_roles(text: str) -> list[Role]:
    roles = []
    for n, (title, body) in enumerate(_split(text, "### ").items(), start=1):
        role_id = f"role{n}"
        meta, _, highlights_text = body.partition("**Highlights:**")
        fields = _fields(meta)
        highlights, theme = [], None
        for line in highlights_text.splitlines():
            if m := re.match(r"^\s*\* (.+)$", line):
                theme = m.group(1).strip()
            elif m := re.match(r"^\s*- (.+)$", line):
                cleaned = _clean(m.group(1))
                if len(cleaned) > 20:
                    highlights.append(
                        Highlight(
                            id=f"{role_id}.h{len(highlights) + 1}",
                            theme=theme,
                            text=cleaned,
                            incomplete=cleaned != m.group(1).strip(),
                        )
                    )
        roles.append(
            Role(
                id=role_id,
                title=title,
                company=fields.get("Company"),
                customer=fields.get("Customer"),
                start=fields.get("Start", ""),
                end=fields.get("End", ""),
                highlights=highlights,
            )
        )
    return roles


def _clean(text: str) -> str:
    """Remove [fill: ...] / [PLANNED: ...] placeholders — they are not evidence."""
    text = PLACEHOLDER.sub("", text).strip()
    text = re.sub(r"\s+([.;,])", r"\1", text)
    return re.sub(r"[;,]+\.?$", ".", text)


# --- 2. Load the job ad --------------------------------------------------------


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0 Safari/537.36"
)


async def load_job(state: CvState) -> dict:
    """Pasted text wins; otherwise fetch the URL; otherwise read the job file."""
    if state.job_text:
        text = state.job_text
        if state.job_url:
            text = f"Source URL: {state.job_url}\n\n{text}"
        return {"job_text": text}
    if state.job_url:
        return {"job_text": await fetch_job_page(state.job_url)}
    if state.job_path:
        return {"job_text": state.job_path.read_text(encoding="utf-8")}
    raise ValueError("No job given: pass a job file, a URL or the job description text")


LINKEDIN_JOB_ID = re.compile(r"(?:currentJobId=|/jobs/view/(?:[^/?]*-)?)(\d{6,})")


def linkedin_job_id(url: str) -> str | None:
    """Job id from any LinkedIn job link (search results, collections, /jobs/view/...)."""
    if "linkedin.com" not in url:
        return None
    match = LINKEDIN_JOB_ID.search(url)
    return match.group(1) if match else None


def normalize_job_url(url: str) -> str:
    """Canonical URL to store: LinkedIn search/collection links become /jobs/view/<id>."""
    job_id = linkedin_job_id(url)
    return f"https://www.linkedin.com/jobs/view/{job_id}" if job_id else url


async def fetch_job_page(url: str) -> str:
    """Download a job ad page and reduce it to text (schema.org JobPosting data first)."""
    import httpx
    from bs4 import BeautifulSoup

    # LinkedIn blocks normal page fetches (HTTP 999) but serves public ads on its guest endpoint.
    job_id = linkedin_job_id(url)
    fetch_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}" if job_id else url
    url = normalize_job_url(url)

    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en,de;q=0.8"}
    async with httpx.AsyncClient(follow_redirects=True, timeout=30, headers=headers) as client:
        response = await client.get(fetch_url)
    if response.status_code != 200:
        raise ValueError(
            f"The site refused the request (HTTP {response.status_code}) — it probably blocks "
            "automated access. Use 'Paste text' to add the job description instead."
        )

    soup = BeautifulSoup(response.text, "html.parser")
    parts = [f"Source URL: {url}"]
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data])
        parts += [
            json.dumps(item, ensure_ascii=False)
            for item in items
            if isinstance(item, dict) and item.get("@type") == "JobPosting"
        ]
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    parts.append(re.sub(r"\n\s*\n+", "\n\n", main.get_text("\n", strip=True)))

    text = "\n\n".join(parts)[:40_000]
    if len(text) < 400:
        raise ValueError(
            "Could not read the job ad from this page (login wall or JavaScript-only). "
            "Paste the job description instead."
        )
    return text


# --- 3. Extract must-have / nice-to-have requirements --------------------------

EXTRACT_SYSTEM = """You are a precise recruiting analyst. Extract the requirements of a job ad into the given schema.

- company, role, location: as stated in the ad (for agency ads, the hiring agency if the client is unnamed).
- description: the job ad itself as clean markdown, keeping its wording; drop page navigation and unrelated text.
- must_have: everything listed as required (requirements, "your profile", "you have", "must").
- nice_to_have: everything marked as optional ("nice to have", "a plus", "bonus", "ideally").
- Keep each requirement atomic and close to the ad's wording. Include logistics (on-site, language) too.
- responsibilities: what the person will actually do in the role, taken from the role description.
- keywords: the terms a recruiter or ATS would scan for.
- Do not invent anything that is not in the ad."""


async def extract_requirements(state: CvState) -> dict:
    requirements = await structured(EXTRACT_SYSTEM, state.job_text, JobRequirements)
    return {"requirements": requirements}


# --- 4. CV writer sub-agent: map evidence, then write ---------------------------


def load_skill(path: Path = SKILL_PATH) -> str:
    """Return the SKILL.md body (frontmatter stripped) as the sub-agent's system prompt."""
    text = path.read_text(encoding="utf-8")
    return re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.DOTALL).strip()


def _inputs(state: CvState) -> str:
    return (
        "## CV database\n\n"
        f"{state.cv.model_dump_json(indent=1, exclude_none=True)}\n\n"
        "## Job requirements\n\n"
        f"{state.requirements.model_dump_json(indent=1)}"
    )


async def map_requirements(state: CvState) -> dict:
    prompt = (
        f"{_inputs(state)}\n\n"
        "Do **Step 1 only**: map every must-have and nice-to-have requirement to evidence."
    )
    mapping = await structured(load_skill(), prompt, RequirementMapping)
    return {"mapping": mapping}


async def write_cv(state: CvState) -> dict:
    prompt = (
        f"{_inputs(state)}\n\n"
        "## Requirement mapping (from Step 1)\n\n"
        f"{state.mapping.model_dump_json(indent=1)}\n\n"
        "Do **Step 2**: write the tailored CV — for every role, one item per requirement. "
        "Use the mapping to decide which evidence to feature and recommend."
    )
    tailored = await structured(load_skill(), prompt, TailoredCv)
    _check_traceability(state.cv, tailored)
    return {"tailored_cv": tailored}


def _check_traceability(cv: CvDatabase, tailored: TailoredCv) -> None:
    role_ids = {r.id for r in cv.roles}
    highlight_ids = {h.id for r in cv.roles for h in r.highlights}
    for role in tailored.roles:
        if role.role_id not in role_ids:
            print(f"warning: writer referenced unknown role {role.role_id}")
        for item in role.items:
            if unknown := set(item.source_ids) - highlight_ids:
                print(f"warning: bullet cites unknown sources {sorted(unknown)}: {item.bullet}")


# --- Clarification (called from the UI, same sub-agent skill) ------------------


def _bullet_context(cv: CvDatabase, requirements: JobRequirements, role_id: str, requirement_id: str, bullet: str | None) -> str:
    role = next(r for r in cv.roles if r.id == role_id)
    requirement = next(
        r for r in requirements.must_have + requirements.nice_to_have if r.id == requirement_id
    )
    return (
        f"## Job\n\n{requirements.role} at {requirements.company}\n\n"
        f"## Requirement\n\n{requirement.model_dump_json()}\n\n"
        f"## Role (CV database)\n\n{role.model_dump_json(indent=1, exclude_none=True)}\n\n"
        f"## Current candidate bullet\n\n{bullet or '(none — no evidence found in this role)'}"
    )


def split_bullets(text: str) -> list[str]:
    """A line starting with '-' starts a new bullet; other lines continue the current one."""
    bullets: list[str] = []
    for line in (line.strip() for line in text.splitlines()):
        if not line:
            continue
        if BULLET_START.match(line) or not bullets:
            bullets.append(BULLET_START.sub("", line))
        else:
            bullets[-1] += f" {line}"
    return [b for b in bullets if b]


def _role_heading(role: Role) -> str:
    employer = format_employer(role)
    return f"## {role.start} – {role.end} · {role.title}" + (f" · {employer}" if employer else "")


def attach_clarifications(cv: CvDatabase, markdown: str) -> None:
    """Add every logged answer as a `clarified` highlight of its role (matched by start date)."""
    roles = {r.start: r for r in cv.roles}
    for heading, body in _split(markdown, "## ").items():
        role = roles.get(heading.split(" ", 1)[0])
        if not role:
            print(f"warning: {CLARIFICATIONS_FILE}: no role starts at {heading!r}")
            continue
        question, n = None, 0
        for line in body.splitlines():
            if m := QUESTION.match(line):
                question = m.group(1).strip()
            elif (m := FACT.match(line)) and question:
                n += 1
                role.highlights.append(
                    Highlight(
                        id=f"{role.id}.c{n}",
                        theme=f"Clarification: {question}",
                        text=m.group(1).strip(),
                        clarified=True,
                    )
                )


def log_clarification(cv_path: Path, role: Role, heading: str, answers: list[dict[str, str]]) -> None:
    """Append the answered questions under the role's section of clarifications.md."""
    entries = []
    for answer in answers:
        if facts := split_bullets(answer.get("answer") or ""):
            question = " ".join(answer["question"].split())
            entries.append(f"- **Q:** {question}\n" + "".join(f"  - {fact}\n" for fact in facts))
    log = cv_path.with_name(CLARIFICATIONS_FILE)
    text = log.read_text(encoding="utf-8") if log.exists() else CLARIFICATIONS_HEADER
    section = re.search(rf"^## {re.escape(role.start)} .*?(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    entries = [e for e in entries if not section or e not in section.group(0)]  # same answer twice
    if not entries:
        return
    block = f"### {heading}\n\n{''.join(entries)}\n"
    if section:
        body = section.group(0).rstrip("\n") + "\n\n"
        text = text[: section.start()] + body + block + text[section.end() :]
    else:
        text = text.rstrip("\n") + f"\n\n{_role_heading(role)}\n\n{block}"
    log.write_text(text.rstrip("\n") + "\n", encoding="utf-8")


async def clarifying_questions(
    cv: CvDatabase, requirements: JobRequirements, role_id: str, requirement_id: str, bullet: str | None
) -> list[str]:
    prompt = f"{_bullet_context(cv, requirements, role_id, requirement_id, bullet)}\n\nDo **Step 3**."
    result = await structured(load_skill(), prompt, ClarifyingQuestions)
    return result.questions


async def refine_bullet(
    cv: CvDatabase,
    requirements: JobRequirements,
    role_id: str,
    requirement_id: str,
    bullet: str | None,
    answers: list[dict[str, str]],
) -> RefinedBullet:
    qa = "\n".join(f"- Q: {a['question']}\n  A: {a.get('answer') or '(no answer)'}" for a in answers)
    prompt = (
        f"{_bullet_context(cv, requirements, role_id, requirement_id, bullet)}\n\n"
        f"## Candidate's answers\n\n{qa}\n\nDo **Step 4**."
    )
    return await structured(load_skill(), prompt, RefinedBullet)


# --- 5. Render markdown --------------------------------------------------------


def render_cv(state: CvState) -> dict:
    slug = cv_slug(state.requirements)
    state.output_dir.mkdir(parents=True, exist_ok=True)
    recommended = {
        role.role_id: [i.bullet for i in role.items if i.bullet and i.recommended]
        for role in state.tailored_cv.roles
    }
    cv_path = state.output_dir / f"{slug}-cv.md"
    cv_path.write_text(cv_markdown(state.cv, state.tailored_cv, recommended), encoding="utf-8")
    (state.output_dir / f"{slug}-match.md").write_text(_match_markdown(state), encoding="utf-8")
    return {"output_path": cv_path}


def cv_slug(requirements: JobRequirements) -> str:
    return re.sub(r"[^a-z0-9]+", "-", f"{requirements.company} {requirements.role}".lower()).strip("-")


def format_period(role: Role) -> str:
    return f"{_period(role.start)} – {_period(role.end)}"


def baseline_bullets(role: Role) -> list[str]:
    """The role's first complete highlights from the CV database, so no period renders empty."""
    return [h.text for h in role.highlights if not h.incomplete and not h.clarified][:BASELINE_BULLETS]


def role_bullets(role: Role, bullets: dict[str, list[str]]) -> list[str]:
    """The role's final bullets: selected texts split on '-' lines, else the baseline."""
    texts = bullets.get(role.id) or baseline_bullets(role)
    return list(dict.fromkeys(b for text in texts for b in split_bullets(text)))


def format_employer(role: Role) -> str:
    employer = role.company or ""
    if role.customer:
        employer = f"{employer} (client: {role.customer})" if employer else role.customer
    return employer


def _period(value: str) -> str:
    if not value or value.lower() == "present":
        return "today"
    year, _, month = value.partition("-")
    return f"{month}/{year[2:]}" if month else year


def _birthday(value: str | None) -> str | None:
    try:
        return f"{date.fromisoformat(value):%-d. %B %Y}"
    except (TypeError, ValueError):
        return value


def cv_markdown(cv: CvDatabase, tailored: TailoredCv, bullets: dict[str, list[str]]) -> str:
    """Render the final CV; `bullets` maps role_id -> the bullet texts to include."""
    contact, personal = cv.contact, cv.personal
    personal_line = " · ".join(
        filter(
            None,
            [
                _birthday(personal.get("Date of Birth")),
                ", ".join(filter(None, [personal.get("Nationality"), personal.get("Work Permit")])),
                personal.get("Driving License") and f"Driving License: {personal['Driving License']}",
                personal.get("Availability"),
            ],
        )
    )
    lines = [
        "# Curriculum Vitae",
        "",
        f"**{cv.name}** — {tailored.headline}",
        "",
        "## Personal Data",
        "",
        f"{contact.get('Address', '')}  ",
        " · ".join(filter(None, [contact.get(k) for k in ("Phone", "Email", "Portfolio", "LinkedIn")]))
        + "  ",
        personal_line,
        "",
        "## Value Proposition",
        "",
        "### My Contribution",
        "",
        tailored.my_contribution,
        "",
        "### My Profile",
        "",
        *[f"- {item}" for item in tailored.my_profile],
        "",
        "## Business Experience",
        "",
    ]
    titles = {r.role_id: r.title for r in tailored.roles}
    for role in cv.roles:  # every role, so the timeline has no gaps
        employer = format_employer(role)
        lines += [
            f"### {format_period(role)} · {titles.get(role.id, role.title)}",
            "",
            f"*{employer}*" if employer else "",
            "",
            *[f"- {text}" for text in role_bullets(role, bullets)],
            "",
        ]
    lines += ["## Core Skills", "", " · ".join(tailored.core_skills), ""]
    if cv.certifications:
        lines += ["## Professional Development", ""]
        for cert in cv.certifications:
            details = ", ".join(filter(None, [cert.issuer, cert.status]))
            lines.append(f"- {cert.name}" + (f" — {details}" if details else ""))
        lines.append("")
    if cv.education:
        lines += ["## Education", ""]
        for edu in cv.education:
            years = " – ".join(filter(None, [edu.start_year, edu.end_year]))
            lines.append(f"- {years} · {', '.join(filter(None, [edu.field, edu.institution]))}")
        lines.append("")
    if cv.interests:
        lines += ["## Interests", "", ", ".join(cv.interests), ""]
    return "\n".join(lines)


def _match_markdown(state: CvState) -> str:
    req = state.requirements
    matches = {m.requirement_id: m for m in state.mapping.matches}
    lines = [
        f"# Requirement match — {req.role}, {req.company}",
        "",
        "| Id | Requirement | Match | Evidence | Rationale |",
        "|----|-------------|-------|----------|-----------|",
    ]
    for r in req.must_have + req.nice_to_have:
        m = matches.get(r.id)
        lines.append(
            f"| {r.id} | {r.text} | {m.strength if m else '—'} | "
            f"{', '.join(m.evidence_ids) if m else ''} | {m.rationale if m else ''} |"
        )
    return "\n".join(lines) + "\n"
