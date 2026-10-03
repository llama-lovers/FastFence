"""Release tags preserve built history, locale paths and generated changelogs."""

import json
import runpy
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILDER = runpy.run_path(str(ROOT / "scripts/versioned_docs.py"))
NOTES = runpy.run_path(str(ROOT / "scripts/release_notes.py"))


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


@pytest.fixture
def release_repository(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    git("init", "-q")
    git("config", "user.name", "Documentation tests")
    git("config", "user.email", "docs@example.invalid")
    (tmp_path / "mkdocs.yml").write_text(
        "site_name: Versioned product\nsite_url: https://example.test/\n"
        "theme:\n  name: material\nextra:\n  version:\n    provider: mike\n"
        "plugins:\n  - search\n  - i18n:\n      languages:\n"
        "        - locale: en\n          name: English\n          default: true\n"
        "        - locale: pl\n          name: Polski\n"
    )
    docs = tmp_path / "docs"
    (docs / "downloads").mkdir(parents=True)
    (docs / "downloads/client.py").write_text("print('example')\n")
    (docs / "index.md").write_text("# Version one\n")
    (docs / "index.pl.md").write_text("# Wersja pierwsza\n")
    (docs / "usage.md").write_text("# Usage\n")
    (docs / "usage.pl.md").write_text("# Uruchomienie\n")
    git("add", ".")
    git("commit", "-qm", "First release")
    git("tag", "v1.0.0")
    (docs / "index.md").write_text("# Version two\n")
    (docs / "index.pl.md").write_text("# Wersja druga\n")
    git("add", ".")
    git("commit", "-qm", "Fix [unsafe](javascript:test) <b>titles</b>")
    git("tag", "v1.0.1")
    return tmp_path


def test_real_mike_build_preserves_tag_history_languages_and_legacy_links(
    release_repository,
):
    output = release_repository / "published"
    BUILDER["build"]("v1.0.1", output, branch="test-pages")
    versions = {
        item["version"]: item
        for item in json.loads((output / "versions.json").read_text())
    }
    assert versions.keys() == {"1.0.0", "1.0.1"}
    assert versions["1.0.1"]["aliases"] == ["latest"]
    assert "Version one" in (output / "1.0.0/index.html").read_text()
    assert "Version two" in (output / "1.0.1/index.html").read_text()
    assert "Wersja pierwsza" in (output / "1.0.0/pl/index.html").read_text()
    assert "Wersja druga" in (output / "1.0.1/pl/index.html").read_text()
    assert 'lang="pl"' in (output / "latest/pl/index.html").read_text()
    assert "/latest/pl/usage/" in (output / "pl/usage/index.html").read_text()
    assert (output / "downloads/client.py").read_bytes() == (
        output / "1.0.1/downloads/client.py"
    ).read_bytes()
    assert not any(path.is_symlink() for path in output.rglob("*"))
    git("checkout", "--detach", "v1.0.0")
    replay = release_repository / "replayed"
    BUILDER["build"]("v1.0.0", replay, branch="test-pages")
    replay_versions = {
        item["version"]: item
        for item in json.loads((replay / "versions.json").read_text())
    }
    assert replay_versions["1.0.1"]["aliases"] == ["latest"]
    assert "Version two" in (replay / "latest/index.html").read_text()


def test_documentation_refuses_unmatched_checkout_and_invalid_tag(
    release_repository,
):
    with pytest.raises(ValueError, match="match the release tag"):
        BUILDER["build"]("v1.0.0", release_repository / "output")
    with pytest.raises(ValueError, match="exact stable"):
        BUILDER["build"]("main", release_repository / "output")


def test_changelog_uses_tag_range_and_escapes_contributor_titles(
    release_repository,
):
    result = NOTES["notes"]("v1.0.1")
    assert "First release" not in result
    assert "Fix \\[unsafe\\]" in result
    assert "<b>" not in result and "&lt;b&gt;" in result
    assert "v1.0.0...v1.0.1" in result
    assert "https://fastfence.dev/1.0.1/" in result
    with pytest.raises(ValueError):
        NOTES["notes"]("--all")


def test_development_build_preserves_releases_and_rejects_stale_source(
    release_repository,
):
    root = release_repository
    BUILDER["build"]("v1.0.1", root / "stable", branch="test-pages")
    (root / "docs/index.md").write_text("# Unreleased first revision\n")
    git("add", "docs")
    git("commit", "-qm", "Development one")
    first = git("rev-parse", "HEAD")
    BUILDER["build_dev"](first, root / "dev-first", branch="test-pages")
    (root / "docs/index.md").write_text("# Unreleased second revision\n")
    (root / "docs/downloads/client.py").write_text("print('unreleased')\n")
    git("add", "docs")
    git("commit", "-qm", "Development two")
    second = git("rev-parse", "HEAD")
    output = root / "dev-second"
    BUILDER["build_dev"](second, output, branch="test-pages")
    versions = {
        item["version"]: item
        for item in json.loads((output / "versions.json").read_text())
    }
    assert versions.keys() == {"1.0.0", "1.0.1", "dev"}
    assert versions["1.0.1"]["aliases"] == ["latest"]
    assert versions["dev"]["aliases"] == []
    assert versions["dev"]["title"] == "dev (unreleased)"
    assert versions["dev"]["properties"]["git_sha"] == second
    assert "Unreleased second" in (output / "dev/index.html").read_text()
    assert "Version two" in (output / "latest/index.html").read_text()
    assert "latest" in (output / "index.html").read_text()
    assert (output / "downloads/client.py").read_bytes() == (
        root / "stable/downloads/client.py"
    ).read_bytes()
    assert (output / "dev/downloads/client.py").read_bytes() != (
        output / "downloads/client.py"
    ).read_bytes()
    git("checkout", "--detach", first)
    with pytest.raises(ValueError, match="older or divergent"):
        BUILDER["build_dev"](first, root / "stale", branch="test-pages")
    assert not (root / "stale").exists()
    git("checkout", "--detach", "v1.0.0")
    BUILDER["build"]("v1.0.0", root / "replay", branch="test-pages")
    assert "Unreleased second" in (root / "replay/dev/index.html").read_text()
    assert "Version two" in (root / "replay/latest/index.html").read_text()


def test_dev_requires_exact_checked_out_sha(
    release_repository,
):
    output = release_repository / "output"
    with pytest.raises(ValueError, match="exact commit SHA"):
        BUILDER["build_dev"]("main", output)
    with pytest.raises(ValueError, match="match the verified"):
        BUILDER["build_dev"]("0" * 40, output)


def test_dev_hook_uses_exact_sha_while_stable_remains_tagged(monkeypatch):
    monkeypatch.setenv("FASTFENCE_DOCS_SOURCE_SHA", "a" * 40)
    monkeypatch.setenv("MIKE_DOCS_VERSION", "dev")
    hook = runpy.run_path(str(ROOT / "scripts/docs_reference.py"))
    assert hook["SOURCE_REF"] == "a" * 40
    assert "unreleased" in hook["development_notice"]()
    assert "niewydana" in hook["development_notice"](True)
    assert "/commit/" + "a" * 40 in hook["development_notice"]()
    assert "/latest/" in hook["development_notice"]()
    monkeypatch.setenv("MIKE_DOCS_VERSION", "1.0.1")
    hook = runpy.run_path(str(ROOT / "scripts/docs_reference.py"))
    assert hook["SOURCE_REF"] == "v1.0.1"
    assert hook["development_notice"]() == ""
    monkeypatch.setenv("FASTFENCE_DOCS_SOURCE_SHA", "main")
    with pytest.raises(ValueError, match="exact SHA"):
        runpy.run_path(str(ROOT / "scripts/docs_reference.py"))


def test_first_dev_bootstraps_only_previously_verified_release(
    release_repository,
):
    output = release_repository / "first-dev"
    BUILDER["build_dev"](git("rev-parse", "HEAD"), output, branch="test-pages")
    versions = {
        item["version"]: item
        for item in json.loads((output / "versions.json").read_text())
    }
    assert versions.keys() == {"1.0.0", "dev"}
    assert versions["1.0.0"]["aliases"] == ["latest"]
    assert "Version one" in (output / "latest/index.html").read_text()
    assert "Version two" in (output / "dev/index.html").read_text()
    assert "latest" in (output / "index.html").read_text()
    assert not any(path.is_symlink() for path in output.rglob("*"))
