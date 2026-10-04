"""Build public source references and LLM-readable docs without runtime state."""

import ast
import io
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from mkdocs.plugins import event_priority

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/fastfence/app/interfaces/http"
RELEASE = os.environ.get("MIKE_DOCS_VERSION", "")
DEV_SHA = os.environ.get("FASTFENCE_DOCS_SOURCE_SHA", "")
if DEV_SHA and not re.fullmatch(r"[0-9a-f]{40}", DEV_SHA):
    raise ValueError("Development documentation source must be an exact SHA")
SOURCE_REF = (
    f"v{RELEASE}"
    if re.fullmatch(r"\d+\.\d+\.\d+", RELEASE)
    else DEV_SHA or "main"
)
REPOSITORY = f"https://github.com/llama-lovers/FastFence/blob/{SOURCE_REF}/"
BUILD_DOCS = tempfile.TemporaryDirectory(prefix="fastfence-docs-")
PAGES = (
    (
        "benchmarks.md",
        "Benchmarks",
        "Reproduce package measurements and understand published latency results.",
    ),
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


BENCHMARK_FILES = (
    "scripts/benchmark_package.py",
    "evaluation/benchmark_gateway.py",
    "evaluation/business_fixture.py",
    "examples/business_tools/tools.py",
    "examples/business_tools/credentials.py",
    "examples/business_tools/policy.yaml",
    "config/signatures.json",
)


def benchmark_download():
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for name in BENCHMARK_FILES:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, (ROOT / name).read_bytes())
    return buffer.getvalue()


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
        "All `/api/` and `/v1/` requests require a provisioned bearer identity. `/api/admin/` requires a management identity. `/health` is public liveness; `/ready` is the public cached semantic-prerequisite readiness check (200/503, no inference). The MCP mount at `/mcp/` uses the same trusted bearer identities and is listed separately in the [integration reference](../integration-reference.md).",
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


def polish_reference(reference):
    replacements = {
        "# HTTP API reference": "# Dokumentacja HTTP API",
        "This endpoint inventory is generated from the Python route declarations on every documentation build. Follow a handler link to inspect its request and response models. The running gateway exposes the complete JSON schemas at `/openapi.json` and an interactive explorer at `/docs`.": "Ten wykaz endpointów powstaje z deklaracji tras w Pythonie przy każdym budowaniu dokumentacji. Link do funkcji prowadzi do modeli żądań i odpowiedzi. Uruchomiona bramka udostępnia pełne schematy JSON pod `/openapi.json` oraz interaktywną dokumentację pod `/docs`.",
        "All `/api/` and `/v1/` requests require a provisioned bearer identity. `/api/admin/` requires a management identity. `/health` is public liveness; `/ready` is the public cached semantic-prerequisite readiness check (200/503, no inference). The MCP mount at `/mcp/` uses the same trusted bearer identities and is listed separately in the [integration reference](../integration-reference.md).": "Wszystkie żądania do `/api/` i `/v1/` wymagają skonfigurowanej tożsamości Bearer. `/api/admin/` wymaga uprawnień administracyjnych. `/health` jest publiczną kontrolą działania procesu; `/ready` sprawdza wymagane zależności semantyczne z cache (200/503, bez inferencji). Endpoint MCP `/mcp/` używa tych samych zaufanych tożsamości; opisuje go [kontrakt integracji](../integration-reference.md).",
        "| Method | Path | Source handler |": "| Metoda | Ścieżka | Funkcja w kodzie |",
        "## Response semantics": "## Znaczenie odpowiedzi",
        "An HTTP 200 response from a protected invocation can still contain a `blocked` security verdict. Check `decision`, `reason` and `upstream_executed`; do not use HTTP status alone as an authorization result. A blocked output can follow an already executed upstream operation.": "Odpowiedź HTTP 200 z chronionego wywołania może zawierać decyzję `blocked`. Sprawdź pola `decision`, `reason` i `upstream_executed`; sam status HTTP nie oznacza zgody na operację. Blokada odpowiedzi może nastąpić po wykonaniu operacji przez docelową usługę.",
        "OpenAI-compatible calls return their endpoint-specific schema. Streaming, arbitrary upstream providers and arbitrary MCP proxying are not implied by this inventory. See the [protocol contract](../integration-reference.md).": "Wywołania zgodne z OpenAI zwracają schemat właściwy dla danego endpointu. Ten wykaz nie oznacza obsługi streamingu, dowolnych dostawców ani dowolnego proxy MCP. Szczegóły zawiera [kontrakt protokołów](../integration-reference.md).",
    }
    for original, translated in replacements.items():
        reference = reference.replace(original, translated)
    return reference


