"""Starting the app: what has to be remade before the browser opens."""

import os

import launcher


def build(tmp_path, source_age: float, build_age: float):
    """A frontend folder whose source and build have the given ages, in seconds ago."""
    frontend = tmp_path / "frontend"
    (frontend / "src" / "components").mkdir(parents=True)
    (frontend / "dist").mkdir()
    (frontend / "src" / "components" / "BrandPanel.tsx").write_text("code")
    (frontend / "index.html").write_text("<html>")
    built = frontend / "dist" / "index.html"
    built.write_text("<html>")
    now = built.stat().st_mtime
    for path in frontend.rglob("*"):
        if path.is_file():
            age = build_age if "dist" in path.parts else source_age
            os.utime(path, (now - age, now - age))
    return frontend


def test_a_build_newer_than_the_code_is_used_as_is(tmp_path, monkeypatch):
    build(tmp_path, source_age=100, build_age=0)
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    assert not launcher.frontend_is_stale()


def test_a_build_from_before_the_last_pull_is_remade(tmp_path, monkeypatch):
    """The build is committed, so a pull hands you new code beside an old interface."""
    build(tmp_path, source_age=0, build_age=100)
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    assert launcher.frontend_is_stale()


def test_no_build_at_all_is_stale(tmp_path, monkeypatch):
    frontend = build(tmp_path, source_age=0, build_age=0)
    (frontend / "dist" / "index.html").unlink()
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    assert launcher.frontend_is_stale()


def test_the_real_project_is_checked_against_its_own_source():
    """Guards the glob list: a typo would quietly stop looking at the code."""
    frontend = launcher.ROOT / "frontend"
    seen = {p for pattern in launcher.SOURCE_GLOBS for p in frontend.glob(pattern) if p.is_file()}
    assert frontend / "src" / "App.tsx" in seen
    assert frontend / "index.html" in seen
    assert frontend / "vite.config.ts" in seen
