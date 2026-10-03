#!/usr/bin/env sh
# Install the locked OCR extra without changing the gateway's .venv.
set -eu

cd "$(dirname "$0")/.."
if ! command -v uv >/dev/null 2>&1; then
    printf '%s\n' 'Install uv before running scripts/setup-ocr.sh.' >&2
    exit 1
fi
umask 077
project_root=$(pwd -P)
state_directory="${FASTFENCE_STATE:-$project_root/state}"
mkdir -p "$state_directory/private"
state_directory=$(cd "$state_directory" && pwd -P)
ocr_environment="$state_directory/private/ocr-env"
ocr_models="$state_directory/private/ocr-models"
UV_PROJECT_ENVIRONMENT="$ocr_environment" uv sync --locked --extra ocr --no-default-groups
"$ocr_environment/bin/python" -m fastfence.modules.ocr.persistence.bootstrap "$ocr_models"
# Preserve literal paths, including spaces and shell metacharacters.
# This environment file is private local operator state.
"$ocr_environment/bin/python" - "$ocr_environment/bin/python" "$ocr_models" "$state_directory/private/ocr.env" <<'PY'
import os
import shlex
import sys
from pathlib import Path

path = Path(sys.argv[3])
contents = (
    f"FASTFENCE_OCR_PYTHON={shlex.quote(sys.argv[1])}\n"
    f"FASTFENCE_OCR_MODELS={shlex.quote(sys.argv[2])}\n"
)
with path.open("w") as stream:
    os.chmod(path, 0o600)
    stream.write(contents)
PY
printf '%s\n' 'OCR installed from uv.lock and models prepared.' \
    'Standard local paths are detected automatically by FastFence.' \
    'For explicit configuration, source the generated private file:' \
    "$state_directory/private/ocr.env" \
    'uv run fastfence serve'
