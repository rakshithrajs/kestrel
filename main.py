"""
Kestrel — a small bird with a long memory that builds what it is told.

   ┃ hover  · read the request, decide if questions are needed
   ┃ lock   · draw up the plan
   ┃ circle · check the line
   ┃ stoop  · build, file by file
   ┃ strike · verify it flies
   ┃ perch  · final review

It hunts for working code. Sometimes it misses and circles back.
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime

# UTF-8 stdout on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

PROJECTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)


# ═════════════════════════════════════════════════════════════════════════
#   IDENTITY
# ═════════════════════════════════════════════════════════════════════════

AGENT_NAME = "Kestrel"
AGENT_VERSION = "0.1"
AGENT_TAGLINE = "small bird · long memory · clean builds"
AGENT_FLYING_ON = "qwen3-coder:480b"

GLYPH = "▲"  # the bird, in profile
SIGIL = "⟁"  # used in dividers


# ═════════════════════════════════════════════════════════════════════════
#   COLORS — terminal palette
# ═════════════════════════════════════════════════════════════════════════


class C:
    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    ITAL = "\033[3m"

    # base
    BLACK = "\033[30m"
    GREY = "\033[90m"
    WHITE = "\033[37m"
    BRIGHT_WHITE = "\033[97m"

    # accent
    AMBER = "\033[38;5;214m"  # primary brand color — kestrel plumage
    RUST = "\033[38;5;130m"  # darker amber for headers
    SLATE = "\033[38;5;67m"  # cool grey-blue
    SAGE = "\033[38;5;108m"  # success
    BLOOD = "\033[38;5;167m"  # failure
    SKY = "\033[38;5;110m"  # thinking / cool info
    PLUM = "\033[38;5;139m"  # transitions
    BONE = "\033[38;5;230m"  # output text


# fallback to 16-color if the 256-color codes aren't supported
# (most modern terminals support 256, this is just safety)


if sys.platform == "win32":
    os.system("")  # enable VT100


def cprint(text: str, color: str = "", end: str = "\n", flush: bool = False) -> None:
    try:
        sys.stdout.write(f"{color}{text}{C.RESET if color else ''}{end}")
        if flush:
            sys.stdout.flush()
    except UnicodeEncodeError:
        clean = text.encode("ascii", errors="replace").decode("ascii")
        sys.stdout.write(f"{clean}{end}")
        if flush:
            sys.stdout.flush()


# ═════════════════════════════════════════════════════════════════════════
#   STAGE TABLE — name, glyph, color, log key, flavor lines
# ═════════════════════════════════════════════════════════════════════════


@dataclass
class Stage:
    name: str  # uppercase short name
    verb: str  # in-flight description
    glyph: str  # single char
    color: str  # ANSI sequence
    log_key: str  # filename slug for .agent_log


STAGES = {
    "hover": Stage("HOVER", "reading the request", "◌", C.SKY, "hover"),
    "lock": Stage("LOCK", "drawing up the plan", "◇", C.AMBER, "lock"),
    "circle": Stage("CIRCLE", "checking the line", "◎", C.SLATE, "circle"),
    "stoop": Stage("STOOP", "building, file by file", "◆", C.RUST, "stoop"),
    "strike": Stage("STRIKE", "verifying it flies", "▶", C.PLUM, "strike"),
    "adjust": Stage("ADJUST", "recalibrating", "↻", C.PLUM, "adjust"),
    "perch": Stage("PERCH", "final review", "●", C.SAGE, "perch"),
}


def stage_header(stage_key: str, suffix: str = "") -> None:
    s = STAGES[stage_key]
    bar = "═" * 60
    line2 = f"  {s.glyph}  {s.name}"
    if suffix:
        line2 += f"  {C.DIM}· {suffix}{C.RESET}{s.color}"
    line3 = f"     {C.DIM}{C.ITAL}{s.verb}{C.RESET}"
    cprint(f"\n{bar}", s.color)
    cprint(line2, s.color + C.BOLD)
    cprint(line3)
    cprint(bar, s.color)


def divider() -> None:
    """Thin horizontal rule between sub-events within a stage."""
    cprint(f"  {C.DIM}{'─' * 56}{C.RESET}")


# Bird-flavored status lines (one-shot, not spammed everywhere)
QUIPS_CAUGHT = [
    "build flies clean.",
    "target acquired.",
    "in the talons.",
    "good wind. clean strike.",
]
QUIPS_MISSED = [
    "missed. coming around again.",
    "wind shift. recalculating.",
    "no purchase. another pass.",
    "strike short. circling.",
]
QUIPS_CLEAR = [
    "sky's clear.",
    "no fog. proceeding.",
    "request reads true.",
]


def quip(pool: list[str]) -> str:
    return random.choice(pool)


# ═════════════════════════════════════════════════════════════════════════
#   FILE HELPERS
# ═════════════════════════════════════════════════════════════════════════


def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9\-]", "", s)
    return s.strip("-")


def make_project_dir(project_name: str) -> str:
    slug = slugify(project_name)
    if not slug:
        raise ValueError(f"invalid project name: {project_name!r}")
    project_path = os.path.join(PROJECTS_DIR, slug)
    os.makedirs(project_path, exist_ok=True)
    return project_path


def write_project_file(project_path: str, filepath: str, content: str) -> None:
    full_path = os.path.join(project_path, filepath)
    parent = os.path.dirname(full_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)


def read_project_file(project_path: str, filepath: str) -> str:
    full_path = os.path.join(project_path, filepath)
    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()


def list_project_files(project_path: str) -> list[str]:
    files: list[str] = []
    skip_dirs = {
        ".git",
        "node_modules",
        "target",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".agent_log",
    }
    for root, dirs, filenames in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for filename in filenames:
            rel = os.path.relpath(os.path.join(root, filename), project_path)
            files.append(rel.replace("\\", "/"))
    return sorted(files)


def list_existing_projects() -> list[str]:
    if not os.path.isdir(PROJECTS_DIR):
        return []
    return sorted(
        d
        for d in os.listdir(PROJECTS_DIR)
        if os.path.isdir(os.path.join(PROJECTS_DIR, d))
    )


# ═════════════════════════════════════════════════════════════════════════
#   MODEL
# ═════════════════════════════════════════════════════════════════════════

model = ChatOllama(
    model="qwen3-coder:480b-cloud",
    reasoning=True,
    temperature=0,
)


def stream_model(
    system_prompt: str,
    user_content: str,
    label: str = "",
    color: str = C.AMBER,
    show_thinking: bool = True,
) -> str:
    """Stream the model. Thinking is dim grey, output is bone-white."""
    msgs = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]

    output_parts: list[str] = []
    thinking_open = False
    output_open = False

    for chunk in model.stream(msgs):
        thinking = ""
        if hasattr(chunk, "additional_kwargs") and chunk.additional_kwargs:
            thinking = (
                chunk.additional_kwargs.get("reasoning_content")
                or chunk.additional_kwargs.get("thinking")
                or ""
            )
        if thinking and show_thinking:
            if not thinking_open:
                cprint(f"\n  {C.DIM}{C.ITAL}∴ {label} · thinking{C.RESET}", "")
                thinking_open = True
            cprint(thinking, C.GREY + C.DIM, end="", flush=True)

        text = chunk.content if hasattr(chunk, "content") else ""
        if not isinstance(text, str):
            text = str(text)
        if text:
            if thinking_open and not output_open:
                cprint("")
                cprint(f"  {color}▶ {label}{C.RESET}", "")
                output_open = True
            elif not output_open:
                output_open = True
                if label:
                    cprint(f"  {color}▶ {label}{C.RESET}", "")
            cprint(text, C.BONE, end="", flush=True)
            output_parts.append(text)

    if output_open or thinking_open:
        cprint("")
    return "".join(output_parts)


# ═════════════════════════════════════════════════════════════════════════
#   LOG (debug trail per project)
# ═════════════════════════════════════════════════════════════════════════


def log_stage(project_path: str, stage: str, content: str) -> None:
    log_dir = os.path.join(project_path, ".agent_log")
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    fname = f"{ts}_{stage}.txt"
    with open(os.path.join(log_dir, fname), "w", encoding="utf-8") as f:
        f.write(content)


# ═════════════════════════════════════════════════════════════════════════
#   PROMPTS  (the agent's voice doesn't bleed into the model — these stay
#            focused and serious. The flair is in the UI.)
# ═════════════════════════════════════════════════════════════════════════

CLARIFY_SYSTEM = """\
You analyze a software request and decide whether to ask clarifying questions.

