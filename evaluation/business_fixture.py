"""Explicit simulated adapter composition for isolated evaluation harnesses."""

import sys
from importlib import import_module
from pathlib import Path

from fastfence.app.factory import create_app as create_product_app
from fastfence.shared.settings.app_settings import AppSettings

# Direct `python evaluation/script.py` starts with evaluation/ on sys.path.
# Examples stay outside the installed product package; load the checkout explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
DemoTools = import_module("examples.business_tools.tools").DemoTools
initialize = import_module("examples.business_tools.credentials").initialize


def create_app(settings: AppSettings | None = None):
    return create_product_app(settings, tools=DemoTools())
