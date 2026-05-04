"""Pipeline: stages and orchestration for building and verifying projects."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Callable, List, Tuple

from .constants import C, QUIPS_CAUGHT, QUIPS_MISSED, QUIPS_CLEAR, GLYPH, quip as _quip
from .utils import (
    cprint,
    divider,
    log_stage,
    stage_header,
    read_interactive_line,
    list_project_files,
    make_project_dir,
    read_project_file,
    slugify,
    write_project_file,
    parse_file_blocks,
    extract_project_name,
    extract_planned_files,
    detect_language,
    verify_project,
    VerificationResult,
)
from .model import stream_model
from .prompts import (
    CLARIFY_SYSTEM,
    PLANNER_SYSTEM,
    PLANNER_EXTEND_SYSTEM,
    CRITIC_SYSTEM,
    BUILDER_FILE_SYSTEM,
    FIXER_SYSTEM,
    REVIEWER_SYSTEM,
)


def quip(pool: list[str]) -> str:
    """Wrapper to use the quip function from constants."""
    return _quip(pool)


def stage_clarify(user_request: str, show_thinking: bool) -> List[str]:
    out = stream_model(
        CLARIFY_SYSTEM,
        f"REQUEST:\n{user_request}",
        label="hover",
        color=C.SKY,
        show_thinking=show_thinking,
    )
    try:
        match = re.search(r"\{.*\}", out, re.DOTALL)
        if not match:
            return []
        data = json.loads(match.group(0))
        questions = data.get("questions", [])
        return [q for q in questions if isinstance(q, str) and q.strip()]
    except json.JSONDecodeError:
        return []


def ask_clarifications(
    questions: List[str], on_ctrl_o: Callable[[], None] | None = None
) -> str:
    if not questions:
        return ""
    cprint(f"\n  {C.AMBER}{C.BOLD}{GLYPH} a few things first:{C.RESET}", "")
    answers = []
    for i, q in enumerate(questions, 1):
        cprint(f"  {C.AMBER}{i}.{C.RESET} {q}", "")
        ans = read_interactive_line(
            f"  {C.DIM}↳{C.RESET} ", on_ctrl_o=on_ctrl_o
        ).strip()
        if ans:
            answers.append(f"Q: {q}\nA: {ans}")
    if not answers:
        return ""
    return "\n\nCLARIFICATIONS:\n" + "\n\n".join(answers)


def stage_plan(
    user_request: str, prior_issues: str = "", show_thinking: bool = True
) -> str:
    user_content = f"USER REQUEST:\n{user_request}"
    if prior_issues:
        user_content += f"\n\nPREVIOUS PLAN ISSUES — fix these:\n{prior_issues}"
    return stream_model(
        PLANNER_SYSTEM,
        user_content,
        label="lock",
        color=C.AMBER,
        show_thinking=show_thinking,
    )


def stage_plan_extend(user_request: str, project_path: str, show_thinking: bool) -> str:
    files = list_project_files(project_path)
    summary = f"PROJECT PATH: {project_path}\nEXISTING FILES:\n"
    summary += "\n".join(f"- {f}" for f in files)
    todo_path = os.path.join(project_path, "TODO.md")
    if os.path.exists(todo_path):
        with open(todo_path, "r", encoding="utf-8") as f:
            summary += f"\n\nPRIOR TODO.md:\n{f.read()[:3000]}"
    user_content = (
        f"CHANGE REQUEST:\n{user_request}\n\nCURRENT PROJECT SUMMARY:\n{summary}"
    )
    return stream_model(
        PLANNER_EXTEND_SYSTEM,
        user_content,
        label="lock·extend",
        color=C.AMBER,
        show_thinking=show_thinking,
    )


def stage_critique(
    user_request: str, plan: str, show_thinking: bool
) -> Tuple[bool, str]:
    user_content = f"USER REQUEST:\n{user_request}\n\nPLAN:\n{plan}"
    out = stream_model(
        CRITIC_SYSTEM,
        user_content,
        label="circle",
        color=C.SLATE,
        show_thinking=show_thinking,
    )
    approved = "VERDICT: APPROVED" in out and "NEEDS_REVISION" not in out
    return approved, out


def stage_build_iterative(
    plan: str, project_path: str, show_thinking: bool
) -> List[str]:
    planned_files = extract_planned_files(plan)
    if not planned_files:
        cprint(
            f"  {C.BLOOD}∙ couldn't read FILES section — diving once for everything.{C.RESET}",
            "",
        )
        return _stage_build_oneshot(plan, project_path, show_thinking)

    cprint(f"  {C.DIM}∙ targets:{C.RESET} {C.RUST}{len(planned_files)}{C.RESET}", "")
    written: List[str] = []
    written_contents: dict[str, str] = {}

    for i, target in enumerate(planned_files, 1):
        divider()
        cprint(
            f"  {C.RUST}◆ {i}/{len(planned_files)}{C.RESET}  "
            f"{C.BOLD}{target}{C.RESET}",
            "",
        )

        context_parts = []
        for path in written:
            content = written_contents[path]
            if len(content) > 4000:
                content = content[:4000] + "\n... [truncated]"
            context_parts.append(f"===EXISTING FILE: {path}===\n{content}\n===END===")
        context = "\n".join(context_parts) if context_parts else "(none yet)"

        all_files_str = "\n".join(f"- {f}" for f in planned_files)

        user_content = (
            f"PLAN:\n{plan}\n\n"
            f"ALL FILES IN PROJECT:\n{all_files_str}\n\n"
            f"FILES ALREADY WRITTEN:\n{context}\n\n"
            f"WRITE THIS FILE NEXT: {target}\n"
            f"Output exactly one ===FILE: {target}=== block."
        )
        out = stream_model(
            BUILDER_FILE_SYSTEM,
            user_content,
            label=f"stoop·{target}",
            color=C.RUST,
            show_thinking=show_thinking,
        )
        log_stage(project_path, f"build_{slugify(target).replace('/', '_')}", out)

        blocks = parse_file_blocks(out)
        if not blocks:
            cprint(
                f"  {C.BLOOD}∙ no block returned for {target}, skipping{C.RESET}", ""
            )
            continue
        chosen = next((b for b in blocks if b[0] == target), blocks[0])
        path, content = chosen
        try:
            write_project_file(project_path, path, content)
            written.append(path)
            written_contents[path] = content
            cprint(
                f"  {C.SAGE}✓{C.RESET} {path} "
                f"{C.DIM}({len(content)} bytes){C.RESET}",
                "",
            )
        except OSError as e:
            cprint(f"  {C.BLOOD}✗{C.RESET} {path}: {e}", "")

    return written


def _stage_build_oneshot(
    plan: str, project_path: str, show_thinking: bool
) -> List[str]:
    out = stream_model(
        BUILDER_FILE_SYSTEM + "\n(You may output multiple file blocks.)",
        f"PLAN:\n{plan}\n\nWrite all files in the FILES section.",
        label="stoop·all",
        color=C.RUST,
        show_thinking=show_thinking,
    )
    log_stage(project_path, "build_oneshot", out)
    blocks = parse_file_blocks(out)
    written = []
    for path, content in blocks:
        try:
            write_project_file(project_path, path, content)
            written.append(path)
            cprint(f"  {C.SAGE}✓{C.RESET} {path}", "")
        except OSError as e:
            cprint(f"  {C.BLOOD}✗{C.RESET} {path}: {e}", "")
    return written


def stage_fix(
    plan: str, project_path: str, error_output: str, show_thinking: bool
) -> List[str]:
    files = list_project_files(project_path)
    parts = [f"PLAN:\n{plan}", "\nFILE TREE:\n" + "\n".join(f"- {f}" for f in files)]
    parts.append("\nFILE CONTENTS:")
    total_size = 0
    for f in files:
        if f.startswith(".agent_log"):
            continue
        try:
            content = read_project_file(project_path, f)
        except (OSError, UnicodeDecodeError):
            continue
        if len(content) > 6000:
            content = content[:6000] + "\n... [truncated]"
        parts.append(f"\n===EXISTING FILE: {f}===\n{content}\n===END===")
        total_size += len(content)
        if total_size > 60000:
            parts.append("\n... [more files omitted due to size]")
            break

    parts.append(f"\nVERIFICATION ERROR:\n{error_output[:8000]}")
    parts.append(
        "\nRewrite ONLY the files that need to change to fix the error. "
        "Output one ===FILE: ... === block per changed file."
    )
    user_content = "\n".join(parts)

    out = stream_model(
        FIXER_SYSTEM,
        user_content,
        label="adjust",
        color=C.PLUM,
        show_thinking=show_thinking,
    )
    log_stage(project_path, "fix", out)
    blocks = parse_file_blocks(out)
    changed = []
    for path, content in blocks:
        try:
            write_project_file(project_path, path, content)
            changed.append(path)
            cprint(
                f"  {C.PLUM}↻{C.RESET} {path} "
                f"{C.DIM}({len(content)} bytes){C.RESET}",
                "",
            )
        except OSError as e:
            cprint(f"  {C.BLOOD}✗{C.RESET} {path}: {e}", "")
    return changed


def stage_review(
    plan: str,
    files: List[str],
    verification: VerificationResult,
    show_thinking: bool,
) -> Tuple[bool, str]:
    file_list = "\n".join(f"- {f}" for f in files)
    verify_str = (
        f"verification command: {verification.command}\n"
        f"ran: {verification.ran}\n"
        f"success: {verification.success}\n"
        f"output:\n{verification.output[:2000]}"
    )
    user_content = (
        f"PLAN:\n{plan}\n\nFILES CREATED:\n{file_list}\n\nVERIFICATION:\n{verify_str}"
    )
    out = stream_model(
        REVIEWER_SYSTEM,
        user_content,
        label="perch",
        color=C.SAGE,
        show_thinking=show_thinking,
    )
    approved = "VERDICT: APPROVED" in out and "NEEDS_FIXES" not in out
    return approved, out


def run_pipeline(
    user_request: str,
    projects_base: str,
    existing_project: str | None = None,
    show_thinking: bool = False,
    on_ctrl_o: Callable[[], None] | None = None,
    max_plan_revisions: int = 2,
    max_fix_rounds: int = 3,
) -> None:
    extending = existing_project is not None

    if not extending:
        stage_header("hover")
        questions = stage_clarify(user_request, show_thinking=show_thinking)
        if questions:
            extras = ask_clarifications(questions, on_ctrl_o=on_ctrl_o)
            if extras:
                user_request = user_request + extras
                cprint(
                    f"\n  {C.SAGE}{GLYPH}{C.RESET} {C.DIM}request annotated.{C.RESET}",
                    "",
                )
        else:
            cprint(
                f"  {C.SAGE}{GLYPH}{C.RESET} {C.DIM}{quip(QUIPS_CLEAR)}{C.RESET}", ""
            )

    stage_header("lock", "extension" if extending else "new build")
    if extending:
        project_path = os.path.join(projects_base, existing_project)  # type: ignore[arg-type]
        plan = stage_plan_extend(
            user_request, project_path, show_thinking=show_thinking
        )
    else:
        project_path = ""
        plan = stage_plan(user_request, show_thinking=show_thinking)

    if not extending:
        stage_header("circle")
        approved, critic_out = stage_critique(
            user_request, plan, show_thinking=show_thinking
        )
        revisions = 0
        while not approved and revisions < max_plan_revisions:
            revisions += 1
            stage_header("lock", f"revision {revisions}")
            plan = stage_plan(
                user_request, prior_issues=critic_out, show_thinking=show_thinking
            )
            stage_header("circle", f"revision {revisions}")
            approved, critic_out = stage_critique(
                user_request, plan, show_thinking=show_thinking
            )
        if not approved:
            cprint(
                f"  {C.BLOOD}!{C.RESET} {C.DIM}circle didn't clear; diving anyway.{C.RESET}",
                "",
            )

    stage_header("stoop", "extending" if extending else "fresh")
    if not extending:
        project_name = extract_project_name(plan)
        project_path = make_project_dir(projects_base, project_name)
        cprint(f"  {C.DIM}∙ nest:{C.RESET} {C.AMBER}{project_path}{C.RESET}", "")
    else:
        cprint(f"  {C.DIM}∙ nest:{C.RESET} {C.AMBER}{project_path}{C.RESET}", "")

    log_stage(project_path, "00_request", user_request)
    log_stage(project_path, "01_plan", plan)

    written = stage_build_iterative(plan, project_path, show_thinking=show_thinking)
    if not written:
        cprint(f"\n  {C.BLOOD}{GLYPH} stoop returned empty. abort.{C.RESET}", "")
        return

    todo_md = (
        f"# Project Notes\n"
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"## Latest request\n{user_request}\n\n"
        f"## Latest plan\n```\n{plan}\n```\n"
    )
    write_project_file(project_path, "TODO.md", todo_md)

    stage_header("strike")
    fix_round = 0
    while True:
        verification = verify_project(project_path, plan)
        if not verification.ran:
            cprint(f"  {C.DIM}∙ skip:{C.RESET} {verification.output}", "")
            break

        cprint(
            f"  {C.DIM}∙ command:{C.RESET} {C.PLUM}{verification.command}{C.RESET}", ""
        )
        if verification.success:
            cprint(f"\n  {C.SAGE}{C.BOLD}{GLYPH} {quip(QUIPS_CAUGHT)}{C.RESET}", "")
            cprint(f"  {C.DIM}{verification.output[:400]}{C.RESET}", "")
            break

        cprint(f"\n  {C.BLOOD}{C.BOLD}{GLYPH} {quip(QUIPS_MISSED)}{C.RESET}", "")
        cprint(f"  {C.DIM}{verification.output[:1200]}{C.RESET}", "")

        if fix_round >= max_fix_rounds:
            cprint(
                f"\n  {C.BLOOD}!{C.RESET} {C.DIM}max passes ({max_fix_rounds}) reached. perching.{C.RESET}",
                "",
            )
            break

        fix_round += 1
        stage_header("adjust", f"pass {fix_round}/{max_fix_rounds}")
        changed = stage_fix(
            plan, project_path, verification.output, show_thinking=show_thinking
        )
        if not changed:
            cprint(
                f"  {C.BLOOD}!{C.RESET} {C.DIM}no changes made. perching.{C.RESET}", ""
            )
            break

    stage_header("perch")
    actual_files = list_project_files(project_path)
    stage_review(plan, actual_files, verification, show_thinking=show_thinking)

    summary_bar = "═" * 60
    cprint(f"\n{summary_bar}", C.SAGE)
    cprint(f"  {GLYPH}  caught.", C.SAGE + C.BOLD)
    cprint(f"{summary_bar}", C.SAGE)
    cprint(
        f"  {C.DIM}project:{C.RESET}  {C.AMBER}{os.path.basename(project_path)}{C.RESET}",
        "",
    )
    cprint(f"  {C.DIM}path:   {C.RESET}  {project_path}", "")
    cprint(
        f"  {C.DIM}flight: {C.RESET}  "
        f"{(C.SAGE + 'verified') if (verification.success and verification.ran) else (C.BLOOD + 'unverified')}{C.RESET}",
        "",
    )
    cprint(f"  {C.DIM}files:  {C.RESET}  {len(actual_files)}", "")
    for f in actual_files[:30]:
        cprint(f"    {C.DIM}·{C.RESET} {f}", "")
    if len(actual_files) > 30:
        cprint(f"    {C.DIM}· … and {len(actual_files) - 30} more{C.RESET}", "")
