"""
github_client.py
────────────────
Fetches SQL files changed in a GitHub Pull Request.

Parses the PR diff and extracts only .sql file changes
so the agents review actual SQL, not the entire diff noise.

Supports both:
  - Full PR URL: https://github.com/owner/repo/pull/123
  - Direct owner/repo/pull_number input
"""

import os
import re
import requests
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
BASE_URL     = "https://api.github.com"

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept":        "application/vnd.github.v3+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


@dataclass
class PRFile:
    filename: str
    status:   str        # added, modified, removed
    patch:    str        # the actual diff/content
    raw_sql:  str        # extracted SQL lines only


@dataclass
class PRInfo:
    title:       str
    description: str
    author:      str
    files:       list[PRFile]
    pr_url:      str


def parse_pr_url(url: str) -> tuple[str, str, int]:
    """
    Parses a GitHub PR URL into (owner, repo, pull_number).
    Supports: https://github.com/owner/repo/pull/123
    """
    pattern = r"github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    match   = re.search(pattern, url)
    if not match:
        raise ValueError(
            f"Invalid GitHub PR URL: {url}\n"
            "Expected format: https://github.com/owner/repo/pull/123"
        )
    owner, repo, number = match.groups()
    return owner, repo, int(number)


def _extract_sql_from_patch(patch: str) -> str:
    """
    Extracts added/modified lines from a diff patch.
    Strips diff metadata (@@, ---, +++) and keeps only SQL content.
    """
    if not patch:
        return ""

    sql_lines = []
    for line in patch.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            sql_lines.append(line[1:])   # strip the leading +
        elif not line.startswith("-") and not line.startswith("@@") and not line.startswith("\\"):
            sql_lines.append(line)

    return "\n".join(sql_lines).strip()


def fetch_pr(pr_url: str) -> PRInfo:
    """
    Fetches PR metadata and changed SQL files from GitHub API.

    Only processes .sql files — skips everything else.
    Raises ValueError if no SQL files are found in the PR.
    """
    if not GITHUB_TOKEN:
        raise ValueError("GITHUB_TOKEN not set in .env")

    owner, repo, pull_number = parse_pr_url(pr_url)

    # Fetch PR metadata
    pr_resp = requests.get(
        f"{BASE_URL}/repos/{owner}/{repo}/pulls/{pull_number}",
        headers=HEADERS,
        timeout=15,
    )
    pr_resp.raise_for_status()
    pr_data = pr_resp.json()

    # Fetch changed files
    files_resp = requests.get(
        f"{BASE_URL}/repos/{owner}/{repo}/pulls/{pull_number}/files",
        headers=HEADERS,
        timeout=15,
    )
    files_resp.raise_for_status()
    files_data = files_resp.json()

    # Filter to SQL files only
    sql_files = []
    for f in files_data:
        filename = f.get("filename", "")
        if not filename.lower().endswith(".sql"):
            continue
        if f.get("status") == "removed":
            continue

        patch   = f.get("patch", "")
        raw_sql = _extract_sql_from_patch(patch)

        if raw_sql:
            sql_files.append(PRFile(
                filename = filename,
                status   = f.get("status", "modified"),
                patch    = patch,
                raw_sql  = raw_sql,
            ))

    if not sql_files:
        raise ValueError(
            f"No SQL files found in PR #{pull_number}. "
            "This reviewer only processes .sql files."
        )

    return PRInfo(
        title       = pr_data.get("title", ""),
        description = pr_data.get("body", "") or "",
        author      = pr_data.get("user", {}).get("login", ""),
        files       = sql_files,
        pr_url      = pr_url,
    )


def combine_sql_from_pr(pr: PRInfo) -> str:
    """
    Combines all SQL from a PR into a single string for agent review.
    Adds file headers so agents can reference specific files.
    """
    parts = []
    for f in pr.files:
        parts.append(f"-- File: {f.filename} ({f.status})")
        parts.append(f.raw_sql)
        parts.append("")
    return "\n".join(parts)