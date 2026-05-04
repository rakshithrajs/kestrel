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

import sys

# Ensure UTF-8 encoding on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

from kestrel import main

if __name__ == "__main__":
    main()
