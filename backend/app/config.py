"""Central configuration: env vars, paths, constants.

Spec: /backend/app/config.py — "All env vars, paths, constants".
Loads .env from the repo root via python-dotenv. In production (Railway),
env vars are injected by the platform and .env is absent — both work.

Only Step 2 concerns live here for now (Supabase). SEC_USER_AGENT and
ANTHROPIC_API_KEY are read too since .env.example defines them, but they
are consumed in Steps 5 and 10 respectively.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# This file is <repo>/backend/app/config.py → parents[2] is the repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Load .env from repo root if present (no-op in prod where vars are injected)
load_dotenv(REPO_ROOT / ".env")

# --- Supabase (Step 2) ---
SUPABASE_URL: str | None = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY: str | None = os.getenv("SUPABASE_SERVICE_KEY")

# --- SEC EDGAR (consumed in Step 5) ---
SEC_USER_AGENT: str | None = os.getenv("SEC_USER_AGENT")

# --- Anthropic (consumed in Step 10) ---
ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")

# --- Paths ---
DATA_DIR = REPO_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
REPORTS_DIR = REPO_ROOT / "reports"


def require(name: str) -> str:
    """Return the env var value or raise a clear, actionable error."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env at the repo root and fill it in "
            f"(or set it in your deployment environment)."
        )
    return value
