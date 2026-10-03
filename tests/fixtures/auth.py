from __future__ import annotations


def headers(tokens, actor="analyst-blue"):
    return {"Authorization": "Bearer " + tokens[actor]}
