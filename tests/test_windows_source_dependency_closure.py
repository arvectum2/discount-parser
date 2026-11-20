"""Guard the exact source dependency in all controlled Windows closure paths."""
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_build_closure_includes_pinned_data_platform():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    dependency, = [d for d in project["project"]["dependencies"] if d.startswith("arvectum-data @ ")]
    assert re.fullmatch(r"arvectum-data @ git\+https://github\.com/arvectum2/data-platform\.git@[a-f0-9]{40}", dependency)
    lock = (ROOT / "requirements/windows-build.lock").read_text()
    assert dependency in lock
    for package in ("fastapi", "pydantic-settings", "uvicorn", "setuptools", "wheel"):
        assert re.search(rf"(?mi)^{re.escape(package)}==[^\s]+$", lock)
    for file, count in (("build-delivery.yml", 2), ("windows-reproducibility.yml", 1), ("windows-installed-acceptance.yml", 1)):
        workflow = (ROOT / ".github/workflows" / file).read_text()
        install = "python -m pip install --no-deps --only-binary=:all: -r requirements/windows-build.lock"
        pinned = f"python -m pip install --no-deps --no-build-isolation '{dependency}'"
        assert workflow.count(install) == workflow.count(pinned) == count
        for segment in workflow.split(install)[1:]:
            assert segment.index(pinned) < segment.index("python -m pip check")
