# Kestrel

Kestrel is a terminal-first coding agent that takes a natural language request and drives a full build loop:

1. Clarify only when needed
2. Plan the implementation
3. Critique the plan
4. Build files iteratively
5. Verify with language-specific checks
6. Patch failures and retry
7. Review and summarize

It is built for polyglot project generation inside the local projects folder, with strong visibility into each stage and automatic debug logs per run.

## Highlights

- Polyglot project generation (Python, Rust, Go, TypeScript, JavaScript, C++, Java)
- Stage-driven pipeline with visible reasoning/output streams
- Deterministic model settings for stable behavior
- File-by-file writing strategy for stronger context retention
- Automatic verification and fix rounds
- Extension mode for modifying existing projects
- Per-project stage logs in .agent_log

## Requirements

- Python 3.12+
- A running Ollama-compatible backend reachable by LangChain Ollama
- The configured model available locally via Ollama

Current model configuration: **qwen3-coder:480b** (defined in `kestrel/constants.py` as `AGENT_FLYING_ON`)

## Quick Start

From the repository root:

 uv sync
 uv run python main.py

If you prefer plain pip in the existing virtual environment:

 pip install -e .
 python main.py

## Commands

- `<request>` : create a new project from your request
- `/list` : list projects in the local nest
- `/extend <slug>` : make the next request modify an existing project
- `/help` : print command reference
- `/exit` : quit
- `Ctrl+O` : toggle streamed thinking on or off during the interactive session

## Typical Workflow

1. Start Kestrel
2. Enter a concrete request, for example:

    build a rust cli todo app with sqlite and tests

3. Let Kestrel run through stages (hover, lock, circle, stoop, strike, perch)
4. Inspect generated files under projects/`project-slug`
5. If needed, use /extend `project-slug` and ask for changes
6. Press Ctrl+O at any prompt to redraw the terminal transcript with thinking hidden or visible

## Repository Layout

```markdown
main.py                     # Entry point (thin wrapper)
pyproject.toml              # Package metadata and dependencies
uv.lock                     # Pinned dependency lockfile
projects/                   # Generated and user-extended projects

kestrel/                    # Main package
├── __init__.py             # Package initialization
├── constants.py            # Centralized configuration (model, colors, stages, regex, language hints)
├── utils.py                # Utility functions (file I/O, parsing, verification, console output)
├── model.py                # LLM interface wrapper (ChatOllama with streaming)
├── prompts.py              # All system prompts for LLM (7 stages: clarify → build → review)
├── pipeline.py             # Core orchestration (stage functions and run_pipeline)
└── cli.py                  # Command-line interface
```

## Architecture

Kestrel follows strict OOP principles with clear separation of concerns:

- **constants.py**: Centralized configuration (model name, colors, stages, regex patterns, language hints). Single source of truth.
- **utils.py**: Pure utility functions for file I/O, parsing LLM output, language detection, build verification, and console formatting.
- **model.py**: LLM interface wrapping ChatOllama with streaming support. Uses `AGENT_FLYING_ON` from constants.
- **prompts.py**: All system prompts for the 7-stage pipeline (clarify, plan, critique, build, fix, review).
- **pipeline.py**: Core orchestration logic. Imports from constants/utils/model/prompts—no duplicate logic.
- **cli.py**: Command-line interface. Simple argument parsing and entry point.
- **main.py**: Thin wrapper that imports and calls the CLI.

This structure ensures:

- No code duplication
- No hardcoded values (all in constants.py)
- Easy testing and maintenance
- Clear data flow and dependencies

## Verification Behavior

Kestrel auto-detects project language and chooses checks such as:

- Rust: cargo check
- Go: go build ./...
- TypeScript: tsc --noEmit
- JavaScript: node --check per file
- Python: py_compile per file
- C++: cmake configure pass

On failure, Kestrel enters fix rounds and rewrites only files that need changes.

## Logs and Traceability

Each generated project contains .agent_log files with timestamped outputs for request, plan, build, and fix stages.

Kestrel also writes a TODO.md in each project containing:

- latest request
- latest plan
