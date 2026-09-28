#!/usr/bin/env python3
"""Read-only check of optional backend checkouts against tested upstream pins.

This checks local setup, not model behavior or detector accuracy. Missing
optional backends are reported without failing the command.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from common import subprocess_creationflags

MANIFEST = Path(__file__).resolve().parents[2] / "config" / "backend-compatibility.json"


def check_checkout(name: str, spec: dict[str, str]) -> dict[str, str | bool | None]:
    raw = os.environ.get(spec["env"])
    directory = Path(raw).expanduser() if raw else Path.home() / spec["default_dir"]
    result: dict[str, str | bool | None] = {
        "path": str(directory),
        "status": "absent",
        "expected_ref": spec["ref"],
        "actual_ref": None,
        "venv_python": False,
    }
    if not directory.is_dir():
        return result
    venv_python = next(
        (
            directory / path
            for path in (".venv/bin/python", ".venv/Scripts/python.exe")
            if (directory / path).is_file()
        ),
        None,
    )
    result["venv_python"] = venv_python is not None
    # MarkDiffusion's default setup installs a PyPI package without a checkout.
    if not (directory / ".git").exists():
        if name != "markdiffusion":
            result["status"] = "not_git_checkout"
        elif venv_python is None:
            result["status"] = "package_venv_missing"
        else:
            try:
                version = subprocess.run(
                    [
                        str(venv_python),
                        "-c",
                        "from importlib.metadata import version; print(version('markdiffusion'))",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=subprocess_creationflags,
                ).stdout.strip()
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
                result["status"] = "package_error"
            else:
                result["installed_version"] = version
                result["status"] = (
                    "ready" if version == spec["version"] else "package_version_mismatch"
                )
        return result
    try:
        head = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess_creationflags,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        result["status"] = "git_error"
        return result
    result["actual_ref"] = head
    if head != spec["ref"]:
        result["status"] = "ref_mismatch"
        return result
    if not (directory / spec["required_path"]).exists():
        result["status"] = "missing_backend_files"
        return result
    result["status"] = "ready" if result["venv_python"] else "venv_missing"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict", action="store_true", help="fail on an unhealthy installed backend"
    )
    args = parser.parse_args()
    specs = json.loads(MANIFEST.read_text(encoding="utf-8"))
    report = {name: check_checkout(name, spec) for name, spec in specs.items()}
    print(json.dumps(report, indent=2, sort_keys=True))
    unhealthy = {
        "not_git_checkout",
        "git_error",
        "ref_mismatch",
        "missing_backend_files",
        "venv_missing",
        "package_venv_missing",
        "package_error",
        "package_version_mismatch",
    }
    return int(args.strict and any(item["status"] in unhealthy for item in report.values()))


if __name__ == "__main__":
    raise SystemExit(main())