def llm_documents(base, language, reference):
    polish = language == "pl"
    localized_base = base + ("/pl" if polish else "")
    title = "Dokumentacja FastFence" if polish else "FastFence documentation"
    introduction = (
        "Uruchom `uv tool run fastfence`. Ollama musi działać. Polecenie przygotowuje brakujące komponenty Laya, skonfigurowany model oceniający i OCR, a następnie uruchamia dashboard. `init --config-only` pomija pobieranie komponentów. Kod źródłowy FastFence nie jest potrzebny. Polityki i tożsamości są lokalne; budżety i audyt należą do procesu. Propozycja Laya wymaga zatwierdzenia przed aktywacją."
        if polish
        else "Run `uv tool run fastfence` with Ollama running. It prepares missing Laya, the configured assessor and OCR components, then starts the dashboard; `init --config-only` skips component downloads. No FastFence checkout is required. Policies and identities are local; budgets and audit are process-local. Laya proposals require explicit review before activation."
    )
    index = [f"# {title}", "", introduction, ""]
    full = [f"# {title}", "", introduction, ""]
    for path, name, description in PAGES:
        source = ROOT / "docs" / path
        if polish:
            source = source.with_suffix(".pl.md")
        if path == "reference/http-api.md":
            content = polish_reference(reference) if polish else reference
        else:
            content = source.read_text()
        if polish:
            name = next(
                line[2:]
                for line in content.splitlines()
                if line.startswith("# ")
            )
            description = ""
        url = f"{localized_base}/{path.removesuffix('.md')}/"
        index.append(
            f"- [{name}]({url})" + (f": {description}" if description else "")
        )
        full.extend(["---", f"Source: {url}", "", embed_sources(content), ""])
    label = "Pełna dokumentacja" if polish else "Full documentation"
    index.extend(["", f"- [{label}]({localized_base}/llms-full.txt)", ""])
    return "\n".join(index), "\n".join(full)


def development_notice(polish=False):
    if RELEASE != "dev" or not DEV_SHA:
        return ""
    if polish:
        notice = "Wersja rozwojowa — niewydana"
        detail = "Ten kod może różnić się od pakietu na PyPI."
        stable = "Dokumentacja stabilna"
    else:
        notice = "Development version — unreleased"
        detail = "This code may differ from the package available on PyPI."
        stable = "Stable documentation"
    source = REPOSITORY.split("/blob/", 1)[0] + "/commit/" + DEV_SHA
    return (
        f'!!! warning "{notice}"\n\n'
        f"    {detail} [{stable}](https://fastfence.dev/latest/). "
        f"[Commit {DEV_SHA[:12]}]({source}).\n\n"
    )


@event_priority(-50)
def on_config(config):
    # Physical staging supports i18n's file resolver without modifying tracked docs.
    target = Path(BUILD_DOCS.name) / "docs"
    if not target.exists():
        shutil.copytree(ROOT / "docs", target)
    base = config.site_url.rstrip("/")
    for path in target.rglob("*.md"):
        content = embed_sources(path.read_text())
        content = development_notice(path.name.endswith(".pl.md")) + content
        if path.name.endswith(".pl.md"):
            content = content.replace("[Download ", "[Pobierz ").replace(
                "[View source]", "[Zobacz źródło]"
            )
        path.write_text(
            content.replace(
                "https://fastfence.dev/downloads/", base + "/downloads/"
            )
        )
    sources, archive = example_downloads()
    sources["fastfence-examples.zip"] = archive
    sources["fastfence-benchmarks.zip"] = benchmark_download()
    for name, content in sources.items():
        destination = target / "downloads" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    reference = endpoint_reference()
    (target / "reference").mkdir(exist_ok=True)
    (target / "reference/http-api.md").write_text(
        development_notice() + reference
    )
    (target / "reference/http-api.pl.md").write_text(
        development_notice(True) + polish_reference(reference)
    )
    for language in ("en", "pl"):
        index, full = llm_documents(base, language, reference)
        suffix = ".pl" if language == "pl" else ""
        (target / f"llms{suffix}.txt").write_text(
            development_notice(language == "pl") + index
        )
        (target / f"llms-full{suffix}.txt").write_text(
            development_notice(language == "pl")
            + full.replace(
                "https://fastfence.dev/downloads/", base + "/downloads/"
            )
        )
    config.docs_dir = str(target)
    return config
