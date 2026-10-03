"""Build public source references and LLM-readable docs without runtime state."""

import ast
import io
import re
import zipfile
from pathlib import Path

from mkdocs.structure.files import File

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/fastfence/app/interfaces/http"
REPOSITORY = (
    "https://github.com/llama-lovers/HackYeah2026-challenge-second/blob/main/"
)
PAGES = (
    (
        "examples/acp.md",
        "Agent Communication Protocol",
        "Protect real synchronous agent-to-agent ACP calls with shared input/output policies.",
    ),
    (
        "examples/custom-detectors.md",
        "Custom Python text detectors",
        "Add trusted literal and regex detect-secrets plugins at startup.",
    ),
    (
        "examples/asymmetric-anonymization.md",
        "Public/private-key anonymization",
        "Generate RSA keys and run authenticated stateless recovery envelopes.",
    ),
    (
        "examples/openai-upstream.md",
        "Model upstreams",
        "Connect Ollama or an OpenAI-compatible model server.",
    ),
    (
        "getting-started.md",
        "Getting started",
        "Install and start a local gateway.",
    ),
    ("learn.md", "Learn", "Follow small, runnable integration tasks."),
    (
        "examples/protected-request.md",
        "Protected request example",
        "Complete executable Python source for a protected model call.",
    ),
    (
        "examples/semantic-policy.md",
        "Named Laya rule example",
        "Version-aware actual-model preview and explicit activation.",
    ),
    (
        "examples/mcp-client.md",
        "MCP client example",
        "Authenticate and call a protected model through MCP.",
    ),
    (
        "examples/fastmcp-server.md",
        "FastMCP server example",
        "Register an actual FastMCP tool behind the control layer.",
    ),
    (
        "examples/openai-client.md",
        "OpenAI client example",
        "Use the standard SDK with the protected compatibility endpoint.",
    ),
    (
        "policies.md",
        "Policies",
        "Configure controls and publish reviewed changes.",
    ),
    ("integrations.md", "Integrations", "Connect Laya, REST, MCP and models."),
    (
        "integration-reference.md",
        "Integration reference",
        "Choose protocols, credentials and request paths.",
    ),
    (
        "reference/http-api.md",
        "HTTP API",
        "Endpoint inventory generated from Python source.",
    ),
    ("settings.md", "Settings", "Environment settings and defaults."),
    (
        "architecture.md",
        "Architecture",
        "Module boundaries, trust and runtime behavior.",
    ),
    (
        "manual-testing.md",
        "Manual verification",
        "Verify behavior on your own local installation.",
    ),
    (
        "security-review.md",
        "Independent security review",
        "Scoped findings, fixes and remaining evaluation limits.",
    ),
    (
        "requirements.md",
        "Requirements and evidence",
        "Partner-task and submitted-feature mapping with current boundaries.",
    ),
)

EXAMPLE_FILES = (
    "acp_server.py",
    "acp_gateway.py",
    "acp_client.py",
    "acp_policy.yaml",
    "custom_detector.py",
    "asymmetric_keys.py",
    "protected_request.py",
    "semantic_policy.py",
    "mcp_client.py",
    "fastmcp_server.py",
    "openai_client.py",
    "policy.yaml",
    "signatures.json",
)


DOCUMENT_FILES = (
    "english.png",
    "polish.jpg",
    "rotated.png",
    "two-pages.pdf",
    "mixed.pdf",
)


