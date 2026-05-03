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
- Access to the configured model in main.py

Current model configuration in the code:

 qwen3-coder:480b-cloud

## Quick Start

From the repository root:

 uv sync
 uv run python main.py

If you prefer plain pip in the existing virtual environment:

 pip install -e .
 python main.py

## Commands

- <request> : create a new project from your request
- /list : list projects in the local nest
- /extend <slug> : make the next request modify an existing project
- /help : print command reference
- /exit : quit

## Typical Workflow

1. Start Kestrel
2. Enter a concrete request, for example:

    build a rust cli todo app with sqlite and tests

3. Let Kestrel run through stages (hover, lock, circle, stoop, strike, perch)
4. Inspect generated files under projects/<project-slug>
5. If needed, use /extend <project-slug> and ask for changes

## Repository Layout

- main.py : the full agent pipeline and CLI
- pyproject.toml : package metadata and dependencies
- uv.lock : pinned dependency lockfile
- projects/ : generated and user-extended projects

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
