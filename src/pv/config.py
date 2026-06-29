"""Configuration loading and provenance.

The frozen scientific parameters are in PREREGISTRATION.md; this module loads the
operational config.yaml and captures run provenance (git sha, UTC timestamps) so every
run directory is reproducible.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"


def utc_now_iso() -> str:
    """UTC timestamp, ISO-8601 with 'Z'. All records get one (plan §3, §5)."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_sha(short: bool = False) -> str | None:
    """Current git commit, for run provenance. None if not a git repo."""
    cmd = ["git", "rev-parse", "--short" if short else "HEAD"]
    try:
        out = subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def git_is_dirty() -> bool | None:
    """True if the working tree has uncommitted changes. None if not a git repo."""
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return bool(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load config.yaml as a plain dict."""
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(p, "r") as f:
        return yaml.safe_load(f)


def require_api_key() -> str:
    """Fetch the OpenRouter key from env. Never hardcode; never log its value."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Export it before running:\n"
            "  export OPENROUTER_API_KEY='sk-or-...'\n"
            "(The harness reads the key only from this env var and never logs it.)"
        )
    return key


@dataclasses.dataclass(frozen=True)
class RunProvenance:
    """Captured once per run; written into the run dir for reproducibility."""

    started_utc: str
    git_sha: str | None
    git_short_sha: str | None
    git_dirty: bool | None
    config_path: str

    @classmethod
    def capture(cls, config_path: str | Path) -> "RunProvenance":
        return cls(
            started_utc=utc_now_iso(),
            git_sha=git_sha(),
            git_short_sha=git_sha(short=True),
            git_dirty=git_is_dirty(),
            config_path=str(config_path),
        )

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)
