"""LLM Race CI scope selection and baseline public-content checks.

Documentation fast paths only affect expensive Python/TypeScript builds. All
changes still pass tracked-file privacy, link and full-history secret checks.
Unknown ref/event/diff input selects full engineering, never a fast path.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
HEX = re.compile(r"^[0-9a-fA-F]{40}$")
DOC_FILES = frozenset({
    "README.md",
    "DESIGN.md",
    "CONTRIBUTING.md",
    "data-pipeline/README.md",
    "mcp-server/README.md",
    "web/README.md",
})
BLOCKED_PARTS = frozenset({"node_modules", ".git", ".venv", "dist", "__pycache__", "secrets"})
BLOCKED_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx", ".p8", ".kdbx"})
PRIVATE_PATTERNS = {
    "local-windows-user-path": re.compile(r"[A-Za-z]:[/\\](?:Users|Works)[/\\]", re.I),
    "private-conversation": re.compile(r"(?:chatgpt\.com/c/|chatgpt-" r"conversation:)", re.I),
    "cn-phone": re.compile(r"(?<![A-Za-z0-9])1[3-9][0-9]{9}(?![A-Za-z0-9])"),
    "cn-national-id": re.compile(r"(?<![A-Za-z0-9])[1-9][0-9]{5}(?:19|20)[0-9]{2}[01][0-9][0-3][0-9][0-9]{3}[0-9Xx](?![A-Za-z0-9])"),
}
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def classify(changes: list[tuple[str, str]] | None) -> bool:
    if not changes:
        return False
    return all(status == "M" and path in DOC_FILES for status, path in changes)


def list_changes(event: str, head: str, before: str, base: str, cwd: Path = ROOT) -> list[tuple[str, str]] | None:
    if event not in ("push", "pull_request") or not HEX.fullmatch(head):
        return None
    start = base if event == "pull_request" else before
    if not HEX.fullmatch(start) or start == "0" * 40:
        return None
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", start, head],
                              cwd=cwd, capture_output=True, check=False)
    if ancestor.returncode != 0:
        return None
    result = subprocess.run(["git", "diff", "--no-renames", "--name-status", "-z", start, head],
                            cwd=cwd, capture_output=True, check=False)
    if result.returncode != 0:
        return None
    tokens = result.stdout.split(b"\0")
    if tokens[-1:] == [b""]:
        tokens.pop()
    if len(tokens) % 2:
        return None
    try:
        return [(tokens[i].decode("ascii"), tokens[i + 1].decode("utf-8"))
                for i in range(0, len(tokens), 2)]
    except UnicodeDecodeError:
        return None


def tracked_files(cwd: Path = ROOT) -> list[str]:
    result = subprocess.check_output(["git", "ls-files", "--cached", "-z"], cwd=cwd)
    return [part.decode("utf-8") for part in result.split(b"\0") if part]


def audit_tree(cwd: Path = ROOT) -> None:
    errors = []
    files = tracked_files(cwd)
    for rel in files:
        file = cwd / rel
        if file.is_symlink() or not file.is_file():
            errors.append(f"non-regular/symlink tracked file: {rel}")
            continue
        name = file.name.lower()
        if ((name.startswith(".env") and name != ".env.example")
                or file.suffix.lower() in BLOCKED_SUFFIXES
                or set(file.parts) & BLOCKED_PARTS):
            errors.append(f"sensitive tracked path: {rel}")
            continue
        try:
            body = file.read_text(encoding="utf-8")
        except UnicodeError:
            errors.append(f"non-UTF8 tracked file: {rel}")
            continue
        for rule, pattern in PRIVATE_PATTERNS.items():
            if pattern.search(body):
                errors.append(f"{rule} in {rel} (review locally; no raw content printed)")
    if errors:
        raise ValueError("; ".join(errors))
    print(f"Public tracked-tree review passed: {len(files)} files")


def check_docs(cwd: Path = ROOT) -> None:
    errors = []
    docs = [p for p in tracked_files(cwd) if p.lower().endswith(".md")]
    for rel in docs:
        file = cwd / rel
        body = file.read_text(encoding="utf-8")
        for match in LINK.finditer(body):
            target = match.group(1).strip().strip("<>")
            if not target or target.startswith(("#", "mailto:", "http://", "https://")):
                continue
            path = unquote(target.split("#", 1)[0])
            if path and not (file.parent / path).exists():
                errors.append(f"broken local Markdown link: {rel}: {target}")
    if errors:
        raise ValueError("; ".join(errors))
    print(f"Markdown link/UTF-8 checks passed: {len(docs)} files")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", default="")
    parser.add_argument("--head", default="")
    parser.add_argument("--before", default="")
    parser.add_argument("--pr-base", default="")
    parser.add_argument("--github-output", default="")
    parser.add_argument("--audit-tree", action="store_true")
    parser.add_argument("--check-docs", action="store_true")
    args = parser.parse_args()
    try:
        if args.audit_tree:
            audit_tree()
        elif args.check_docs:
            check_docs()
        else:
            if not args.github_output:
                parser.error("--github-output required for classification")
            changes = list_changes(args.event, args.head, args.before, args.pr_base)
            docs_only = classify(changes)
            print(f"CI scope: {'DOCS_ONLY' if docs_only else 'FULL_ENGINEERING'}; changed: {len(changes) if changes is not None else 'unknown'}")
            with Path(args.github_output).open("a", encoding="utf-8") as out:
                out.write(f"docs_only={'true' if docs_only else 'false'}\n")
    except (OSError, UnicodeError, subprocess.SubprocessError, ValueError) as exc:
        print(f"Public check failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
