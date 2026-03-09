#!/usr/bin/env python3
"""Fetch CodeRabbit review comments from a GitHub PR and pipe them to Codex CLI.

Usage:
    # Print formatted prompt (for inspection or manual paste)
    python scripts/coderabbit_to_codex.py 42

    # Pipe directly to Codex with full-auto mode
    python scripts/coderabbit_to_codex.py 42 --run

    # Use a specific repo (defaults to origin remote)
    python scripts/coderabbit_to_codex.py 42 --repo owner/repo --run

Requires:
    - GITHUB_TOKEN env var (with repo/PR read access)
    - Codex CLI installed (`npm i -g @openai/codex`) when using --run
    - OPENAI_API_KEY env var when using --run
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error


def get_repo_from_git() -> str:
    """Derive owner/repo from the git remote 'origin'."""
    try:
        url = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"],
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""

    # SSH: git@github.com:owner/repo.git
    if url.startswith("git@"):
        path = url.split(":", 1)[1]
    # HTTPS: https://github.com/owner/repo.git
    elif "github.com" in url:
        path = url.split("github.com/", 1)[1]
    else:
        return ""

    return path.removesuffix(".git")


def github_api(endpoint: str, token: str) -> list | dict:
    """Make a GET request to the GitHub REST API."""
    url = f"https://api.github.com{endpoint}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def fetch_coderabbit_comments(repo: str, pr_number: int, token: str) -> list[dict]:
    """Fetch all CodeRabbit review comments for a PR."""
    page = 1
    all_comments = []
    while True:
        comments = github_api(
            f"/repos/{repo}/pulls/{pr_number}/comments?per_page=100&page={page}",
            token,
        )
        if not comments:
            break
        all_comments.extend(comments)
        page += 1

    return [
        c for c in all_comments
        if c.get("user", {}).get("login") == "coderabbitai[bot]"
    ]


def build_prompt(comments: list[dict]) -> str:
    """Build a structured Codex prompt from CodeRabbit comments."""
    grouped: dict[str, list[dict]] = {}
    for c in comments:
        path = c.get("path", "unknown")
        grouped.setdefault(path, []).append({
            "line": c.get("original_line") or c.get("line"),
            "body": c.get("body", ""),
            "diff_hunk": c.get("diff_hunk", ""),
        })

    lines = [
        "You are resolving code review feedback. Fix each issue described below.",
        "Only modify the files mentioned. Keep changes minimal and focused.",
        "",
    ]

    for file, file_comments in grouped.items():
        lines.append(f"### File: {file}")
        for fc in file_comments:
            line_num = fc["line"] or "?"
            lines.append(f"- **Line {line_num}**: {fc['body']}")
            if fc["diff_hunk"]:
                lines.append(f"  Context:\n```\n{fc['diff_hunk']}\n```")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch CodeRabbit comments and send them to Codex CLI",
    )
    parser.add_argument("pr_number", type=int, help="Pull request number")
    parser.add_argument(
        "--repo",
        default="",
        help="GitHub repo as owner/repo (default: auto-detect from git remote)",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run Codex CLI with the generated prompt (requires OPENAI_API_KEY)",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Use full-auto approval mode (no confirmations)",
    )
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN environment variable is required.", file=sys.stderr)
        sys.exit(1)

    repo = args.repo or get_repo_from_git()
    if not repo:
        print(
            "Error: Could not detect repo. Pass --repo owner/repo explicitly.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Fetching CodeRabbit comments for {repo}#{args.pr_number}...", file=sys.stderr)
    comments = fetch_coderabbit_comments(repo, args.pr_number, token)

    if not comments:
        print("No CodeRabbit review comments found on this PR.", file=sys.stderr)
        sys.exit(0)

    print(f"Found {len(comments)} CodeRabbit comment(s).", file=sys.stderr)
    prompt = build_prompt(comments)

    if not args.run:
        # Just print the prompt to stdout
        print(prompt)
        return

    # Run Codex CLI
    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable is required for --run.", file=sys.stderr)
        sys.exit(1)

    # Write prompt to temp file to avoid shell escaping issues
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(prompt)
        prompt_file = f.name

    try:
        cmd = ["codex", "--quiet"]
        if args.auto:
            cmd.extend(["--approval-mode", "full-auto"])
        cmd.append(prompt)

        print(f"Running Codex...", file=sys.stderr)
        result = subprocess.run(cmd, check=False)
        sys.exit(result.returncode)
    finally:
        os.unlink(prompt_file)


if __name__ == "__main__":
    main()
