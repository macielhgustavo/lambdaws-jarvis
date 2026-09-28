"""Deterministic workstation context collectors for LambdaWS."""

from __future__ import annotations

import os
import platform
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any


def _run(command: list[str], *, timeout: float = 3.0) -> str | None:
    try:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return output or None


def _first_available(commands: list[list[str]]) -> str | None:
    for command in commands:
        if shutil.which(command[0]) is None:
            continue
        output = _run(command)
        if output:
            return output
    return None


def active_window() -> dict[str, Any]:
    """Return active-window information without relying on an LLM."""
    if shutil.which("kdotool"):
        window_id = _run(["kdotool", "getactivewindow"])
        title = _run(["kdotool", "getactivewindow", "getwindowname"])
        if window_id or title:
            return {
                "source": "kdotool",
                "id": window_id,
                "title": title,
            }

    if shutil.which("xdotool"):
        window_id = _run(["xdotool", "getactivewindow"])
        title = None
        if window_id:
            title = _run(["xdotool", "getwindowname", window_id])
        if window_id or title:
            return {
                "source": "xdotool",
                "id": window_id,
                "title": title,
            }

    return {"source": None, "available": False}


def kde_context() -> dict[str, Any]:
    result: dict[str, Any] = {
        "desktop_session": os.environ.get("XDG_CURRENT_DESKTOP"),
        "session_type": os.environ.get("XDG_SESSION_TYPE"),
    }

    if shutil.which("qdbus6"):
        support = _run(
            ["qdbus6", "org.kde.KWin", "/KWin", "org.kde.KWin.supportInformation"],
            timeout=4,
        )
        if support:
            result["kwin_available"] = True
            desktop_match = re.search(
                r"(?im)^\s*(?:Current Desktop|currentDesktop)\s*[:=]\s*(.+?)\s*$",
                support,
            )
            if desktop_match:
                result["current_desktop"] = desktop_match.group(1).strip()
            activity_match = re.search(
                r"(?im)^\s*(?:Current Activity|currentActivity)\s*[:=]\s*(.+?)\s*$",
                support,
            )
            if activity_match:
                result["current_activity"] = activity_match.group(1).strip()
        else:
            result["kwin_available"] = False

    return result


def clipboard_preview(limit: int = 1200) -> dict[str, Any]:
    """Read a bounded plaintext preview from the local clipboard."""
    output = _first_available(
        [
            ["wl-paste", "--no-newline", "--type", "text"],
            ["xclip", "-selection", "clipboard", "-o"],
            ["xsel", "--clipboard", "--output"],
        ]
    )
    if output is None:
        return {"available": False}

    text = output[: max(1, min(limit, 5000))]
    return {
        "available": True,
        "content": text,
        "truncated": len(output) > len(text),
        "untrusted_external_content": True,
    }


def media_context() -> dict[str, Any]:
    if shutil.which("playerctl") is None:
        return {"available": False}

    status = _run(["playerctl", "status"])
    metadata = _run(
        [
            "playerctl",
            "metadata",
            "--format",
            "{{playerName}}\t{{status}}\t{{artist}}\t{{title}}\t{{album}}",
        ]
    )
    if not status and not metadata:
        return {"available": False}

    result: dict[str, Any] = {"available": True, "status": status}
    if metadata:
        parts = metadata.split("\t")
        labels = ["player", "status_detail", "artist", "title", "album"]
        result.update(
            {
                label: value
                for label, value in zip(labels, parts)
                if value
            }
        )
    return result


def process_context() -> dict[str, Any]:
    interesting = {
        "ollama": ["pgrep", "-a", "ollama"],
        "vscode": ["pgrep", "-a", "-f", "code|visual-studio-code"],
        "firefox": ["pgrep", "-a", "firefox"],
        "konsole": ["pgrep", "-a", "konsole"],
        "python": ["pgrep", "-a", "-f", "python.*jarvis"],
    }
    found: dict[str, list[str]] = {}
    for name, command in interesting.items():
        output = _run(command)
        if output:
            found[name] = output.splitlines()[:12]
    return found


def user_services() -> dict[str, Any]:
    if shutil.which("systemctl") is None:
        return {"available": False}

    failed = _run(
        [
            "systemctl",
            "--user",
            "--failed",
            "--no-legend",
            "--plain",
        ],
        timeout=5,
    )
    jarvis = _run(
        [
            "systemctl",
            "--user",
            "is-active",
            "lambdaws-jarvis.service",
        ]
    )
    return {
        "available": True,
        "jarvis": jarvis or "unknown",
        "failed": failed.splitlines()[:20] if failed else [],
    }


def _git_info(path: Path) -> dict[str, Any] | None:
    branch = _run(["git", "-C", str(path), "branch", "--show-current"])
    if branch is None:
        return None
    status = _run(["git", "-C", str(path), "status", "--short"])
    top = _run(["git", "-C", str(path), "rev-parse", "--show-toplevel"])
    return {
        "path": top or str(path),
        "branch": branch or "(detached)",
        "dirty": bool(status),
        "changes": status.splitlines()[:20] if status else [],
    }


def recent_projects(home: Path, limit: int = 8) -> list[dict[str, Any]]:
    candidates: list[tuple[float, Path]] = []
    roots = [home / "Projects", home / "projects", home / "Code", home / "code"]

    for root in roots:
        if not root.is_dir():
            continue
        try:
            for child in root.iterdir():
                if not child.is_dir():
                    continue
                git_dir = child / ".git"
                if git_dir.exists():
                    try:
                        stamp = git_dir.stat().st_mtime
                    except OSError:
                        stamp = 0
                    candidates.append((stamp, child))
        except OSError:
            continue

    projects = []
    seen = set()
    for _, path in sorted(candidates, reverse=True):
        info = _git_info(path)
        if not info:
            continue
        key = info["path"]
        if key in seen:
            continue
        seen.add(key)
        projects.append(info)
        if len(projects) >= max(1, min(limit, 20)):
            break
    return projects


def workstation_context(
    home: Path,
    *,
    include_clipboard: bool = False,
    include_processes: bool = True,
    include_projects: bool = True,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "observed_at": int(time.time()),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "kde": kde_context(),
        "active_window": active_window(),
        "media": media_context(),
        "services": user_services(),
    }

    if include_processes:
        result["processes"] = process_context()
    if include_projects:
        result["recent_projects"] = recent_projects(home)
    if include_clipboard:
        result["clipboard"] = clipboard_preview()

    return result


def project_context(path: Path) -> dict[str, Any]:
    info = _git_info(path)
    if info is None:
        return {"error": "O caminho não é um repositório Git."}

    info["recent_commits"] = (
        _run(
            [
                "git",
                "-C",
                str(path),
                "log",
                "-5",
                "--pretty=format:%h\t%ad\t%s",
                "--date=short",
            ]
        )
        or ""
    ).splitlines()
    return info
