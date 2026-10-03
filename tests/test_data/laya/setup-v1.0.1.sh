#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/../.."
for dependency in git uv; do
    if ! command -v "$dependency" >/dev/null 2>&1; then
        printf 'Install %s before running integrations/laya/setup.sh.\n' "$dependency" >&2
        exit 1
    fi
done
umask 077
upstream="state/laya/upstream"
revision="b3b998c03dc44076675305581eb4640b9bf6ff8f"
if [ ! -d "$upstream/.git" ]; then
    mkdir -p state/laya
    git init "$upstream"
    git -C "$upstream" remote add origin https://github.com/aayushch/laya.git
fi
git -C "$upstream" fetch --depth 1 origin "$revision"
git -C "$upstream" checkout --detach "$revision"
if [ ! -x state/laya/venv/bin/python ]; then
    uv venv --python 3.12 state/laya/venv
fi
uv pip install --python state/laya/venv/bin/python --require-hashes \
    -r "$upstream/engine/requirements.lock"
