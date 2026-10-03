"""Published example downloads include only exact executable public sources."""

import io
import runpy
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
        assert len(sources) == 14
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