def example_downloads():
    sources = {
        name: (ROOT / "examples/docs" / name).read_bytes()
        for name in EXAMPLE_FILES
    }
    sources.update(
        {
            f"documents/{name}": (
                ROOT / "examples/documents" / name
            ).read_bytes()
            for name in DOCUMENT_FILES
        }
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for name, content in sources.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    return sources, buffer.getvalue()


SOURCE_MARKER = re.compile(
    r"<!-- source: (examples/docs/[a-z_]+\.(?:py|yaml)) -->"
)


def embed_sources(markdown):
    def embed(match):
        relative = match.group(1)
        source = (ROOT / relative).read_text().rstrip()
        language = "python" if relative.endswith(".py") else "yaml"
        return f"```{language}\n{source}\n```\n\n[Download {Path(relative).name}](https://fastfence.dev/downloads/{Path(relative).name}) · [View source]({REPOSITORY}{relative})"

    return SOURCE_MARKER.sub(embed, markdown)


def router_prefixes(tree):
    prefixes = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(
            node.value, ast.Call
        ):
            continue
        call = node.value
        if not isinstance(call.func, ast.Name) or call.func.id != "APIRouter":
            continue
        for keyword in call.keywords:
            if keyword.arg == "prefix" and isinstance(
                keyword.value, ast.Constant
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        prefixes[target.id] = keyword.value.value
    return prefixes


def endpoint_reference():
    rows = []
    for path in sorted(SOURCE.glob("*.py")):
        tree = ast.parse(path.read_text())
        prefixes = router_prefixes(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                if not (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr
                    in {"get", "post", "put", "delete", "patch"}
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)
                    and isinstance(decorator.args[0].value, str)
                ):
                    continue
                route = decorator.args[0].value
                if isinstance(decorator.func.value, ast.Name):
                    route = prefixes.get(decorator.func.value.id, "") + route
                if route == "/" or route.startswith("/assets/"):
                    continue
                method = decorator.func.attr.upper()
                source = path.relative_to(ROOT).as_posix()
                link = f"{REPOSITORY}{source}#L{node.lineno}"
                rows.append((route, method, node.name, link))
    lines = [
        "# HTTP API reference",
        "",
        "This endpoint inventory is generated from the Python route declarations on every documentation build. Follow a handler link to inspect its request and response models. The running gateway exposes the complete JSON schemas at `/openapi.json` and an interactive explorer at `/docs`.",
        "",
        "All `/api/` and `/v1/` requests require a provisioned bearer identity. `/api/admin/` requires a management identity. `/health` is public. The MCP mount at `/mcp/` uses the same trusted bearer identities and is listed separately in the [integration reference](../integration-reference.md).",
        "",
        "| Method | Path | Source handler |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| `{method}` | `{route}` | [{handler}]({link}) |"
        for route, method, handler, link in sorted(rows)
    )
    lines.extend(
        [
            "",
            "## Response semantics",
            "",
            "An HTTP 200 response from a protected invocation can still contain a `blocked` security verdict. Check `decision`, `reason` and `upstream_executed`; do not use HTTP status alone as an authorization result. A blocked output can follow an already executed upstream operation.",
            "",
            "OpenAI-compatible calls return their endpoint-specific schema. Streaming, arbitrary upstream providers and arbitrary MCP proxying are not implied by this inventory. See the [protocol contract](../integration-reference.md).",
            "",
        ]
    )
    return "\n".join(lines)


def on_files(files, config):
    sources, archive = example_downloads()
    for name, content in sources.items():
        files.append(
            File.generated(config, f"downloads/{name}", content=content)
        )
    files.append(
        File.generated(
            config, "downloads/fastfence-examples.zip", content=archive
        )
    )
    for file in list(files):
        if file.src_uri.endswith(".md") and SOURCE_MARKER.search(
            file.content_string
        ):
            rendered = embed_sources(file.content_string)
            files.remove(file)
            files.append(File.generated(config, file.src_uri, content=rendered))
    reference = endpoint_reference()
    files.append(
        File.generated(config, "reference/http-api.md", content=reference)
    )
    base = config.site_url.rstrip("/")
    index = [
        "# FastFence",
        "",
        "> Local security policy enforcement for AI agents, models and tools.",
        "",
        "FastFence is installed as a Python 3.12 package with pip install fastfence uv, followed by fastfence init --anonymization and fastfence setup-laya. No FastFence checkout is required. Runnable example source and its ZIP archive are available under /downloads/. Policies and identities are local configuration; budgets and audit are process-local. Laya authoring produces a reviewed proposal, never implicit activation.",
        "",
        "## Documentation",
        "",
    ]
    full = [
        "# FastFence documentation",
        "",
        "Generated from the same Markdown and route source as the public documentation site. Source pages below are authoritative; historical evaluation reports are intentionally excluded.",
        "",
    ]
    for path, title, description in PAGES:
        url = f"{base}/{path.removesuffix('.md')}/"
        index.append(f"- [{title}]({url}): {description}")
        content = (
            reference
            if path == "reference/http-api.md"
            else (ROOT / "docs" / path).read_text()
        )
        full.extend(["---", f"Source: {url}", "", embed_sources(content), ""])
    index.extend(
        [
            "",
            "## Complete text",
            "",
            f"- [Full documentation]({base}/llms-full.txt): Curated pages in one text response.",
            f"- [Source repository]({config.repo_url}): Apache-2.0 source, tests and specifications.",
            "",
        ]
    )
    files.append(File.generated(config, "llms.txt", content="\n".join(index)))
    files.append(
        File.generated(config, "llms-full.txt", content="\n".join(full))
    )
    return files
