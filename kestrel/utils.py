"""Utility helpers: printing, file helpers, parsing, and verification."""

from __future__ import annotations

import os
import re
import subprocess
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Tuple

from .constants import (
    C,
    STAGES,
    FILE_BLOCK_RE,
    PROJECT_NAME_RE,
    FILES_SECTION_RE,
    FILES_TO_ADD_RE,
    FILES_TO_MODIFY_RE,
    LANG_HINTS,
)

_CPRINT_RECORDER: Callable[[str, str, str, str, bool], None] | None = None


def clear_screen() -> None:
    """Clear the terminal screen in a cross-platform way."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32
            hStdOut = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE

            csbi = ctypes.create_string_buffer(22)
            res = kernel32.GetConsoleScreenBufferInfo(hStdOut, csbi)
            if res:
                import struct

                (
                    _, _, _, _, wattr,
                    left, top, right, bottom,
                    _, _,
                ) = struct.unpack("hhhhHhhhhhh", csbi.raw)
                columns = right - left + 1
                rows = bottom - top + 1

                written = wintypes.DWORD()
                coord = wintypes._COORD(0, 0)
                kernel32.FillConsoleOutputCharacterA(
                    hStdOut, ord(" "), columns * rows, coord, ctypes.byref(written)
                )
                kernel32.FillConsoleOutputAttribute(
                    hStdOut, wattr, columns * rows, coord, ctypes.byref(written)
                )
                kernel32.SetConsoleCursorPosition(hStdOut, coord)
                return
        except Exception:
            pass
        try:
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
        except Exception:
            os.system("cls")
    else:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


def set_cprint_recorder(
    recorder: Callable[[str, str, str, str, bool], None] | None,
) -> None:
    """Install or clear the transcript recorder used by the CLI."""
    global _CPRINT_RECORDER
    _CPRINT_RECORDER = recorder


def cprint(
    text: str,
    color: str = "",
    end: str = "\n",
    flush: bool = False,
    kind: str = "output",
    emit: bool = True,
) -> None:
    if _CPRINT_RECORDER is not None:
        _CPRINT_RECORDER(text, color, end, kind, emit)
    if not emit:
        return
    try:
        sys.stdout.write(f"{color}{text}{C.RESET if color else ''}{end}")
        if flush:
            sys.stdout.flush()
    except UnicodeEncodeError:
        clean = text.encode("ascii", errors="replace").decode("ascii")
        sys.stdout.write(f"{clean}{end}")
        if flush:
            sys.stdout.flush()


def read_interactive_line(
    prompt: str, on_ctrl_o: Callable[[], None] | None = None
) -> str:
    """Read a single line while supporting Ctrl+O toggles on Windows terminals."""
    if os.name != "nt":
        return input(prompt)

    import msvcrt

    sys.stdout.write(prompt)
    sys.stdout.flush()
    buffer: list[str] = []

    while True:
        ch = msvcrt.getwch()

        if ch in ("\r", "\n"):
            sys.stdout.write("\n")
            sys.stdout.flush()
            return "".join(buffer).strip()

        if ch == "\x0f" and on_ctrl_o is not None:
            on_ctrl_o()
            sys.stdout.write(prompt + "".join(buffer))
            sys.stdout.flush()
            continue

        if ch == "\x03":
            raise KeyboardInterrupt

        if ch == "\b":
            if buffer:
                buffer.pop()
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            continue

        if ch in ("\x00", "\xe0"):
            msvcrt.getwch()
            continue

        buffer.append(ch)
        sys.stdout.write(ch)
        sys.stdout.flush()


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
    cprint(f"  {C.DIM}{'─' * 56}{C.RESET}")


def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9\-]", "", s)
    return s.strip("-")


def make_project_dir(projects_base: str, project_name: str) -> str:
    slug = slugify(project_name)
    if not slug:
        raise ValueError(f"invalid project name: {project_name!r}")
    project_path = os.path.join(projects_base, slug)
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


def list_project_files(project_path: str) -> List[str]:
    files: List[str] = []
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


def list_existing_projects(projects_base: str) -> List[str]:
    if not os.path.isdir(projects_base):
        return []
    return sorted(
        d
        for d in os.listdir(projects_base)
        if os.path.isdir(os.path.join(projects_base, d))
    )


def log_stage(project_path: str, stage: str, content: str) -> None:
    log_dir = os.path.join(project_path, ".agent_log")
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    fname = f"{ts}_{stage}.txt"
    with open(os.path.join(log_dir, fname), "w", encoding="utf-8") as f:
        f.write(content)


@dataclass
class VerificationResult:
    """Result of project verification (build/compile check)."""

    ran: bool
    success: bool
    command: str
    output: str


def parse_file_blocks(text: str) -> List[Tuple[str, str]]:
    """Extract ===FILE: ... === blocks from LLM output."""
    out: List[Tuple[str, str]] = []
    for m in FILE_BLOCK_RE.finditer(text):
        path = m.group("path").strip().lstrip("/").replace("\\", "/")
        if ".." in path.split("/"):
            continue
        out.append((path, m.group("content")))
    return out


def extract_project_name(plan: str) -> str:
    """Extract PROJECT NAME from plan."""
    m = PROJECT_NAME_RE.search(plan)
    return m.group(1).strip() if m else "untitled-project"


def extract_planned_files(plan: str) -> List[str]:
    """Extract file list from FILES section in plan."""
    matches: List[str] = []
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


def detect_language(project_path: str, plan: str) -> str:
    """Detect project language from files and plan."""
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
    """Check if command is available."""
    return shutil.which(cmd) is not None


def _run(cmd: list[str], cwd: str, timeout: int = 120) -> tuple[bool, str]:
    """Run a command and return success status and output."""
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
    """Verify project builds successfully."""
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
