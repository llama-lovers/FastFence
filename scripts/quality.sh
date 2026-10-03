#!/usr/bin/env sh
set -eu

# Run from any directory; validation uses the committed project configuration.
cd "$(dirname "$0")/.."
uv lock --check
uv sync --locked --all-groups
uv run pre-commit run --all-files
uv run pytest
uv build
