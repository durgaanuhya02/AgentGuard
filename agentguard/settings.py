"""Load settings from the project's .env file into environment variables.

Values already set in the real environment win over .env. Set AGENTGUARD_SKIP_DOTENV=1 to skip
loading (the tests do this, so your real keys never change how the tests run).
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env(path: Path = ENV_FILE) -> None:
    if os.getenv("AGENTGUARD_SKIP_DOTENV") == "1" or not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:  # empty values in .env mean "not set"
            os.environ.setdefault(key.strip(), value)