Ask questions ONLY if the request is genuinely ambiguous in a way that would
materially change the implementation (language unspecified for non-obvious case,
auth required vs not, persistence type, scale assumptions, etc.).

Do NOT ask questions just to be thorough. Most requests are clear enough.

OUTPUT FORMAT (JSON, exactly this shape):

If no questions are needed:
{"questions": []}

If questions are needed (max 3, only the most important):
{"questions": ["question 1?", "question 2?"]}

Output the JSON object only. No markdown, no commentary.
"""

PLANNER_SYSTEM = """\
You are a software project planner. Produce a detailed implementation plan
that uses EXACTLY what the user asked for.

HARD RULES:
- Honor the user's choice of LANGUAGE, FRAMEWORK, DATABASE if specified.
  Do NOT swap (Rust stays Rust, FastAPI stays FastAPI, Postgres stays Postgres).
- If the user did NOT specify a language/framework, pick a sensible one and STATE IT.
- Do not invent features the user didn't mention.

OUTPUT FORMAT (use these exact headings, in this order):

PROJECT NAME: <short slug-friendly name>
DESCRIPTION: <one sentence>
LANGUAGE: <e.g. Python 3.11, Rust 1.75+, Go 1.22, TypeScript / Node 20>
FRAMEWORK: <name, or "none / standard library">
DATABASE: <name, or "in-memory", or "none">
CACHE: <name, or "none">
BUILD / PACKAGE MANAGER: <pip+venv | uv | cargo | go modules | npm | pnpm | cmake | gradle | ...>

