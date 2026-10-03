"""Public fences keep their source while Material receives highlighted tokens."""

import runpy
from html.parser import HTMLParser
from pathlib import Path

import pytest
from markdown import markdown
from mkdocs.config import load_config

ROOT = Path(__file__).resolve().parents[2]


class CodeMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.classes = set()
        self.source = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key == "class":
                self.classes.update(value.split())

    def handle_data(self, data):
        self.source.append(data)


def render(source):
    config = load_config(str(ROOT / "mkdocs.yml"))
    result = CodeMarkup()
    result.feed(
        markdown(
            source,
            extensions=config.markdown_extensions,
            extension_configs=config.mdx_configs,
        )
    )
    return result


@pytest.mark.parametrize(
    ("language", "source", "token"),
    [
        ("python", 'def greeting():\n    return "hello"', "k"),
        ("bash", 'export GREETING="hello"\nprintf "%s\\n" "$GREETING"', "nb"),
        ("yaml", "semantic:\n  provider: laya\n  scan_output: true", "nt"),
        ("json", '{\n  "enabled": true,\n  "limit": 32\n}', "nt"),
    ],
)
def test_multiline_fences_preserve_source_and_highlight_tokens(
    language, source, token
):
    rendered = render(f"```{language}\n{source}\n```")
    assert {"highlight", f"language-{language}", token} <= rendered.classes
    assert "".join(rendered.source).strip() == source


def test_embedded_executable_source_is_highlighted_and_copy_enabled():
    hook = runpy.run_path(str(ROOT / "scripts/docs_reference.py"))
    rendered = render(
        hook["embed_sources"](
            "<!-- source: examples/docs/custom_detector.py -->"
        )
    )
    assert {"language-python", "highlight", "k", "s2"} <= rendered.classes
    source = (ROOT / "examples/docs/custom_detector.py").read_text().rstrip()
    assert source in "".join(rendered.source)
    config = load_config(str(ROOT / "mkdocs.yml"))
    assert "content.code.copy" in config.theme["features"]


def test_mermaid_remains_unhighlighted_and_matches_diagram_loader():
    rendered = render("```mermaid\ngraph LR\n  A --> B\n```")
    assert "language-mermaid" in rendered.classes
    assert "highlight" not in rendered.classes
    assert "graph LR\n  A --> B" in "".join(rendered.source)
    script = (ROOT / "docs/javascripts/mermaid.mjs").read_text()
    assert "pre.language-mermaid > code" in script
