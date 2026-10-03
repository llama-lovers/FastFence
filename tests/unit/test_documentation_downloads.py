"""Published example downloads include only exact executable public sources."""

import io
import json
import runpy
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = runpy.run_path(str(ROOT / "scripts/docs_reference.py"))


def test_example_archive_is_complete_deterministic_and_source_identical():
    sources, content = HOOK["example_downloads"]()
    assert HOOK["example_downloads"]()[1] == content
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert set(archive.namelist()) == set(sources)
        assert {"fastmcp_server.py", "policy.yaml", "signatures.json"} <= set(
            sources
        )
        assert "custom_detector.py" in sources
        assert {
            "acp_server.py",
            "acp_gateway.py",
            "acp_client.py",
            "acp_policy.yaml",
        } <= set(sources)
        assert len(sources) == 18
        assert {f"documents/{name}" for name in HOOK["DOCUMENT_FILES"]} <= set(
            sources
        )
        assert "documents/generate.py" not in sources
        for name in archive.namelist():
            assert not Path(name).is_absolute() and ".." not in Path(name).parts
            source = (
                ROOT / "examples" / name
                if name.startswith("documents/")
                else ROOT / "examples/docs" / name
            )
            assert archive.read(name) == source.read_bytes()
    assert not any(
        "credentials" in name or "private" in name for name in sources
    )


def test_embedded_source_and_download_are_the_same_public_file():
    sources, _ = HOOK["example_downloads"]()
    for name, content in sources.items():
        if not name.endswith((".py", ".yaml")):
            continue
        rendered = HOOK["embed_sources"](
            f"<!-- source: examples/docs/{name} -->"
        )
        assert content.decode().rstrip() in rendered
        assert f"https://fastfence.dev/downloads/{name}" in rendered


def test_public_build_excludes_internal_records_from_pages_search_and_llms(
    tmp_path,
):
    site = tmp_path / "site"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "mkdocs",
            "build",
            "--strict",
            "--site-dir",
            str(site),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    internal = {
        "anonymization-plan",
        "challenge-readiness",
        "contributing",
        "deployment",
        "publishing",
        "requirements",
        "security-review",
        "testing",
    }
    search = json.loads((site / "search/search_index.json").read_text())
    locations = [item["location"] for item in search["docs"]]
    llms = (site / "llms.txt").read_text() + (
        site / "llms-full.txt"
    ).read_text()
    for name in internal:
        assert (ROOT / "maintainer" / f"{name}.md").is_file()
        assert not (site / name).exists()
        assert not any(
            location.startswith(f"{name}/") for location in locations
        )
        assert f"https://fastfence.dev/{name}/" not in llms
    assert not (site / "maintainer").exists()
    assert (site / "examples/mcp-client/index.html").is_file()
    assert "Source: https://fastfence.dev/getting-started/" in llms
