# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _source_files(directory: Path):
    """Every hand-written .py file under directory. generated/ is excluded —
    the generator owns it (and stamps its own header via regenerate.py)."""
    files = []
    for path in directory.rglob("*.py"):
        if "generated" in path.relative_to(ROOT).parts:
            continue
        if "__pycache__" in path.parts:
            continue
        files.append(path)
    return files


def test_every_hand_written_source_file_carries_the_spdx_header():
    files = []
    for name in ["src", "tests", "scripts", "examples"]:
        directory = ROOT / name
        if directory.exists():
            files.extend(_source_files(directory))

    assert len(files) > 0

    missing = []
    for file in files:
        head = file.read_text(encoding="utf-8")[:300]
        if "SPDX-License-Identifier: MIT" not in head or "Copyright (c) 2026 Truestock" not in head:
            missing.append(str(file.relative_to(ROOT)))

    assert missing == [], f"missing licence header:\n" + "\n".join(missing)


def test_the_license_file_is_mit_and_names_the_copyright_holder():
    licence = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in licence
    assert "Copyright (c) 2026 Truestock" in licence
    assert "WITHOUT WARRANTY OF ANY KIND" in licence


def test_pyproject_declares_the_same_licence():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'license = "MIT"' in pyproject
