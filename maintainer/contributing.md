# Contributing

This page is for changing FastFence source and running its development suites. Product installation uses the [Python package](../docs/getting-started.md) and does not require this checkout.

## Source environment

```sh
git clone https://github.com/llama-lovers/HackYeah2026-challenge-second.git
cd HackYeah2026-challenge-second
uv sync --locked --all-groups
uv run pre-commit install
```

Add or update a change specification under `specs/changes/` with implementation changes. Python models use Pydantic; architecture imports and no-dataclass rules are enforced automatically.

## Validate a change

```sh
uv run pytest -q
uv run pre-commit run --all-files
uv run mkdocs build --strict
```

The documentation hook embeds the actual `examples/docs/` files, publishes individual downloads and builds an archive with the supporting policy/signatures. Keep source, tests and documented behavior together.

## Clean-install acceptance

```sh
# Fresh checkout, environment and private state; no model service required.
uv run python scripts/smoke_clean_install.py

# Full isolated feature installation; requires running Ollama.
uv run python scripts/smoke_clean_install.py --full
```

The offline run deliberately disables semantic inference. The full run installs isolated Laya/OCR, pulls models and exercises actual feature paths. Neither copies operator credentials or policy edits. See [recorded evidence](testing.md).

## Focused security regressions

```sh
uv run pytest --no-cov tests/unit/test_asymmetric_anonymization.py tests/integration/test_asymmetric_anonymization.py tests/unit/test_anonymization_tokens.py
uv run pytest --no-cov tests/unit/test_openai_upstream.py tests/integration/test_openai_upstream_transport.py
uv run python evaluation/benchmark_asymmetric.py --output state/private/asymmetric-benchmark.json
```

The cryptographic benchmark excludes key generation, gateway work, matching, model calls and I/O from timed operations. Treat it as codec evidence, not a whole-product latency guarantee.
