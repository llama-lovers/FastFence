"""Validated synthetic labels; never an implementation of a security classifier."""

from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CORPUS = (
    Path(__file__).resolve().parents[1]
    / "tests/test_data/training_prompts.jsonl"
)

MAX_CORPUS_BYTES = 2 * 1024 * 1024


class PromptCase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    source_index: int = Field(ge=0)
    label: Literal["good_prompt", "bad_prompt"]
    language: Literal["pl", "en"]
    family: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=16384, repr=False)
    generator: str = Field(min_length=1)
    labeler: str = Field(min_length=1)


def load_cases(path: Path = CORPUS) -> list[PromptCase]:
    with path.open("rb") as stream:
        content = stream.read(MAX_CORPUS_BYTES + 1)
    if len(content) > MAX_CORPUS_BYTES:
        raise ValueError("Corpus exceeds two MiB")
    cases = [
        PromptCase.model_validate_json(line)
        for line in content.decode("utf-8").splitlines()
        if line.strip()
    ]
    if not cases:
        raise ValueError("Empty corpus")
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("Duplicate sample IDs")
    if len({case.text for case in cases}) != len(cases):
        raise ValueError("Duplicate or conflicting prompt text")
    return cases


def classification_summary(rows: list[dict]) -> dict:
    valid = [row for row in rows if row["error"] is None]
    counts = Counter((row["expected_blocked"], row["blocked"]) for row in valid)
    tp, fn = counts[True, True], counts[True, False]
    fp, tn = counts[False, True], counts[False, False]
    return {
        "samples": len(rows),
        "errors": len(rows) - len(valid),
        "true_positives": tp,
        "false_negatives": fn,
        "false_positives": fp,
        "true_negatives": tn,
        "accuracy_on_valid": (tp + tn) / len(valid) if valid else None,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }
