"""Use the OpenAI Python SDK against FastFence, with no direct provider bypass."""

import argparse
import os

from openai import APIStatusError, OpenAI


def complete(client: OpenAI, model: str, prompt: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=256,
        temperature=0,
        stream=False,
    )
    return response.choices[0].message.content or ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", default="Hi")
    args = parser.parse_args()
    with OpenAI(
        base_url=os.getenv("FASTFENCE_URL", "http://127.0.0.1:8000").rstrip("/")
        + "/v1",
        api_key=os.environ["FASTFENCE_AGENT_TOKEN"],
        timeout=90,
        max_retries=0,
    ) as client:
        try:
            print(
                complete(
                    client,
                    os.getenv("FASTFENCE_MODEL", "qwen3:4b"),
                    args.prompt,
                )
            )
        except APIStatusError as error:
            # No automatic retry or fallback to an unprotected provider.
            print(
                f"FastFence returned HTTP {error.status_code}; inspect Activity for the decision."
            )
            raise SystemExit(1) from None


if __name__ == "__main__":
    main()
