"""Pins and local probes must reveal drift before optional backends run."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "service" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_backends


def test_manifest_matches_installers_and_images():
    manifest = json.loads(check_backends.MANIFEST.read_text(encoding="utf-8"))
    sources = {
        "markllm": [SCRIPTS / "setup_markllm.sh", ROOT / "service/Dockerfile.markllm"],
        "reverse_synthid": [
            SCRIPTS / "setup_synthid.sh",
            SCRIPTS / "setup_synthid.ps1",
            ROOT / "service/Dockerfile.synthid",
        ],
        "ctrlregen": [SCRIPTS / "setup_ctrlregen.sh", SCRIPTS / "setup_ctrlregen.ps1"],
        "markdiffusion": [SCRIPTS / "setup_markdiffusion.sh"],
    }
    for name, paths in sources.items():
        for path in paths:
            assert manifest[name]["ref"] in path.read_text(encoding="utf-8"), path
    assert (
        f'markdiffusion=={manifest["markdiffusion"]["version"]}'
        in (SCRIPTS / "requirements-markdiffusion.txt").read_text(encoding="utf-8")
    )
    torch_pin = "torch==2.14.0.*"
    assert torch_pin in (SCRIPTS / "requirements-markllm.txt").read_text(encoding="utf-8")
    assert torch_pin in (ROOT / "service/Dockerfile.markllm").read_text(encoding="utf-8")


def test_probe_absent_checkout_is_optional(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKLLM_DIR", str(tmp_path / "absent"))
    spec = json.loads(check_backends.MANIFEST.read_text(encoding="utf-8"))["markllm"]
    assert check_backends.check_checkout("markllm", spec)["status"] == "absent"


def test_strict_probe_ignores_absent_but_flags_drift(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["check_backends.py", "--strict"])
    monkeypatch.setattr(
        check_backends, "check_checkout", lambda name, spec: {"status": "absent"}
    )
    assert check_backends.main() == 0
    capsys.readouterr()
    monkeypatch.setattr(
        check_backends, "check_checkout", lambda name, spec: {"status": "ref_mismatch"}
    )
    assert check_backends.main() == 1


@pytest.mark.skipif(os.name == "nt", reason="tests the Unix setup scripts")
@pytest.mark.parametrize(
    ("name", "script", "extra_args"),
    [
        ("markllm", "setup_markllm.sh", []),
        ("reverse_synthid", "setup_synthid.sh", []),
        ("ctrlregen", "setup_ctrlregen.sh", []),
        ("markdiffusion", "setup_markdiffusion.sh", ["--checkout"]),
    ],
)
def test_existing_checkout_fails_before_install_if_ref_mismatches(
    tmp_path, monkeypatch, name, script, extra_args
):
    checkout = tmp_path / name
    checkout.mkdir()
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    (checkout / "README.md").write_text("fixture", encoding="utf-8")
    subprocess.run(["git", "-C", str(checkout), "add", "README.md"], check=True)
    subprocess.run(
        [
            "git", "-C", str(checkout), "-c", "user.name=Test",
            "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture",
        ],
        check=True,
    )
    head_command = ["git", "-C", str(checkout), "rev-parse", "HEAD"]
    actual = subprocess.check_output(head_command, text=True).strip()
    spec = json.loads(check_backends.MANIFEST.read_text(encoding="utf-8"))[name]
    monkeypatch.setenv(spec["env"], str(checkout))
    probe = subprocess.run(
        ["bash", str(SCRIPTS / script), *extra_args],
        env=os.environ.copy(), capture_output=True, text=True, check=False,
    )
    assert probe.returncode == 1
    assert "expected" in probe.stderr
    assert not (checkout / ".venv").exists()
    assert subprocess.check_output(head_command, text=True).strip() == actual
    assert check_backends.check_checkout("markllm", spec)["status"] == "ref_mismatch"
