from __future__ import annotations

import os

def resolve_version(cli_version: str | None) -> str:
    if cli_version and cli_version.strip():
        return cli_version.strip()
    git_sha = os.getenv("GIT_SHA")
    return git_sha if git_sha else "dev"