DEPENDENCIES:
- <pkg/crate> - <purpose>

FEATURES:
- <feature>

DATA MODEL:
- <Type>: <fields>
  (omit if no domain data)

INTERFACE:
- <CLI command / HTTP endpoint / library function>

FILES:
- <relative/path> - <purpose>
  Include manifest file appropriate to language:
    Python -> requirements.txt or pyproject.toml
    Rust   -> Cargo.toml
    Go     -> go.mod
    Node   -> package.json (and tsconfig.json for TS)
    C++    -> CMakeLists.txt
    Java   -> pom.xml or build.gradle
  Always include README.md.

IMPLEMENTATION NOTES:
- <decision>

Output the plan only. No preamble, no code.
"""

PLANNER_EXTEND_SYSTEM = """\
You are a software project planner extending an EXISTING project.

You will receive:
- The user's change request
- A summary of the current project (files and a partial plan if available)

Your job: produce a plan describing what to ADD or CHANGE. Do not re-describe
parts that don't change. Do not invent unrelated changes.

OUTPUT FORMAT:

PROJECT NAME: <existing slug, copy as-is>
CHANGE TYPE: extension
DESCRIPTION: <one sentence describing the change>
LANGUAGE: <existing language - copy from current project>
FRAMEWORK: <existing>

NEW DEPENDENCIES:
- <pkg> - <purpose>
  (or "none")

CHANGES:
- <high-level change>

FILES TO ADD:
- <path> - <purpose>

FILES TO MODIFY:
- <path> - <what changes>

FILES TO REMOVE:
- <path>
  (or "none")

IMPLEMENTATION NOTES:
- <decision>

Output the plan only.
"""

CRITIC_SYSTEM = """\
You are a strict plan reviewer. You will receive the USER REQUEST and the PLAN.

Verify:
1. LANGUAGE matches user's spec (if specified).
2. FRAMEWORK / libraries match (if specified).
3. DATABASE matches (if specified).
4. All user-mentioned features are in the plan.
5. Plan includes appropriate manifest file for the language.
6. DEPENDENCIES, FILES, INTERFACE sections are filled in.

OUTPUT FORMAT (one of these two, exactly):

VERDICT: APPROVED

VERDICT: NEEDS_REVISION
Issues:
- <issue>
Required fixes:
- <fix>

