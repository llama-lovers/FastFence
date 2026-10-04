# FastFence — HackYeah 2026 submission

**Team: llama-lovers.** Security policies between agents and their models or tools. Describe a policy, review and test it, activate it without restarting, then inspect its effect on real interactions.

## Start here

- [Three-minute demo with music, no voice](presentation/output/fastfence-submission.mp4)
- [Presentation — exactly ten slides, PDF](presentation/output/fastfence-submission.pdf)
- [Editable presentation with Polish speaker notes](presentation/output/fastfence-submission.pptx)
- [Plain-text opening instructions](presentation/instructions.txt)

Slides and video captions are in English. The film combines recorded product interactions with clearly labelled replays of actual client results. It includes OpenAI, MCP, synchronous text ACP, local OCR-to-Markdown and authorized public/private-key restoration.

## Organizer assessment structure

| Category | Weight | Review entry point |
|---|---:|---|
| Robustness and quality of guardrails | 30% | [1-solution](1-solution/README.md) |
| Architecture and performance | 20% | [2-architecture](2-architecture/README.md) |
| Security reporting | 20% | [3-reporting](3-reporting/README.md) |
| Completeness of self-testing | 15% | [4-testing](4-testing/README.md) |
| Implementability and scalability | 15% | [5-implementation](5-implementation/README.md) |

The folders reference the actual source and evidence without duplicating implementation. The code is in [src/fastfence](src/fastfence/). [Criterion-to-evidence map](presentation/demo-criteria-map.md) provides additional traceability.

## Run the product

With uv, Git, sh and a running Ollama service on macOS or Linux, run in an empty configuration directory:

```sh
uv tool run --python 3.12 fastfence@1.0.7
```

The first launch provisions the configured components and may download models. Open **http://127.0.0.1:8000** and use your private `state/credentials.json` entries in Connection. No FastFence checkout is required. See the implementation folder for integration examples and startup details.

The demo uses public 1.0.7. Historical latency measurements are labelled 1.0.2; queue checks and source/public-package suites have separate scopes. In-memory quotas and audit are per process and reset on restart. Semantic judgments require evaluation against the intended policy; the recorded examples do not establish universal accuracy.
