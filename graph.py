"""LangGraph flow: CV database + job ad -> tailored CV.

    load_cv -> load_job -> extract_requirements -> cv_writer -> render_cv
                                                   (sub-agent: map_requirements -> write_cv)
"""

import argparse
import asyncio
from pathlib import Path

from langgraph.graph import END, START, StateGraph

import nodes
from state import CvState


def build_cv_writer():
    """CV writer sub-agent, driven by skills/cv-writer/SKILL.md."""
    builder = StateGraph(CvState)
    builder.add_node("map_requirements", nodes.map_requirements)
    builder.add_node("write_cv", nodes.write_cv)
    builder.add_edge(START, "map_requirements")
    builder.add_edge("map_requirements", "write_cv")
    builder.add_edge("write_cv", END)
    return builder.compile()


def build_graph():
    builder = StateGraph(CvState)
    builder.add_node("load_cv", nodes.load_cv)
    builder.add_node("load_job", nodes.load_job)
    builder.add_node("extract_requirements", nodes.extract_requirements)
    builder.add_node("cv_writer", build_cv_writer())
    builder.add_node("render_cv", nodes.render_cv)
    builder.add_edge(START, "load_cv")
    builder.add_edge("load_cv", "load_job")
    builder.add_edge("load_job", "extract_requirements")
    builder.add_edge("extract_requirements", "cv_writer")
    builder.add_edge("cv_writer", "render_cv")
    builder.add_edge("render_cv", END)
    return builder.compile()


graph = build_graph()


async def run(job_path: Path, cv_path: Path, output_dir: Path) -> CvState:
    result = await graph.ainvoke(CvState(cv_path=cv_path, job_path=job_path, output_dir=output_dir))
    return CvState.model_validate(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Tailor the CV to a job ad.")
    parser.add_argument(
        "job",
        type=Path,
        nargs="?",
        default=Path("output/Zuhlke_Java_FullStack.md"),
        help="Path to the job description markdown file",
    )
    parser.add_argument("--cv", type=Path, default=Path("cv/cv.md"))
    parser.add_argument("--out", type=Path, default=Path("output"))
    args = parser.parse_args()
    if not args.job.is_file():
        parser.error(f"job file not found: {args.job}")

    state = asyncio.run(run(args.job, args.cv, args.out))
    req = state.requirements
    print(f"{req.role} @ {req.company}: {len(req.must_have)} must-have, {len(req.nice_to_have)} nice-to-have")
    for m in state.mapping.matches:
        print(f"  {m.requirement_id:<4} {m.strength:<8} {', '.join(m.evidence_ids)}")
    print(f"CV written to {state.output_path}")


if __name__ == "__main__":
    main()