No other text.
"""

BUILDER_FILE_SYSTEM = """\
You are a polyglot software developer. You will be asked to write ONE FILE
of a project. You have:
- The full plan
- The list of files in the project
- The contents of files already written (if any)

Write COMPLETE, RUNNABLE code for the requested file. No "...", no "TODO",
no stubs. Use the language and framework from the plan. Follow idiomatic style.

OUTPUT FORMAT - exactly this, nothing else:

===FILE: <relative/path>===
<full file content, no fences, no commentary>
===END===

Output exactly ONE file block. No prose before or after.
"""

FIXER_SYSTEM = """\
You are a polyglot software developer fixing a build/compile error.

You will receive:
- The plan
- The full project file tree
- The contents of all files
- The error output from the build/compile/typecheck command

Identify which file(s) need to be changed and rewrite ONLY those files.
Output one or more file blocks. Do NOT rewrite files that are correct.

OUTPUT FORMAT - file blocks only:

===FILE: <relative/path>===
<full new content for this file>
===END===
===FILE: <relative/path>===
<full new content for this file>
===END===

No prose before or after the blocks. If you cannot determine the fix,
output a single file block for a file named "FIX_NOTES.md" with your analysis.
"""

REVIEWER_SYSTEM = """\
You are a code reviewer. You will receive the PLAN, list of FILES, and the
build/verification result.

