from __future__ import annotations


def chat_request(**changes):
    return {
        "model": "qwen3:0.6b",
        "messages": [
            {
                "role": "system",
                "content": "Summarize approved business reports.",
            },
            {"role": "user", "content": "Quarterly forecast"},
        ],
        "max_tokens": 64,
        **changes,
    }
