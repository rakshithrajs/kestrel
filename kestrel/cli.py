"""CLI entrypoint for Kestrel — interactive agent shell with banner and colors."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

from .pipeline import run_pipeline
from .model import ModelUnavailableError
from .utils import (
    cprint,
    clear_screen,
    list_project_files,
    read_interactive_line,
    set_cprint_recorder,
)
from .constants import (
    C,
    GLYPH,
    SIGIL,
    AGENT_NAME,
    AGENT_VERSION,
    AGENT_TAGLINE,
    AGENT_FLYING_ON,
)

PROJECTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)


@dataclass
class TranscriptEntry:
    text: str
    color: str
    end: str
    kind: str
    emit: bool


@dataclass
class TranscriptBuffer:
    entries: list[TranscriptEntry] = field(default_factory=list)
    recording_enabled: bool = True

    def record(self, text: str, color: str, end: str, kind: str, emit: bool) -> None:
        if self.recording_enabled:
            self.entries.append(TranscriptEntry(text, color, end, kind, emit))

    def redraw(self, show_thinking: bool) -> None:
        self.recording_enabled = False
        try:
            clear_screen()
            for entry in self.entries:
                if entry.kind == "thinking" and not show_thinking:
                    continue
                try:
                    sys.stdout.write(
                        f"{entry.color}{entry.text}{C.RESET if entry.color else ''}{entry.end}"
                    )
                except UnicodeEncodeError:
                    clean = entry.text.encode("ascii", errors="replace").decode("ascii")
                    sys.stdout.write(f"{clean}{entry.end}")
            sys.stdout.flush()
        finally:
            self.recording_enabled = True


def print_banner() -> None:
    """Print the fancy ASCII kestrel banner with colors."""
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


def print_help() -> None:
    """Print help menu with formatted command list."""
    cprint(f"\n  {C.BOLD}commands{C.RESET}", "")
    help_lines = [
        (f"{C.AMBER}<request>{C.RESET}", "build a new project from scratch"),
        (f"{C.AMBER}/list{C.RESET}", "list all projects in the nest"),
        (
            f"{C.AMBER}/extend {C.DIM}<slug>{C.RESET}",
            "next request modifies that project",
        ),
        (f"{C.AMBER}/help{C.RESET}", "show this list"),
        (f"{C.AMBER}/exit{C.RESET}", "fly home"),
    ]
    for cmd, desc in help_lines:
        cprint(f"  {cmd:<24} {C.DIM}· {desc}{C.RESET}", "")
    cprint("")


def list_existing_projects() -> list[str]:
    """List all existing projects in the nest."""
    if not os.path.isdir(PROJECTS_DIR):
        return []
    return sorted(
        d
        for d in os.listdir(PROJECTS_DIR)
        if os.path.isdir(os.path.join(PROJECTS_DIR, d))
    )


def choose_existing_project(on_ctrl_o=None) -> str | None:
    """Interactive project selector."""
    projects = list_existing_projects()
    if not projects:
        cprint(f"  {C.DIM}nest is empty.{C.RESET}", "")
        return None
    cprint(f"\n  {C.BOLD}{GLYPH} the nest{C.RESET}", "")
    for i, p in enumerate(projects, 1):
        cprint(f"  {C.AMBER}{i:>2}{C.RESET}  {p}", "")
    cprint(f"\n  {C.DIM}↳ number or name (blank to cancel){C.RESET}", "")
    sel = read_interactive_line(f"  {C.DIM}↳{C.RESET} ", on_ctrl_o=on_ctrl_o).strip()
    if not sel:
        return None
    if sel.isdigit():
        idx = int(sel) - 1
        if 0 <= idx < len(projects):
            return projects[idx]
        return None
    return sel if sel in projects else None


def main() -> None:
    """Main interactive CLI loop."""
    transcript = TranscriptBuffer()
    show_thinking = [False]
    pending_extend: str | None = None
    task_count = 0

    def sync_recorder() -> None:
        set_cprint_recorder(transcript.record)

    def toggle_thinking() -> None:
        show_thinking[0] = not show_thinking[0]
        transcript.redraw(show_thinking[0])
        cprint(
            f"  {C.DIM}thinking:{C.RESET} {C.AMBER}{'on' if show_thinking[0] else 'off'}{C.RESET}  {C.DIM}(Ctrl+O toggles){C.RESET}",
            "",
        )

    def prompt_text() -> str:
        label = "kestrel·perch" if pending_extend else "kestrel"
        return f"\n  {C.AMBER}{GLYPH} {label}{C.RESET} {C.DIM}↳{C.RESET} "

    try:
        sync_recorder()
        print_banner()
        cprint(f"  {C.DIM}polyglot · verified builds · iterative writes{C.RESET}", "")
        cprint(
            f"  {C.DIM}thinking hidden by default · press {C.AMBER}Ctrl+O{C.DIM} to toggle{C.RESET}",
            "",
        )
        cprint(
            f"  {C.DIM}wins in {C.SAGE}sage{C.DIM}, misses in {C.BLOOD}blood{C.DIM}.{C.RESET}",
            "",
        )
        print_help()

        while True:
            try:
                user_input = read_interactive_line(
                    prompt_text(), on_ctrl_o=toggle_thinking
                ).strip()

                if not user_input:
                    continue

                cmd = user_input.lower()

                # Exit commands
                if cmd in ("/exit", "exit", "quit", "q"):
                    cprint(
                        f"\n  {C.AMBER}{GLYPH}{C.RESET} {C.DIM}{C.ITAL}flying home.{C.RESET}\n",
                        "",
                    )
                    return

                # Help command
                if cmd in ("/help", "help"):
                    print_help()
                    continue

                # List command
                if cmd == "/list":
                    projects = list_existing_projects()
                    if not projects:
                        cprint(f"  {C.DIM}nest is empty.{C.RESET}", "")
                    else:
                        cprint(f"\n  {C.BOLD}{GLYPH} the nest{C.RESET}", "")
                        for p in projects:
                            cprint(f"    {C.DIM}·{C.RESET} {p}", "")
                    continue

                # Extend command
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
                        chosen = choose_existing_project(on_ctrl_o=toggle_thinking)
                        if chosen:
                            pending_extend = chosen
                            cprint(
                                f"  {C.SAGE}{GLYPH}{C.RESET} {C.DIM}next request extends{C.RESET} "
                                f"{C.AMBER}{chosen}{C.RESET}",
                                "",
                            )
                    continue

                # Regular request or build
                task_count += 1
                cprint(
                    f"\n  {C.RUST}{SIGIL}{C.RESET} {C.DIM}flight #{task_count}{C.RESET}",
                    "",
                )
                if pending_extend:
                    cprint(
                        f"  {C.DIM}extending:{C.RESET} {C.AMBER}{pending_extend}{C.RESET}",
                        "",
                    )
                    project = pending_extend
                    pending_extend = None
                else:
                    project = None

                run_pipeline(
                    user_input,
                    projects_base=PROJECTS_DIR,
                    existing_project=project,
                    show_thinking=show_thinking,
                    on_ctrl_o=toggle_thinking,
                )

            except KeyboardInterrupt:
                cprint(
                    f"\n\n  {C.AMBER}{GLYPH}{C.RESET} {C.DIM}{C.ITAL}flying home.{C.RESET}\n",
                    "",
                )
                return
            except Exception as e:
                if isinstance(e, ModelUnavailableError):
                    cprint(f"\n  {C.BLOOD}✗{C.RESET} {e}", "")
                    cprint(
                        f"  {C.DIM}start Ollama locally, then rerun the request.{C.RESET}",
                        "",
                    )
                    return
                cprint(f"\n  {C.BLOOD}✗ {type(e).__name__}:{C.RESET} {e}", "")
                import traceback

                cprint(f"  {C.DIM}{traceback.format_exc()}{C.RESET}", "")
                continue
    finally:
        set_cprint_recorder(None)


if __name__ == "__main__":
    main()
