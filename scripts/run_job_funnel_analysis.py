#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_search_assistant.analyzer.job_packet import load_text_input
from job_search_assistant.analyzer.runner import run_analysis, save_outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Job Funnel / Resume Fit Analyst on one JD.")
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--jd-file", help="Path to a file containing the raw JD text.")
    input_group.add_argument("--jd-text", help="Raw JD text.")
    parser.add_argument("--company-name", help="Optional company name override.")
    parser.add_argument("--job-url", help="Optional job posting URL.")
    parser.add_argument("--special-questions-file", help="Optional file containing the main questions for this run.")
    parser.add_argument("--notes-file", help="Optional file with extra notes or context.")
    parser.add_argument("--image", action="append", default=[], help="Optional screenshot image path. Repeatable.")
    parser.add_argument(
        "--profile-stack",
        default="profiles/default_stack.json",
        help="Profile stack JSON file. Defaults to profiles/default_stack.json.",
    )
    parser.add_argument(
        "--profile-fragment",
        action="append",
        default=[],
        help="Extra profile fragment to append on top of the stack. Repeatable.",
    )
    parser.add_argument("--analysis-mode", choices=["quick", "full"], default="quick")
    parser.add_argument("--provider", choices=["auto", "openai", "mock"], default="auto")
    parser.add_argument("--model", default="gpt-5.2", help="Model name for the OpenAI Responses API.")
    parser.add_argument(
        "--enable-web-search",
        action="store_true",
        help="Allow the model to use web search for evidence collection when the provider supports it.",
    )
    parser.add_argument("--markdown-output", help="Optional output path for the rendered markdown report.")
    parser.add_argument("--json-output", help="Optional output path for the raw JSON payload.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    jd_text = args.jd_text or load_text_input(args.jd_file)
    special_questions = load_text_input(args.special_questions_file) if args.special_questions_file else None
    notes = load_text_input(args.notes_file) if args.notes_file else None

    result = run_analysis(
        repo_root=ROOT,
        jd_text=jd_text,
        profile_stack_path=args.profile_stack,
        extra_profile_fragments=args.profile_fragment,
        provider_name=args.provider,
        model=args.model,
        analysis_mode=args.analysis_mode,
        enable_web_search=args.enable_web_search,
        company_name=args.company_name,
        job_url=args.job_url,
        special_questions=special_questions,
        image_paths=args.image,
        notes=notes,
    )
    save_outputs(result, args.markdown_output, args.json_output)
    print(result.markdown)


if __name__ == "__main__":
    main()