Verify:
1. All files from plan exist.
2. Appropriate manifest file present.
3. README.md exists.
4. Build/verification succeeded (you'll be told).

OUTPUT FORMAT (one of these two, exactly):

VERDICT: APPROVED

VERDICT: NEEDS_FIXES
Missing:
- <file>
Issues:
- <issue>

No other text.
"""


# ═════════════════════════════════════════════════════════════════════════
#   PARSING
# ═════════════════════════════════════════════════════════════════════════

FILE_BLOCK_RE = re.compile(
    r"===FILE:\s*(?P<path>[^\n=]+?)\s*===\s*\n(?P<content>.*?)\n===END===",
    re.DOTALL,
)
PROJECT_NAME_RE = re.compile(r"^PROJECT NAME:\s*(.+)$", re.MULTILINE)
LANGUAGE_RE = re.compile(r"^LANGUAGE:\s*(.+)$", re.MULTILINE)
FILES_SECTION_RE = re.compile(r"^FILES:\s*\n(?P<body>(?:- .*\n?)+)", re.MULTILINE)
FILES_TO_ADD_RE = re.compile(r"^FILES TO ADD:\s*\n(?P<body>(?:- .*\n?)+)", re.MULTILINE)
FILES_TO_MODIFY_RE = re.compile(
    r"^FILES TO MODIFY:\s*\n(?P<body>(?:- .*\n?)+)", re.MULTILINE
)


def parse_file_blocks(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in FILE_BLOCK_RE.finditer(text):
        path = m.group("path").strip().lstrip("/").replace("\\", "/")
        if ".." in path.split("/"):
            continue
        out.append((path, m.group("content")))
    return out


def extract_project_name(plan: str) -> str:
    m = PROJECT_NAME_RE.search(plan)
    return m.group(1).strip() if m else "untitled-project"


def extract_language(plan: str) -> str:
    m = LANGUAGE_RE.search(plan)
    return m.group(1).strip() if m else ""


def extract_planned_files(plan: str) -> list[str]:
    matches: list[str] = []
    for regex in (FILES_SECTION_RE, FILES_TO_ADD_RE, FILES_TO_MODIFY_RE):
        m = regex.search(plan)
        if m:
            for line in m.group("body").splitlines():
                line = line.strip()
                if not line.startswith("-"):
                    continue
                rest = line.lstrip("- ").strip()
                if " - " in rest:
                    path = rest.split(" - ", 1)[0].strip()
                else:
                    path = rest.split()[0] if rest else ""
                path = path.strip().strip("`").rstrip("/")
                if path and path not in matches:
                    matches.append(path)
    return matches


# ═════════════════════════════════════════════════════════════════════════
#   LANGUAGE DETECTION & VERIFICATION
# ═════════════════════════════════════════════════════════════════════════


@dataclass
class VerificationResult:
    ran: bool
    success: bool
    command: str
    output: str


LANG_HINTS = [
    ("rust", ["Cargo.toml", "src/main.rs", "src/lib.rs"], ".rs"),
    ("go", ["go.mod"], ".go"),
    ("typescript", ["tsconfig.json"], ".ts"),
    ("javascript", ["package.json"], ".js"),
    ("python", ["pyproject.toml", "requirements.txt", "setup.py"], ".py"),
    ("cpp", ["CMakeLists.txt"], ".cpp"),
    ("java", ["pom.xml", "build.gradle"], ".java"),
]


def detect_language(project_path: str, plan: str) -> str:
    files = list_project_files(project_path)
    file_set = set(files)

    def has_ext(ext: str) -> bool:
        return any(f.endswith(ext) for f in files)

    for lang, manifests, _ in LANG_HINTS:
        if any(m in file_set for m in manifests):
            return lang

    for lang, _, ext in LANG_HINTS:
        if has_ext(ext):
            return lang

    plan_lower = plan.lower()
    for lang, _, _ in LANG_HINTS:
        if lang in plan_lower:
            return lang
    return "unknown"


def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run(cmd: list[str], cwd: str, timeout: int = 120) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return proc.returncode == 0, out.strip()
    except FileNotFoundError:
        return False, f"[command not found: {cmd[0]}]"
    except subprocess.TimeoutExpired:
        return False, f"[timeout after {timeout}s: {' '.join(cmd)}]"
    except Exception as e:
        return False, f"[error running {' '.join(cmd)}: {e}]"


def verify_project(project_path: str, plan: str) -> VerificationResult:
    lang = detect_language(project_path, plan)
    cprint(f"  {C.DIM}∙ language:{C.RESET} {C.AMBER}{lang}{C.RESET}", "")

    if lang == "rust" and _which("cargo"):
        ok, out = _run(["cargo", "check", "--quiet"], project_path)
        return VerificationResult(True, ok, "cargo check", out)

    if lang == "go" and _which("go"):
        ok, out = _run(["go", "build", "./..."], project_path)
        return VerificationResult(True, ok, "go build ./...", out)

    if lang == "typescript" and _which("npx"):
        if os.path.exists(os.path.join(project_path, "tsconfig.json")):
            ok, out = _run(
                ["npx", "--yes", "tsc", "--noEmit"], project_path, timeout=180
            )
            return VerificationResult(True, ok, "tsc --noEmit", out)

    if lang == "javascript" and _which("node"):
        errors: list[str] = []
        for f in list_project_files(project_path):
            if f.endswith(".js"):
                ok, out = _run(["node", "--check", f], project_path, timeout=20)
                if not ok:
                    errors.append(f"{f}:\n{out}")
        return VerificationResult(
            True,
            len(errors) == 0,
            "node --check (per file)",
            "\n\n".join(errors) if errors else "all files parsed",
        )

    if lang == "python":
        errors: list[str] = []
        py_files = [f for f in list_project_files(project_path) if f.endswith(".py")]
        for f in py_files:
            ok, out = _run(
                [sys.executable, "-m", "py_compile", f], project_path, timeout=20
            )
            if not ok:
                errors.append(f"{f}:\n{out}")
        return VerificationResult(
            True,
            len(errors) == 0,
            "py_compile (per file)",
            "\n\n".join(errors) if errors else f"{len(py_files)} files compiled",
        )

    if lang == "cpp" and _which("cmake"):
        build_dir = os.path.join(project_path, "build")
        os.makedirs(build_dir, exist_ok=True)
        ok, out = _run(["cmake", ".."], build_dir)
        return VerificationResult(True, ok, "cmake configure", out)

    return VerificationResult(
        False,
        True,
        "no verifier available",
        f"No verification tool found for language={lang!r}.",
    )


# ═════════════════════════════════════════════════════════════════════════
#   STAGES
# ═════════════════════════════════════════════════════════════════════════


def stage_clarify(user_request: str) -> list[str]:
    out = stream_model(
        CLARIFY_SYSTEM, f"REQUEST:\n{user_request}", label="hover", color=C.SKY
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


def ask_clarifications(questions: list[str]) -> str:
    if not questions:
        return ""
    cprint(f"\n  {C.AMBER}{C.BOLD}{GLYPH} a few things first:{C.RESET}", "")
    answers = []
    for i, q in enumerate(questions, 1):
        cprint(f"  {C.AMBER}{i}.{C.RESET} {q}", "")
        ans = input(f"  {C.DIM}↳{C.RESET} ").strip()
        if ans:
            answers.append(f"Q: {q}\nA: {ans}")
    if not answers:
        return ""
    return "\n\nCLARIFICATIONS:\n" + "\n\n".join(answers)


def stage_plan(user_request: str, prior_issues: str = "") -> str:
    user_content = f"USER REQUEST:\n{user_request}"
    if prior_issues:
        user_content += f"\n\nPREVIOUS PLAN ISSUES — fix these:\n{prior_issues}"
    return stream_model(PLANNER_SYSTEM, user_content, label="lock", color=C.AMBER)


def stage_plan_extend(user_request: str, project_path: str) -> str:
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
        PLANNER_EXTEND_SYSTEM, user_content, label="lock·extend", color=C.AMBER
    )


def stage_critique(user_request: str, plan: str) -> tuple[bool, str]:
    user_content = f"USER REQUEST:\n{user_request}\n\nPLAN:\n{plan}"
    out = stream_model(CRITIC_SYSTEM, user_content, label="circle", color=C.SLATE)
    approved = "VERDICT: APPROVED" in out and "NEEDS_REVISION" not in out
    return approved, out


def stage_build_iterative(plan: str, project_path: str) -> list[str]:
    planned_files = extract_planned_files(plan)
    if not planned_files:
        cprint(
            f"  {C.BLOOD}∙ couldn't read FILES section — diving once for everything.{C.RESET}",
            "",
        )
        return _stage_build_oneshot(plan, project_path)

    cprint(f"  {C.DIM}∙ targets:{C.RESET} {C.RUST}{len(planned_files)}{C.RESET}", "")
    written: list[str] = []
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
            BUILDER_FILE_SYSTEM, user_content, label=f"stoop·{target}", color=C.RUST
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


def _stage_build_oneshot(plan: str, project_path: str) -> list[str]:
    out = stream_model(
        BUILDER_FILE_SYSTEM + "\n(You may output multiple file blocks.)",
        f"PLAN:\n{plan}\n\nWrite all files in the FILES section.",
        label="stoop·all",
        color=C.RUST,
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


def stage_fix(plan: str, project_path: str, error_output: str) -> list[str]:
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

    out = stream_model(FIXER_SYSTEM, user_content, label="adjust", color=C.PLUM)
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
    plan: str, files: list[str], verification: VerificationResult
) -> tuple[bool, str]:
    file_list = "\n".join(f"- {f}" for f in files)
    verify_str = (
        f"verification command: {verification.command}\n"
        f"ran: {verification.ran}\n"
        f"success: {verification.success}\n"
        f"output:\n{verification.output[:2000]}"
    )
    user_content = (
        f"PLAN:\n{plan}\n\nFILES CREATED:\n{file_list}\n\n"
        f"VERIFICATION:\n{verify_str}"
    )
    out = stream_model(REVIEWER_SYSTEM, user_content, label="perch", color=C.SAGE)
    approved = "VERDICT: APPROVED" in out and "NEEDS_FIXES" not in out
    return approved, out


# ═════════════════════════════════════════════════════════════════════════
#   PIPELINE
# ═════════════════════════════════════════════════════════════════════════


def run_pipeline(
    user_request: str,
    existing_project: str | None = None,
    max_plan_revisions: int = 2,
    max_fix_rounds: int = 3,
) -> None:
    extending = existing_project is not None

    # ───── HOVER ─────
    if not extending:
        stage_header("hover")
        questions = stage_clarify(user_request)
        if questions:
            extras = ask_clarifications(questions)
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

    # ───── LOCK ─────
    stage_header("lock", "extension" if extending else "new build")
    if extending:
        project_path = os.path.join(PROJECTS_DIR, existing_project)  # type: ignore[arg-type]
        plan = stage_plan_extend(user_request, project_path)
    else:
        plan = stage_plan(user_request)

    # ───── CIRCLE ─────
    if not extending:
        stage_header("circle")
        approved, critic_out = stage_critique(user_request, plan)
        revisions = 0
        while not approved and revisions < max_plan_revisions:
            revisions += 1
            stage_header("lock", f"revision {revisions}")
            plan = stage_plan(user_request, prior_issues=critic_out)
            stage_header("circle", f"revision {revisions}")
            approved, critic_out = stage_critique(user_request, plan)
        if not approved:
            cprint(
                f"  {C.BLOOD}!{C.RESET} {C.DIM}circle didn't clear; diving anyway.{C.RESET}",
                "",
            )

    # ───── STOOP ─────
    stage_header("stoop", "extending" if extending else "fresh")
    if not extending:
        project_name = extract_project_name(plan)
        project_path = make_project_dir(project_name)
        cprint(f"  {C.DIM}∙ nest:{C.RESET} {C.AMBER}{project_path}{C.RESET}", "")
    else:
        cprint(f"  {C.DIM}∙ nest:{C.RESET} {C.AMBER}{project_path}{C.RESET}", "")

    log_stage(project_path, "00_request", user_request)
    log_stage(project_path, "01_plan", plan)

    written = stage_build_iterative(plan, project_path)
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

    # ───── STRIKE ─────
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
        changed = stage_fix(plan, project_path, verification.output)
        if not changed:
            cprint(
                f"  {C.BLOOD}!{C.RESET} {C.DIM}no changes made. perching.{C.RESET}", ""
            )
            break

    # ───── PERCH ─────
    stage_header("perch")
    actual_files = list_project_files(project_path)
    stage_review(plan, actual_files, verification)

    # ───── ROOST ─────
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


# ═════════════════════════════════════════════════════════════════════════
#   BANNER & CLI
# ═════════════════════════════════════════════════════════════════════════


def print_banner() -> None:
    # Two-tone banner: amber bird + grey wordmark
    art = [
        f"        {C.AMBER}▲{C.RESET}",
        f"       {C.AMBER}▲▲▲{C.RESET}        {C.BONE}{C.BOLD}╦╔═ ╔═╗ ╔═╗ ╔╦╗ ╦═╗ ╔═╗ ╦{C.RESET}",
        f"      {C.AMBER}▲▲ ▲▲{C.RESET}       {C.BONE}{C.BOLD}╠╩╗ ║╣  ╚═╗  ║  ╠╦╝ ║╣  ║{C.RESET}",
        f"     {C.AMBER}▲▲   ▲▲{C.RESET}      {C.BONE}{C.BOLD}╩ ╩ ╚═╝ ╚═╝  ╩  ╩╚═ ╚═╝ ╩═╝{C.RESET}",
        f"    {C.AMBER}▲▲     ▲▲{C.RESET}",
        f"   {C.AMBER}▲▲       ▲▲{C.RESET}    {C.DIM}{C.ITAL}{AGENT_TAGLINE}{C.RESET}",
        f"   {C.RUST}═══════════{C.RESET}    {C.DIM}v{AGENT_VERSION} · flying on {C.AMBER}{AGENT_FLYING_ON}{C.RESET}",
    ]
    cprint("")
    for line in art:
        cprint(line)
    cprint("")


HELP_LINES = [
    (f"{C.AMBER}<request>{C.RESET}", "build a new project from scratch"),
    (f"{C.AMBER}/list{C.RESET}", "list all projects in the nest"),
    (f"{C.AMBER}/extend {C.DIM}<slug>{C.RESET}", "next request modifies that project"),
    (f"{C.AMBER}/help{C.RESET}", "show this list"),
    (f"{C.AMBER}/exit{C.RESET}", "fly home"),
]


def print_help() -> None:
    cprint(f"\n  {C.BOLD}commands{C.RESET}", "")
    for cmd, desc in HELP_LINES:
        cprint(f"  {cmd:<24} {C.DIM}· {desc}{C.RESET}", "")
    cprint("")


def choose_existing_project() -> str | None:
    projects = list_existing_projects()
    if not projects:
        cprint(f"  {C.DIM}nest is empty.{C.RESET}", "")
        return None
    cprint(f"\n  {C.BOLD}{GLYPH} the nest{C.RESET}", "")
    for i, p in enumerate(projects, 1):
        cprint(f"  {C.AMBER}{i:>2}{C.RESET}  {p}", "")
    cprint(f"\n  {C.DIM}↳ number or name (blank to cancel){C.RESET}", "")
    sel = input(f"  {C.DIM}↳{C.RESET} ").strip()
    if not sel:
        return None
    if sel.isdigit():
        idx = int(sel) - 1
        if 0 <= idx < len(projects):
            return projects[idx]
        return None
    return sel if sel in projects else None


def main() -> None:
    print_banner()
    cprint(f"  {C.DIM}polyglot · verified builds · iterative writes{C.RESET}", "")
    cprint(
        f"  {C.DIM}thinking shows in {C.GREY}grey{C.DIM}, output in white,{C.RESET}", ""
    )
    cprint(
        f"  {C.DIM}wins in {C.SAGE}sage{C.DIM}, misses in {C.BLOOD}blood{C.DIM}.{C.RESET}",
        "",
    )
    print_help()

    pending_extend: str | None = None
    task_count = 0

    while True:
        try:
            label = "kestrel·perch" if pending_extend else "kestrel"
            user_input = input(
                f"\n  {C.AMBER}{GLYPH} {label}{C.RESET} {C.DIM}↳{C.RESET} "
            ).strip()

            if not user_input:
                continue

            cmd = user_input.lower()
            if cmd in ("/exit", "exit", "quit", "q"):
                cprint(
                    f"\n  {C.AMBER}{GLYPH}{C.RESET} {C.DIM}{C.ITAL}flying home.{C.RESET}\n",
                    "",
                )
                return
            if cmd in ("/help", "help"):
                print_help()
                continue
            if cmd == "/list":
                projects = list_existing_projects()
                if not projects:
                    cprint(f"  {C.DIM}nest is empty.{C.RESET}", "")
                else:
                    cprint(f"\n  {C.BOLD}{GLYPH} the nest{C.RESET}", "")
                    for p in projects:
                        cprint(f"    {C.DIM}·{C.RESET} {p}", "")
                continue
            if cmd.startswith("/extend"):
                parts = user_input.split(maxsplit=1)
                if len(parts) == 2:
                    candidate = parts[1].strip()
                    if candidate in list_existing_projects():
                        pending_extend = candidate
                        cprint(
                            f"  {C.SAGE}{GLYPH}{C.RESET} {C.DIM}next request extends{C.RESET} "
                            f"{C.AMBER}{candidate}{C.RESET}",
                            "",
                        )
                    else:
                        cprint(
                            f"  {C.BLOOD}!{C.RESET} {C.DIM}no such project: {candidate}{C.RESET}",
                            "",
                        )
                else:
                    chosen = choose_existing_project()
                    if chosen:
                        pending_extend = chosen
                        cprint(
                            f"  {C.SAGE}{GLYPH}{C.RESET} {C.DIM}next request extends{C.RESET} "
                            f"{C.AMBER}{chosen}{C.RESET}",
                            "",
                        )
                continue

            task_count += 1
            cprint(
                f"\n  {C.RUST}{SIGIL}{C.RESET} {C.DIM}flight #{task_count}{C.RESET}", ""
            )
            if pending_extend:
                cprint(
                    f"  {C.DIM}extending:{C.RESET} {C.AMBER}{pending_extend}{C.RESET}",
                    "",
                )
            cprint(f"  {C.DIM}request: {C.RESET}{user_input}", "")

            run_pipeline(user_input, existing_project=pending_extend)
            pending_extend = None

        except KeyboardInterrupt:
            cprint(
                f"\n\n  {C.AMBER}{GLYPH}{C.RESET} {C.DIM}{C.ITAL}flying home.{C.RESET}\n",
                "",
            )
            return
        except Exception as e:
            cprint(f"\n  {C.BLOOD}✗ {type(e).__name__}:{C.RESET} {e}", "")
            import traceback

            cprint(f"  {C.DIM}{traceback.format_exc()}{C.RESET}", "")
            continue


if __name__ == "__main__":
    main()
