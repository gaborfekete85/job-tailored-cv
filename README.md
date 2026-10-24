# Job-tailored CV

Tailors `cv/cv.md` (the full experience database) to one job ad with a LangGraph flow and a CV-writer sub-agent (`skills/cv-writer/SKILL.md`).

## Setup

```bash
uv sync
cp .env.example .env          # ENV=local uses your Claude subscription
cd frontend && bun install
```

## Run the UI

Two terminals:

```bash
uv run uvicorn api:app --reload --port 8432    # backend
cd frontend && bun run dev                     # http://localhost:5173
```

Or a single process: `cd frontend && bun run build`, then `uv run uvicorn api:app --port 8432` and open http://localhost:8432.

## Run from the CLI

```bash
uv run graph.py jobs/Job-Rapidata.md
```

## Tests

```bash
uv run pytest
```

## Data

| Where | What |
|---|---|
| `data/cv.db` | SQLite: jobs, status history, analyses, per-role bullet candidates, clarifications, exported CV versions |
| `output/*-cv.md` | Exported CVs (Markdown) |
| `output/*-match.md` | Requirement → evidence match report (from the analysis run) |
