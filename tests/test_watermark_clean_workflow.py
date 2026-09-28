"""Focused checks for the one-command user workflow."""

import importlib.machinery
import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "watermark-clean"


def run(*args: str):
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True)


def make_docx(path: Path):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Hello&#8203; world</w:t></w:r></w:p></w:body></w:document>')
        archive.writestr("docProps/core.xml", '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>AI generated</dc:title></cp:coreProperties>')


def test_docx_metadata_and_layer_a_preserve_original(tmp_path):
    original = tmp_path / "resume.docx"
    make_docx(original)
    source_bytes = original.read_bytes()
    result = run(str(original), "--detectors", "none")
    assert result.returncode == 0, result.stderr
    output = tmp_path / "resume.cleaned.docx"
    assert output.is_file() and original.read_bytes() == source_bytes
    report = json.loads((tmp_path / "resume.cleaned.docx.report.json").read_text())
    assert report["before"]["layer_a"] > 0
    assert report["after"]["layer_a"] == 0
    assert report["after"]["extracted_text_layer_a"] == 0
    assert report["after"]["ai_metadata"] is False
    with zipfile.ZipFile(output) as archive:
        assert "Hello world" in archive.read("word/document.xml").decode()
    second = run(str(original), "--detectors", "none")
    assert second.returncode == 0, second.stderr
    assert (tmp_path / "resume.cleaned-2.docx").is_file()


def test_text_preserved_when_no_deterministic_marks(tmp_path):
    source = tmp_path / "draft.md"
    source.write_text("Plain content.\n")
    result = run(str(source), "--detectors", "none")
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "draft.cleaned.md").read_bytes() == source.read_bytes()


def test_unknown_format_has_clear_error_and_no_output(tmp_path):
    source = tmp_path / "file.xyz"
    source.write_bytes(b"\x00\x01unknown")
    result = run(str(source), "--detectors", "none")
    assert result.returncode == 1
    assert "unrecognized file format" in result.stderr
    assert not (tmp_path / "file.cleaned.xyz").exists()


def test_detectors_are_read_only_and_use_existing_cli(tmp_path, monkeypatch):
    loader = importlib.machinery.SourceFileLoader("watermark_clean", str(CLI))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    text = tmp_path / "cleaned-text.txt"
    text.write_text("Untouched text")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"is_watermarked": False,
                                    "score": 0.1, "threshold": 0.5, "model": "test"}), "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    report = module.detect(text, "local")
    assert [r["scheme"] for r in report] == ["kgw", "exp", "synthid-text"]
    assert all(r["status"] == "negative" for r in report)
    assert all("detect_text_watermark.py" in cmd[1] and "detect" in cmd and
               "--offline" in cmd for cmd in calls)
    assert text.read_text() == "Untouched text"
