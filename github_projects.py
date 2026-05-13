"""Fetch and summarize Abhishek's public GitHub projects."""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Dict, List


GITHUB_USERNAME = "abhishekraj1305"
GITHUB_REPOS_URL = (
    f"https://api.github.com/users/{GITHUB_USERNAME}/repos?per_page=100&sort=updated"
)
CACHE_PATH = Path(__file__).resolve().parent / "data" / "github_repos_cache.json"
CACHE_TTL_SECONDS = 60 * 60 * 12


def _repo_to_project(repo: Dict) -> Dict:
    return {
        "name": repo.get("name") or "Untitled repository",
        "description": repo.get("description") or "",
        "language": repo.get("language") or "Not specified",
        "url": repo.get("html_url") or "",
        "stars": repo.get("stargazers_count") or 0,
        "updated_at": repo.get("updated_at") or "",
    }


def _load_cache() -> List[Dict]:
    if not CACHE_PATH.exists():
        return []

    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if time.time() - payload.get("fetched_at", 0) > CACHE_TTL_SECONDS:
            return []
        return payload.get("projects", [])
    except Exception:
        return []


def _save_cache(projects: List[Dict]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fetched_at": time.time(), "projects": projects}
    CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def fetch_github_projects(use_cache: bool = True) -> List[Dict]:
    """Fetch public GitHub repos, falling back to the local cache."""
    if use_cache:
        cached = _load_cache()
        if cached:
            return cached

    try:
        request = urllib.request.Request(
            GITHUB_REPOS_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "abhishek-portfolio-chatbot",
            },
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            repos = json.loads(response.read().decode("utf-8"))
        projects = [_repo_to_project(repo) for repo in repos if not repo.get("fork")]
        _save_cache(projects)
        return projects
    except Exception:
        return _load_cache()


def summarize_github_projects(limit: int = 10) -> str:
    projects = fetch_github_projects()
    if not projects:
        return ""

    priority_terms = (
        "ml",
        "machine",
        "data",
        "fraud",
        "ocr",
        "nlp",
        "object",
        "portfolio",
        "scrap",
        "bot",
        "mlops",
    )

    def score(project: Dict) -> tuple:
        text = f"{project['name']} {project['description']}".lower()
        term_score = sum(1 for term in priority_terms if term in text)
        return (-term_score, project.get("updated_at", ""))

    selected = sorted(projects, key=score)[:limit]
    lines = []
    for project in selected:
        description = project["description"] or "public GitHub project"
        language = project["language"]
        lines.append(f"- {project['name']} ({language}): {description}")
    return "\n".join(lines)
