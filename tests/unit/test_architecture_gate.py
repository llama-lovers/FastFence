"""The architecture gate rejects dataclass aliases and permits Pydantic models."""

from __future__ import annotations

import pytest

from scripts.check_architecture import violations


@pytest.mark.parametrize(
    "source",
    [
        "from dataclasses import dataclass\n",
        "import dataclasses as dc\n",
        "from pydantic.dataclasses import dataclass\n",
    ],
)
def test_dataclass_import_forms_are_rejected(tmp_path, source):
    module = tmp_path / "model.py"
    module.write_text(source)
    errors = violations(module)
    assert errors
    assert all("dataclasses are forbidden" in error for error in errors)


def test_pydantic_model_is_an_allowed_boundary(tmp_path):
    module = tmp_path / "model.py"
    module.write_text(
        "from pydantic import BaseModel\n\nclass Identity(BaseModel):\n    subject: str\n"
    )
    assert violations(module) == []
