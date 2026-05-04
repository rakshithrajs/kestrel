"""Constant values and simple dataclasses for the kestrel agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict
import random
import re

AGENT_NAME = "Kestrel"
AGENT_VERSION = "0.1"
AGENT_TAGLINE = "small bird · long memory · clean builds"
AGENT_FLYING_ON = "kimi-k2.6:cloud"

GLYPH = "▲"
SIGIL = "⟁"


class C:
    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    ITAL = "\033[3m"

    BLACK = "\033[30m"
    GREY = "\033[90m"
    WHITE = "\033[37m"
    BRIGHT_WHITE = "\033[97m"

    AMBER = "\033[38;5;214m"
    RUST = "\033[38;5;130m"
    SLATE = "\033[38;5;67m"
    SAGE = "\033[38;5;108m"
    BLOOD = "\033[38;5;167m"
    SKY = "\033[38;5;110m"
    PLUM = "\033[38;5;139m"
    BONE = "\033[38;5;230m"


@dataclass
class Stage:
    name: str
    verb: str
    glyph: str
    color: str
    log_key: str


STAGES: Dict[str, Stage] = {
    "hover": Stage("HOVER", "reading the request", "◌", C.SKY, "hover"),
    "lock": Stage("LOCK", "drawing up the plan", "◇", C.AMBER, "lock"),
    "circle": Stage("CIRCLE", "checking the line", "◎", C.SLATE, "circle"),
    "stoop": Stage("STOOP", "building, file by file", "◆", C.RUST, "stoop"),
    "strike": Stage("STRIKE", "verifying it flies", "▶", C.PLUM, "strike"),
    "adjust": Stage("ADJUST", "recalibrating", "↻", C.PLUM, "adjust"),
    "perch": Stage("PERCH", "final review", "●", C.SAGE, "perch"),
}

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
    """Return a random quip from the pool."""
    return random.choice(pool)


FILE_BLOCK_RE = re.compile(
    r"===FILE:\s*(?P<path>[^\n=]+?)\s*===\s*\n(?P<content>.*?)\n===END===",
    re.DOTALL,
)
PROJECT_NAME_RE = re.compile(r"^PROJECT NAME:\s*(.+)$", re.MULTILINE)
FILES_SECTION_RE = re.compile(r"^FILES:\s*\n(?P<body>(?:- .*\n?)+)", re.MULTILINE)
FILES_TO_ADD_RE = re.compile(r"^FILES TO ADD:\s*\n(?P<body>(?:- .*\n?)+)", re.MULTILINE)
FILES_TO_MODIFY_RE = re.compile(
    r"^FILES TO MODIFY:\s*\n(?P<body>(?:- .*\n?)+)", re.MULTILINE
)

# Language detection hints
LANG_HINTS = [
    ("rust", ["Cargo.toml", "src/main.rs", "src/lib.rs"], ".rs"),
    ("go", ["go.mod"], ".go"),
    ("typescript", ["tsconfig.json"], ".ts"),
    ("javascript", ["package.json"], ".js"),
    ("python", ["pyproject.toml", "requirements.txt", "setup.py"], ".py"),
    ("cpp", ["CMakeLists.txt"], ".cpp"),
    ("java", ["pom.xml", "build.gradle"], ".java"),
]
