#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/../.."
exec state/laya/venv/bin/python integrations/laya/author_rule.py "$@"
